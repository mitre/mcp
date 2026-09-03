"""A workflow must not be handed a tool it denies.

Author's signature says not to run operations, but caldera_core is required
and cti_pipeline is optional, and between them they expose three tools that
do. denied_tools is what turns that instruction into a boundary, so the risk
is that it silently stops covering a tool: a denylist fails open, and a new
executing tool on either server would reach Author by default.

These tests pin both halves. The declaration has to name every executing tool
the two servers expose, and run()'s assembly loop has to actually drop them.
"""
import re
from pathlib import Path

from plugins.mcp.app.workflows.author import WORKFLOWS as AUTHOR_WORKFLOWS
from plugins.mcp.app.workflows.plan_execute import WORKFLOWS as PLAN_WORKFLOWS

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# A tool that starts an operation is one that makes CALDERA run something on
# an agent. Matched by name because both servers name them consistently, and
# a new one that breaks the convention should fail the coverage test below
# rather than pass unnoticed.
_EXECUTING = re.compile(r"(run_operation|create_operation|add_link_to_operation)$")


def _tool_names(server: Path) -> list[str]:
    """Tool names a server registers, read rather than imported: importing
    mcp_server would construct a FastMCP app and reach for config."""
    source = server.read_text(encoding="utf-8")
    return re.findall(r'@mcp\.tool\(name="([^"]+)"', source)


def _author():
    return next(w for w in AUTHOR_WORKFLOWS if w.id == "author")


def test_author_denies_every_executing_tool_it_can_reach():
    reachable: list[str] = []
    for server in ("app/mcp_server.py", "mcp_server.py"):
        reachable += _tool_names(_PLUGIN_ROOT / server)

    executing = {name for name in reachable if _EXECUTING.search(name)}
    assert executing, "no executing tools found; the name convention changed"

    denied = set(_author().denied_tools)
    missing = executing - denied
    assert not missing, (
        f"author can reach {sorted(missing)}, which start operations. "
        f"Add them to denied_tools or rename them out of the convention."
    )


def test_plan_execute_denies_nothing():
    """The boundary is Author's. Plan and Execute is supposed to run things,
    so an empty list here is the assertion, not an oversight."""
    plan = next(w for w in PLAN_WORKFLOWS if w.id == "plan_execute")
    assert plan.denied_tools == []


def test_run_honours_the_declaration():
    """The declaration only matters if run() drops the tool.

    Asserted against run()'s source rather than a mirror of its filter: a
    reimplementation here would pass whatever the real loop did.
    """
    source = (_PLUGIN_ROOT / "app/workflows/author.py").read_text(encoding="utf-8")
    assert "denied = set(denied_tools or ())" in source
    assert "if tool.name in denied:\n                        continue" in source


def test_author_still_gets_the_tools_it_needs():
    """Denying too much is the other way to break this."""
    denied = set(_author().denied_tools)
    for needed in (
        "core_create_windows_ability",
        "core_create_linux_ability",
        "core_create_adversary",
        "cti_pipeline_build_adversary",
    ):
        assert needed not in denied
