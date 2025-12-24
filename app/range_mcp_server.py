# app/range_mcp_server.py
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
import requests
import collections
from datetime import datetime

mcp = FastMCP("Caldera Range MCP Server")

class RangeRequest:
    def __init__(self, url, api_key):
        self.base_url = url
        self.api_key = api_key
        self.headers = {
            "KEY": self.api_key,
            "Content-Type": "application/json"
        }
        self.total_get_requests = collections.defaultdict(list)
        self.total_post_requests = collections.defaultdict(list)

    def make_get_request(self, endpoint):
        # same structure as CalderaRequest.make_get_request
        ...

    def make_post_request(self, endpoint, body):
        # same structure as CalderaRequest.make_post_request
        ...

range_request = RangeRequest(
    url="http://localhost:8888/api/v2/",   # or plugin-specific base
    api_key="ADMIN123"
)

@mcp.tool()
def list_ranges():
    """List all ranges managed by the Range plugin."""
    return range_request.make_get_request("plugins/range/ranges")

@mcp.tool()
def create_range(name: str, template_id: str, cloud: str):
    """Create a new range using an IaC template."""
    body = {
        "name": name,
        "template": template_id,
        "cloud": cloud
    }
    return range_request.make_post_request("plugins/range/ranges", body)

@mcp.tool()
def deploy_range(range_id: str):
    """Deploy a range."""
    return range_request.make_post_request(f"plugins/range/ranges/{range_id}/deploy", {})
