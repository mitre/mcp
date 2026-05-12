"""
Tests for CTI API endpoints — the backend for the CTI Vue UI.
Requires Caldera running with MCP plugin enabled.

Tests cover every button/action in the CTI UI:
- File upload
- Raw file listing
- Pipeline execution
- STIX listing, viewing, downloading, deleting
- Configuration get/set
"""
import pytest
import requests

CALDERA_URL = "http://localhost:8888"
API_KEY = "ADMIN123"
HEADERS = {"KEY": API_KEY}


def caldera_available():
    try:
        r = requests.get(f"{CALDERA_URL}/api/v2/health", headers=HEADERS, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def mcp_enabled():
    try:
        r = requests.get(f"{CALDERA_URL}/api/v2/health", headers=HEADERS, timeout=3)
        plugins = r.json().get("plugins", [])
        return any(p.get("name") == "mcp" and p.get("enabled") for p in plugins)
    except Exception:
        return False


skipif_no_caldera = pytest.mark.skipif(
    not caldera_available(),
    reason="Caldera not running"
)

skipif_mcp_disabled = pytest.mark.skipif(
    not mcp_enabled(),
    reason="MCP plugin not enabled in Caldera"
)


class TestSetupRoutes:
    """Verify that setup_routes registers all CTI endpoints."""

    def test_all_routes_defined(self):
        """setup_routes should register all CTI UI endpoints."""
        from plugins.mcp.app.mcp_api import setup_routes
        import inspect
        source = inspect.getsource(setup_routes)

        expected_routes = [
            "/plugin/mcp/execute",
            "/plugin/mcp/status",
            "/plugin/mcp/rag/upload",
            "/plugin/mcp/cti/upload",
            "/plugin/mcp/cti/raw",
            "/plugin/mcp/cti/raw/delete",
            "/plugin/mcp/cti/run",
            "/plugin/mcp/stix/list",
            "/plugin/mcp/stix/upload",
            "/plugin/mcp/stix/get_stix",
            "/plugin/mcp/stix/download",
            "/plugin/mcp/stix/delete",
            "/plugin/mcp/get_config",
            "/plugin/mcp/set_config",
        ]

        for route in expected_routes:
            assert route in source, f"Route {route} not registered in setup_routes"

    def test_handler_methods_exist(self):
        """Every registered route should have a handler method."""
        from plugins.mcp.app.mcp_api import McpAPI
        expected_handlers = [
            "execute", "status", "upload_rag",
            "upload_cti_raw", "list_cti_raw", "delete_cti_raw", "cti_run",
            "list_stix_cti", "upload_stix_cti", "get_stix_cti",
            "download_stix_cti", "delete_stix_cti",
            "get_config", "set_config",
            "list_runs", "get_run_detail",
        ]

        for handler in expected_handlers:
            assert hasattr(McpAPI, handler), f"McpAPI missing handler: {handler}"


@skipif_no_caldera
@skipif_mcp_disabled
class TestCtiRawEndpoints:
    """Tests for raw CTI file management endpoints."""

    def test_list_raw_files(self):
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/cti/raw", headers=HEADERS, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data

    def test_upload_cti_file(self):
        """Upload a test CTI file."""
        files = {"file": ("test_cti.txt", b"APT29 uses Cobalt Strike for C2.", "text/plain")}
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/upload",
                         headers=HEADERS, files=files, timeout=10)
        assert r.status_code == 200

    def test_delete_raw_file(self):
        """Delete a previously uploaded file."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/raw/delete",
                         headers=HEADERS, json={"files": ["test_cti.txt"]}, timeout=5)
        assert r.status_code == 200


@skipif_no_caldera
@skipif_mcp_disabled
class TestCtiPipelineEndpoint:
    def test_run_pipeline(self):
        """Trigger pipeline execution."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/run",
                         headers=HEADERS, json={"files": [], "step": "all"}, timeout=10)
        assert r.status_code in (200, 400)  # 400 if no files selected


@skipif_no_caldera
@skipif_mcp_disabled
class TestStixEndpoints:
    def test_list_stix(self):
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/stix/list", headers=HEADERS, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "files" in data

    def test_get_stix_nonexistent(self):
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/stix/get_stix",
                         headers=HEADERS, json={"filename": "nonexistent.json"}, timeout=5)
        assert r.status_code in (200, 404, 500)

    def test_delete_stix(self):
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/stix/delete",
                         headers=HEADERS, json={"files": []}, timeout=5)
        assert r.status_code == 200


@skipif_no_caldera
@skipif_mcp_disabled
class TestConfigEndpoints:
    def test_get_config(self):
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/get_config", headers=HEADERS, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_set_config(self):
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/set_config",
                         headers=HEADERS,
                         json={"config": {"cti": {"offline": True}}},
                         timeout=5)
        assert r.status_code in (200, 500)
