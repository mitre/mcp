"""
cti_extract_software.py -- Software + Version Extraction for Stage 1

PURPOSE
-------
Extract software names AND versions from CTI text and validate each
candidate against:
    1. MITRE ATT&CK 'tool'/'malware' name_index (always available).
    2. OSV.dev HTTP API (https://api.osv.dev/v1/query) -- optional.
    3. NIST NVD via `nvdlib` (lazy import) -- optional.

The output augments the IR with an ``ir["software"][]`` list, distinct
from the existing ``ir["tools"][]`` (which stays scoped to ATT&CK-known
offensive software). The range plugin's LLM deploy step needs the
version + canonical identifier to pre-stage matching binaries via
ansible, so each entry surfaces a Package URL (PURL) when one can be
formed.

Driving use case
----------------
The MITRE ATT&CK BlackCat (ALPHV) Adversary Emulation plan calls out
specific software with versions, e.g. ``rclone v1.64.0``, ``ADRecon.ps1``,
``InfoStealer``, ``BITSAdmin``, ``ExMatter``, ``Empire scanner``,
``PsExec``. The patterns below match the canonical filename+extension
and ``name vX.Y.Z`` introductions used throughout AE plans, Microsoft
DART case studies, Mandiant M-Trends, and CISA advisories.

Design constraints
------------------
* **No static lists.** Every classification / known-software lookup is:
    - an ontology query against MITRE ATT&CK's `name_index`
      (``tool:<name>`` / ``malware:<name>``); or
    - an external library API call (``nvdlib``); or
    - an HTTP API call (OSV.dev); or
    - a regex over the *structure* of CTI prose (not over a vocabulary).
* **Offline-safe.** ``use_external_apis=False`` skips OSV/NVD entirely
  so CI runs and unit tests don't touch the network.
* **Cached.** OSV/NVD responses are persisted to
  ``app/utilities/data/cache/software_lookup_cache.json`` (gitignored).
* **Never invent.** ``version`` is set ONLY when the source text
  introduces it explicitly. Categorisation falls back to ``unknown``
  rather than guessing.
* **PURL canonicalisation.** When ``packageurl-python`` is available we
  format ``pkg:pypi/<name>@<version>``, ``pkg:github/<org>/<repo>@<tag>``,
  or ``pkg:generic/<name>@<version>`` per the PURL spec
  (https://github.com/package-url/purl-spec).

Public API
----------
``extract_software(text, taxonomy=None, *, nlp=None,
                   use_external_apis=False) -> list[dict]``
"""

from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional


# =============================================================
# Cache (offline-safe, gitignored)
# =============================================================

_CACHE_DIR = Path(__file__).resolve().parent / "data" / "cache"
_CACHE_PATH = _CACHE_DIR / "software_lookup_cache.json"


def _load_cache() -> dict:
    try:
        if _CACHE_PATH.exists():
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        # Best-effort cache write; never crash the pipeline on a cache fail.
        pass


_CACHE: dict = _load_cache()


# =============================================================
# Lazy library import helpers
# =============================================================

@lru_cache(maxsize=1)
def _try_import_packageurl():
    """Lazy import of packageurl-python. Returns module or None."""
    try:
        from packageurl import PackageURL  # type: ignore
        return PackageURL
    except Exception:
        return None


@lru_cache(maxsize=1)
def _try_import_nvdlib():
    """Lazy import of nvdlib. Returns module or None."""
    try:
        import nvdlib  # type: ignore
        return nvdlib
    except Exception:
        return None


# =============================================================
# Regex grammars
# =============================================================
#
# These regexes match the STRUCTURE of CTI software introductions, not
# any specific vocabulary. They are derived from canonical phrasings
# seen in AE plans, Microsoft DART case studies, Mandiant M-Trends,
# and CISA advisories.

# 1) "<name>.<extension>" -- script/binary filenames.
#    Matches canonical filename-with-extension introductions such as
#    "ADRecon.ps1", "rclone.exe", "infostealer.dll".
#    Extensions are RFC-compatible script/binary suffixes used widely
#    in incident reports.
_FILENAME_RE = re.compile(
    r"\b([A-Za-z][\w-]{2,30})\.(ps1|exe|bat|sh|py|dll|jar)\b",
    re.IGNORECASE,
)

# 2) "<name> v?<version>" -- name followed by a semver-ish tag.
#    Matches "rclone v1.64.0", "Mimikatz 2.2.0", "ExMatter v3.0".
_NAME_VERSION_RE = re.compile(
    r"\b([A-Za-z][\w-]{2,30})\s+v?(\d+\.\d+(?:\.\d+(?:\.\d+)?)?)\b",
)

# 3) Bare identifier token candidates. Used ONLY to probe the ATT&CK
#    name_index -- if the token matches a known ATT&CK tool/malware
#    entry, we accept it; otherwise we drop it. This is pure ontology
#    lookup, NOT a static vocabulary list -- the regex matches any
#    identifier-shaped token, and the ATT&CK index decides admission.
#    Case-insensitive on purpose so we catch "rclone", "mimikatz", etc.
_TOKEN_RE = re.compile(r"\b([A-Za-z][A-Za-z][\w-]{1,30})\b")

# 4) Enumeration-style introductions: "Tools used: X, Y, Z" /
#    "Software used: ..." / "Utilities: ..." / "Binaries used: ...".
#    Captures the *body* of the enumeration; each comma-separated
#    proper-noun token in that body becomes a candidate. This is a
#    *structural* pattern (header-noun + colon + comma list), not a
#    vocabulary list -- the header-noun pattern is fixed structure,
#    while the body contents are pure data.
_ENUMERATION_RE = re.compile(
    # Header: tools|software|utility|... (+ optional verb) + colon.
    # Body: continues until a sentence terminator. A dot is allowed inside
    # the body when followed by a digit (versions like "v1.64.0") OR by
    # a letter (filename extensions like ".ps1") -- only a dot followed
    # by whitespace / end-of-string terminates the enumeration.
    r"\b(?:tools?|software|utilit(?:y|ies)|binaries|payloads?)"
    r"\s+(?:used|deployed|executed|leveraged|observed)?\s*:\s*"
    r"((?:[^.\n]|\.(?=[A-Za-z0-9]))+)",
    re.IGNORECASE,
)
_ENUM_ITEM_RE = re.compile(r"([A-Z][\w.-]{2,40}(?:\s+scanner|\s+module|\s+agent|\s+stealer|\s+miner)?)")


# =============================================================
# ATT&CK ontology helpers
# =============================================================

# Tactic -> software_kind mapping (this is just renaming spec tactics
# to the friendlier slugs consumed by the range plugin's deploy step;
# the source-of-truth tactics come from ATT&CK's `kill_chain_phases`).
_TACTIC_TO_KIND = {
    "reconnaissance":       "recon",
    "discovery":            "recon",
    "command-and-control":  "c2",
    "credential-access":    "credential-access",
    "lateral-movement":     "lateral-movement",
    "exfiltration":         "exfiltration",
    "impact":               "ransomware",  # only when 'data-destruction' / 'data-encrypted' AP present
    "execution":            "living-off-the-land",
    "defense-evasion":      "living-off-the-land",
}


def _attack_lookup(name: str, taxonomy: Optional[dict]) -> Optional[tuple]:
    """Return (kind_label, attack_id, kcp_tactics) for an ATT&CK hit, else None.

    ``kind_label`` is the STIX type from the name_index ('tool' or
    'malware'). ``kcp_tactics`` is the set of tactic phase_name values
    derived from the `uses` relationships originating at this ATT&CK
    software entry (ATT&CK tool/malware objects themselves do not carry
    kill_chain_phases; the tactic information lives on the relationships
    they participate in).
    """
    if not taxonomy or not name:
        return None

    name_idx = taxonomy.get("name_index", {})
    key_low = name.strip().lower()

    hit = None
    for kind in ("tool", "malware"):
        entry = name_idx.get(f"{kind}:{key_low}")
        if entry:
            hit = (kind, entry)
            break
        # token-normalized fallback (the taxonomy loader also indexes
        # under a whitespace-collapsed form for hyphenated names).
        norm = re.sub(r"[^a-z0-9]+", " ", key_low).strip()
        entry = name_idx.get(f"{kind}:{norm}")
        if entry:
            hit = (kind, entry)
            break

    if not hit:
        return None

    kind, (_stype, sid, sobj) = hit

    # ATT&CK technique id from external_references
    attack_id = None
    for ref in sobj.get("external_references", []) or []:
        if ref.get("source_name") == "mitre-attack":
            attack_id = ref.get("external_id")
            break

    # Tactics: walk `uses` relationships originating from this software
    # to attack-patterns, then collect those APs' kill_chain_phases.
    tactics: set[str] = set()
    ap_index = taxonomy.get("attack_patterns", {})  # id -> attack-pattern object
    for rel in taxonomy.get("relationships", []) or []:
        if (rel.get("relationship_type") != "uses"
                or rel.get("source_ref") != sid):
            continue
        ap = ap_index.get(rel.get("target_ref"))
        if not ap:
            continue
        for kcp in ap.get("kill_chain_phases", []) or []:
            if kcp.get("kill_chain_name") == "mitre-attack":
                pn = kcp.get("phase_name")
                if pn:
                    tactics.add(pn)

    return kind, attack_id, tactics


def _classify_kind(name: str, taxonomy: Optional[dict]) -> tuple[str, Optional[str]]:
    """Return (software_kind, attack_id).

    Pure ontology classification: ATT&CK tactic -> kind slug via
    ``_TACTIC_TO_KIND``. ATT&CK 'malware' objects are upgraded to
    ``ransomware`` only when their tactics include 'impact' AND their
    malware_types claim ransomware-adjacent labels (also from ATT&CK,
    not from us).
    """
    hit = _attack_lookup(name, taxonomy)
    if not hit:
        return "unknown", None

    kind_label, attack_id, tactics = hit

    # Ransomware refinement -- TWO ontology signals (no static lists):
    #
    #   a) ATT&CK explicitly sets `malware_types` to include "ransomware";
    #      OR
    #   b) the entry is `is_family=True` AND its tactics include "impact"
    #      (ATT&CK groups all ransomware families under impact-tactic
    #      `uses` relationships; this is an ontology-derived test, not a
    #      hand-maintained list).
    if kind_label == "malware":
        entry = taxonomy["name_index"].get(f"malware:{name.strip().lower()}")
        if entry:
            sobj = entry[2]
            mtypes = [m.lower() for m in (sobj.get("malware_types") or [])]
            if "ransomware" in mtypes:
                return "ransomware", attack_id
            if sobj.get("is_family") and "impact" in tactics:
                return "ransomware", attack_id

    # Prefer the most-specific tactic when multiple are present, using
    # the canonical kill-chain ordering.
    priority = (
        "exfiltration", "credential-access", "lateral-movement",
        "command-and-control", "recon", "ransomware",
        "living-off-the-land",
    )
    # First, map tactics -> kinds.
    mapped_kinds = {
        _TACTIC_TO_KIND[t] for t in tactics if t in _TACTIC_TO_KIND
    }
    if not mapped_kinds:
        return "unknown", attack_id
    for k in priority:
        if k in mapped_kinds:
            return k, attack_id
    # Fall back to any mapped kind.
    return next(iter(mapped_kinds)), attack_id


# =============================================================
# External-API validators (OSV / NVD) -- all cached, all off by default
# =============================================================

def _osv_query(name: str, version: Optional[str]) -> dict:
    """
    Query OSV.dev for a package name. Cached. Returns:
        {'known': bool, 'vuln_ids': [str, ...]}
    """
    cache_key = f"osv:{name.lower()}:{(version or '').strip()}"
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached

    result = {"known": False, "vuln_ids": []}
    try:
        import urllib.request
        import urllib.error
        payload = {"package": {"name": name}}
        if version:
            payload["version"] = version
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.osv.dev/v1/query",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        vulns = body.get("vulns") or []
        if vulns:
            result["known"] = True
            result["vuln_ids"] = [
                v.get("id") for v in vulns if v.get("id")
            ][:10]
    except Exception:
        # Network unavailable / API timeout / any other error -- mark as
        # not-known. The pipeline will fall back to attack/cti-text-only.
        result = {"known": False, "vuln_ids": []}

    _CACHE[cache_key] = result
    _save_cache(_CACHE)
    return result


def _nvd_query(name: str) -> list[str]:
    """Query NVD via nvdlib (lazy). Cached. Returns list of CVE IDs."""
    cache_key = f"nvd:{name.lower()}"
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached

    nvdlib = _try_import_nvdlib()
    if nvdlib is None:
        _CACHE[cache_key] = []
        _save_cache(_CACHE)
        return []

    cves: list[str] = []
    try:
        results = nvdlib.searchCVE(
            keywordSearch=name,
            limit=5,  # cap; we only need to know "is there any signal?"
            delay=1,
        )
        for cve in results or []:
            cid = getattr(cve, "id", None)
            if cid:
                cves.append(cid)
    except Exception:
        cves = []

    _CACHE[cache_key] = cves
    _save_cache(_CACHE)
    return cves


# =============================================================
# PURL formatting
# =============================================================

def _format_purl(name: str, version: Optional[str], purl_type: str = "generic") -> Optional[str]:
    """Format a PURL string; returns None if packageurl-python is absent."""
    PackageURL = _try_import_packageurl()
    if PackageURL is None or not name:
        return None
    try:
        kwargs = {"type": purl_type, "name": name.lower(), "version": version}
        return PackageURL(**{k: v for k, v in kwargs.items() if v}).to_string()
    except Exception:
        return None


# =============================================================
# Evidence-window helper
# =============================================================

def _evidence_window(text: str, start: int, end: int, span: int = 100) -> str:
    a = max(0, start - span)
    b = min(len(text), end + span)
    return text[a:b].replace("\n", " ").strip()


# =============================================================
# Candidate filtering
# =============================================================

# We reject regex hits whose head token is a common English noun
# (e.g. "scanner", "module"). Reuse the WordNet check from
# cti_extract_users when NLTK is available; degrade to a tiny grammatical
# filler set otherwise. We deliberately do not maintain a hand-rolled
# "bad token" list.
try:
    from plugins.mcp.app.utilities.cti_extract_users import (
        _is_stopword_or_common as _is_grammar_or_common,
    )
except Exception:
    # Fallback when import context blocks the relative import.
    _FALLBACK_FILLERS = {"the", "a", "an", "and", "or"}
    def _is_grammar_or_common(token: str) -> bool:
        return (token or "").lower() in _FALLBACK_FILLERS


def _candidate_ok(name: str) -> bool:
    if not name or len(name) < 3:
        return False
    # Reject pure-digit or pure-symbol tokens.
    if not re.search(r"[A-Za-z]", name):
        return False
    # If WordNet recognises the lowercase token AS A COMMON NOUN, skip
    # it -- "scanner", "module", "agent" all return WordNet synsets and
    # are too generic to be the canonical name of a piece of software
    # on their own.
    if _is_grammar_or_common(name):
        return False
    return True


# =============================================================
# Public API
# =============================================================

def extract_software(
    text: str,
    taxonomy: Optional[dict] = None,
    *,
    nlp=None,
    use_external_apis: bool = False,
) -> list[dict]:
    """
    Extract observed software (with versions when present) from CTI text.

    Parameters
    ----------
    text : str
        Cleaned CTI text (Stage-1 output).
    taxonomy : dict | None
        MITRE ATT&CK taxonomy dict from
        ``cti_taxonomy_loader.load_mitre_taxonomy``. When provided each
        candidate is checked against ``taxonomy['name_index']`` for an
        ATT&CK 'tool' or 'malware' entry, and the entry's tactics are
        derived from the `uses` relationships it participates in.
    nlp : spacy.Language | None
        Optional preloaded spaCy model (reserved; not used today).
    use_external_apis : bool
        When True, also probe OSV.dev (HTTP) and NIST NVD (via nvdlib)
        for additional validation and CVE references. Default False so
        unit tests + CI run offline.

    Returns
    -------
    list[dict]
        One dict per distinct (name-lower, version) pair, with keys:
            name, version, source, purl, software_kind,
            attack_id, cve_refs, evidence, confidence

        - source        : 'attack' | 'osv' | 'nvd' | 'cti-text-only'
        - purl          : packageurl string when resolvable, else None
        - software_kind : ATT&CK-derived kind slug or 'unknown'
        - cve_refs      : list of CVE IDs (empty unless use_external_apis)
        - confidence    : float in [0,1]
    """
    if not text:
        return []

    candidates: dict[tuple[str, str], dict] = {}

    # ---- Pass 1: filename-with-extension hits ----
    #
    # We emit BOTH the full filename (e.g. "ADRecon.ps1") AND the bare
    # canonical name (e.g. "ADRecon") so downstream consumers that
    # match by either form (CTID AE-plan vocabulary uses the bare name,
    # range deploy needs the artifact extension) get a hit. Each form
    # rides as its own candidate with the same evidence span. ATT&CK
    # lookup happens on the bare form below.
    for m in _FILENAME_RE.finditer(text):
        base = m.group(1).strip()
        ext = m.group(2).lower()
        if not _candidate_ok(base):
            continue
        evidence = _evidence_window(text, m.start(), m.end())
        # Bare canonical name -- the form CTID emulation plans cite.
        bare_key = (base.lower(), "")
        candidates.setdefault(bare_key, {
            "name": base,
            "version": None,
            "evidence": evidence,
            "_origin": "filename-canonical",
        })
        # Full filename -- the form range deploy needs.
        full_name = f"{base}.{ext}"
        full_key = (full_name.lower(), "")
        candidates.setdefault(full_key, {
            "name": full_name,
            "version": None,
            "evidence": evidence,
            "_origin": "filename",
        })

    # ---- Pass 2: name + version hits ----
    for m in _NAME_VERSION_RE.finditer(text):
        base = m.group(1).strip()
        version = m.group(2).strip()
        if not _candidate_ok(base):
            continue
        key = (base.lower(), version)
        evidence = _evidence_window(text, m.start(), m.end())
        # If a versioned hit collides with an unversioned filename hit
        # (e.g. rclone.exe and rclone v1.64.0), keep both -- the
        # downstream consumer wants the version.
        candidates.setdefault(key, {
            "name": base,
            "version": version,
            "evidence": evidence,
            "_origin": "name-version",
        })

    # ---- Pass 2b: enumeration-style "Tools used: X, Y, Z" ----
    #
    # Captures items from a structural enumeration header. Items here
    # are admitted with origin='enumeration' regardless of WordNet
    # noun status, because the enclosing structure ("Tools used:")
    # has already disambiguated them as software references. Items
    # are still subject to the ATT&CK upgrade in the per-candidate
    # classification step below.
    for em in _ENUMERATION_RE.finditer(text):
        body = em.group(1)
        body_start = em.start(1)
        # Split on comma OR " and "
        parts = re.split(r",|\s+and\s+", body)
        for part in parts:
            stripped = part.strip().rstrip(".;: ")
            if not stripped:
                continue
            # Pull the first proper-noun token (allowing extensions / spaces).
            mm = _ENUM_ITEM_RE.search(stripped)
            if not mm:
                continue
            item = mm.group(1).strip()
            # Filename-with-extension already handled by Pass 1; skip dupes.
            if "." in item and re.search(r"\.(ps1|exe|bat|sh|py|dll|jar)$", item, re.IGNORECASE):
                continue
            # Strip trailing role-suffix tokens (so "Empire scanner" -> "Empire").
            head = re.split(r"\s+", item, maxsplit=1)[0]
            if not head or len(head) < 3 or not re.search(r"[A-Za-z]", head):
                continue
            key = (head.lower(), "")
            if key in candidates:
                continue
            # Compute evidence using the enumeration body window.
            ev = _evidence_window(text, body_start, em.end(1))
            candidates[key] = {
                "name": head,
                "version": None,
                "evidence": ev,
                "_origin": "enumeration",
            }

    # ---- Pass 3: bare-token candidates gated by ATT&CK ontology ----
    #
    # Walk every identifier-shaped token and admit it ONLY if the ATT&CK
    # name_index recognises it as a 'tool' or 'malware'. No static
    # vocabulary list is consulted -- admission is purely an ontology
    # lookup against the loaded ATT&CK bundle.
    #
    # Note: ATT&CK admission OVERRIDES the WordNet common-noun filter.
    # Names like "Empire" or "Cobalt Strike" are common English nouns
    # AND legitimate ATT&CK tool entries -- the ontology has final say.
    if taxonomy and taxonomy.get("name_index"):
        for m in _TOKEN_RE.finditer(text):
            base = m.group(1).strip()
            # Minimal sanity guard -- length / alphabetic-content only.
            if not base or len(base) < 3 or not re.search(r"[A-Za-z]", base):
                continue
            # Skip tokens that are the filename-extension portion of an
            # already-captured pass-1 hit (e.g. "ps1" in "ADRecon.ps1").
            # A preceding "." in the text indicates we are inside a
            # filename-with-extension match, not at a token boundary.
            if m.start() > 0 and text[m.start() - 1] == ".":
                continue
            key = (base.lower(), "")
            if key in candidates:
                continue
            # Probe ATT&CK -- if it's not in the ontology, drop the token.
            if _attack_lookup(base, taxonomy) is None:
                continue
            evidence = _evidence_window(text, m.start(), m.end())
            candidates[key] = {
                "name": base,
                "version": None,
                "evidence": evidence,
                "_origin": "attack-token",
            }

    if not candidates:
        return []

    # If a name has BOTH a versioned and an unversioned entry, drop the
    # unversioned one -- the version-bearing record is strictly more
    # useful for the range deploy step (it knows which binary to stage).
    versioned_names = {
        low_name for (low_name, ver) in candidates.keys() if ver
    }
    for (low_name, ver) in list(candidates.keys()):
        if not ver and low_name in versioned_names:
            del candidates[(low_name, ver)]

    results: list[dict] = []
    seen_emitted: set[tuple[str, str]] = set()

    for (low_name, version), cand in candidates.items():
        name = cand["name"]
        evidence = cand["evidence"]
        origin = cand["_origin"]
        # Strip extension for ATT&CK / OSV / NVD lookups -- ATT&CK keys
        # by the bare software name, not by filename.
        lookup_name = name
        if origin == "filename":
            lookup_name = name.rsplit(".", 1)[0]

        software_kind, attack_id = _classify_kind(lookup_name, taxonomy)

        source = "cti-text-only"
        purl = None
        cve_refs: list[str] = []
        confidence = 0.4

        if attack_id:
            source = "attack"
            confidence = 0.9
            purl = _format_purl(lookup_name, version or None, purl_type="generic")
        else:
            # Only consult network APIs when explicitly enabled.
            if use_external_apis:
                osv = _osv_query(lookup_name, version or None)
                if osv["known"]:
                    source = "osv"
                    confidence = 0.7
                    cve_refs.extend(osv["vuln_ids"])
                    purl = _format_purl(lookup_name, version or None, purl_type="generic")
                else:
                    nvd_cves = _nvd_query(lookup_name)
                    if nvd_cves:
                        source = "nvd"
                        confidence = 0.65
                        cve_refs.extend(nvd_cves)
                        purl = _format_purl(lookup_name, version or None, purl_type="generic")

            if source == "cti-text-only":
                # Generic PURL is still useful for the range deploy step.
                purl = _format_purl(lookup_name, version or None, purl_type="generic")
                confidence = 0.45 if version else 0.35

        # Dedup by the emitted NAME (not lookup_name) so a bare
        # canonical hit (e.g. "ADRecon") and its filename sibling
        # ("ADRecon.ps1") can both surface -- they share a lookup_name
        # for ATT&CK / OSV / NVD queries but are distinct artifacts
        # for downstream consumers (deploy step + CTID-compatible
        # vocabulary). Versioned entries still dedup against
        # themselves via the existing version-bearing logic.
        emit_key = (name.lower(), version or "")
        if emit_key in seen_emitted:
            continue
        seen_emitted.add(emit_key)

        results.append({
            "name": name,
            "version": version or None,
            "source": source,
            "purl": purl,
            "software_kind": software_kind,
            "attack_id": attack_id,
            "cve_refs": cve_refs,
            "evidence": evidence,
            "confidence": confidence,
        })

    return results
