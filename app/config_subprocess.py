"""Subprocess-side LM bootstrap, paired with config.parent.

The MCP subprocess (e.g. caldera_core's mcp_server.py spawned by the
parent over stdio) needs DSPy configured before the first signature or
ChainOfThought call. The parent forwards the resolved LM settings into
the subprocess environment via the DSPY_* names below; this module
reads them lazily on the first call to ensure_lm_configured().

Lives under app/config/ so subprocess-side and parent-side
configuration are siblings under one namespace. The two halves cannot
share imports (the subprocess does not have Caldera's framework on
its sys.path) but they share the env-var contract documented here.

When you change one of the ENV_* constants, change the corresponding
key in plugins/mcp/app/workflows/*.py get_env(), which is what writes
these into the subprocess env at spawn.
"""
import os
import dspy

ENV_MODEL = "DSPY_MODEL"
ENV_API_KEY = "DSPY_API_KEY"
ENV_API_BASE = "DSPY_API_BASE"
ENV_TEMPERATURE = "DSPY_TEMPERATURE"
ENV_MAX_TOKENS = "DSPY_MAX_TOKENS"

_DEFAULTS = {
    "model": "gpt-4o",
    "temperature": 0.5,
    "max_tokens": 10000,
}

_LM_CONFIGURED = False


def ensure_lm_configured() -> None:
    """Configure dspy with an LM read from this subprocess's environment.

    Lazy and idempotent: runs on first call, no-ops afterward. Raises
    RuntimeError when DSPY_API_KEY is empty so the failure is loud at
    the moment the env contract is violated rather than at the first
    signature call far downstream.
    """
    global _LM_CONFIGURED
    if _LM_CONFIGURED:
        return

    api_key = os.environ.get(ENV_API_KEY, "")
    if not api_key:
        raise RuntimeError(
            f"{ENV_API_KEY} is empty in the MCP subprocess environment. "
            "The parent process is responsible for forwarding the resolved "
            "LLM key into this env var via the workflow's get_env() before "
            "spawning the subprocess. See plugins/mcp/app/config/parent.py."
        )

    lm_kwargs = {
        "model": os.environ.get(ENV_MODEL) or _DEFAULTS["model"],
        "api_key": api_key,
        "temperature": float(
            os.environ.get(ENV_TEMPERATURE) or _DEFAULTS["temperature"]
        ),
        "max_tokens": int(
            os.environ.get(ENV_MAX_TOKENS) or _DEFAULTS["max_tokens"]
        ),
    }
    api_base = os.environ.get(ENV_API_BASE)
    if api_base:
        lm_kwargs["api_base"] = api_base

    dspy.configure(lm=dspy.LM(**lm_kwargs))
    _LM_CONFIGURED = True
