#!/usr/bin/env python3
"""
Phase 3 — Infrastructure Reasoning (LLM-Assisted, Analyst-Grade)

This stage performs NO extraction and NO deterministic inference.

It derives *required or implied infrastructure* by reasoning over
already-extracted, defensible CTI facts from Stage 2 STIX.

Key Properties:
- Non-brittle
- RAG-safe
- Merge-safe
- Auditable
- Analyst-aligned

Infrastructure is emitted as HYPOTHESES, not asserted facts.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List

from plugins.mcp.app.utilities.cti_stix_builders import new_stix_id, now
from plugins.mcp.app.utilities.llm_client import llm_generate
from plugins.mcp.app.utilities.cti_infra_aggregation import aggregate_infrastructure_hypotheses


# ============================================================
# STAGE 3 OUTPUT OBJECT (AUTHORITATIVE SCHEMA)
# ============================================================

INFRA_REASONING_OBJECT_TYPE = "x-cti-infrastructure-reasoning"

ALLOWED_INFRA_CATEGORIES = {
    "service",
    "server",
    "client",
    "proxy",
    "credential",
    "network",
}


# ============================================================
# PUBLIC ENTRYPOINT
# ============================================================

def run_phase3_infrastructure(
    base_dir: Path,
    *,
    use_llm: bool = True,
):
    """
    Entry point for Phase 3.

    For each outputs_stix/*.stix.json:
      - load finalized STIX
      - load cleaned source text
      - infer infrastructure hypotheses (LLM reasoning)
      - write outputs_stix/infra/<stem>.infra.stix.json

    This stage NEVER mutates the original STIX bundle.
    """

    outputs_stix = base_dir / "outputs_stix"
    clean_dir = base_dir / "clean"
    out_dir = outputs_stix / "infra"

    out_dir.mkdir(parents=True, exist_ok=True)

    stix_files = sorted(p for p in outputs_stix.glob("*.stix.json") if p.is_file())

    if not stix_files:
        print("[STAGE3][INFRA] No STIX files found")
        return

    for stix_path in stix_files:
        stem = stix_path.stem.replace(".stix", "")
        clean_path = clean_dir / f"{stem}.txt"

        if not clean_path.exists():
            print(f"[STAGE3][INFRA] SKIP (no clean text): {stem}")
            continue

        bundle = json.loads(stix_path.read_text(encoding="utf-8"))
        clean_text = clean_path.read_text(encoding="utf-8", errors="ignore")

        infra_obj = infer_infrastructure_reasoning(
            bundle=bundle,
            clean_text=clean_text,
            source_stix_file=stix_path.name,
            use_llm=use_llm,
        )

        out_bundle = {
            "type": "bundle",
            "id": new_stix_id("bundle"),
            "objects": [infra_obj],
        }

        out_path = out_dir / f"{stem}.infra.stix.json"
        out_path.write_text(
            json.dumps(out_bundle, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(
            f"[STAGE3][INFRA] {stem}: "
            f"hypotheses={len(infra_obj.get('x_infrastructure_hypotheses', []))}"
        )
        agg = aggregate_infrastructure_hypotheses(out_dir)

        agg_path = out_dir / "_aggregated.infrastructure.json"
        agg_path.write_text(
            json.dumps(agg, indent=2, ensure_ascii=False)
        )

        print(
            f"[STAGE3][INFRA] Aggregated components={len(agg)} "
            f"→ {agg_path.name}"
        )


# ============================================================
# FACT EXTRACTION (NO INFERENCE HERE)
# ============================================================

def extract_reasoning_facts(bundle: dict) -> Dict[str, List[dict]]:
    """
    Extract ONLY defensible, analyst-grade facts from STIX.
    No inference. No guessing.
    """

    facts = {
        "relationships": [],
        "behaviors": [],
        "techniques": [],
        "threat_actors": [],
    }

    for obj in bundle.get("objects", []):
        otype = obj.get("type")

        if otype == "relationship":
            facts["relationships"].append({
                "source_ref": obj.get("source_ref"),
                "relationship": obj.get("relationship_type"),
                "target_ref": obj.get("target_ref"),
                "confidence": obj.get("confidence"),
                "evidence": obj.get("evidence"),
            })

        elif otype == "observed-data":
            obs = obj.get("objects", {}).get("0", {})
            if obs:
                facts["behaviors"].append({
                    "behavior": obs.get("x_behavior"),
                    "confidence": obj.get("x_cti_confidence"),
                    "evidence": obj.get("x_cti_evidence"),
                })

        elif otype == "attack-pattern":
            facts["techniques"].append({
                "id": (
                    obj.get("external_references", [{}])[0]
                    .get("external_id")
                ),
                "name": obj.get("name"),
            })

        elif otype == "threat-actor":
            facts["threat_actors"].append({
                "id": obj.get("id"),
                "name": obj.get("name"),
            })

    return facts


# ============================================================
# CORE REASONING LOGIC
# ============================================================

def infer_infrastructure_reasoning(
        *,
        bundle: dict,
        clean_text: str,
        source_stix_file: str,
        use_llm: bool,
    ) -> dict:
    """
    Produce a single infrastructure reasoning object.
    """

    facts = extract_reasoning_facts(bundle)
    actor_ids = [a["id"] for a in facts["threat_actors"] if a.get("id")]

    hypotheses: List[dict] = []

    if use_llm:
        hypotheses = run_llm_infrastructure_reasoning(
            facts=facts,
            clean_text=clean_text,
        )

    return {
        "type": INFRA_REASONING_OBJECT_TYPE,
        "spec_version": "2.1",
        "id": new_stix_id(INFRA_REASONING_OBJECT_TYPE),
        "created": now(),
        "modified": now(),
        "x_derived_from_stix": source_stix_file,
        "x_attributed_to": actor_ids,
        "x_infrastructure_hypotheses": hypotheses,
    }


# ============================================================
# LLM-ASSISTED REASONING (BOUNDED + SAFE)
# ============================================================

def run_llm_infrastructure_reasoning(
        *,
        facts: dict,
        clean_text: str,
    ) -> List[dict]:
    """
    Ask the LLM to reason about *required infrastructure*,
    not to extract or invent facts.
    """

    prompt = {
        "role": "senior cyber threat intelligence analyst",
        "task": (
            "Infer infrastructure components that are logically REQUIRED "
            "or IMPLIED by the observed adversary actions."
        ),
        "constraints": [
            "Do NOT invent new behaviors, actions, techniques, or targets",
            "Only infer infrastructure that must exist for the listed actions to occur",
            "If something is optional or speculative, state that clearly",
            "Do NOT infer IP addresses, domains, vendors, or locations unless explicitly stated",
            "Base all reasoning strictly on the provided facts and evidence",
            "Attach confidence and analyst-style rationale",
        ],
        "observed_facts": facts,
        "text_evidence": clean_text[:6000],
        "output_schema": {
            "component": "string (e.g. 'ssh-server')",
            "category": "service|server|client|proxy|credential|network",
            "required_for": "string (behavior or relationship)",
            "confidence": "float (0.0–1.0)",
            "rationale": "string",
            "evidence": ["string"],
        },
    }

    raw = asyncio.run(
        llm_generate(json.dumps(prompt, ensure_ascii=False), profile="cti")
    )

    try:
        parsed = json.loads(raw)
    except Exception:
        return []

    return validate_llm_hypotheses(parsed)


# ============================================================
# OUTPUT VALIDATION (MANDATORY)
# ============================================================

def validate_llm_hypotheses(items) -> List[dict]:
    """
    Enforce schema, bounds, and safety.
    """
    safe: List[dict] = []

    if not isinstance(items, list):
        return safe

    for it in items:
        try:
            component = it.get("component", "").strip()
            category = it.get("category", "").strip()
            confidence = float(it.get("confidence", 0.0))
            rationale = it.get("rationale", "").strip()
            evidence = [e for e in it.get("evidence", []) if isinstance(e, str)]

            if not component or not rationale or not evidence:
                continue

            if category not in ALLOWED_INFRA_CATEGORIES:
                continue

            confidence = max(0.0, min(confidence, 1.0))

            safe.append({
                "component": component,
                "category": category,
                "required_for": it.get("required_for", ""),
                "confidence": round(confidence, 2),
                "rationale": rationale,
                "evidence": evidence[:3],
            })

        except Exception:
            continue

    return safe
