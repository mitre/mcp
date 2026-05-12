"""Optional LLM refinement pass for CTI topology extraction."""

from __future__ import annotations

import json
import re
from typing import Any


def _compact_topology(topology: dict) -> dict:
    return {
        "hosts": [
            {
                "name": h.get("name"),
                "role": h.get("role"),
                "platform": h.get("platform"),
                "services": h.get("services") or [],
                "software_required": h.get("software_required") or [],
            }
            for h in topology.get("hosts") or []
        ],
        "users": [
            {
                "username": u.get("username"),
                "domain": u.get("domain"),
                "privilege": u.get("privilege"),
            }
            for u in topology.get("user_accounts") or []
        ],
        "networks": topology.get("networks") or [],
        "attack_surface": topology.get("attack_surface") or {},
    }


def _extract_json_array(text: str) -> list[dict]:
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
        if isinstance(parsed, dict):
            vals = parsed.get("candidate_additions") or parsed.get("candidates")
            if isinstance(vals, list):
                return [x for x in vals if isinstance(x, dict)]
    except Exception:
        pass
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        parsed = json.loads(m.group(0))
    except Exception:
        return []
    return [x for x in parsed if isinstance(x, dict)] if isinstance(parsed, list) else []


async def refine_topology_with_dspy_react(raw_report: str, topology: dict,
                                          *, profile: str = "llm") -> dict[str, Any]:
    """
    Ask DSPy ReAct for implied-but-missing topology candidates with
    cite-back. Returns a skipped result when the configured LLM profile is
    offline/mock/unavailable.
    """
    try:
        import dspy
        from plugins.mcp.app.dspy_runner import safe_react_acall
        from plugins.mcp.app.utilities.llm_client import build_dspy_lm
    except Exception as e:
        return {
            "candidate_additions": [],
            "skipped": True,
            "reason": f"DSPy unavailable: {e}",
        }

    class CTITopologyRefiner(dspy.Signature):
        """Given extracted topology and the original CTI report, identify
        infrastructure elements that are implied but missing. Every
        candidate must cite the exact report sentence that justifies it.
        Return JSON only: [{"kind": "host|service|software|user|edge",
        "value": {...}, "confidence": 0.0-1.0, "citation": "..."}].
        """

        raw_report: str = dspy.InputField()
        extracted_topology: str = dspy.InputField()
        candidate_additions: str = dspy.OutputField()

    try:
        lm = build_dspy_lm(profile)
        react = dspy.ReAct(CTITopologyRefiner, tools=[], max_iters=1)
        with dspy.context(lm=lm):
            pred = await safe_react_acall(
                react,
                raw_report=raw_report[:24000],
                extracted_topology=json.dumps(_compact_topology(topology), default=str),
            )
    except Exception as e:
        return {
            "candidate_additions": [],
            "skipped": True,
            "reason": f"LLM refinement skipped: {e}",
        }

    text = getattr(pred, "candidate_additions", "") or getattr(pred, "process_result", "")
    candidates = _extract_json_array(text)
    return {
        "candidate_additions": candidates,
        "skipped": False,
        "reason": None,
    }
