"""
llm_client.py — Centralized, deterministic LLM access layer

Responsibilities:
- Load effective MCP config (local.yml → default.yml)
- Provide a single async LLM client
- Support offline + mock modes
- Expose deterministic provenance for STIX / CTI artifacts
"""

import logging
import aiohttp
import yaml
import dspy
from pathlib import Path
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from plugins.mcp.app.utilities.paths import get_mcp_root

def init_mlflow(profile: str):
    """
    Initialize MLflow deterministically from config.
    Safe to call multiple times.
    Must only be called at runtime (never import-time).
    """
    import mlflow
    import dspy
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
    # DSPy autolog is NOT safe in async / multi-task execution.
    # DSPy must be controlled via dspy.context() only.
    if autolog_cfg.get("dspy", False):
        logging.getLogger("plugins.mcp").warning(
            "[MCP] mlflow.dspy.autolog() is disabled (unsafe with async tasks)"
        )

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

def reload_config():
    """Force reload MCP config from disk."""
    load_config.cache_clear()
    return load_config()


def normalize_openai_api_base(api_base: str | None) -> str | None:
    """Normalize OpenAI-compatible endpoints to the versioned API root."""
    if not api_base:
        return api_base
    cleaned = api_base.rstrip("/")
    parts = urlsplit(cleaned)
    if parts.path.rstrip("/").endswith("/v1"):
        return cleaned
    path = f"{parts.path.rstrip('/')}/v1"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

# ------------------------------------------------------
# Provenance (Stage 2 / STIX support)
# ------------------------------------------------------

def get_llm_provenance(profile: str = "llm", *, runtime: bool = False) -> dict:
    """
    Provenance metadata for logging + deterministic audit.

    If runtime=True, include runtime fields required to execute (api_key, api_base).
    Keep runtime=False as safe-to-log (no secrets).
    """
    cfg = load_config()
    llm = cfg.get(profile, {}) or {}

    base = {
        "provider": llm.get("provider", "openai_compatible"),
        "model": llm.get("model"),
        "offline": llm.get("offline", False),
        "use_mock": llm.get("use_mock", False),
        "temperature": llm.get("temperature"),
        "top_p": llm.get("top_p"),
        "max_tokens": llm.get("max_tokens"),
        "timeout": llm.get("timeout", 60),
        # Optional: allow config to specify embedding model explicitly
        "embed_model": llm.get("embed_model") or llm.get("model"),
    }

    if not runtime:
        return base

    # Runtime-only fields (do NOT log these)
    base["api_key"] = llm.get("api_key")
    base["api_base"] = llm.get("api_base")
    if base["provider"] == "openai_compatible":
        base["api_base"] = normalize_openai_api_base(base["api_base"])

    if not base["api_key"]:
        raise ValueError(f"{profile}.api_key missing from MCP config")
    if base["provider"] == "openai_compatible" and not base["api_base"]:
        raise ValueError(f"{profile}.api_base missing from MCP config")

    return base

def build_dspy_lm(profile: str = "llm") -> dspy.LM:
    """
    Build a DSPy LM instance from MCP config.
    Must only be called at runtime.
    """
    llm_rt = get_llm_provenance(profile, runtime=True)

    # Deterministic early exit
    if llm_rt.get("offline") or llm_rt.get("use_mock"):
        raise RuntimeError(f"LLM profile '{profile}' is offline/mock; cannot build DSPy LM")

    kwargs = {
        "model": llm_rt["model"],
        "api_key": llm_rt["api_key"],
        "provider": llm_rt["provider"],
    }

    # If your provider uses a gateway/base URL, pass it through
    if llm_rt.get("api_base"):
        kwargs["api_base"] = llm_rt["api_base"]

    # Only include if explicitly set (DSPy/LiteLLM can behave oddly with None)
    if llm_rt.get("temperature") is not None:
        kwargs["temperature"] = llm_rt["temperature"]
    if llm_rt.get("max_tokens") is not None:
        kwargs["max_tokens"] = llm_rt["max_tokens"]

    return dspy.LM(**kwargs)

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
        if provider == "openai_compatible":
            api_base = normalize_openai_api_base(api_base)

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
