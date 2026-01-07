"""
llm_client.py — Centralized, deterministic LLM access layer

Responsibilities:
- Load effective MCP config (local.yml → default.yml)
- Provide a single async LLM client
- Support offline + mock modes
- Expose deterministic provenance for STIX / CTI artifacts
"""

import aiohttp
import yaml
from pathlib import Path
from functools import lru_cache
from plugins.mcp.app.utilities.paths import get_mcp_root
import mlflow
import dspy

def init_mlflow(profile: str):
    """
    Initialize MLflow deterministically from config.
    Safe to call multiple times.
    Must only be called at runtime (never import-time).
    """
    cfg = load_config()
    mlflow_cfg = cfg.get("mlflow", {})

    if not mlflow_cfg.get("enabled", False):
        return

    tracking_uri = mlflow_cfg.get("tracking_uri")
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    experiment_cfg = mlflow_cfg.get("experiment", {})
    experiment_name = experiment_cfg.get(profile)
    if experiment_name:
        mlflow.set_experiment(experiment_name)

    autolog_cfg = mlflow_cfg.get("autolog", {})
    if autolog_cfg.get("dspy", False):
        mlflow.dspy.autolog()

# ------------------------------------------------------
# Config loader (local, explicit, deterministic)
# ------------------------------------------------------

@lru_cache(maxsize=1)
def load_config() -> dict:
    """
    Load effective config with precedence:
    1. conf/local.yml (if present)
    2. conf/default.yml

    This function is deterministic and cached.
    """
    root_dir = get_mcp_root()
    default_path = root_dir / "conf" / "default.yml"
    local_path = root_dir / "conf" / "local.yml"

    if local_path.exists():
        with local_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    if default_path.exists():
        with default_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    raise FileNotFoundError("No config found (default.yml or local.yml)")

# ------------------------------------------------------
# Provenance (Stage 2 / STIX support)
# ------------------------------------------------------

def get_llm_provenance(profile: str = "llm") -> dict:
    """
    Return deterministic LLM provenance metadata.

    This MUST NOT make network calls and MUST be safe in
    offline / mock modes.
    """
    cfg = load_config()
    llm = cfg.get(profile, {}) or {}

    return {
        "provider": llm.get("provider"),
        "model": llm.get("model"),
        "offline": llm.get("offline", False),
        "use_mock": llm.get("use_mock", False),
        "temperature": llm.get("temperature"),
        "top_p": llm.get("top_p"),
        "max_tokens": llm.get("max_tokens"),
    }

# ------------------------------------------------------
# Central LLM Client
# ------------------------------------------------------

class LLMClient:
    """
    Central async LLM client.

    Guarantees:
    - No calls when offline or mock enabled
    - Provider routing by config only
    - No hard dependency on OpenAI SDKs
    """

    def __init__(self):
        self.cfg = load_config()

    async def generate(self, prompt: str, profile: str = "llm") -> str | None:
        llm_cfg = self.cfg.get(profile, {})
        if not llm_cfg:
            raise KeyError(f"No LLM profile '{profile}' in config")

        # Deterministic early exit
        if llm_cfg.get("offline") or llm_cfg.get("use_mock"):
            return None

        model = llm_cfg.get("model")
        api_base = llm_cfg.get("api_base")
        temperature = llm_cfg.get("temperature", 0.0)

        if not model or not api_base:
            raise ValueError("LLM config missing model or api_base")

        provider = llm_cfg.get("provider", "openai_compatible")

        if provider == "ollama":
            if not model.startswith("ollama/"):
                raise ValueError(
                    f"Ollama provider requires model prefix 'ollama/': {model}"
                )
            return await self._ollama_generate(
                prompt,
                model.split("/", 1)[1],
                api_base,
                temperature,
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
            "messages": [{"role": "user", "content": prompt}],
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
# Singleton helpers
# ------------------------------------------------------

_llm_client = None

def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client

async def llm_generate(prompt: str, profile: str = "llm") -> str | None:
    """
    Convenience wrapper used throughout the CTI pipeline.
    """
    return await get_llm_client().generate(prompt, profile)
