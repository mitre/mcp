"""Parent-side configuration resolver.

Two credentials, three tiers, one resolver:

  CORE_CALDERA_API_KEY   env only. Authenticates the caldera_core MCP
                         subprocess to the running Caldera REST API.
  MCP_LLM_API_KEY        env default plus per-session UI override.
                         Authenticates DSPy / signatures / embeddings to
                         the LLM provider.

Storage tiers:

  conf/default.yml carries non-secret defaults and names of env vars to
  consult. It never holds credential values.

  .env carries credential values. It is gitignored. The plugin's hook.py
  loads it once in the parent process; subprocesses inherit.

  The UI submits per-session overrides on each /execute request and never
  writes back to disk.

Resolution order for an LLM request:

  1. yaml defaults (model, api_base, temperature, ...)
  2. env-resolved api_key (read from the env var named in api_key_env)
  3. UI overrides (only non-empty fields, only fields not declared
     fields_locked: true in yaml)
"""
import os

from app.utility.base_world import BaseWorld


_YAML_PATH = 'plugins/mcp/conf/default.yml'

_NUMERIC_FALLBACKS = {
    "temperature": 0.5,
    "max_tokens": 10000,
    "max_tool_calls": 5,
}


def _load_defaults() -> dict:
    """Returns the parsed yaml file as a dict. Empty dict on failure."""
    try:
        return BaseWorld.strip_yml(_YAML_PATH)[0] or {}
    except Exception:
        return {}


def llm_defaults() -> dict:
    """Resolve the LLM block: yaml shape plus api_key from its env var.

    api_key is empty string when the env var is unset; the caller decides
    whether that is fatal.
    """
    cfg = dict(_load_defaults().get('llm') or {})
    env_var = cfg.pop('api_key_env', None)
    cfg['api_key'] = os.environ.get(env_var, '') if env_var else cfg.get('api_key', '') or ''
    cfg.setdefault('fields_locked', {})
    for key, fallback in _NUMERIC_FALLBACKS.items():
        cfg.setdefault(key, fallback)
    return cfg


def caldera_connection() -> dict:
    """Resolve the Caldera REST connection: {url, api_key}.

    Both come from env vars whose names are declared in yaml's caldera
    block. Falls back to local-dev values when the env vars are unset
    so a fresh checkout works without configuration.
    """
    cfg = dict(_load_defaults().get('caldera') or {})
    url_var = cfg.get('url_env', 'CALDERA_URL')
    key_var = cfg.get('api_key_env', 'CORE_CALDERA_API_KEY')
    return {
        'url': os.environ.get(url_var, 'http://localhost:8888/api/v2/'),
        'api_key': os.environ.get(key_var, 'ADMIN123'),
        'url_env': url_var,
        'api_key_env': key_var,
    }


def resolve_llm_config(ui_overrides: dict | None) -> dict:
    """Merge yaml defaults, .env credential, and UI overrides.

    Empty / None UI fields do not override defaults (clearing the UI field
    is the natural way for a user to fall back to the server default).
    Fields declared fields_locked: true in yaml ignore UI overrides
    entirely; the UI also disables those inputs client-side via the
    /defaults endpoint.

    Raises ValueError when no api_key can be resolved from any tier so
    callers fail loudly instead of attempting an unauthenticated LLM call.
    """
    base = llm_defaults()
    locked = base.get('fields_locked') or {}
    overrides = {
        key: value
        for key, value in (ui_overrides or {}).items()
        if value not in ("", None) and not locked.get(key, False)
    }
    merged = {**base, **overrides}
    if not merged.get('api_key'):
        raise ValueError(
            "No LLM API key. Set MCP_LLM_API_KEY in plugins/mcp/.env or "
            "enter one in the UI's Global Model Configuration."
        )
    return merged
