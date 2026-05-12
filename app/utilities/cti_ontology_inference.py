"""Data-driven ATT&CK technique inference from extracted CTI entities."""

from __future__ import annotations

import re
from typing import Iterable

from plugins.mcp.app.utilities.cti_defend_validation import (
    filter_by_keyword_evidence,
    validate_techniques_by_tactic,
)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", (text or "").lower()))


def _entity_names(ir: dict) -> list[str]:
    names: list[str] = []
    for bucket in ("tools", "malware", "infrastructure", "attack_patterns"):
        for item in ir.get(bucket) or []:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
    return names


def _score_candidate(entity_tokens: set[str], source_tokens: set[str], tech: dict) -> int:
    name_tokens = set(tech.get("tokens") or set())
    desc_tokens = set(tech.get("desc_tokens") or set())
    score = 0
    score += 4 * len(entity_tokens & name_tokens)
    score += 3 * len(entity_tokens & desc_tokens)
    score += len(source_tokens & name_tokens)
    score += min(3, len(source_tokens & desc_tokens))
    return score


def infer_techniques_from_entities(
    ir: dict,
    technique_lookup: dict[str, dict],
    *,
    source_text: str = "",
    max_results: int = 15,
) -> list[dict]:
    """Infer ATT&CK techniques by matching entities against ATT&CK text."""
    if not ir or not technique_lookup:
        return []

    source_tokens = _tokens(source_text)
    scored: dict[str, tuple[int, dict]] = {}
    for name in _entity_names(ir):
        entity_tokens = _tokens(name)
        if not entity_tokens:
            continue
        for tid, tech in technique_lookup.items():
            score = _score_candidate(entity_tokens, source_tokens, tech)
            if score <= 0:
                continue
            current = scored.get(tid)
            if current and current[0] >= score:
                continue
            candidate = {
                "id": tid,
                "name": tech.get("name", ""),
                "description": tech.get("description", ""),
                "source": "ontology-inference",
                "confidence": min(0.95, 0.45 + (score / 20)),
                "matched_entity": name,
            }
            scored[tid] = (score, candidate)

    ranked = [item for _, item in sorted(scored.values(), key=lambda pair: pair[0], reverse=True)]
    ranked = filter_by_keyword_evidence(ranked, source_text or " ".join(_entity_names(ir)), min_overlap=1)
    ranked = validate_techniques_by_tactic(ranked, source_text, strict=bool(source_text))
    return ranked[:max_results]
