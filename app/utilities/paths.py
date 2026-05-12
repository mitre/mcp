from pathlib import Path

def get_mcp_root() -> Path:
    # plugins/mcp
    return Path(__file__).resolve().parents[2]

def get_mcp_data_dir() -> Path:
    return get_mcp_root() / "data"
