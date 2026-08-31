"""The writer must enforce the same rule as the reader.

set_config used to accept any key in any section and answer "saved", while
layered_profile then dropped everything outside the allowlist. A setting that
is persisted and never read is worse than one that is refused, because the
file looks like it took effect.
"""
import pytest
import yaml

from plugins.mcp.app.utilities import llm_client


DEFAULTS = {
    "llm": {"provider": "openai_compatible", "model": "shipped", "api_base": ""},
    "mlflow": {"host": "127.0.0.1", "port": 5000},
}


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


@pytest.fixture
def api(tmp_path, monkeypatch):
    from plugins.mcp.app import mcp_api

    conf = tmp_path / "conf"
    conf.mkdir()
    (conf / "default.yml").write_text(yaml.safe_dump(DEFAULTS))

    # Both modules must see the sandbox: the endpoint resolves the lock map
    # through llm_client.load_config, not through its own root.
    monkeypatch.setattr(mcp_api, "get_mcp_root", lambda: tmp_path)
    monkeypatch.setattr(mcp_api, "get_mcp_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(llm_client, "get_mcp_root", lambda: tmp_path)
    llm_client.load_config.cache_clear()
    return mcp_api.McpAPI({"mcp_svc": None})


def _saved(tmp_path):
    return yaml.safe_load((tmp_path / "conf" / "local.yml").read_text())


def _lock(tmp_path, locked):
    (tmp_path / "conf" / "local.yml").write_text(
        yaml.safe_dump({"llm": {"fields_locked": locked}})
    )
    llm_client.load_config.cache_clear()


class TestWorkloadProfilesRefuseTheConnection:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "key,value",
        [("model", "devstral"), ("api_base", "https://gw/v1"),
         ("provider", "ollama"), ("ssl_verify", False), ("api_key", "sk-x")],
    )
    async def test_a_connection_key_is_refused(self, api, tmp_path, key, value):
        resp = await api.set_config(_FakeRequest({"cti": {key: value}}))
        assert resp.status == 400
        assert not (tmp_path / "conf" / "local.yml").exists()

    @pytest.mark.asyncio
    async def test_the_message_names_the_key_and_the_owner(self, api):
        resp = await api.set_config(_FakeRequest({"cti": {"model": "devstral"}}))
        assert "cti.model" in resp.text and "'llm'" in resp.text

    @pytest.mark.asyncio
    async def test_a_generation_setting_is_accepted(self, api, tmp_path):
        resp = await api.set_config(_FakeRequest({"cti": {"temperature": 0.0}}))
        assert resp.status == 200
        assert _saved(tmp_path)["cti"]["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_the_connection_is_accepted_on_llm(self, api, tmp_path):
        resp = await api.set_config(_FakeRequest(
            {"llm": {"model": "devstral", "api_base": "https://gw/v1"}}))
        assert resp.status == 200
        assert _saved(tmp_path)["llm"]["model"] == "devstral"


class TestUnrelatedSectionsAreNotLlmProfiles:
    @pytest.mark.asyncio
    async def test_mlflow_is_not_subject_to_the_allowlist(self, api, tmp_path):
        resp = await api.set_config(_FakeRequest({"mlflow": {"port": 5050}}))
        assert resp.status == 200
        assert _saved(tmp_path)["mlflow"]["port"] == 5050

    @pytest.mark.asyncio
    async def test_caldera_is_not_subject_to_the_allowlist(self, api, tmp_path):
        resp = await api.set_config(_FakeRequest(
            {"caldera": {"url_env": "CALDERA_URL"}}))
        assert resp.status == 200


class TestTheLockIsNotSelfDefeating:
    @pytest.mark.asyncio
    async def test_fields_locked_cannot_be_written(self, api):
        resp = await api.set_config(_FakeRequest(
            {"llm": {"fields_locked": {"model": False}}}))
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_a_locked_field_is_refused(self, api, tmp_path):
        _lock(tmp_path, {"model": True})
        resp = await api.set_config(_FakeRequest({"llm": {"model": "evil"}}))
        assert resp.status == 400
        assert _saved(tmp_path)["llm"].get("model") is None

    @pytest.mark.asyncio
    async def test_an_unlocked_field_still_saves(self, api, tmp_path):
        _lock(tmp_path, {"model": True})
        resp = await api.set_config(_FakeRequest(
            {"llm": {"api_base": "https://gw/v1"}}))
        assert resp.status == 200
        assert _saved(tmp_path)["llm"]["api_base"] == "https://gw/v1"
