import dspy
import os

# Configure DSPy from environment variables (passed from parent process)
# This allows the MCP server subprocess to use the same API key as the main workflow
def configure_dspy_from_env():
    model = os.environ.get('DSPY_MODEL', 'gpt-4o')
    api_key = os.environ.get('DSPY_API_KEY', '')
    api_base = os.environ.get('DSPY_API_BASE', '')
    temperature = float(os.environ.get('DSPY_TEMPERATURE', '0.5'))
    max_tokens = int(os.environ.get('DSPY_MAX_TOKENS', '10000'))

    if api_key:  # Only configure if we have an API key
        lm_kwargs = dict(model=model, api_key=api_key, temperature=temperature, max_tokens=max_tokens)
        if api_base:
            lm_kwargs['api_base'] = api_base
        lm = dspy.LM(**lm_kwargs)
        dspy.configure(lm=lm)

configure_dspy_from_env()

class RankApproaches(dspy.Signature):
    """Rank the approaches to create the command."""

    description: str = dspy.InputField()
    technologies: list[str] = dspy.InputField()
    approaches: list[str] = dspy.OutputField()

class IdentifyTechnologies(dspy.Signature):
    """
    Identify the technologies that are relevant to the command.
    For windows, the basic shell interpreter is powershell.exe.
    For linux, the basic shell interpreter is bash.
    """
    
    description: str = dspy.InputField()
    platform: str = dspy.InputField()
    technologies: list[str] = dspy.OutputField()

class CreateFullCommand(dspy.Signature):
    """Create the full command. Only produce the command, do not give reasoning or comments.  Do not wrap the response in any tags."""
    technologies: list[str] = dspy.InputField()
    approaches: list[str] = dspy.InputField()
    command: str = dspy.OutputField()

class CreateCommand(dspy.Module):
    def __init__(self):
        self.identify_technologies = dspy.ChainOfThought(IdentifyTechnologies)
        self.rank_approaches = dspy.ChainOfThought(RankApproaches)
        self.create_full_command = dspy.ChainOfThought(CreateFullCommand)
        #self.log = logging.getLogger("plugins.mcp")
        #self.log.info("[MCP] Initialized CreateCommand Module")

    def forward(self, description: str, platform: str):
        identified_technologies = self.identify_technologies(description=description, platform=platform)
        ranked_approaches = self.rank_approaches(description=description, technologies=identified_technologies)
        full_command = self.create_full_command(technologies=identified_technologies, approaches=ranked_approaches)
        return full_command.command
        
