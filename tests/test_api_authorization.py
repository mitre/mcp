"""Every McpAPI route must require authorization.

Caldera gates plugin routes per handler rather than with a middleware:
auth_svc.apply installs only the session and security machinery, and
check_authorization is what calls check_permissions. A route registered
without the decorator is reachable unauthenticated.
"""
import inspect

from plugins.mcp.app.mcp_api import McpAPI


def _public_methods():
    return {
        name: fn
        for name, fn in inspect.getmembers(McpAPI, inspect.isfunction)
        if not name.startswith("_")
    }


class TestEveryRouteIsAuthorized:
    def test_all_public_methods_are_wrapped(self):
        """for_all_public_methods replaces each public method with the
        check_authorization helper closure."""
        unwrapped = [
            name for name, fn in _public_methods().items()
            if fn.__name__ != "helper"
        ]
        assert not unwrapped, f"unauthorized routes: {sorted(unwrapped)}"

    def test_the_class_is_decorated_at_all(self):
        """Guards against someone removing the decorator wholesale, which
        would leave every method unwrapped and the test above vacuous."""
        assert _public_methods(), "McpAPI exposes no public methods"
        assert any(fn.__name__ == "helper" for fn in _public_methods().values())

    def test_auth_svc_is_available_to_the_decorator(self):
        """check_authorization reads self.auth_svc; without it every request
        raises AttributeError instead of being checked."""
        src = inspect.getsource(McpAPI.__init__)
        assert "self.auth_svc" in src
