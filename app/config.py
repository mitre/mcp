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
from plugins.mcp.app.dspy_env import coerce_optional_bool
from plugins.mcp.app.utilities.llm_client import load_config, normalize_openai_api_base


_YAML_PATH = 'plugins/mcp/conf/default.yml'

# max_tokens is the per-completion budget DSPy passes to the LM. Each
# ReAct iteration consumes one completion, and a verbose model on a
# multi-server tool surface (caldera_core + range = 27 tools) routinely
# produces a long `next_thought` per iteration. With the previous 10k
# default, those iterations would truncate, the closing parser marker
# never got emitted, and DSPy's ChatAdapter would fail the whole run.
# 24k buys enough headroom for the verbose path without inflating cost
# on short turns (LMs only bill for tokens actually emitted).
_NUMERIC_FALLBACKS = {
    "temperature": 0.5,
    "max_tokens": 24000,
    "max_tool_calls": 5,
    "timeout": 120,
}

_BOOLEAN_FALLBACKS = {
    "ssl_verify": True,
}


def _load_defaults() -> dict:
    """Returns the parsed yaml file as a dict. Empty dict on failure."""
    try:
        return load_config()
    except Exception:
        try:
            return BaseWorld.strip_yml(_YAML_PATH)[0] or {}
        except Exception:
            return {}


def mlflow_settings() -> dict:
    """Resolve MLflow tracking server settings: {host, port, tracking_uri}.

    Reads `mlflow.host` and `mlflow.port` from the plugin's yaml. Falls
    back to 127.0.0.1:5000 (MLflow's own default) so a fresh checkout
    keeps the historical behavior, but lets a deployment override the
    port to avoid colliding with another Caldera tree's MLflow on the
    same host. Mirrors the dynamic-port pattern caldera itself uses
    via `conf/local.yml:port`.
    """
    cfg = dict(_load_defaults().get('mlflow') or {})
    host = str(cfg.get('host') or '127.0.0.1').strip()
    try:
        port = int(cfg.get('port') or 5000)
    except (TypeError, ValueError):
        port = 5000
    return {
        'host': host,
        'port': port,
        'tracking_uri': f'http://{host}:{port}',
    }


def llm_defaults() -> dict:
    """Resolve the LLM block: yaml shape plus api_key from its env var.

    api_key is empty string when the env var is unset; the caller decides
    whether that is fatal.
    """
    cfg = dict(_load_defaults().get('llm') or {})
    env_var = cfg.pop('api_key_env', None)
    cfg['api_key'] = os.environ.get(env_var, '') if env_var else cfg.get('api_key', '') or ''
    if cfg.get('provider', 'openai_compatible') == 'openai_compatible':
        cfg['api_base'] = normalize_openai_api_base(cfg.get('api_base'))
    cfg.setdefault('provider', 'openai_compatible')
    cfg.setdefault('fields_locked', {})
    for key, fallback in _NUMERIC_FALLBACKS.items():
        cfg.setdefault(key, fallback)
    for key, fallback in _BOOLEAN_FALLBACKS.items():
        value = coerce_optional_bool(cfg.get(key))
        cfg[key] = fallback if value is None else value
    return cfg


def _normalise_api_url(url: str) -> str:
    base = str(url or '').strip().rstrip('/')
    if not base:
        return ''
    if base.startswith('http://0.0.0.0'):
        base = base.replace('http://0.0.0.0', 'http://localhost', 1)
    elif base.startswith('https://0.0.0.0'):
        base = base.replace('https://0.0.0.0', 'https://localhost', 1)
    if base.endswith('/api/v2'):
        return base + '/'
    return base + '/api/v2/'


def _read_caldera_main_config_from_disk() -> dict:
    """Read caldera's main config directly from conf/local.yml (preferred)
    or conf/default.yml (stock fallback).

    Used when ``BaseWorld.get_config()`` returns an empty dict — typically
    when this module is imported by a subprocess (e.g. MCP stdio server
    launched by an external client like Claude Desktop) that did NOT go
    through ``server.py``'s ``BaseWorld.apply_config`` boot path. Without
    this fallback, ``_caldera_url_from_server_config`` would resolve to
    the literal default ``localhost:8888`` regardless of which
    ``-E <env>`` the operator actually started the caldera server with,
    so a DetectionsVENV server on ``:8788`` (or any non-default port)
    would be silently unreachable to its own MCP subprocess.
    """
    import pathlib
    # this file lives at <repo>/plugins/mcp/app/config.py — climb 3 dirs
    # to reach the caldera repo root.
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    for env in ('local', 'default'):
        p = repo_root / 'conf' / f'{env}.yml'
        if p.is_file():
            try:
                return BaseWorld.strip_yml(str(p))[0] or {}
            except Exception:
                continue
    return {}


def _caldera_url_from_server_config() -> str:
    try:
        main = BaseWorld.get_config() or {}
    except Exception:
        main = {}

    # If BaseWorld is empty (we're running as a subprocess outside the
    # caldera server process), fall back to parsing the main config
    # files from disk so the URL still picks up the operator's port
    # override (e.g. -E local with port: 8788) instead of defaulting
    # to 8888.
    if not main:
        main = _read_caldera_main_config_from_disk()

    # For MCP's local REST calls, always target localhost on the port
    # from caldera's main config. We deliberately DON'T use
    # `app.contact.http` here even though it carries a fully-formed URL:
    # that field is the URL the operator wants *sandcat agents* (running
    # inside the bridge network) to call home on — typically the
    # bridge-side IP (e.g. http://10.10.0.1:8788). MCP and caldera run on
    # the same host, so localhost:<port> is always reachable, never
    # blocked by an iptables forward rule, and removes one source of
    # config drift between sandcat callbacks and MCP API calls.
    port = main.get('port') or 8888
    return _normalise_api_url(f'http://localhost:{port}')


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
        'url': os.environ.get(url_var) or _caldera_url_from_server_config(),
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
    for key in _BOOLEAN_FALLBACKS:
        if key in merged:
            value = coerce_optional_bool(merged.get(key))
            if value is not None:
                merged[key] = value
    if not merged.get('api_key'):
        raise ValueError(
            "No LLM API key. Set MCP_LLM_API_KEY in plugins/mcp/.env or "
            "enter one in the UI's Global Model Configuration."
        )
    if merged.get('provider', 'openai_compatible') == 'openai_compatible':
        merged['api_base'] = normalize_openai_api_base(merged.get('api_base'))
    return merged
