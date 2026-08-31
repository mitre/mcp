"""A report is processed when it has an IR, not when it sits in a directory.

The listing stamped a literal "processed" on everything in raw/processed, and
finalize_run moved every upload there regardless of the selection. So a report
that was never selected, never cleaned and never extracted rendered green.
"""
import json

import pytest


@pytest.fixture
def api(tmp_path, monkeypatch):
    from plugins.mcp.app import mcp_api
    monkeypatch.setattr(mcp_api, "get_mcp_root", lambda: tmp_path)
    monkeypatch.setattr(mcp_api, "get_mcp_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(mcp_api, "reload_config", dict)
    return mcp_api.McpAPI({"mcp_svc": None})


def _items(resp):
    return {i["name"]: i for i in json.loads(resp.text)["items"]}


@pytest.mark.asyncio
async def test_a_retired_report_with_no_ir_is_not_processed(api):
    processed = api.base_dir / "raw" / "processed"
    processed.mkdir(parents=True)
    (processed / "never-run.html").write_text("x")

    assert _items(await api.list_cti_raw(None))["never-run.html"]["status"] == "pending"


@pytest.mark.asyncio
async def test_a_report_with_a_current_ir_is_processed(api):
    processed = api.base_dir / "raw" / "processed"
    ir = api.base_dir / "outputs_ir" / "complete"
    processed.mkdir(parents=True)
    ir.mkdir(parents=True)
    (processed / "done.pdf").write_text("x")
    # The IR is keyed on the clean stem, which folds the source extension in.
    (ir / "done_pdf.json").write_text("{}")

    assert _items(await api.list_cti_raw(None))["done.pdf"]["status"] == "processed"


@pytest.mark.asyncio
async def test_a_stale_ir_is_pending_again(api):
    import os
    processed = api.base_dir / "raw" / "processed"
    ir = api.base_dir / "outputs_ir" / "complete"
    processed.mkdir(parents=True)
    ir.mkdir(parents=True)
    (ir / "edited_txt.json").write_text("{}")
    src = processed / "edited.txt"
    src.write_text("x")
    os.utime(src, (2 ** 31, 2 ** 31))  # newer than its IR

    assert _items(await api.list_cti_raw(None))["edited.txt"]["status"] == "pending"


@pytest.mark.asyncio
async def test_an_upload_that_was_already_extracted_shows_processed(api):
    uploads = api.base_dir / "raw" / "uploads"
    ir = api.base_dir / "outputs_ir" / "complete"
    uploads.mkdir(parents=True)
    ir.mkdir(parents=True)
    (uploads / "kept.md").write_text("x")
    (ir / "kept_md.json").write_text("{}")

    # Status follows the artifact, not which directory the file sits in.
    assert _items(await api.list_cti_raw(None))["kept.md"]["status"] == "processed"
