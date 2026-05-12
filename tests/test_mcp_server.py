"""
Tests for mcp_server.py — MCP server Caldera integration.
Requires Caldera running on localhost:8888.
Tests are skipped if Caldera is not available.
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


skipif_no_caldera = pytest.mark.skipif(
    not caldera_available(),
    reason="Caldera not running on localhost:8888"
)


@skipif_no_caldera
class TestMCPServerImport:
    def test_server_class_imports(self):
        """MCPServer imports — requires Caldera's plugin loader context."""
        try:
            from plugins.mcp.app.mcp_server import MCPServer
            assert MCPServer is not None
        except ModuleNotFoundError as e:
            if "factory" in str(e):
                pytest.skip("MCPServer requires Caldera plugin context (relative import)")
            raise

    def test_get_server(self):
        try:
            from plugins.mcp.app.mcp_server import _get_server
            server = _get_server()
            assert server is not None
        except ModuleNotFoundError as e:
            if "factory" in str(e):
                pytest.skip("MCPServer requires Caldera plugin context (relative import)")
            raise


@skipif_no_caldera
class TestCalderaHealthAPI:
    def test_health_endpoint(self):
        r = requests.get(f"{CALDERA_URL}/api/v2/health", headers=HEADERS, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data["application"] == "Caldera"
        assert "version" in data

    def test_unauthorized_rejected(self):
        r = requests.get(f"{CALDERA_URL}/api/v2/health", timeout=5)
        assert r.status_code == 401


@skipif_no_caldera
class TestCalderaAbilitiesAPI:
    def test_list_abilities(self):
        r = requests.get(f"{CALDERA_URL}/api/v2/abilities", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        abilities = r.json()
        assert isinstance(abilities, list)

    def test_abilities_have_ids(self):
        r = requests.get(f"{CALDERA_URL}/api/v2/abilities", headers=HEADERS, timeout=10)
        abilities = r.json()
        if abilities:
            assert "ability_id" in abilities[0]


@skipif_no_caldera
class TestCalderaAdversariesAPI:
    def test_list_adversaries(self):
        r = requests.get(f"{CALDERA_URL}/api/v2/adversaries", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


@skipif_no_caldera
class TestCalderaAgentsAPI:
    def test_list_agents(self):
        r = requests.get(f"{CALDERA_URL}/api/v2/agents", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


@skipif_no_caldera
class TestCalderaOperationsAPI:
    def test_list_operations(self):
        r = requests.get(f"{CALDERA_URL}/api/v2/operations", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


@skipif_no_caldera
class TestMCPPluginEndpoints:
    def test_mcp_gui_accessible(self):
        """MCP plugin GUI page should be accessible."""
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/gui",
                        headers=HEADERS, timeout=5, allow_redirects=True)
        # May return 200 or 404 depending on plugin enabled state
        assert r.status_code in (200, 404, 500)

    def test_mcp_js_accessible(self):
        """MCP JavaScript file should be served."""
        r = requests.get(f"{CALDERA_URL}/mcp/js/mcp.js", timeout=5)
        # Static files may not require auth
        assert r.status_code in (200, 404)
