# utilities/cti_llm_client.py

import aiohttp
import yaml
from pathlib import Path

# ------------------------------------------------------
# Config loader (local, explicit, deterministic)
# ------------------------------------------------------

def load_config() -> dict:
    cfg_path = Path(__file__).resolve().parents[2] / "conf" / "default.yml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Missing config: {cfg_path}")
    with cfg_path.open("r") as f:
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

        if model.startswith("ollama/"):
            return await self._ollama_generate(
                prompt, model.split("/", 1)[1], api_base, temperature
            )

        raise ValueError(f"Unsupported model provider: {model}")

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

# ------------------------------------------------------
# Singleton
# ------------------------------------------------------

_llm_client = LLMClient()

async def llm_generate(prompt: str, profile: str = "llm") -> str | None:
    return await _llm_client.generate(prompt, profile)
