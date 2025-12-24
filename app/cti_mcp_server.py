# plugins/mcp/app/cti_mcp_server.py
import os
import json
import uuid
import requests
from datetime import datetime
from typing import List, Dict

from mcp.server.fastmcp import FastMCP
from app.utility.base_world import BaseWorld

mcp = FastMCP("CTI → STIX MCP Server")

def _load_cti_config():
    cfg = BaseWorld.strip_yml('plugins/mcp/conf/default.yml')[0]
    cti = cfg.get('cti', {})
    cti.setdefault('stix_dir', 'plugins/mcp/data/stix_cti')
    return cti

CTI_CONFIG = _load_cti_config()
STIX_DIR = CTI_CONFIG['stix_dir']
os.makedirs(STIX_DIR, exist_ok=True)

def _ollama_generate(prompt: str) -> str:
    """Call the CTI LLM (via Ollama) to get a response string."""
    model = CTI_CONFIG.get("model", "ollama/gemma3n:latest").split("/", 1)[-1]
    api_base = CTI_CONFIG.get("api_base", "http://127.0.0.1:11434")
    url = f"{api_base}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": CTI_CONFIG.get("temperature", 0.1)
        },
    }
    r = requests.post(url, json=payload, timeout=600)
    r.raise_for_status()
    data = r.json()
    # Ollama returns { "response": "...", ... }
    return data.get("response", "")

def _cti_to_stix(cti_text: str) -> Dict:
    """Use the LLM to convert CTI text → STIX 2.1 bundle (dict)."""
    prompt = f"""
You are a cyber threat intelligence (CTI) to STIX 2.1 converter.

Input: raw CTI report text.

Output: a single valid STIX 2.1 bundle in JSON with:
- "type": "bundle"
- "id": "bundle--<uuid4>"
- "objects": list of STIX 2.1 objects such as:
  - intrusion-set, threat-actor, malware, tool, campaign, vulnerability,
    indicator, attack-pattern, relationship, report

Rules:
- Only output JSON (no explanation, no markdown).
- Use proper STIX 2.1 types and IDs: e.g. "indicator--<uuid4>".
- Link entities with "relationship" objects where appropriate.

CTI REPORT:
\"\"\"{cti_text}\"\"\"
"""
    raw = _ollama_generate(prompt).strip()
    # Best-effort JSON cleanup
    try:
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
        bundle = json.loads(raw)
    except Exception:
        # Wrap raw text if model did not behave:
        bundle = {
            "type": "bundle",
            "id": f"bundle--{uuid.uuid4()}",
            "objects": [
                {
                    "type": "note",
                    "id": f"note--{uuid.uuid4()}",
                    "abstract": "LLM produced non-JSON output; stored as note.",
                    "content": raw,
                }
            ],
        }
    return bundle

@mcp.tool()
def upload_cti_text(filename: str, content: str) -> Dict:
    """
    Upload a CTI document as plain text and convert it to a STIX 2.1 bundle.

    Args:
      filename: logical name for this CTI file (e.g. 'report1.txt').
      content:  raw CTI text.

    Returns:
      {
        "bundle_id": "<uuid>",
        "stix_path": "plugins/mcp/data/stix_cti/<bundle_id>.json"
      }
    """
    bundle_id = str(uuid.uuid4())
    bundle = _cti_to_stix(content)
    bundle["id"] = f"bundle--{bundle_id}"

    stix_path = os.path.join(STIX_DIR, f"{bundle_id}.json")
    with open(stix_path, "w") as f:
        json.dump(bundle, f, indent=2)

    return {
        "bundle_id": bundle_id,
        "stix_path": stix_path,
        "created": datetime.utcnow().isoformat() + "Z",
        "filename": filename,
    }

@mcp.tool()
def list_stix_bundles() -> List[Dict]:
    """
    List all STIX bundles created by this CTI MCP.
    """
    out = []
    for fn in os.listdir(STIX_DIR):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(STIX_DIR, fn)
        bundle_id = fn[:-5]
        out.append({
            "bundle_id": bundle_id,
            "stix_path": path,
        })
    return out

@mcp.tool()
def get_stix_bundle(bundle_id: str) -> Dict:
    """
    Get a STIX bundle by bundle_id.
    """
    path = os.path.join(STIX_DIR, f"{bundle_id}.json")
    if not os.path.exists(path):
        return {"error": f"Bundle {bundle_id} not found"}
    with open(path, "r") as f:
        return json.load(f)

if __name__ == "__main__":
    mcp.run()
