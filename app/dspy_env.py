"""Command-synthesis signatures and module for the caldera_core MCP server.

Runs only inside a spawned MCP server subprocess (see mcp_server.py).
The subprocess's sys.path is rooted at app/, so the bootstrap is
imported via the sibling-style `config.subprocess` path.

DSPy is configured lazily on the first CreateCommand() instantiation.
Importing this module is now inert; the global LM state changes only
when CreateCommand actually needs it.
"""
import dspy

from config.subprocess import ensure_lm_configured


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
