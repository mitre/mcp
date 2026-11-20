"""enable() must wire every route to an authorized handler.

Nothing else calls enable(): the unit suites build McpAPI and MCPService
directly, so a name missing from hook.py, or a handler registered without
authorization, only showed up when the server booted.
"""
import asyncio
import inspect
from pathlib import Path

import pytest
from aiohttp import web

from plugins.mcp import hook
from plugins.mcp.app.mcp_api import McpAPI


class _DataSvc:
    def __init__(self, services):
        self._services = services

    def add_service(self, name, svc):
        self._services[name] = svc


@pytest.fixture
def routes(monkeypatch):
    """Run enable() against a bare aiohttp app and return its mcp routes."""
    async def _no_tracking(mcp_svc):
        return None
    # enable() mounts 'plugins/mcp/static/' relative to the caldera root, the
    # cwd a real server runs from.
    monkeypatch.chdir(Path(__file__).resolve().parents[3])

    # The real task probes the MLflow port and may spawn a server.
    monkeypatch.setattr(hook, "_bring_up_tracking", _no_tracking)

    app = web.Application()
    services = {"auth_svc": None, "file_svc": None}
    services["app_svc"] = type("AppSvc", (), {"application": app})()
    services["data_svc"] = _DataSvc(services)

    async def _enable():
        await hook.enable(services)
        # Let the scheduled tracking task finish before the loop closes.
        await asyncio.sleep(0)

    asyncio.run(_enable())

    return {
        route.resource.canonical: route.handler
        for route in app.router.routes()
        if route.resource.canonical.startswith("/plugin/mcp/")
    }


def test_enable_registers_the_service_and_its_routes(routes):
    assert "/plugin/mcp/execute" in routes
    assert "/plugin/mcp/gui" in routes


def test_every_registered_handler_is_authorized(routes):
    """check_authorization replaces each handler with its helper closure."""
    unauthorized = sorted(
        path for path, handler in routes.items() if handler.__name__ != "helper"
    )
    assert not unauthorized, f"routes registered without authorization: {unauthorized}"


def test_every_api_handler_is_reachable(routes):
    """A public McpAPI method with no route is a handler nobody can call."""
    registered = {
        handler.__self__.__class__.__name__ + "." + name
        for handler in routes.values()
        for name, member in inspect.getmembers(handler.__self__)
        if getattr(member, "__func__", None) is getattr(handler, "__func__", object())
    }
    public = {
        f"McpAPI.{name}"
        for name, fn in inspect.getmembers(McpAPI, inspect.isfunction)
        if not name.startswith("_")
    }
    missing = sorted(public - registered)
    assert not missing, f"handlers with no route: {missing}"
