"""The delete endpoints must not reach outside their own directories."""
import asyncio
import json
import logging

import pytest

from plugins.mcp.app import mcp_api


class _Req:
    def __init__(self, body): self._body = body
    async def json(self): return self._body


def _call(api, fn, body):
    res = asyncio.run(fn(api, _Req(body)))
    return res.status, json.loads(res.body.decode())


@pytest.fixture
def api(tmp_path):
    stub = mcp_api.McpAPI.__new__(mcp_api.McpAPI)
    stub.base_dir = tmp_path
    stub.log = logging.getLogger("test")
    (tmp_path / "outputs_stix").mkdir()
    (tmp_path / "outputs_stix" / "real.stix.json").write_text("{}")
    (tmp_path / "raw" / "uploads").mkdir(parents=True)
    (tmp_path / "raw" / "uploads" / "a.txt").write_text("a")
    (tmp_path / "raw" / "processed").mkdir(parents=True)
    (tmp_path / "OUTSIDE.txt").write_text("must survive")
    return stub


class TestDeleteStix:
    def test_traversal_cannot_delete_outside(self, api):
        _call(api, mcp_api.McpAPI.delete_stix_cti, {"files": ["../OUTSIDE.txt"]})
        assert (api.base_dir / "OUTSIDE.txt").exists()

    def test_reports_only_what_it_deleted(self, api):
        """It used to echo the request back, so a rejected name still read as
        deleted."""
        _, data = _call(api, mcp_api.McpAPI.delete_stix_cti,
                        {"files": ["../OUTSIDE.txt"]})
        assert data["deleted"] == []

    def test_legitimate_delete_still_works(self, api):
        _, data = _call(api, mcp_api.McpAPI.delete_stix_cti,
                        {"files": ["real.stix.json"]})
        assert data["deleted"] == ["real.stix.json"]
        assert not (api.base_dir / "outputs_stix" / "real.stix.json").exists()

    def test_non_string_elements_are_rejected(self, api):
        status, _ = _call(api, mcp_api.McpAPI.delete_stix_cti, {"files": [{"a": 1}]})
        assert status == 400


class TestDeleteRaw:
    def test_empty_name_cannot_remove_the_base_directory(self, api):
        """The guard admitted target == base, and the else-branch is an
        unconditional rmtree, so an empty name wiped uploads entirely."""
        _call(api, mcp_api.McpAPI.delete_cti_raw, {"files": ["", ""]})
        assert (api.base_dir / "raw" / "uploads").exists()
        assert (api.base_dir / "raw" / "processed").exists()

    def test_named_file_still_deletes(self, api):
        _, data = _call(api, mcp_api.McpAPI.delete_cti_raw, {"files": ["a.txt"]})
        assert "a.txt" in data.get("deleted", [])
