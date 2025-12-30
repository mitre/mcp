# utilities/cti_llm_client.py

import aiohttp
import yaml
from pathlib import Path
from functools import lru_cache
# ------------------------------------------------------
# Config loader (local, explicit, deterministic)
# ------------------------------------------------------

@lru_cache(maxsize=1)
def load_config() -> dict:
    cfg_path = Path(__file__).resolve().parents[2] / "conf" / "local.yml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Missing config: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

# ------------------------------------------------------
# Central LLM Client
# ------------------------------------------------------

class LLMClient:
    def __init__(self):
        self.cfg = load_config()

    async def generate(self, prompt: str, profile: str = "llm") -> str | None:
        llm_cfg = self.cfg.get(profile, {})
        if not llm_cfg:
            raise KeyError(f"No LLM profile '{profile}' in config")

        if llm_cfg.get("offline") or llm_cfg.get("use_mock"):
            return None

        model = llm_cfg.get("model")
        api_base = llm_cfg.get("api_base")
        temperature = llm_cfg.get("temperature", 0.0)

        if not model or not api_base:
            raise ValueError("LLM config missing model or api_base")

        # --------------------------------------------------
        # Provider routing (string-based, no imports)
        # --------------------------------------------------

        provider = llm_cfg.get("provider", "openai_compatible")

        if provider == "ollama":
            if not model.startswith("ollama/"):
                raise ValueError(f"Ollama provider requires model prefix 'ollama/': {model}")
            return await self._ollama_generate(
                prompt, model.split("/", 1)[1], api_base, temperature
            )

        if provider == "openai_compatible":
            return await self._openai_compatible_generate(
                prompt=prompt,
                model=model,
                api_base=api_base,
                temperature=temperature,
                llm_cfg=llm_cfg,
            )

        raise ValueError(f"Unsupported model provider: {provider}")

    # --------------------------------------------------
    # Providers
    # --------------------------------------------------

    async def _ollama_generate(self, prompt, model, api_base, temperature):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{api_base}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "temperature": temperature,
                    "stream": False,
                },
            ) as resp:
                data = await resp.json()
                return data.get("response")
            
    async def _openai_compatible_generate(
            self,
            prompt: str,
            model: str,
            api_base: str,
            temperature: float,
            llm_cfg: dict,
        ) -> str | None:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {llm_cfg.get('api_key') or ''}",
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": llm_cfg.get("max_tokens", 1024),
        }

        timeout = aiohttp.ClientTimeout(total=llm_cfg.get("timeout", 60))

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"LLM HTTP {resp.status}: {text}")

                data = await resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return None
                return choices[0]["message"].get("content")

# ------------------------------------------------------
# Singleton
# ------------------------------------------------------

_llm_client = LLMClient()

async def llm_generate(prompt: str, profile: str = "llm") -> str | None:
    return await _llm_client.generate(prompt, profile)
