"""conf/local.yml must never receive a credential.

set_config is the plugin's own Save endpoint and the UI posts api_key with
every save, so the filter lives server-side where a stale browser cannot
bypass it.
"""
import pytest
import yaml


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


@pytest.fixture
def api(tmp_path, monkeypatch):
    from plugins.mcp.app import mcp_api

    monkeypatch.setattr(mcp_api, "get_mcp_root", lambda: tmp_path)
    monkeypatch.setattr(mcp_api, "get_mcp_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(mcp_api, "reload_config", dict)
    return mcp_api.McpAPI({"mcp_svc": None})


def _saved(tmp_path):
    return yaml.safe_load((tmp_path / "conf" / "local.yml").read_text())


@pytest.mark.asyncio
async def test_api_key_is_not_written(api, tmp_path):
    await api.set_config(_FakeRequest({
        "llm": {"model": "openai/x", "api_base": "https://gw/v1", "api_key": "sk-secret"}
    }))
    saved = _saved(tmp_path)
    assert "api_key" not in saved["llm"]
    assert "sk-secret" not in (tmp_path / "conf" / "local.yml").read_text()
    assert saved["llm"]["api_base"] == "https://gw/v1"


@pytest.mark.asyncio
async def test_every_secret_field_is_stripped(api, tmp_path):
    await api.set_config(_FakeRequest({
        "llm": {"api_key": "a", "embed_api_key": "b", "rag_api_key": "c", "model": "m"}
    }))
    assert _saved(tmp_path)["llm"] == {"model": "m"}


@pytest.mark.asyncio
async def test_save_scrubs_a_key_an_earlier_build_wrote(api, tmp_path):
    conf = tmp_path / "conf"
    conf.mkdir()
    (conf / "local.yml").write_text(yaml.safe_dump({
        "llm": {"model": "old", "api_key": "sk-legacy"},
        "cti": {"model": "old", "api_key": "sk-legacy-cti"},
    }))

    # Saving an unrelated section still cleans the whole file.
    await api.set_config(_FakeRequest({"llm": {"model": "new"}}))

    text = (conf / "local.yml").read_text()
    assert "sk-legacy" not in text
    assert "api_key" not in text
    assert _saved(tmp_path)["cti"]["model"] == "old"


@pytest.mark.asyncio
async def test_strips_nested_secrets(api, tmp_path):
    # set_config accepts arbitrary top-level keys, so callers have produced
    # nested shapes like {"config": {"cti": {...}}}. A one-level scrub
    # walked straight past those.
    await api.set_config(_FakeRequest({
        "config": {"cti": {"model": "m", "api_key": "sk-nested"}},
    }))
    text = (tmp_path / "conf" / "local.yml").read_text()
    assert "sk-nested" not in text
    assert _saved(tmp_path)["config"]["cti"] == {"model": "m"}


@pytest.mark.asyncio
async def test_strips_secrets_inside_lists(api, tmp_path):
    await api.set_config(_FakeRequest({
        "llm": {"profiles": [{"name": "a", "api_key": "sk-in-list"}]},
    }))
    assert "sk-in-list" not in (tmp_path / "conf" / "local.yml").read_text()


@pytest.mark.asyncio
async def test_strips_every_key_field_the_ui_uses(api, tmp_path):
    # A fixed list kept missing new ones as the RAG panels grew.
    await api.set_config(_FakeRequest({
        "llm": {"api_key": "sk-a", "embed_api_key": "sk-b", "plan_api_key": "sk-c",
                "rag_api_key": "sk-d", "cti_rag_api_key": "sk-e", "apiKey": "sk-f",
                "model": "keep-me"},
    }))
    text = (tmp_path / "conf" / "local.yml").read_text()
    for leaked in ("sk-a", "sk-b", "sk-c", "sk-d", "sk-e", "sk-f"):
        assert leaked not in text
    assert _saved(tmp_path)["llm"] == {"model": "keep-me"}


@pytest.mark.asyncio
async def test_keeps_the_env_var_indirection(api, tmp_path):
    # api_key_env names a variable, not a value. Dropping it would silently
    # disable .env resolution for the whole deployment.
    await api.set_config(_FakeRequest({
        "llm": {"api_key_env": "MCP_LLM_API_KEY", "api_base_env": "MCP_LLM_API_BASE"},
    }))
    assert _saved(tmp_path)["llm"] == {
        "api_key_env": "MCP_LLM_API_KEY", "api_base_env": "MCP_LLM_API_BASE",
    }
