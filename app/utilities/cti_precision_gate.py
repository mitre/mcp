"""
cti_precision_gate.py — Unified Precision Gate for ATT&CK Techniques

Combines multiple non-ML methods to filter false positive techniques:

1. PMI Co-occurrence: measures statistical association between technique
   keywords and the source text within document windows
2. Sub-technique Hierarchy: enforces ATT&CK parent↔child consistency
3. Entity-Technique Clique: requires mutual corroboration between
   co-occurring entities and their inferred techniques
4. TF-IDF Evidence Scoring: weights technique evidence by term
   specificity to reject generic matches

All methods use only local data (MITRE taxonomy, D3FEND ontology,
source text). No ML, no LLM, no network.
"""

import re
import math
from collections import Counter, defaultdict
from functools import lru_cache


# ============================================================
# 1. PMI CO-OCCURRENCE FILTERING
# ============================================================

def _build_document_term_counts(text: str, window_size: int = 200) -> dict:
    """
    Build term frequency map from document using sliding windows.
    Returns: {term: count_of_windows_containing_term}
    """
    words = re.findall(r"[a-z]{3,}", text.lower())
    total_windows = max(1, len(words) - window_size + 1)

    term_window_count = Counter()
    for i in range(0, len(words), window_size // 2):  # 50% overlap
        window = set(words[i:i + window_size])
        for w in window:
            term_window_count[w] += 1

    return term_window_count, total_windows


def compute_pmi(term_a_count: int, term_b_count: int,
                cooccurrence_count: int, total_windows: int) -> float:
    """
    Pointwise Mutual Information between two terms.
    PMI(a,b) = log2(P(a,b) / (P(a) * P(b)))
    """
    if cooccurrence_count == 0 or total_windows == 0:
        return 0.0

    p_a = term_a_count / total_windows
    p_b = term_b_count / total_windows
    p_ab = cooccurrence_count / total_windows

    if p_a == 0 or p_b == 0:
        return 0.0

    return math.log2(p_ab / (p_a * p_b))


def pmi_score_technique(technique: dict, text: str,
                        term_counts: dict, total_windows: int,
                        window_size: int = 200) -> float:
    """
    Score a technique by PMI between its key terms and the source text.
    High PMI = technique terms genuinely co-occur with report content.
    Low PMI = spurious association.
    """
    # Extract technique signature terms from name + description
    tech_name = (technique.get("name") or "").lower()
    tech_desc = (technique.get("description") or "").lower()

    # Use technique name terms (most discriminative)
    tech_terms = set(re.findall(r"[a-z]{4,}", tech_name))
    # Add a few description terms (nouns/verbs only, skip common words)
    desc_terms = set(re.findall(r"[a-z]{5,}", tech_desc))
    STOPWORDS = {
        "which", "these", "those", "their", "other", "about", "after",
        "before", "being", "could", "would", "should", "through", "using",
        "example", "information", "techniques", "adversaries", "adversary",
        "system", "systems", "command", "commands", "within", "against",
        "between", "during", "access", "perform", "including", "specific",
    }
    desc_terms -= STOPWORDS

    # Combine, prioritizing name terms
    sig_terms = tech_terms | (desc_terms - tech_terms)
    if not sig_terms:
        return 0.0

    words = re.findall(r"[a-z]{3,}", text.lower())

    # Find co-occurrence windows between entity evidence and technique terms
    best_pmi = 0.0
    for term in sig_terms:
        term_count = term_counts.get(term, 0)
        if term_count == 0:
            continue

        # Check co-occurrence with the entity that triggered this technique
        evidence = technique.get("evidence", [])
        entity_terms = set()
        for ev in evidence:
            if "MITRE taxonomy:" in str(ev):
                entity = str(ev).split("MITRE taxonomy:")[1].split("uses")[0].strip()
                entity_terms.update(re.findall(r"[a-z]{3,}", entity.lower()))

        for et in entity_terms:
            et_count = term_counts.get(et, 0)
            if et_count == 0:
                continue

            # Count windows where both appear
            cooccur = 0
            for i in range(0, len(words), window_size // 2):
                window = set(words[i:i + window_size])
                if term in window and et in window:
                    cooccur += 1

            pmi = compute_pmi(et_count, term_count, cooccur, total_windows)
            best_pmi = max(best_pmi, pmi)

    return best_pmi


# ============================================================
# 2. SUB-TECHNIQUE HIERARCHY ENFORCEMENT
# ============================================================

def enforce_hierarchy(techniques: list[dict]) -> list[dict]:
    """
    Enforce ATT&CK parent↔sub-technique consistency.

    Rules:
    - If sub-technique T1078.002 exists, parent T1078 is implied (add it)
    - Orphan sub-techniques with no sibling or parent support get
      confidence downgrade
    """
    tid_set = {t.get("id") for t in techniques if t.get("id")}

    # Build parent→children map
    parents = defaultdict(set)
    for tid in tid_set:
        if "." in tid:
            parent = tid.split(".")[0]
            parents[parent].add(tid)

    # Score: sub-techniques with siblings are stronger
    hierarchy_scores = {}
    for parent, children in parents.items():
        for child in children:
            # More siblings = more confidence
            hierarchy_scores[child] = min(len(children) / 3.0, 1.0)

    # Apply: downgrade orphan sub-techniques from ontology inference
    result = []
    for t in techniques:
        tid = t.get("id", "")
        if "." in tid and tid in hierarchy_scores:
            if hierarchy_scores[tid] < 0.34:  # only child, no siblings
                if t.get("source") == "ontology-inference":
                    t = dict(t)
                    t["confidence"] = min(t.get("confidence", 1.0), 0.6)
                    t["x_hierarchy_orphan"] = True
        result.append(t)

    return result


# ============================================================
# 3. ENTITY-TECHNIQUE CLIQUE CORROBORATION
# ============================================================

def clique_filter(techniques: list[dict], ir: dict) -> list[dict]:
    """
    Entity-technique clique corroboration.

    Principle: techniques inferred from multiple co-occurring entities
    are more likely correct than techniques from a single entity.

    A technique supported by 2+ entities in the same report gets a
    confidence boost. A technique from only one entity (especially
    a broad-profile one) gets downgraded.
    """
    # Count how many distinct entities support each technique
    technique_entity_support = defaultdict(set)
    for t in techniques:
        tid = t.get("id", "")
        for ev in (t.get("evidence") or []):
            if "MITRE taxonomy:" in str(ev):
                entity = str(ev).split("MITRE taxonomy:")[1].split("uses")[0].strip()
                technique_entity_support[tid].add(entity)

    # Also count entities in the IR
    all_entities = set()
    for group in ("tools", "malware"):
        for ent in ir.get(group, []):
            name = (ent.get("name") or "").strip().lower()
            if name:
                all_entities.add(name)

    result = []
    for t in techniques:
        tid = t.get("id", "")
        supporters = technique_entity_support.get(tid, set())

        if t.get("source") != "ontology-inference":
            # Non-ontology techniques pass through
            result.append(t)
            continue

        if len(supporters) >= 2:
            # Multi-entity support = strong signal, boost confidence
            t = dict(t)
            t["confidence"] = min(t.get("confidence", 0.9) + 0.05, 0.97)
            t["x_clique_support"] = len(supporters)
            result.append(t)
        elif len(supporters) == 1:
            # Single entity support — check if that entity is broad-profile
            entity = list(supporters)[0]
            entity_techniques = [
                t2 for t2 in techniques
                if t2.get("source") == "ontology-inference"
                and any(entity in str(e) for e in (t2.get("evidence") or []))
            ]
            if len(entity_techniques) > 15:
                # Broad-profile entity — mark but don't drop
                t = dict(t)
                t["x_broad_profile_entity"] = entity
                t["x_broad_profile_count"] = len(entity_techniques)
            result.append(t)
        else:
            result.append(t)

    return result


# ============================================================
# 4. TF-IDF EVIDENCE SCORING
# ============================================================

def tfidf_score_evidence(technique: dict, text: str,
                         corpus_term_freq: dict) -> float:
    """
    Score technique evidence using TF-IDF principles.

    High score = evidence terms are frequent in THIS document
    but rare across general text (discriminative).
    Low score = evidence terms are generic/common.
    """
    evidence = technique.get("evidence", [])
    if not evidence:
        return 0.0

    doc_words = re.findall(r"[a-z]{3,}", text.lower())
    doc_tf = Counter(doc_words)
    doc_len = max(len(doc_words), 1)

    total_score = 0.0
    term_count = 0

    for ev in evidence:
        ev_str = str(ev)
        # Skip MITRE taxonomy evidence strings — score only text evidence
        if "MITRE taxonomy:" in ev_str:
            continue

        ev_terms = set(re.findall(r"[a-z]{4,}", ev_str.lower()))
        for term in ev_terms:
            tf = doc_tf.get(term, 0) / doc_len
            # IDF approximation: rare terms in general English score higher
            idf = corpus_term_freq.get(term, 1.0)
            total_score += tf * idf
            term_count += 1

    return total_score / max(term_count, 1)


# General English IDF approximations for common CTI terms
# Higher = more discriminative (rarer in general text)
# Lower = more common (less useful for precision)
_GENERAL_IDF = {
    # Very common (low IDF) — these don't help distinguish techniques
    "system": 0.5, "process": 0.6, "access": 0.5, "data": 0.4,
    "file": 0.6, "network": 0.6, "service": 0.5, "user": 0.5,
    "information": 0.3, "application": 0.4, "security": 0.5,
    "tool": 0.5, "technique": 0.4, "attack": 0.6,
    # Moderately discriminative
    "credential": 1.5, "registry": 1.5, "executable": 1.5,
    "encryption": 1.5, "lateral": 2.0, "exfiltration": 2.0,
    "privilege": 1.5, "persistence": 1.8, "evasion": 1.8,
    # Highly discriminative (high IDF)
    "lsass": 3.0, "mimikatz": 3.0, "psexec": 3.0, "vssadmin": 3.0,
    "ransomware": 2.5, "keylogger": 3.0, "shellcode": 3.0,
    "powershell": 2.0, "wmic": 2.5, "bcdedit": 3.0,
    "kerberos": 2.5, "ntlm": 2.5, "rdp": 2.0,
}


def get_idf(term: str) -> float:
    """Get IDF approximation for a term. Default 1.0 for unknown terms."""
    return _GENERAL_IDF.get(term, 1.0)


# ============================================================
# UNIFIED PRECISION GATE
# ============================================================

def apply_precision_gate(
    techniques: list[dict],
    source_text: str,
    ir: dict,
    min_confidence: float = 0.50,
) -> list[dict]:
    """
    Unified precision gate combining all methods.

    Pipeline:
    1. Hierarchy enforcement (structural)
    2. Clique corroboration (entity-level)
    3. PMI co-occurrence scoring (statistical)
    4. Confidence threshold (final cut)

    Techniques below min_confidence after all scoring are dropped.
    """
    if not techniques:
        return techniques

    print(f"[PRECISION] Input: {len(techniques)} techniques")

    # --- 1. Hierarchy enforcement ---
    techniques = enforce_hierarchy(techniques)

    # --- 2. Clique corroboration ---
    techniques = clique_filter(techniques, ir)

    # --- 3. PMI co-occurrence for ontology-inferred techniques ---
    term_counts, total_windows = _build_document_term_counts(source_text)

    for t in techniques:
        if t.get("source") != "ontology-inference":
            continue

        pmi = pmi_score_technique(t, source_text, term_counts, total_windows)
        t["x_pmi_score"] = round(pmi, 3)

        # PMI scoring only downgrades broad-profile entity techniques
        # (already flagged by clique filter). Others keep their confidence.
        is_broad = t.get("x_broad_profile_entity")

        if is_broad:
            if pmi <= 0:
                t["confidence"] = min(t.get("confidence", 1.0), 0.40)
            elif pmi < 1.5:
                t["confidence"] = min(t.get("confidence", 1.0), 0.50)
            elif pmi >= 2.5:
                t["confidence"] = min(t.get("confidence", 1.0) + 0.05, 0.97)

    # --- 4. Cap broad-profile entities to top-N by PMI ---
    MAX_PER_BROAD_ENTITY = 15
    broad_entities = defaultdict(list)
    non_broad = []

    for t in techniques:
        entity = t.get("x_broad_profile_entity")
        if entity and t.get("source") == "ontology-inference":
            broad_entities[entity].append(t)
        else:
            non_broad.append(t)

    for entity, techs in broad_entities.items():
        # Sort by PMI score descending, keep top N
        techs.sort(key=lambda x: x.get("x_pmi_score", 0), reverse=True)
        for t in techs[:MAX_PER_BROAD_ENTITY]:
            non_broad.append(t)
        dropped_count = max(0, len(techs) - MAX_PER_BROAD_ENTITY)
        if dropped_count:
            print(f"[PRECISION] Capped {entity}: kept {min(len(techs), MAX_PER_BROAD_ENTITY)}, dropped {dropped_count}")

    techniques = non_broad

    # --- 5. Confidence threshold ---
    kept = []
    dropped = 0
    for t in techniques:
        if t.get("confidence", 1.0) >= min_confidence:
            kept.append(t)
        else:
            dropped += 1

    # Stats
    ontology_kept = sum(1 for t in kept if t.get("source") == "ontology-inference")
    ontology_dropped = sum(1 for t in techniques if t.get("source") == "ontology-inference") - ontology_kept
    broad_flagged = sum(1 for t in kept if t.get("x_broad_profile_entity"))
    orphan_flagged = sum(1 for t in kept if t.get("x_hierarchy_orphan"))

    print(f"[PRECISION] Output: {len(kept)} kept, {dropped} dropped")
    print(f"[PRECISION] Ontology: {ontology_kept} kept, {ontology_dropped} dropped")
    if broad_flagged:
        print(f"[PRECISION] Broad-profile downgraded: {broad_flagged}")
    if orphan_flagged:
        print(f"[PRECISION] Hierarchy orphans: {orphan_flagged}")

    return kept
