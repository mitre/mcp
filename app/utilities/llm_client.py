"""
llm_client.py — Centralized, deterministic LLM access layer

Responsibilities:
- Load effective MCP config (local.yml → default.yml)
- Provide a single async LLM client
- Support offline + mock modes
- Expose deterministic provenance for STIX / CTI artifacts
"""

import logging
import os
import ssl
import aiohttp
import yaml
import dspy
from pathlib import Path
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from plugins.mcp.app.dspy_env import (
    apply_litellm_ssl_verify,
    coerce_optional_bool,
    dspy_lm_kwargs_from_settings,
)
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

def _deep_merge(base: dict, override: dict) -> dict:
    """Overlay override onto base, recursing into nested dicts."""
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@lru_cache(maxsize=1)
def load_config() -> dict:
    """conf/default.yml overlaid with conf/local.yml, key by key.

    local.yml used to replace default.yml wholesale, so a partial file, which
    is what the UI's Save writes, dropped the api_key_env / api_base_env keys
    and silently disabled .env resolution for the whole deployment.

    Deterministic and cached; call reload_config() after writing local.yml.
    """
    root_dir = get_mcp_root()
    default_path = root_dir / "conf" / "default.yml"
    local_path = root_dir / "conf" / "local.yml"

    config = {}
    if default_path.exists():
        with default_path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    if local_path.exists():
        with local_path.open("r", encoding="utf-8") as f:
            config = _deep_merge(config, yaml.safe_load(f) or {})

    if not config:
        raise FileNotFoundError("No config found (default.yml or local.yml)")
    return config

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


# field -> (sibling yaml key naming an env var, env_wins). Secrets resolve
# env-first so rotating .env takes effect without editing tracked yaml;
# endpoints resolve yaml-first so a deployment can pin one on disk.
ENV_INDIRECT_FIELDS = {
    "api_key": ("api_key_env", True),
    "api_base": ("api_base_env", False),
}


def resolve_env_indirection(cfg: dict) -> dict:
    """Resolve a profile's *_env indirection into concrete values.

    Every profile in the yaml (`llm`, `cti`, ...) shares one shape, so the
    parent-side resolver in app/config.py and the provenance path here read
    credentials through this single function rather than each rolling its
    own. Returns a copy; the caller's dict is not mutated.

    The *_env keys are consumed so they never reach the settings dict handed
    to DSPy. Values are stripped because normalize_openai_api_base treats a
    blank-but-truthy string as a real URL and would turn it into the
    relative path "/v1".

    Credentials come back as empty strings when neither yaml nor env supplies
    one; the caller decides whether that is fatal.
    """
    resolved = dict(cfg or {})
    for field, (env_key, env_wins) in ENV_INDIRECT_FIELDS.items():
        env_var = resolved.pop(env_key, None)
        yaml_value = str(resolved.get(field) or "").strip()
        env_value = os.environ.get(env_var, "").strip() if env_var else ""
        resolved[field] = env_value if (env_wins and env_var) else (yaml_value or env_value)
    # `or` rather than setdefault: yaml may carry an explicit null, which
    # setdefault would leave in place. dspy_env.py coerces the same way, and
    # a None here would skip every `provider == "openai_compatible"` branch.
    resolved["provider"] = resolved.get("provider") or "openai_compatible"
    if resolved["provider"] == "openai_compatible":
        resolved["api_base"] = normalize_openai_api_base(resolved["api_base"]) or ""
    return resolved


def _aiohttp_ssl_arg(ssl_verify):
    """Return aiohttp's per-request SSL argument for MCP LLM config."""
    verify = coerce_optional_bool(ssl_verify)
    if verify is False:
        return False
    if verify is True or ssl_verify in (None, ""):
        return None
    # Non-boolean strings are treated as a CA bundle path.
    cafile = str(ssl_verify).strip()
    return ssl.create_default_context(cafile=cafile)

# ------------------------------------------------------
# Provenance (Stage 2 / STIX support)
# ------------------------------------------------------

def get_llm_provenance(profile: str = "llm", *, runtime: bool = False) -> dict:
    """
    Provenance metadata for logging + deterministic audit.

    If runtime=True, include runtime fields required to execute (api_key, api_base).
    Keep runtime=False as safe-to-log (no secrets).
    """
    llm = resolve_env_indirection(load_config().get(profile, {}) or {})

    base = {
        "provider": llm["provider"],
        "model": llm.get("model"),
        "offline": llm.get("offline", False),
        "use_mock": llm.get("use_mock", False),
        "temperature": llm.get("temperature"),
        "top_p": llm.get("top_p"),
        "max_tokens": llm.get("max_tokens"),
        "timeout": llm.get("timeout", 60),
        "ssl_verify": llm.get("ssl_verify", True),
        # Optional: allow config to specify embedding model explicitly
        "embed_model": llm.get("embed_model") or llm.get("model"),
    }

    if not runtime:
        return base

    # Runtime-only fields (do NOT log these). Already env-resolved and
    # normalized above, so these are what reach the provider.
    base["api_key"] = llm["api_key"]
    base["api_base"] = llm["api_base"]

    if not base["api_key"]:
        raise ValueError(f"{profile}.api_key missing from MCP config")
    if not base["api_base"]:
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

    kwargs = dspy_lm_kwargs_from_settings(llm_rt)

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
        raw_cfg = self.cfg.get(profile, {})
        if not raw_cfg:
            raise KeyError(f"No LLM profile '{profile}' in config")

        # Deterministic early exit, before credential resolution: an
        # offline profile may legitimately carry no key and no base.
        if raw_cfg.get("offline") or raw_cfg.get("use_mock"):
            return None

        llm_cfg = resolve_env_indirection(raw_cfg)
        model = llm_cfg.get("model")
        api_base = llm_cfg["api_base"]
        temperature = llm_cfg.get("temperature", 0.0)

        if not model or not api_base:
            raise ValueError("LLM config missing model or api_base")

        provider = llm_cfg["provider"]
        if provider == "openai_compatible":
            apply_litellm_ssl_verify(llm_cfg.get("ssl_verify"))

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
        api_key = llm_cfg.get("api_key") or ""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": llm_cfg.get("max_tokens", 1024),
        }

        timeout = aiohttp.ClientTimeout(total=llm_cfg.get("timeout", 60))
        ssl_arg = _aiohttp_ssl_arg(llm_cfg.get("ssl_verify", True))

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
                ssl=ssl_arg,
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
