"""
llm_client.py — Centralized, deterministic LLM access layer

Responsibilities:
- Load effective MCP config (local.yml → default.yml)
- Provide a single async LLM client
- Support offline mode
- Expose deterministic provenance for STIX / CTI artifacts
"""

import logging
import os
import ssl
import aiohttp
import yaml
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from plugins.mcp.app.dspy_env import (
    apply_litellm_ssl_verify,
    coerce_optional_bool,
)
from plugins.mcp.app.utilities.paths import get_mcp_root


# ------------------------------------------------------
# Config loader (local, explicit, deterministic)
# ------------------------------------------------------

def deep_merge(base: dict, override: dict) -> dict:
    """Overlay override onto base, recursing into nested dicts.

    Public because set_config needs the same semantics local.yml already uses
    when it overlays default.yml.
    """
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


# get_config returns the raw file alongside a server-resolved view, so a
# GET-edit-POST round trip carries both. Only 'config' is the payload.
_ENVELOPE_SIBLINGS = frozenset({"config", "resolved"})


def unwrap_config_envelope(local: dict) -> dict:
    """get_config returns {"config": cfg}, so a GET-edit-POST round trip used
    to persist that envelope as a literal `config:` root the overlay ignored.

    The response grew a sibling 'resolved' key, which made the exact-key-set
    test below fail, so a round trip stopped being recognised as an envelope:
    it wrote two inert top-level sections and slipped past the per-section
    validation that set_config applies to the unwrapped form.
    """
    inner = local.get("config")
    if isinstance(inner, dict) and set(local) <= _ENVELOPE_SIBLINGS:
        return inner
    return local


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
            config = deep_merge(config, unwrap_config_envelope(yaml.safe_load(f) or {}))

    if not config:
        raise FileNotFoundError("No config found (default.yml or local.yml)")
    return config

def reload_config():
    """Force reload MCP config from disk.

    Also drops the LLMClient singleton. It snapshots the config at
    construction, so without this a Save reached get_llm_provenance, which
    reads fresh, but not generate(), which reads the snapshot: the bundle got
    stamped with a model that did not produce it.
    """
    global _llm_client
    load_config.cache_clear()
    _llm_client = None
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

# What a workload profile is allowed to differ on. Everything else, above all
# the endpoint and the credentials, belongs to 'llm' and to 'llm' only.
#
# This used to be an unrestricted merge, so any key under cti won. A model
# pinned there beat the global one with nothing in the UI to show it, and the
# panel that wrote those keys put them there by accident. One endpoint, one
# model, and per-workload generation settings is the whole model now.
# The LLM profiles. conf/local.yml also holds unrelated sections such as
# 'caldera' and 'mlflow', and the allowlist below must not be applied to those.
LLM_PROFILES = frozenset({"llm", "cti"})

# temperature and max_tokens are deliberately NOT here. They are displayed and
# edited by two panels, and two stored copies drift: the CTI panel showed 0 and
# 8192 while the global panel showed 0.5 and 24000, with nothing to say which
# one a run would use. They live on 'llm' so there is one value to disagree
# about.
# What the 'llm' profile itself accepts over the API. Anything not here is
# either meaningless or belongs in .env, and set_config used to take any key
# in this section at all.
LLM_OVERRIDABLE = frozenset({
    "provider", "model", "api_base", "api_base_env", "api_key_env",
    "ssl_verify", "offline", "temperature", "top_p", "max_tokens",
    "max_tool_calls", "timeout", "stream", "embed_model",
    "rag_topk", "rag_embed_model",
})

WORKLOAD_OVERRIDABLE = frozenset({
    "top_p",
    # Extraction legitimately waits longer than an interactive chat turn.
    "timeout",
    "stream",
    # Per-workload run mode: extraction can go offline without silencing chat.
    "offline",
    # A different embedding model is a separate axis from the chat endpoint,
    # so it cannot be confused with one.
    "embed_model",
})


def layered_profile(cfg: dict, profile: str) -> dict:
    """Resolve a workload profile over the global 'llm' profile.

    'llm' owns the connection: provider, model, api_base, credentials and TLS.
    A workload profile such as 'cti' may only adjust generation settings.
    Anything else it declares is ignored and logged, because silently honouring
    it is how extraction ended up on a different endpoint from everything else.
    """
    raw = (cfg or {}).get(profile) or {}
    if profile == "llm":
        return raw

    glob = (cfg or {}).get("llm") or {}

    # An absent or empty workload profile inherits outright. Returning {} here
    # meant a deployment that deleted its cti block got "No LLM profile 'cti'"
    # rather than the global connection the UI promises it shares.
    if not raw:
        return dict(glob)

    # A key present but empty (a cleared number input sends '', a bare
    # 'timeout:' parses as None) must fall through to the global value rather
    # than override it with nothing. timeout=None means no timeout at all.
    allowed = {
        k: v for k, v in raw.items()
        if k in WORKLOAD_OVERRIDABLE and v is not None and v != ""
    }
    # Only warn about a dropped key that would actually have changed something.
    # A key the loader already promoted onto 'llm' now holds the same value, so
    # reporting it as ignored contradicts the promotion notice.
    ignored = sorted(
        k for k in set(raw) - set(allowed)
        if not (k in WORKLOAD_OVERRIDABLE and (raw[k] is None or raw[k] == ""))
        and raw[k] != glob.get(k)
    )
    if ignored:
        logging.getLogger("plugins.mcp").warning(
            "[MCP] %s: ignoring %s. These are set once on the 'llm' profile; "
            "remove them from conf/local.yml.",
            profile, ", ".join(ignored),
        )
    return {**glob, **allowed}


def get_llm_provenance(profile: str = "llm", *, runtime: bool = False) -> dict:
    """
    Provenance metadata for logging + deterministic audit.

    If runtime=True, include runtime fields required to execute (api_key, api_base).
    Keep runtime=False as safe-to-log (no secrets).
    """
    llm = resolve_env_indirection(layered_profile(load_config(), profile))

    base = {
        "provider": llm["provider"],
        "model": llm.get("model"),
        "offline": llm.get("offline", False),
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


# ------------------------------------------------------
# Central LLM Client
# ------------------------------------------------------

class LLMHTTPError(RuntimeError):
    """A non-200 from the provider, with the status kept for the caller.

    Callers need to tell a misconfiguration apart from a blip: the raw body is
    provider JSON and says nothing about where the setting lives.
    """

    def __init__(self, status: int, model: str, body: str):
        self.status = status
        self.model = model
        self.body = body
        super().__init__(self._explain())

    def _explain(self) -> str:
        b = (self.body or "").lower()
        if "does not exist" in b or "not available for inference" in b:
            return (
                f"Model not available: the provider has no {self.model}. Set a "
                f"model it serves in Global Model Config, or in llm.model in "
                f"conf/local.yml."
            )
        if "at capacity" in b:
            return (f"Model busy: the provider has no free slot for "
                    f"{self.model}. Retry, or pick another model.")
        if self.status in (401, 403):
            return ("LLM authentication failed: the provider rejected the API "
                    "key. Check MCP_LLM_API_KEY in plugins/mcp/.env.")
        return f"LLM HTTP {self.status} for {self.model}: {self.body[:200]}"

    @property
    def is_transient(self) -> bool:
        """Retryable or load related, as opposed to a wrong setting."""
        return self.status == 429 or self.status >= 500 or "at capacity" in (self.body or "").lower()


class LLMClient:
    """
    Central async LLM client.

    Guarantees:
    - No calls when offline
    - Provider routing by config only
    - No hard dependency on OpenAI SDKs
    """

    def __init__(self):
        self.cfg = load_config()

    async def generate(self, prompt: str, profile: str = "llm") -> str | None:
        raw_cfg = layered_profile(self.cfg, profile)
        if not raw_cfg:
            raise KeyError(f"No LLM profile '{profile}' in config")

        # Deterministic early exit, before credential resolution: an
        # offline profile may legitimately carry no key and no base.
        if raw_cfg.get("offline"):
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
        # Provenance stamps top_p into every bundle, so it has to actually be
        # sent or the bundle documents a setting that never applied.
        top_p = llm_cfg.get("top_p")
        if top_p is not None:
            payload["top_p"] = top_p

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
                    raise LLMHTTPError(resp.status, model, text)

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
