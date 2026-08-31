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
         ("provider", "ollama"), ("ssl_verify", False),
         # Shown by two panels, so stored once on llm.
         ("temperature", 0.0), ("max_tokens", 4000)],
    )
    async def test_a_connection_key_is_refused(self, api, tmp_path, key, value):
        resp = await api.set_config(_FakeRequest({"cti": {key: value}}))
        assert resp.status == 400
        assert not (tmp_path / "conf" / "local.yml").exists()

    @pytest.mark.asyncio
    async def test_a_credential_is_stripped_rather_than_refused(self, api, tmp_path):
        # An older cached bundle still posts api_key. Refusing the whole
        # payload would stop it saving anything; the scrub is what protects
        # the file.
        resp = await api.set_config(_FakeRequest(
            {"cti": {"timeout": 120, "api_key": "sk-x"}}))
        assert resp.status == 200
        assert "sk-x" not in (tmp_path / "conf" / "local.yml").read_text()
        assert _saved(tmp_path)["cti"]["timeout"] == 120

    @pytest.mark.asyncio
    async def test_the_message_names_the_key_and_the_owner(self, api):
        resp = await api.set_config(_FakeRequest({"cti": {"model": "devstral"}}))
        assert "cti.model" in resp.text and "'llm'" in resp.text

    @pytest.mark.asyncio
    async def test_a_generation_setting_is_accepted(self, api, tmp_path):
        resp = await api.set_config(_FakeRequest({"cti": {"timeout": 120}}))
        assert resp.status == 200
        assert _saved(tmp_path)["cti"]["timeout"] == 120

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


class TestGetConfigResolvesServerSide:
    """The panel must not re-implement the resolver in JavaScript.

    It layered the profiles itself over raw yaml and skipped the env
    indirection, so it displayed "not set" for an endpoint that came from
    MCP_LLM_API_BASE while extraction dialled it correctly.
    """

    @pytest.mark.asyncio
    async def test_the_connection_is_resolved_onto_the_workload(self, api, tmp_path):
        (tmp_path / "conf" / "local.yml").write_text(yaml.safe_dump(
            {"llm": {"model": "devstral", "api_base": "https://gw/v1"},
             "cti": {"timeout": 120}}))
        llm_client.load_config.cache_clear()

        resp = await api.get_config(None)
        body = __import__("json").loads(resp.text)

        assert body["resolved"]["cti"]["model"] == "devstral"
        assert body["resolved"]["cti"]["api_base"] == "https://gw/v1"
        assert body["resolved"]["cti"]["timeout"] == 120

    @pytest.mark.asyncio
    async def test_the_env_indirection_is_applied(self, api, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_GATEWAY", "https://from-env/v1")
        (tmp_path / "conf" / "local.yml").write_text(yaml.safe_dump(
            {"llm": {"model": "m", "api_base": "", "api_base_env": "MY_GATEWAY"}}))
        llm_client.load_config.cache_clear()

        resp = await api.get_config(None)
        body = __import__("json").loads(resp.text)
        assert body["resolved"]["cti"]["api_base"] == "https://from-env/v1"

    @pytest.mark.asyncio
    async def test_no_credential_reaches_the_browser(self, api, tmp_path, monkeypatch):
        monkeypatch.setenv("MCP_LLM_API_KEY", "sk-live")
        (tmp_path / "conf" / "local.yml").write_text(yaml.safe_dump(
            {"llm": {"model": "m", "api_base": "https://gw/v1",
                     "api_key_env": "MCP_LLM_API_KEY"}}))
        llm_client.load_config.cache_clear()

        resp = await api.get_config(None)
        assert "sk-live" not in resp.text


class TestOnlyKnownSectionsAndKeys:
    """The llm section used to accept any key at all, and any section was new.

    A gateway credential arrives as an Authorization or x-api-key header, and
    conf/local.yml is plaintext beside tracked config.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["extra_headers", "not_a_setting"])
    async def test_an_unknown_llm_key_is_refused(self, api, tmp_path, key):
        resp = await api.set_config(_FakeRequest({"llm": {key: "x"}}))
        assert resp.status == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["Authorization", "x-api-key"])
    async def test_a_header_credential_never_reaches_the_file(self, api, tmp_path, key):
        await api.set_config(_FakeRequest({"llm": {"model": "m", key: "sk-live"}}))
        assert "sk-live" not in (tmp_path / "conf" / "local.yml").read_text()

    @pytest.mark.asyncio
    async def test_an_unknown_section_is_refused(self, api):
        resp = await api.set_config(_FakeRequest({"totally_new": {"password": "x"}}))
        assert resp.status == 400
        assert "unknown config section" in resp.text

    @pytest.mark.asyncio
    async def test_the_get_config_envelope_does_not_bypass_validation(self, api):
        # get_config returns {"config": ..., "resolved": ...}. That sibling key
        # made the envelope test fail, so a round trip was treated as a literal
        # payload and slipped past the per-section rules.
        resp = await api.set_config(_FakeRequest(
            {"config": {"cti": {"model": "sneaky"}}, "resolved": {}}))
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_a_round_trip_does_not_persist_the_envelope(self, api, tmp_path):
        resp = await api.set_config(_FakeRequest(
            {"config": {"cti": {"timeout": 120}}, "resolved": {"cti": {}}}))
        assert resp.status == 200
        saved = _saved(tmp_path)
        assert saved["cti"]["timeout"] == 120
        assert "config" not in saved and "resolved" not in saved


class TestMlflowStaysOnLoopback:
    """hook.py passes mlflow.host to 'mlflow server --host'.

    That server holds every prompt and response the plugin has logged, with no
    authentication, so rebinding it off loopback is a deployment decision
    rather than something one authenticated POST should do.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("host", ["0.0.0.0", "10.0.0.5", "::"])
    async def test_a_non_loopback_bind_is_refused(self, api, host):
        resp = await api.set_config(_FakeRequest({"mlflow": {"host": host}}))
        assert resp.status == 400
        assert "tracking server" in resp.text

    @pytest.mark.asyncio
    async def test_loopback_and_port_are_fine(self, api, tmp_path):
        resp = await api.set_config(
            _FakeRequest({"mlflow": {"host": "127.0.0.1", "port": 5050}}))
        assert resp.status == 200
        assert _saved(tmp_path)["mlflow"]["port"] == 5050


def test_max_tokens_is_not_mistaken_for_a_credential():
    # The widened secret pattern matches "token"; max_tokens is a generation
    # setting, and dropping it silently is worse than not matching a secret.
    from plugins.mcp.app.mcp_api import _is_secret
    assert not _is_secret("max_tokens")
    assert _is_secret("access_token")
