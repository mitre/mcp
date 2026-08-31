"""set_config must merge into a section, not replace it.

conf/local.yml is a sparse overlay that operators also hand-edit. The CTI
panel posts four keys, so assigning the section outright deleted a pinned
model, api_base or ssl_verify on every Save.
"""
import asyncio
import logging

import pytest
import yaml

from plugins.mcp.app import mcp_api


class _Req:
    def __init__(self, body): self._body = body
    async def json(self): return self._body


@pytest.fixture
def api(tmp_path):
    stub = mcp_api.McpAPI.__new__(mcp_api.McpAPI)
    stub.root_dir = tmp_path
    stub.log = logging.getLogger("test")
    stub.services = {}
    (tmp_path / "conf").mkdir()
    return stub


def _local(api):
    return yaml.safe_load((api.root_dir / "conf" / "local.yml").read_text())


def _save(api, payload):
    asyncio.run(mcp_api.McpAPI.set_config(api, _Req(payload)))


class TestSetConfigMerges:
    def test_a_partial_save_keeps_pinned_keys(self, api):
        (api.root_dir / "conf" / "local.yml").write_text(
            "cti:\n  top_p: 0.9\n  offline: true\n  timeout: 60\n"
        )
        _save(api, {"cti": {"timeout": 120}})
        cti = _local(api)["cti"]
        assert cti["top_p"] == 0.9
        assert cti["offline"] is True
        assert cti["timeout"] == 120

    def test_other_sections_are_untouched(self, api):
        (api.root_dir / "conf" / "local.yml").write_text(
            "llm:\n  model: qwen\ncti:\n  timeout: 60\n"
        )
        _save(api, {"cti": {"timeout": 120}})
        assert _local(api)["llm"]["model"] == "qwen"

    def test_a_new_section_is_created(self, api):
        (api.root_dir / "conf" / "local.yml").write_text("llm:\n  model: qwen\n")
        _save(api, {"cti": {"timeout": 120}})
        assert _local(api)["cti"]["timeout"] == 120

    def test_writes_a_file_that_does_not_exist_yet(self, api):
        _save(api, {"cti": {"timeout": 120}})
        assert _local(api)["cti"]["timeout"] == 120

    def test_secrets_never_reach_the_file(self, api):
        # api_key belongs to the connection, so it goes to 'llm'. On a
        # workload profile the allowlist refuses it outright.
        _save(api, {"llm": {"model": "m", "api_key": "sk-secret"}})
        assert "api_key" not in _local(api)["llm"]
