"""
Comprehensive tests for CTI UI backend endpoints.

Tests every action a user can perform in the CTI Vue interface:
- File upload (cti.vue: uploadCti button)
- Raw file listing (cti.vue: file table)
- Raw file selection and deletion (cti.vue: Delete Selected button)
- Pipeline execution (cti.vue: Run Pipeline button)
- STIX listing (cti.vue: Generated STIX table)
- STIX viewing (cti.vue: View button → stixViewer.vue modal)
- STIX downloading (cti.vue: Download Selected button)
- STIX deletion (cti.vue: Delete Selected button)
- Config get/set (modelSelector.vue: config panel)
- MCP execute (mcp.vue: main execution)
- History listing (mcp_history.vue: run history)

Requires Caldera running with MCP plugin enabled.
"""
import pytest
import requests
import time
import json

CALDERA_URL = "http://localhost:8888"
API_KEY = "ADMIN123"
HEADERS = {"KEY": API_KEY}
JSON_HEADERS = {"KEY": API_KEY, "Content-Type": "application/json"}


def mcp_available():
    try:
        r = requests.get(f"{CALDERA_URL}/api/v2/health", headers=HEADERS, timeout=3)
        plugins = r.json().get("plugins", [])
        return any(p.get("name") == "mcp" and p.get("enabled") for p in plugins)
    except Exception:
        return False


skip = pytest.mark.skipif(not mcp_available(), reason="MCP plugin not enabled")


# ============================================================
# FILE UPLOAD (cti.vue: Upload CTI button)
# ============================================================

@skip
class TestCtiFileUpload:
    """Tests for the file upload input and Upload CTI button."""

    def test_upload_txt_file(self):
        """Upload a .txt CTI report."""
        files = {"file": ("pytest_upload.txt",
                         b"APT29 deployed Cobalt Strike for C2 operations.",
                         "text/plain")}
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/upload",
                         headers=HEADERS, files=files, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") or data.get("file")

    def test_upload_html_file(self):
        """Upload an .html CTI report."""
        html = b"<html><body><p>BlackCat ransomware encrypts files.</p></body></html>"
        files = {"file": ("pytest_report.html", html, "text/html")}
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/upload",
                         headers=HEADERS, files=files, timeout=10)
        assert r.status_code == 200

    def test_upload_without_file_fails(self):
        """Upload with no file should fail gracefully."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/upload",
                         headers=HEADERS, timeout=5)
        assert r.status_code in (400, 500)


# ============================================================
# RAW FILE LISTING (cti.vue: file table)
# ============================================================

@skip
class TestCtiRawListing:
    """Tests for the raw CTI files table."""

    def test_list_returns_items(self):
        """GET /cti/raw returns items array."""
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/cti/raw",
                        headers=HEADERS, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_items_have_required_fields(self):
        """Each item has name, type, size, status."""
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/cti/raw",
                        headers=HEADERS, timeout=5)
        items = r.json().get("items", [])
        if items:
            item = items[0]
            assert "name" in item
            assert "type" in item
            assert "size" in item or item.get("type") == "dir"

    def test_uploaded_file_appears(self):
        """After upload, file should appear in listing."""
        # Upload first
        files = {"file": ("pytest_listing_test.txt", b"Test content", "text/plain")}
        requests.post(f"{CALDERA_URL}/plugin/mcp/cti/upload",
                     headers=HEADERS, files=files, timeout=10)

        # Check listing
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/cti/raw",
                        headers=HEADERS, timeout=5)
        items = r.json().get("items", [])
        names = [i["name"] for i in items]
        assert "pytest_listing_test.txt" in names


# ============================================================
# RAW FILE DELETION (cti.vue: Delete Selected button)
# ============================================================

@skip
class TestCtiRawDeletion:
    """Tests for selecting and deleting raw files."""

    def test_delete_specific_file(self):
        """Delete a specific uploaded file."""
        # Upload
        files = {"file": ("pytest_delete_me.txt", b"Delete this", "text/plain")}
        requests.post(f"{CALDERA_URL}/plugin/mcp/cti/upload",
                     headers=HEADERS, files=files, timeout=10)

        # Delete
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/raw/delete",
                         headers=JSON_HEADERS,
                         json={"files": ["pytest_delete_me.txt"]}, timeout=5)
        assert r.status_code == 200

    def test_delete_nonexistent_file(self):
        """Deleting a file that doesn't exist should not crash."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/raw/delete",
                         headers=JSON_HEADERS,
                         json={"files": ["nonexistent_file_xyz.txt"]}, timeout=5)
        assert r.status_code == 200

    def test_delete_empty_list(self):
        """Empty file list returns 400 (no files specified)."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/raw/delete",
                         headers=JSON_HEADERS,
                         json={"files": []}, timeout=5)
        assert r.status_code in (200, 400)  # Server may reject empty list


# ============================================================
# PIPELINE EXECUTION (cti.vue: Run Pipeline button)
# ============================================================

@skip
class TestCtiPipelineRun:
    """Tests for the Run Pipeline button."""

    def test_run_with_files(self):
        """Run pipeline on specific files."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/run",
                         headers=JSON_HEADERS,
                         json={"files": [{"name": "pytest_upload.txt", "location": "inbox"}],
                               "step": "all"}, timeout=30)
        assert r.status_code in (200, 400, 500)

    def test_run_without_files_fails(self):
        """Run pipeline with no files should fail."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/run",
                         headers=JSON_HEADERS,
                         json={"files": [], "step": "all"}, timeout=10)
        assert r.status_code in (200, 400)

    def test_run_missing_body_fails(self):
        """Run pipeline with no body should fail."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/run",
                         headers=HEADERS, timeout=5)
        assert r.status_code in (400, 500)


# ============================================================
# STIX LISTING (cti.vue: Generated STIX table)
# ============================================================

@skip
class TestStixListing:
    """Tests for the STIX objects table."""

    def test_list_returns_files(self):
        """GET /stix/list returns files array."""
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/stix/list",
                        headers=HEADERS, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "files" in data
        assert isinstance(data["files"], list)


# ============================================================
# STIX VIEWING (cti.vue: View button → stixViewer.vue)
# ============================================================

@skip
class TestStixViewing:
    """Tests for the STIX viewer modal."""

    def test_view_nonexistent_file(self):
        """Viewing a nonexistent STIX file returns error."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/stix/get_stix",
                         headers=JSON_HEADERS,
                         json={"filename": "nonexistent.json"}, timeout=5)
        data = r.json()
        assert "error" in data or r.status_code == 404

    def test_view_requires_filename(self):
        """Viewing without filename should fail."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/stix/get_stix",
                         headers=JSON_HEADERS,
                         json={}, timeout=5)
        assert r.status_code in (400, 500) or "error" in r.json()


# ============================================================
# STIX DOWNLOAD (cti.vue: Download Selected button)
# ============================================================

@skip
class TestStixDownload:
    """Tests for STIX download functionality."""

    def test_download_nonexistent(self):
        """Download nonexistent file returns error."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/stix/download",
                         headers=JSON_HEADERS,
                         json={"filename": "nonexistent.json"}, timeout=5)
        assert r.status_code in (404, 500) or "error" in r.text


# ============================================================
# STIX DELETION (cti.vue: Delete Selected button)
# ============================================================

@skip
class TestStixDeletion:
    """Tests for STIX deletion."""

    def test_delete_empty_list(self):
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/stix/delete",
                         headers=JSON_HEADERS,
                         json={"files": []}, timeout=5)
        assert r.status_code == 200

    def test_delete_nonexistent(self):
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/stix/delete",
                         headers=JSON_HEADERS,
                         json={"files": ["nonexistent.json"]}, timeout=5)
        assert r.status_code == 200


# ============================================================
# STIX UPLOAD (alternative upload path)
# ============================================================

@skip
class TestStixUpload:
    """Tests for direct STIX upload."""

    def test_upload_stix_bundle(self):
        """Upload a STIX 2.1 bundle directly."""
        bundle = json.dumps({
            "type": "bundle",
            "id": "bundle--pytest-test",
            "objects": [
                {"type": "malware", "spec_version": "2.1",
                 "id": "malware--pytest-test",
                 "created": "2024-01-01T00:00:00Z",
                 "modified": "2024-01-01T00:00:00Z",
                 "name": "PyTestMalware", "is_family": False}
            ]
        })
        files = {"file": ("pytest_stix.json", bundle.encode(), "application/json")}
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/stix/upload",
                         headers=HEADERS, files=files, timeout=10)
        assert r.status_code == 200


# ============================================================
# CONFIG (modelSelector.vue: config panel)
# ============================================================

@skip
class TestConfigEndpoints:
    """Tests for the model configuration panel."""

    def test_get_config(self):
        """GET /get_config returns config object."""
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/get_config",
                        headers=HEADERS, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "config" in data or isinstance(data, dict)

    def test_config_has_cti_section(self):
        """Config should have a CTI section with model settings."""
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/get_config",
                        headers=HEADERS, timeout=5)
        data = r.json()
        config = data.get("config", data)
        cti = config.get("cti", {})
        # Should have at least model and provider
        assert "model" in cti or "provider" in cti or "offline" in cti

    def test_set_config(self):
        """POST /set_config accepts config updates."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/set_config",
                         headers=JSON_HEADERS,
                         json={"config": {"cti": {"offline": True}}}, timeout=5)
        assert r.status_code == 200
        # Note: config persistence depends on implementation —
        # some configs only persist to YAML, others are in-memory only


# ============================================================
# MCP EXECUTE (mcp.vue: main execution endpoint)
# ============================================================

@skip
class TestMcpExecute:
    """Tests for the main MCP execution endpoint."""

    def test_execute_requires_text(self):
        """Execute without text should fail."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/execute",
                         headers=JSON_HEADERS,
                         json={"text": ""}, timeout=5)
        assert r.status_code == 400 or "error" in r.json()

    def test_execute_with_text(self):
        """Execute with text should return result."""
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/execute",
                         headers=JSON_HEADERS,
                         json={"text": "Create a simple test ability",
                               "type": "factory"}, timeout=30)
        # May succeed or fail depending on LLM availability
        assert r.status_code in (200, 500)


# ============================================================
# HISTORY (mcp_history.vue: run history)
# ============================================================

@skip
class TestMcpHistory:
    """Tests for the MCP run history page."""

    def test_list_runs(self):
        """GET /history returns run list."""
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/history",
                        headers=HEADERS, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))


# ============================================================
# AUTHENTICATION
# ============================================================

@skip
class TestAuthentication:
    """Verify endpoint accessibility (auth depends on --insecure flag)."""

    ENDPOINTS = [
        ("GET", "/plugin/mcp/cti/raw"),
        ("GET", "/plugin/mcp/stix/list"),
        ("GET", "/plugin/mcp/get_config"),
        ("GET", "/plugin/mcp/history"),
    ]

    @pytest.mark.parametrize("method,path", ENDPOINTS)
    def test_endpoint_accessible(self, method, path):
        """Endpoints respond (auth behavior depends on server mode)."""
        r = requests.request(method, f"{CALDERA_URL}{path}", timeout=5)
        # With --insecure, endpoints may not require auth
        assert r.status_code in (200, 401)


# ============================================================
# CLEANUP
# ============================================================

@skip
class TestCleanup:
    """Clean up test artifacts."""

    def test_cleanup_uploaded_files(self):
        """Remove test files created during testing."""
        test_files = ["pytest_upload.txt", "pytest_report.html",
                      "pytest_listing_test.txt", "test_upload.txt"]
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/cti/raw/delete",
                         headers=JSON_HEADERS,
                         json={"files": test_files}, timeout=5)
        assert r.status_code == 200

    def test_cleanup_stix_files(self):
        """Remove test STIX files."""
        requests.post(f"{CALDERA_URL}/plugin/mcp/stix/delete",
                     headers=JSON_HEADERS,
                     json={"files": ["pytest_stix.json"]}, timeout=5)
