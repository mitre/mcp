"""
Cross-report aggregation for infrastructure hypotheses.

This module NEVER invents infrastructure.
It ONLY aggregates confidence across multiple hypothesis bundles.
"""

import json
from collections import defaultdict
from pathlib import Path


def aggregate_infrastructure_hypotheses(infra_dir: Path) -> list[dict]:
    """
    Aggregate infra hypotheses across reports.

    Aggregation key:
      (component, category)

    Confidence model:
      independent corroboration increases confidence
    """

    buckets = defaultdict(list)

    for path in infra_dir.glob("*.infra.stix.json"):
        bundle = json.loads(path.read_text())
        for obj in bundle.get("objects", []):
            if obj.get("type") != "x-cti-infrastructure-reasoning":
                continue

            for h in obj.get("x_infrastructure_hypotheses", []):
                key = (h.get("component"), h.get("category"))
                buckets[key].append(h)

    aggregated = []

    for (component, category), items in buckets.items():
        confidences = [i.get("confidence", 0.0) for i in items]
        avg_conf = sum(confidences) / len(confidences)

        # Soft corroboration boost (bounded)
        boosted = min(avg_conf + (0.05 * (len(items) - 1)), 0.95)

        aggregated.append({
            "component": component,
            "category": category,
            "reports": len(items),
            "confidence": round(boosted, 2),
            "rationales": list({
                i.get("rationale") for i in items if i.get("rationale")
            }),
            "evidence": list({
                e for i in items for e in i.get("evidence", [])
            })[:5],
        })

    return sorted(
        aggregated,
        key=lambda x: (x["confidence"], x["reports"]),
        reverse=True,
    )
