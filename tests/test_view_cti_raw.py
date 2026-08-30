"""Tests for the raw report preview endpoint backing the View column."""
import asyncio
import json
import logging
from pathlib import Path

import pytest

from plugins.mcp.app import mcp_api


class _Req:
    def __init__(self, body, malformed=False):
        self._body, self._malformed = body, malformed

    async def json(self):
        if self._malformed:
            raise ValueError("not json")
        return self._body


@pytest.fixture
def api(tmp_path):
    stub = mcp_api.McpAPI.__new__(mcp_api.McpAPI)
    stub.base_dir = tmp_path
    stub.log = logging.getLogger("test")
    uploads = tmp_path / "raw" / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "report.txt").write_text("APT29 used PowerShell.", encoding="utf-8")
    (uploads / "nested").mkdir()
    (uploads / "nested" / "inner.md").write_text("# Inner", encoding="utf-8")
    processed = tmp_path / "raw" / "processed"
    processed.mkdir(parents=True)
    (processed / "done.txt").write_text("already run", encoding="utf-8")
    return stub


def _call(api, body, malformed=False):
    res = asyncio.run(mcp_api.McpAPI.view_cti_raw(api, _Req(body, malformed)))
    return res.status, json.loads(res.body.decode())


class TestViewCtiRaw:
    def test_reads_an_upload(self, api):
        status, data = _call(api, {"filename": "report.txt"})
        assert status == 200
        assert data["text"] == "APT29 used PowerShell."
        assert data["kind"] == "txt"

    def test_reads_a_processed_file(self, api):
        """A report stays viewable after the pipeline moves it."""
        status, data = _call(api, {"filename": "done.txt"})
        assert status == 200
        assert data["text"] == "already run"

    def test_reads_a_nested_upload(self, api):
        """Directory uploads are addressed as <dir>/<name>, so basename
        alone would reject them."""
        status, data = _call(api, {"filename": "nested/inner.md"})
        assert status == 200
        assert data["text"] == "# Inner"

    def test_rejects_traversal(self, api):
        status, _ = _call(api, {"filename": "../../../etc/passwd"})
        assert status == 404

    def test_rejects_missing_filename(self, api):
        status, data = _call(api, {})
        assert status == 400
        assert "filename" in data["error"].lower()

    def test_rejects_malformed_body(self, api):
        status, data = _call(api, None, malformed=True)
        assert status == 400
        assert "JSON" in data["error"]

    def test_missing_file_is_404(self, api):
        status, _ = _call(api, {"filename": "absent.txt"})
        assert status == 404
