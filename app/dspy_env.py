"""DSPy environment for the caldera_core MCP server subprocess.

Owns the DSPy library contract end-to-end:

  * The DSPY_* env-var names that bridge parent and subprocess.
  * The lazy LM bootstrap that runs on the first CreateCommand().
  * The signatures and CreateCommand module that mcp_server.py uses
    to author abilities.

Has no Caldera framework dependency; imports only os and dspy. The
parent's get_env helper imports the ENV_* constants from here so the
env-var contract has a single source of truth.

Importing this module is inert. The global LM state changes only when
CreateCommand() is first instantiated, at which point
ensure_lm_configured() reads the subprocess environment and either
configures DSPy or raises a loud RuntimeError if the parent did not
forward the API key.
"""
import os
import dspy


ENV_MODEL = "DSPY_MODEL"
ENV_API_KEY = "DSPY_API_KEY"
ENV_API_BASE = "DSPY_API_BASE"
ENV_TEMPERATURE = "DSPY_TEMPERATURE"
ENV_MAX_TOKENS = "DSPY_MAX_TOKENS"
ENV_PROVIDER = "DSPY_PROVIDER"
ENV_TIMEOUT = "DSPY_TIMEOUT"
ENV_SSL_VERIFY = "DSPY_SSL_VERIFY"

_DEFAULTS = {
    "model": "gpt-4o",
    "temperature": 0.5,
    "max_tokens": 10000,
}

_LM_CONFIGURED = False


def coerce_optional_bool(value):
    """Return bool for config/env truthy strings, or None when unset."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return None


def apply_litellm_ssl_verify(value):
    """Apply SSL verification before LiteLLM/OpenAI clients are created."""
    ssl_verify = coerce_optional_bool(value)
    if ssl_verify is None:
        return None
    os.environ["SSL_VERIFY"] = "true" if ssl_verify else "false"
    try:
        import litellm
        litellm.ssl_verify = ssl_verify
    except Exception:
        pass
    return ssl_verify


def dspy_lm_kwargs_from_settings(settings: dict) -> dict:
    """Translate resolved MCP LLM settings into DSPy/LiteLLM kwargs."""
    settings = settings or {}
    lm_kwargs = {
        "model": settings.get("model") or _DEFAULTS["model"],
        "api_key": settings.get("api_key") or "",
    }
    if settings.get("api_base"):
        lm_kwargs["api_base"] = settings.get("api_base")
    if settings.get("temperature") is not None:
        lm_kwargs["temperature"] = settings.get("temperature")
    if settings.get("max_tokens") is not None:
        lm_kwargs["max_tokens"] = settings.get("max_tokens")
    if settings.get("timeout") is not None:
        lm_kwargs["timeout"] = settings.get("timeout")

    provider = settings.get("provider") or "openai_compatible"
    if provider == "openai_compatible" and settings.get("api_base"):
        lm_kwargs["custom_llm_provider"] = "custom_openai"

    apply_litellm_ssl_verify(settings.get("ssl_verify"))
    return lm_kwargs


def ensure_lm_configured() -> None:
    """Configure dspy with an LM read from this subprocess's environment.

    Lazy and idempotent: runs on first call, no-ops afterward. Raises
    RuntimeError when DSPY_API_KEY is empty so the failure is loud at
    the env-contract boundary rather than at the first signature call
    far downstream.
    """
    global _LM_CONFIGURED
    if _LM_CONFIGURED:
        return

    api_key = os.environ.get(ENV_API_KEY, "")
    if not api_key:
        raise RuntimeError(
            f"{ENV_API_KEY} is empty in the MCP subprocess environment. "
            "The parent process forwards the resolved LLM key into this "
            "env var via the workflow's get_env() before spawning. "
            "See plugins/mcp/app/config.py for the parent-side resolver."
        )

    lm_kwargs = dspy_lm_kwargs_from_settings({
        "model": os.environ.get(ENV_MODEL) or _DEFAULTS["model"],
        "api_key": api_key,
        "api_base": os.environ.get(ENV_API_BASE),
        "provider": os.environ.get(ENV_PROVIDER) or "openai_compatible",
        "temperature": float(
            os.environ.get(ENV_TEMPERATURE) or _DEFAULTS["temperature"]
        ),
        "max_tokens": int(
            os.environ.get(ENV_MAX_TOKENS) or _DEFAULTS["max_tokens"]
        ),
        "timeout": int(os.environ[ENV_TIMEOUT]) if os.environ.get(ENV_TIMEOUT) else None,
        "ssl_verify": os.environ.get(ENV_SSL_VERIFY),
    })

    dspy.configure(lm=dspy.LM(**lm_kwargs))
    _LM_CONFIGURED = True


class RankApproaches(dspy.Signature):
    """Rank the approaches to create the command."""

    description: str = dspy.InputField()
    technologies: list[str] = dspy.InputField()
    approaches: list[str] = dspy.OutputField()


class IdentifyTechnologies(dspy.Signature):
    """Identify the technologies that are relevant to the command.

    For windows, the basic shell interpreter is powershell.exe.
    For linux, the basic shell interpreter is bash.
    """

    description: str = dspy.InputField()
    platform: str = dspy.InputField()
    technologies: list[str] = dspy.OutputField()


class CreateFullCommand(dspy.Signature):
    """Create the full command. Only produce the command, do not give reasoning or comments. Do not wrap the response in any tags."""
    technologies: list[str] = dspy.InputField()
    approaches: list[str] = dspy.InputField()
    command: str = dspy.OutputField()


class CreateCommand(dspy.Module):
    def __init__(self):
        ensure_lm_configured()
        self.identify_technologies = dspy.ChainOfThought(IdentifyTechnologies)
        self.rank_approaches = dspy.ChainOfThought(RankApproaches)
        self.create_full_command = dspy.ChainOfThought(CreateFullCommand)

    def forward(self, description: str, platform: str):
        identified_technologies = self.identify_technologies(description=description, platform=platform)
        ranked_approaches = self.rank_approaches(description=description, technologies=identified_technologies)
        full_command = self.create_full_command(technologies=identified_technologies, approaches=ranked_approaches)
        return full_command.command
