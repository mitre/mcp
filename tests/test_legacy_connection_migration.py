"""A pre-allowlist conf/local.yml must not silently retarget extraction.

Before the connection was centralised, local.yml carried the endpoint under
the workload that used it. Dropping those keys is correct for the new model
but sends report text to whatever default.yml ships instead of the operator's
own gateway, with only a log line to say so.
"""
import pytest
import yaml

from plugins.mcp.app.utilities import llm_client


DEFAULTS = {
    "llm": {
        "provider": "openai_compatible",
        "model": "openai/gpt-oss-120b",
        "api_base": "",
    },
    "mlflow": {"host": "127.0.0.1", "port": 5000},
}

LEGACY = {
    "cti": {
        "provider": "openai_compatible",
        "model": "devstral",
        "api_base": "https://localhost:8443/v1",
        "ssl_verify": False,
        "temperature": 0.0,
    }
}


@pytest.fixture
def loader(tmp_path, monkeypatch):
    conf = tmp_path / "conf"
    conf.mkdir()
    (conf / "default.yml").write_text(yaml.safe_dump(DEFAULTS))
    monkeypatch.setattr(llm_client, "get_mcp_root", lambda: tmp_path)

    def _load(local=None):
        if local is not None:
            (conf / "local.yml").write_text(yaml.safe_dump(local))
        llm_client.load_config.cache_clear()
        return llm_client.load_config()

    return _load


class TestLegacyConnectionIsHonoured:
    def test_the_operators_gateway_survives(self, loader):
        cfg = loader(LEGACY)
        assert cfg["llm"]["api_base"] == "https://localhost:8443/v1"
        assert cfg["llm"]["model"] == "devstral"
        assert cfg["llm"]["ssl_verify"] is False

    def test_extraction_resolves_to_that_gateway(self, loader):
        r = llm_client.layered_profile(loader(LEGACY), "cti")
        assert r["api_base"] == "https://localhost:8443/v1"
        assert r["model"] == "devstral"
        # The generation setting it was always entitled to still applies.
        assert r["temperature"] == 0.0

    def test_it_says_so(self, loader, caplog):
        loader(LEGACY)
        assert "declares no 'llm' block" in caplog.text

    def test_generation_settings_are_not_promoted(self, loader):
        assert "temperature" not in loader(LEGACY)["llm"]


class TestMigrationIsNarrow:
    def test_a_declared_llm_block_means_the_operator_migrated(self, loader):
        cfg = loader({"llm": {"model": "chosen"}, "cti": {"model": "stale"}})
        assert cfg["llm"]["model"] == "chosen"

    def test_a_lone_model_is_not_an_endpoint(self, loader):
        # Without an api_base nothing is retargeted, so the allowlist is
        # entitled to drop it and the shipped default stands.
        assert loader({"cti": {"model": "junk"}})["llm"]["model"] == "openai/gpt-oss-120b"

    def test_unrelated_sections_are_not_llm_profiles(self, loader):
        cfg = loader({"mlflow": {"host": "10.0.0.1", "port": 5050}})
        assert cfg["llm"]["model"] == "openai/gpt-oss-120b"
        assert cfg["mlflow"]["host"] == "10.0.0.1"

    def test_api_base_env_also_counts_as_an_endpoint(self, loader):
        cfg = loader({"cti": {"api_base_env": "MY_GATEWAY", "model": "devstral"}})
        assert cfg["llm"]["api_base_env"] == "MY_GATEWAY"
        assert cfg["llm"]["model"] == "devstral"

    def test_a_stock_clone_is_untouched(self, loader):
        assert loader()["llm"]["model"] == "openai/gpt-oss-120b"


class TestSaveReachesTheRunningClient:
    """LLMClient snapshots the config at construction.

    Without dropping the singleton, a Save reached get_llm_provenance, which
    reads fresh, but not generate(), which reads the snapshot: the bundle got
    stamped with a model that did not produce it.
    """

    def test_reload_drops_the_snapshot(self, loader, monkeypatch):
        loader({"llm": {"model": "old", "api_base": "https://gw/v1"}})
        first = llm_client.get_llm_client()
        assert first.cfg["llm"]["model"] == "old"

        loader({"llm": {"model": "new", "api_base": "https://gw/v1"}})
        llm_client.reload_config()

        second = llm_client.get_llm_client()
        assert second is not first
        assert second.cfg["llm"]["model"] == "new"
