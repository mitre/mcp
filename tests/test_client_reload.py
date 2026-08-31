"""A Save must reach the running client, not only the provenance stamp.

LLMClient snapshots the config at construction. Without dropping the
singleton, a Save reached get_llm_provenance, which reads fresh, but not
generate(), which reads the snapshot: the bundle was stamped with a model that
did not produce it.
"""
import pytest
import yaml

from plugins.mcp.app.utilities import llm_client


@pytest.fixture
def write_config(tmp_path, monkeypatch):
    conf = tmp_path / "conf"
    conf.mkdir()
    (conf / "default.yml").write_text(yaml.safe_dump(
        {"llm": {"provider": "openai_compatible", "model": "shipped", "api_base": ""}}
    ))
    monkeypatch.setattr(llm_client, "get_mcp_root", lambda: tmp_path)

    def _write(local):
        (conf / "local.yml").write_text(yaml.safe_dump(local))
        return llm_client.reload_config()

    return _write


def test_reload_drops_the_snapshot(write_config):
    write_config({"llm": {"model": "old", "api_base": "https://gw/v1"}})
    first = llm_client.get_llm_client()
    assert first.cfg["llm"]["model"] == "old"

    write_config({"llm": {"model": "new", "api_base": "https://gw/v1"}})

    second = llm_client.get_llm_client()
    assert second is not first
    assert second.cfg["llm"]["model"] == "new"
