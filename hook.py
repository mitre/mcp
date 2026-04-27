import os
import subprocess
import socket
import time
import traceback
import logging
import psutil

from app.utility.base_world import BaseWorld

name = 'mcp'
description = 'Attachment for Model Context Protocol'
address = '/plugin/mcp/gui'
access = BaseWorld.Access.APP

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
    from plugins.mcp.app.mcp_svc import MCPService
    from plugins.mcp.app.mcp_gui import McpGUI
    from plugins.mcp.app.mcp_api import McpAPI
    from plugins.mcp.app.discovery.servers import discover_mcp_servers
    from plugins.mcp.app.discovery.workflows import discover_workflows
    from plugins.mcp.app.discovery.capabilities import discover_capabilities
    logging.getLogger("litellm_logging").setLevel(logging.ERROR)

except ImportError as e:
    log.error(f"[MCP] Error importing MCP plugin modules: {e}")
    traceback.print_exc()

async def enable(services):
    app = services.get('app_svc').application

    # Discover MCP servers, workflows, and capabilities at boot. Each registry is
    # built once and handed to MCPService; nothing rescans at request time.
    import pathlib
    plugins_root = pathlib.Path(__file__).resolve().parent.parent
    server_registry = discover_mcp_servers(plugins_root)
    workflow_registry = discover_workflows(plugins_root)
    capability_registry = discover_capabilities(plugins_root)
    log.info(f"[MCP] Server registry: {list(server_registry.keys())}")
    log.info(f"[MCP] Workflow registry: {list(workflow_registry.keys())}")
    log.info(f"[MCP] Capability registry: {list(capability_registry.keys())}")

    services.get('data_svc').add_service(
        'mcp_svc', MCPService(
            services,
            server_registry=server_registry,
            workflow_registry=workflow_registry,
            capability_registry=capability_registry,
        )
    )
    mcp_gui = McpGUI(services, name=name, description=description)
    app.router.add_static('/mcp', 'plugins/mcp/static/', append_version=True)

    mcp_api = McpAPI(services)
    app.router.add_route('POST', '/plugin/mcp/execute', mcp_api.execute)
    app.router.add_route('GET', '/plugin/mcp/status', mcp_api.status)
    app.router.add_route('POST', "/plugin/mcp/rag/upload", mcp_api.upload_rag)
    app.router.add_route('GET', "/plugin/mcp/rag/list", mcp_api.list_rag)
    app.router.add_route('GET', '/plugin/mcp/servers', mcp_api.list_servers)
    app.router.add_route('GET', '/plugin/mcp/defaults', mcp_api.defaults)
    app.router.add_route('GET', '/plugin/mcp/history/runs', mcp_api.list_runs)
    app.router.add_route('GET', '/plugin/mcp/history/run', mcp_api.get_run_detail)
