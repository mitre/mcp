import os
import subprocess
import socket
import time
import traceback
import logging
import psutil
from dotenv import load_dotenv

from app.utility.base_world import BaseWorld

# Load the plugin's .env once in the parent process. Every MCP server
# subprocess and DSPy worker spawned later inherits this environment, so
# CORE_CALDERA_API_KEY and MCP_LLM_API_KEY are visible everywhere without
# each child reloading the file itself.
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(_PLUGIN_DIR, '.env'))

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



def is_port_open(port, host='127.0.0.1'):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) == 0

# Resolve MLflow host+port from the plugin's yaml so two Caldera trees
# on the same host (e.g. CalderaVENV on :5000, CalderaDetectionsVENV on
# :5050) don't share an MLflow tracking server and cross-contaminate runs.
from plugins.mcp.app.config import mlflow_settings as _mlflow_settings
_mlflow = _mlflow_settings()
_MLFLOW_HOST = _mlflow['host']
_MLFLOW_PORT = _mlflow['port']
_MLFLOW_URI = _mlflow['tracking_uri']
os.environ.setdefault('MLFLOW_TRACKING_URI', _MLFLOW_URI)

# 🔁 Start MLflow server if it's not already running
if not is_port_open(_MLFLOW_PORT, _MLFLOW_HOST):
    # 🧼 Kill old MLflow server if it exists
    kill_existing_mlflow(_MLFLOW_PORT)
    try:
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        mlruns_path = os.path.join(plugin_dir, 'mlruns')
        db_path = os.path.join(plugin_dir, 'mlruns.db')
        subprocess.Popen([
            "mlflow", "server",
            "--backend-store-uri", f"sqlite:///{db_path}",
            "--default-artifact-root", mlruns_path,
            "--host", _MLFLOW_HOST,
            "--port", str(_MLFLOW_PORT),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.debug(f"[MCP] Starting MLflow server at {_MLFLOW_URI}")
    except Exception as e:
        log.error(f"[MCP] Failed to start MLflow server: {e}")
        traceback.print_exc()
else:
    log.info(f"[MCP] MLflow server already running on {_MLFLOW_HOST}:{_MLFLOW_PORT}")

# 💤 Optional: Wait until server is reachable
for i in range(10):
    if is_port_open(_MLFLOW_PORT, _MLFLOW_HOST):
        log.debug("[MCP] MLflow is ready.")
        break
    time.sleep(1)
else:
    log.error(f"[MCP] MLflow failed to start within 10 seconds on {_MLFLOW_HOST}:{_MLFLOW_PORT}.")

# ✅ Now import modules that depend on MLflow
try:
    from plugins.mcp.app.mcp_svc import MCPService
    from plugins.mcp.app.mcp_gui import McpGUI
    from plugins.mcp.app.mcp_api import McpAPI
    from plugins.mcp.app.discovery.servers import discover_mcp_servers
    from plugins.mcp.app.discovery.workflows import discover_workflows
    from plugins.mcp.app.discovery.capabilities import discover_capabilities
    from plugins.mcp.app.config import caldera_connection
    logging.getLogger("litellm_logging").setLevel(logging.ERROR)

except ImportError as e:
    log.error(f"[MCP] Error importing MCP plugin modules: {e}")
    traceback.print_exc()


def report_caldera_connection():
    """Log the resolved Caldera REST connection, and say so when it won't work.

    A rejected key is otherwise near-undiagnosable: caldera 401s, the tool
    wraps that in a successful result, and the operator sees only a confused
    agent trajectory.
    """
    caldera = caldera_connection()
    if caldera['key_valid'] is False:
        log.warning(
            f"[MCP] Caldera at {caldera['url']} rejects the configured API key. "
            f"Set {caldera['api_key_env']} in plugins/mcp/.env to this server's "
            f"API_TOKEN, printed once in the caldera log when conf/local.yml "
            f"was generated."
        )
    else:
        log.info(f"[MCP] Caldera REST resolved to {caldera['url']}")


async def enable(services):
    app = services.get('app_svc').application

    try:
        report_caldera_connection()
    except Exception as e:
        log.warning(f"[MCP] Could not resolve the Caldera REST connection: {e}")

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

    mcp_svc = MCPService(
        services,
        server_registry=server_registry,
        workflow_registry=workflow_registry,
        capability_registry=capability_registry,
    )
    services.get('data_svc').add_service('mcp_svc', mcp_svc)

    # Runs stranded as RUNNING by a previous process can only be closed out
    # from outside the task that owned them, so it happens here at boot.
    await mcp_svc.reconcile_orphaned_runs()
    mcp_gui = McpGUI(services, name=name, description=description)
    app.router.add_static('/mcp', 'plugins/mcp/static/', append_version=True)
    # Server-rendered landing page. Reports plugin readiness (LLM key,
    # Caldera connection, discovered registries) before the user steps
    # into the Vue workspace.
    app.router.add_route('GET', '/plugin/mcp/gui', mcp_gui.splash)

    mcp_api = McpAPI(services)
    app.router.add_route('POST', '/plugin/mcp/execute', mcp_api.execute)
    app.router.add_route('GET', '/plugin/mcp/status', mcp_api.status)
    app.router.add_route('POST', "/plugin/mcp/rag/upload", mcp_api.upload_rag)
    app.router.add_route('GET', "/plugin/mcp/rag/list", mcp_api.list_rag)
    app.router.add_route('GET', '/plugin/mcp/servers', mcp_api.list_servers)
    app.router.add_route('GET', '/plugin/mcp/workflows', mcp_api.list_workflows)
    app.router.add_route('GET', '/plugin/mcp/capabilities', mcp_api.list_capabilities)
    app.router.add_route('GET', '/plugin/mcp/features', mcp_api.features)
    app.router.add_route('GET', '/plugin/mcp/defaults', mcp_api.defaults)
    app.router.add_route('GET', '/plugin/mcp/history/runs', mcp_api.list_runs)
    app.router.add_route('GET', '/plugin/mcp/history/run', mcp_api.get_run_detail)

    # ===== CTI ingestion endpoints (imported from CTI branch) =====
    # Configuration management for the CTI/LLM pipeline.
    app.router.add_route('GET',  '/plugin/mcp/get_config', mcp_api.get_config)
    app.router.add_route('POST', '/plugin/mcp/set_config', mcp_api.set_config)

    # STIX bundle management.
    app.router.add_route('POST', '/plugin/mcp/stix/upload',   mcp_api.upload_stix_cti)
    app.router.add_route('GET',  '/plugin/mcp/stix/list',     mcp_api.list_stix_cti)
    app.router.add_route('POST', '/plugin/mcp/stix/delete',   mcp_api.delete_stix_cti)
    app.router.add_route('POST', '/plugin/mcp/stix/get_stix', mcp_api.get_stix_cti)
    app.router.add_route('POST', '/plugin/mcp/stix/download', mcp_api.download_stix_cti)

    # Raw CTI text/PDF/HTML ingestion + pipeline driver.
    app.router.add_route('POST', '/plugin/mcp/cti/upload',     mcp_api.upload_cti_raw)
    app.router.add_route('GET',  '/plugin/mcp/cti/raw',        mcp_api.list_cti_raw)
    app.router.add_route('POST', '/plugin/mcp/cti/raw/delete', mcp_api.delete_cti_raw)
    app.router.add_route('POST', '/plugin/mcp/cti/run',        mcp_api.cti_run)

    # AE end-to-end orchestration. Replaces the shell driver as the
    # canonical entry point for the full vision pipeline. See
    # plugins/mcp/app/workflows/ae_e2e.py for the stage list.
    app.router.add_route(
        'POST', '/plugin/mcp/workflows/run-ae-end-to-end',
        mcp_api.run_ae_end_to_end,
    )
