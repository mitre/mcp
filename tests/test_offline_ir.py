"""Tests for cti_offline_ir.py — offline IR extraction."""


class TestExtractIrOffline:
    def test_basic_extraction(self):
        from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline
        text = "APT29 deployed Cobalt Strike for command and control."
        ir = extract_ir_offline(text)
        assert isinstance(ir, dict)
        for key in ("threat_actors",
                    "behaviors", "attack_patterns", "relationships"):
            assert key in ir


    def test_empty_text(self):
        from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline
        ir = extract_ir_offline("")
        assert isinstance(ir, dict)
        assert ir.get("threat_actors") == []

    def test_actor_frequency_inference(self):
        from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline
        text = """Wizard Spider attacked multiple organizations. Wizard Spider
        used encryption. Wizard Spider operators deployed tools."""
        ir = extract_ir_offline(text)
        actor_names = {a.get("name", "").lower() for a in ir["threat_actors"]}
        assert "wizard spider" in actor_names


    def test_behavior_extraction(self):
        from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline
        text = "The malware encrypts all files on the local drive and deletes backups."
        ir = extract_ir_offline(text)
        assert len(ir["behaviors"]) >= 1


class TestUnreachableEndpointFallsBack:
    """A configured but unreachable endpoint used to abort the whole run:
    the guard tested only for a falsy return, so a transport exception
    propagated out of extract_ir and killed Stage 1 for every file."""

    def test_connection_refused_degrades_to_offline(self):
        import asyncio
        import aiohttp
        from plugins.mcp.app.utilities import cti_parsing

        original = cti_parsing.llm_generate

        async def refused(prompt, profile="cti"):
            async with aiohttp.ClientSession() as s:
                # Port 9 (discard) is closed on a normal host.
                async with s.post("http://127.0.0.1:9/v1/chat/completions") as r:
                    return await r.text()

        cti_parsing.llm_generate = refused
        try:
            ir = asyncio.run(cti_parsing.extract_ir("APT29 used PowerShell."))
        finally:
            cti_parsing.llm_generate = original

        assert ir["extractor"] == "offline"

    def test_config_errors_still_raise(self):
        """A missing api_base is the operator's mistake, not a transient
        fault, so it must not be silently swallowed."""
        import asyncio
        import pytest
        from plugins.mcp.app.utilities import cti_parsing

        original = cti_parsing.llm_generate

        async def misconfigured(prompt, profile="cti"):
            raise ValueError("cti.api_base missing from MCP config")

        cti_parsing.llm_generate = misconfigured
        try:
            with pytest.raises(ValueError):
                asyncio.run(cti_parsing.extract_ir("APT29 used PowerShell."))
        finally:
            cti_parsing.llm_generate = original
