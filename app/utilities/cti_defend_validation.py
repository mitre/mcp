"""ATT&CK tactic and evidence validation helpers for CTI inference."""

from __future__ import annotations

import functools
import re
from typing import Iterable

from plugins.mcp.app.utilities.cti_taxonomy_loader import (
    build_normalized_attack_patterns,
)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", (text or "").lower()))


def _signal_name(phase: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[-_\s]+", phase or "") if part)


@functools.lru_cache(maxsize=1)
def _technique_lookup() -> dict[str, dict]:
    _, lookup = build_normalized_attack_patterns()
    return lookup


def extract_tactic_signals(text: str) -> set[str]:
    """Infer ATT&CK tactic signals from source text using ATT&CK content."""
    text_tokens = _tokens(text)
    if not text_tokens:
        return set()

    signals: set[str] = set()
    for tech in _technique_lookup().values():
        technique_tokens = set(tech.get("tokens") or set())
        desc_tokens = set(tech.get("desc_tokens") or set())
        name_hits = text_tokens & technique_tokens
        desc_hits = text_tokens & desc_tokens
        if len(name_hits) >= 1 or len(desc_hits) >= 2:
            for phase in tech.get("kill_chain") or []:
                signal = _signal_name(phase)
                if signal:
                    signals.add(signal)
    return signals


def _technique_tactics(technique_id: str) -> set[str]:
    tech = _technique_lookup().get((technique_id or "").upper())
    if not tech:
        return set()
    return {_signal_name(phase) for phase in tech.get("kill_chain") or [] if phase}


def validate_techniques_by_tactic(
    techniques: Iterable[dict],
    text: str,
    *,
    strict: bool = False,
) -> list[dict]:
    """Filter ontology-inferred techniques whose ATT&CK tactics lack evidence."""
    items = list(techniques or [])
    if not strict:
        return items

    signals = extract_tactic_signals(text)
    if not signals:
        return [t for t in items if t.get("source") != "ontology-inference"]

    kept: list[dict] = []
    for tech in items:
        if tech.get("source") != "ontology-inference":
            kept.append(tech)
            continue
        if _technique_tactics(tech.get("id", "")) & signals:
            kept.append(tech)
    return kept


def filter_by_keyword_evidence(
    techniques: Iterable[dict],
    text: str,
    *,
    min_overlap: int = 2,
) -> list[dict]:
    """Keep ontology-inferred techniques with enough lexical evidence."""
    text_tokens = _tokens(text)
    kept: list[dict] = []
    for tech in techniques or []:
        if tech.get("source") != "ontology-inference":
            kept.append(tech)
            continue
        evidence_tokens = _tokens(
            " ".join(
                str(part or "")
                for part in (
                    tech.get("name"),
                    tech.get("description"),
                    tech.get("x_cti_evidence"),
                )
            )
        )
        if len(text_tokens & evidence_tokens) >= min_overlap:
            kept.append(tech)
    return kept
