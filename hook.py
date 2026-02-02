import os
import subprocess
import socket
import time
import traceback
import logging
import psutil

from app.utility.base_world import BaseWorld

name = 'mcp'
address = '/plugin/mcp/gui'
access = BaseWorld.Access.APP
description = {
    "name": "mcp",
    "version": "1.0.0",
    "author": "MITRE",
    "description": "MCP LLM + RAG plugin",
    "services": ["MCPService"],
}


# Set global logging level
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


# Silence noisy modules
for mod in [
    "LiteLLM",                # LiteLLM main
    "litellm",                # Fallback
    "litellm_logging",        # Specific module if imported
    "httpcore",               # Transport layer
    "httpx",                  # High-level HTTP client
    "urllib3",                # Used by requests
    "openai",                 # If OpenAI SDK is leaking logs
    "asyncio",                # Sometimes prints polling debug
]:
    logging.getLogger(mod).setLevel(logging.WARNING)

def kill_existing_mlflow(port=5000):
    """Find and kill any process listening on the specified port (usually MLflow)."""
    for proc in psutil.process_iter(attrs=["pid", "name"]):
        try:
            connections = proc.connections(kind='inet')
            for conn in connections:
                if conn.status == psutil.CONN_LISTEN and conn.laddr.port == port:
                    print(f"[MCP] Killing existing MLflow process (PID {proc.pid}) on port {port}")
                    proc.kill()
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as e:
            print(f"[MCP] Unexpected error while checking connections: {e}")
            continue

def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(('127.0.0.1', port)) == 0

# 🔁 Start MLflow server if it's not already running
if not is_port_open(5000):
    # 🧼 Kill old MLflow server if it exists
    kill_existing_mlflow(5000)
    try:
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        mlruns_path = os.path.join(plugin_dir, 'mlruns')
        db_path = os.path.join(plugin_dir, 'mlruns.db')
        subprocess.Popen([
            "mlflow", "server",
            "--backend-store-uri", f"sqlite:///{db_path}",
            "--default-artifact-root", mlruns_path,
            "--host", "127.0.0.1",
            "--port", "5000"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.debug("[MCP] Starting MLflow server at http://localhost:5000")
    except Exception as e:
        log.error(f"[MCP] Failed to start MLflow server: {e}")
        traceback.print_exc()
else:
    log.info("[MCP] MLflow server already running on port 5000")

# 💤 Optional: Wait until server is reachable
for i in range(10):
    if is_port_open(5000):
        log.debug("[MCP] MLflow is ready.")
        break
    time.sleep(1)
else:
    log.error("[MCP] MLflow failed to start within 10 seconds.")

# ✅ Now import modules that depend on MLflow
try:
    log.debug("[MCP] Importing MCP plugin modules...")
    from plugins.mcp.app.mcp_svc import MCPService
    from plugins.mcp.app.mcp_gui import McpGUI
    from plugins.mcp.app.mcp_api import McpAPI
    logging.getLogger("litellm_logging").setLevel(logging.ERROR)

except ImportError as e:
    log.error(f"[MCP] Error importing MCP plugin modules: {e}")
    traceback.print_exc()

async def enable(services):
    app = services.get('app_svc').application

    services.get('data_svc').add_service('mcp_svc', MCPService(services))
    mcp_gui = McpGUI(services, name=name, description=description)
    app.router.add_static('/mcp', 'plugins/mcp/static/', append_version=True)
    
    mcp_api = McpAPI(services)
    app.router.add_route('POST', '/plugin/mcp/execute', mcp_api.execute)
    app.router.add_route('GET', '/plugin/mcp/status', mcp_api.status)
    app.router.add_route('GET', '/plugin/mcp/history', mcp_api.list_runs)
    app.router.add_route("GET", "/plugin/mcp/get_config", mcp_api.get_config)
    app.router.add_route("POST", "/plugin/mcp/set_config", mcp_api.set_config)

    
    app.router.add_route('POST', "/plugin/mcp/rag/upload", mcp_api.upload_rag)
    
    app.router.add_route("POST", "/plugin/mcp/stix/upload", mcp_api.upload_stix_cti)
    app.router.add_route("GET", "/plugin/mcp/stix/list", mcp_api.list_stix_cti)
    app.router.add_route("POST", "/plugin/mcp/stix/delete", mcp_api.delete_stix_cti)
    app.router.add_route("POST", "/plugin/mcp/stix/get_stix", mcp_api.get_stix_cti)
    app.router.add_route("POST", "/plugin/mcp/stix/download", mcp_api.download_stix_cti)

    
    app.router.add_route("POST", "/plugin/mcp/cti/upload", mcp_api.upload_cti_raw)
    app.router.add_route("GET", "/plugin/mcp/cti/raw", mcp_api.list_cti_raw)
    app.router.add_route("POST", "/plugin/mcp/cti/raw/delete", mcp_api.delete_cti_raw)
    app.router.add_route("POST", "/plugin/mcp/cti/run", mcp_api.cti_run)
    
