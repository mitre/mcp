import atexit
import json
import os
import subprocess
import socket
import sys
import time
import traceback
import logging
import urllib.error
import urllib.request

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

# This tree's tracking store. The artifact root doubles as the fingerprint
# that tells our own server apart from another tree's on the same port.
_MLFLOW_BACKEND_URI = f"sqlite:///{os.path.join(_PLUGIN_DIR, 'mlruns.db')}"
_MLFLOW_ARTIFACT_ROOT = os.path.join(_PLUGIN_DIR, 'mlruns')

# Only set when this process started MLflow, so shutdown never kills a server
# the operator is running themselves.
_mlflow_proc = None


def _stop_mlflow_server():
    if _mlflow_proc is None or _mlflow_proc.poll() is not None:
        return
    log.info("[MCP] Stopping the MLflow server this process started")
    _mlflow_proc.terminate()
    try:
        _mlflow_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _mlflow_proc.kill()


def _probe_listener(timeout=2):
    """The artifact root of the server on our port, or None if not MLflow.

    A TCP connect only proves something answers. Adopting a listener that
    is not MLflow -- macOS binds :5000 to AirPlay Receiver -- makes every
    create_run fail with a 403 the operator only sees as a dead run.
    Returns "" when it answers the tracking API but names no root.
    """
    url = f"{_MLFLOW_URI}/api/2.0/mlflow/experiments/get?experiment_id=0"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as e:
        # A deleted default experiment still answers with an MLflow error body.
        body = e.read()
    except Exception:
        return None
    try:
        payload = json.loads(body.decode())
    except Exception:
        return None
    if "experiment" not in payload and "error_code" not in payload:
        return None
    return str((payload.get("experiment") or {}).get("artifact_location") or "")


def _serves_our_store(artifact_root):
    """Whether that artifact root is this tree's, so the server is ours."""
    if not artifact_root:
        return False
    path = artifact_root.split("://", 1)[-1]
    try:
        root = os.path.realpath(_MLFLOW_ARTIFACT_ROOT)
        return os.path.realpath(path).startswith(root + os.sep)
    except Exception:
        return False


def _mlflow_server_port(cmdline):
    """The port an ``mlflow server``/``mlflow ui`` argv serves, else None."""
    if not any("mlflow" in part for part in cmdline):
        return None
    if "server" not in cmdline and "ui" not in cmdline:
        return None
    if "--port" in cmdline:
        try:
            return int(cmdline[cmdline.index("--port") + 1])
        except (IndexError, ValueError):
            return None
    return 5000  # mlflow's own default when the flag is absent


def _reclaim_port():
    """Stop the foreign MLflow on our port, returning whether it freed.

    Only an mlflow server bound to our port is a candidate. macOS denies
    a port-to-pid lookup without root, so the owner is found by cmdline.
    """
    victims = []
    for proc in psutil.process_iter(["cmdline"]):
        try:
            if _mlflow_server_port(proc.info.get("cmdline") or []) == _MLFLOW_PORT:
                victims.append(proc)
        except psutil.Error:
            continue
    for proc in victims:
        # The CLI parent forks uvicorn workers that hold the socket, so
        # terminating it alone leaves the port bound.
        try:
            targets = proc.children(recursive=True) + [proc]
            for target in targets:
                target.terminate()
            _, alive = psutil.wait_procs(targets, timeout=5)
            for target in alive:
                target.kill()
        except psutil.Error as e:
            log.warning(f"[MCP] Could not stop MLflow pid {proc.pid}: {e}")

    for _ in range(10):
        if not is_port_open(_MLFLOW_PORT, _MLFLOW_HOST):
            return True
        time.sleep(0.5)
    return False


def _start_mlflow_server():
    global _mlflow_proc
    try:
        # The interpreter running caldera, not a bare "mlflow": restarting a
        # reclaimed server is now a normal path, and PATH may not carry the
        # venv that holds the mlflow client this process imports.
        _mlflow_proc = subprocess.Popen([
            sys.executable, "-m", "mlflow", "server",
            "--backend-store-uri", _MLFLOW_BACKEND_URI,
            "--default-artifact-root", _MLFLOW_ARTIFACT_ROOT,
            "--host", _MLFLOW_HOST,
            "--port", str(_MLFLOW_PORT),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Caldera has no plugin teardown hook, so without this the server is
        # reparented to init and outlives every restart.
        atexit.register(_stop_mlflow_server)
        log.debug(f"[MCP] Starting MLflow server at {_MLFLOW_URI}")
    except Exception as e:
        log.error(f"[MCP] Failed to start MLflow server: {e}")
        traceback.print_exc()
        return

    for _ in range(10):
        if is_port_open(_MLFLOW_PORT, _MLFLOW_HOST):
            log.debug("[MCP] MLflow is ready.")
            return
        time.sleep(1)
    log.error(f"[MCP] MLflow did not start within 10s on {_MLFLOW_HOST}:{_MLFLOW_PORT}.")


# Started from enable(), not at import: this spawns a process and blocks for
# up to 10s, and importing the module should do neither.
def _ensure_mlflow_server():
    if is_port_open(_MLFLOW_PORT, _MLFLOW_HOST):
        artifact_root = _probe_listener()
        if artifact_root is None:
            log.error(
                f"[MCP] {_MLFLOW_HOST}:{_MLFLOW_PORT} is held by something that is "
                f"not MLflow, so every run will fail to start. Free the port, or "
                f"set mlflow.port in plugins/mcp/conf/default.yml."
            )
            return
        if _serves_our_store(artifact_root):
            log.info(f"[MCP] MLflow already running on {_MLFLOW_HOST}:{_MLFLOW_PORT}")
            return
        # Sharing another tree's store crosses both trees' history, and the
        # boot reconcile then marks that tree's live runs KILLED.
        log.warning(
            f"[MCP] The MLflow server on {_MLFLOW_HOST}:{_MLFLOW_PORT} tracks "
            f"{artifact_root or 'an unknown store'}, not {_MLFLOW_ARTIFACT_ROOT}. "
            f"Restarting it against this tree's store."
        )
        if not _reclaim_port():
            log.error(
                f"[MCP] Could not free {_MLFLOW_HOST}:{_MLFLOW_PORT}. Runs would land "
                f"in another tree's store, so that server is left alone and runs will "
                f"fail. Stop it, or set mlflow.port in plugins/mcp/conf/default.yml."
            )
            return
    _start_mlflow_server()


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

    _ensure_mlflow_server()

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
    app.router.add_route('POST', '/plugin/mcp/cancel', mcp_api.cancel)
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
    app.router.add_route('POST', '/plugin/mcp/cti/raw/view',   mcp_api.view_cti_raw)
    app.router.add_route('POST', '/plugin/mcp/cti/run',        mcp_api.cti_run)
    app.router.add_route('GET',  '/plugin/mcp/cti/status',     mcp_api.cti_status)
