"""
cti_defend_validation.py — D3FEND Ontology-Based Technique Validation

Uses the D3FEND ontology to validate and filter ATT&CK techniques
based on tactic relevance and artifact corroboration.

This is a UNIVERSAL validation gate — not tuned to any specific
adversary or campaign. It works by:

1. Extracting tactic signals from the source text (e.g., mentions of
   "encrypt", "lateral movement", "credential" → relevant tactics)
2. Mapping each candidate technique to its D3FEND tactic classification
3. Keeping techniques whose tactic is relevant to the source text
4. Using D3FEND's digital artifact taxonomy to corroborate techniques
   with artifact mentions in the text

Data source: d3fend-protege.ttl (2.7MB, already local)
"""

import re
from pathlib import Path
from functools import lru_cache
from rdflib import Graph, Namespace, RDFS


# ============================================================
# TACTIC SIGNAL EXTRACTION (from source text)
# ============================================================

# Map natural language indicators → D3FEND tactic categories
# These are generic CTI terms, not adversary-specific
TACTIC_INDICATORS = {
    "InitialAccess": [
        "initial access", "phishing", "spearphishing", "exploit public",
        "drive-by", "supply chain", "trusted relationship", "valid account",
        "vpn", "rdp access", "brute force", "credential stuffing",
    ],
    "Execution": [
        "execute", "execution", "scripting", "powershell", "command line",
        "cmd.exe", "wscript", "cscript", "mshta", "rundll32", "regsvr32",
        "scheduled task", "service execution", "wmi", "api call",
    ],
    "Persistence": [
        "persistence", "registry run key", "scheduled task", "boot",
        "startup", "service creation", "implant", "backdoor", "rootkit",
        "logon script", "account creation",
    ],
    "PrivilegeEscalation": [
        "privilege escalation", "elevat", "uac bypass", "exploit",
        "token manipulation", "sudo", "setuid", "admin", "root access",
    ],
    "DefenseEvasion": [
        "defense evasion", "evasion", "obfuscat", "packing", "disable",
        "defender", "antivirus", "security tool", "tamper", "clear log",
        "event log", "indicator removal", "masquerad",
    ],
    "CredentialAccess": [
        "credential", "password", "hash", "lsass", "mimikatz", "kerberos",
        "brute force", "keylog", "dump", "ntlm", "token", "lazagne",
        "stored password", "browser credential",
    ],
    "Discovery": [
        "discovery", "enumerat", "reconnaissance", "scan", "network scan",
        "port scan", "system information", "process list", "directory listing",
        "account discovery", "adrecon", "whoami",
    ],
    "LateralMovement": [
        "lateral movement", "remote desktop", "rdp", "psexec", "smb",
        "wmi", "winrm", "ssh", "remote service", "pass the hash",
        "remote execution", "propagat",
    ],
    "Collection": [
        "collection", "screen capture", "clipboard", "keylog",
        "audio capture", "video capture", "email collection", "data staged",
    ],
    "CommandAndControl": [
        "command and control", "c2", "c&c", "beacon", "callback",
        "tunnel", "proxy", "dns tunnel", "reverse shell", "cobalt strike",
        "brute ratel", "sliver",
    ],
    "Exfiltration": [
        "exfiltrat", "data theft", "upload", "megasync", "mega cloud",
        "rclone", "cloud storage", "sftp", "ftp upload",
    ],
    "Impact": [
        "impact", "encrypt", "ransomware", "ransom", "wipe", "destruct",
        "defacement", "wallpaper", "shadow copy", "vssadmin",
        "recovery disable", "bcdedit", "service stop", "terminate process",
    ],
}


def extract_tactic_signals(text: str) -> set[str]:
    """
    Identify which ATT&CK tactic categories are evidenced in the text.
    Returns a set of tactic names (e.g., {'Impact', 'LateralMovement'}).
    """
    text_lower = text.lower()
    detected = set()

    for tactic, indicators in TACTIC_INDICATORS.items():
        for indicator in indicators:
            if indicator in text_lower:
                detected.add(tactic)
                break

    return detected


# ============================================================
# D3FEND ONTOLOGY LOADING
# ============================================================

@lru_cache(maxsize=1)
def _load_d3fend_technique_tactics():
    """
    Load ATT&CK technique → tactic mapping from D3FEND ontology.
    Returns dict: technique_id → set of tactic names.
    """
    ttl_dir = Path(__file__).resolve().parent / "D3fend_CAD" / "ontology" / "src" / "ontology"
    main_ttl = ttl_dir / "d3fend-protege.ttl"

    if not main_ttl.exists():
        print("[D3FEND-VAL] Ontology not found, skipping tactic validation")
        return {}

    g = Graph()
    g.parse(str(main_ttl), format="turtle")

    D3F = Namespace("http://d3fend.mitre.org/ontologies/d3fend.owl#")

    TACTIC_CLASSES = {
        "CollectionTechnique": "Collection",
        "CommandAndControlTechnique": "CommandAndControl",
        "CredentialAccessTechnique": "CredentialAccess",
        "DefenseEvasionTechnique": "DefenseEvasion",
        "DiscoveryTechnique": "Discovery",
        "ExecutionTechnique": "Execution",
        "ExfiltrationTechnique": "Exfiltration",
        "ImpactTechnique": "Impact",
        "InitialAccessTechnique": "InitialAccess",
        "LateralMovementTechnique": "LateralMovement",
        "PersistenceTechnique": "Persistence",
        "PrivilegeEscalationTechnique": "PrivilegeEscalation",
        "ReconnaissanceTechnique": "Discovery",
        "ResourceDevelopmentTechnique": "ResourceDevelopment",
    }

    # Get all attack-ids
    technique_ids = {}
    for s, p, o in g.triples((None, D3F["attack-id"], None)):
        technique_ids[s] = str(o).strip()

    # Walk subClassOf chain to find tactic
    technique_to_tactic = {}
    for uri, tid in technique_ids.items():
        if not tid.startswith("T"):
            continue
        tactics = set()
        for _, _, parent in g.triples((uri, RDFS.subClassOf, None)):
            pname = str(parent).split("#")[-1]
            if pname in TACTIC_CLASSES:
                tactics.add(TACTIC_CLASSES[pname])
            for _, _, gp in g.triples((parent, RDFS.subClassOf, None)):
                gpname = str(gp).split("#")[-1]
                if gpname in TACTIC_CLASSES:
                    tactics.add(TACTIC_CLASSES[gpname])
        if tactics:
            technique_to_tactic[tid] = tactics

    print(f"[D3FEND-VAL] Loaded tactic mappings for {len(technique_to_tactic)} techniques")
    return technique_to_tactic


# ============================================================
# VALIDATION GATE
# ============================================================

def _build_technique_keywords():
    """Build keyword sets per technique from MITRE name + first sentence of description."""
    from plugins.mcp.app.utilities.cti_taxonomy_loader import build_normalized_attack_patterns
    import re as _re
    techniques, _ = build_normalized_attack_patterns()
    GENERIC = {"and","the","via","for","from","with","over","non","pre","sub","based","standard","multi"}
    STOP = {"adversaries","adversary","techniques","information","example",
            "system","systems","within","including","specific","through",
            "between","perform","against","during","access","command",
            "network","software"}
    result = {}
    for t in techniques:
        name = (t.get("name") or "").lower()
        desc = (t.get("description") or "")[:300].lower()
        name_words = set(_re.findall(r"[a-z]{4,}", name)) - GENERIC
        first_sent = desc.split(".")[0] if "." in desc else desc
        desc_words = set(_re.findall(r"[a-z]{5,}", first_sent)) - GENERIC - STOP
        result[t["id"]] = name_words | desc_words
    return result


def filter_by_keyword_evidence(
    techniques: list[dict],
    source_text: str,
    min_overlap: int = 2,
) -> list[dict]:
    """
    Filter techniques by keyword evidence: technique name/description
    keywords must appear in the source text.

    Keeps techniques that:
    - Have >=min_overlap keyword matches with source text
    - Were from explicit T-number extraction
    - Were confirmed by LLM validation
    """
    if not techniques or not source_text:
        return techniques

    tech_kw = _build_technique_keywords()
    text_words = set(re.findall(r"[a-z]{4,}", source_text.lower()))

    kept = []
    dropped = 0
    for t in techniques:
        tid = t.get("id", "")
        kw = tech_kw.get(tid, set())
        overlap = kw & text_words

        if (len(overlap) >= min_overlap or
                t.get("source") == "explicit" or
                t.get("x_llm_validated") is True):
            kept.append(t)
        else:
            dropped += 1

    if dropped:
        print(f"[D3FEND-KW] {len(techniques)} → {len(kept)} "
              f"({dropped} dropped, no keyword evidence)")
    return kept


def validate_techniques_by_tactic(
    techniques: list[dict],
    source_text: str,
    strict: bool = True,
) -> list[dict]:
    """
    Filter candidate ATT&CK techniques using D3FEND tactic relevance.

    For each candidate technique:
    1. Look up its tactic classification in D3FEND
    2. Check if that tactic is evidenced in the source text
    3. Keep if tactic matches; drop if not (strict mode)
       or downgrade confidence (non-strict mode)

    This is universal — works for any CTI data, not adversary-specific.
    The tactic signals come from the actual source text.
    """
    if not source_text:
        return techniques

    technique_tactics = _load_d3fend_technique_tactics()
    if not technique_tactics:
        return techniques

    text_tactics = extract_tactic_signals(source_text)
    if not text_tactics:
        # Can't determine tactics from text — pass through
        return techniques

    print(f"[D3FEND-VAL] Detected tactics in text: {sorted(text_tactics)}")

    kept = []
    dropped = 0

    for tech in techniques:
        tid = tech.get("id", "")
        source = tech.get("source", "")
        tech_tactics = technique_tactics.get(tid, set())

        if not tech_tactics:
            # Unknown technique in D3FEND — keep it (don't filter what we can't validate)
            kept.append(tech)
            continue

        # Check tactic overlap
        if tech_tactics & text_tactics:
            # Tactic is relevant to source text — keep
            kept.append(tech)
        elif source == "ontology-inference" and strict:
            # Ontology-inferred technique with irrelevant tactic — drop
            dropped += 1
        else:
            # Non-ontology technique (explicit, semantic) — keep with lower confidence
            tech = dict(tech)
            tech["confidence"] = min(tech.get("confidence", 1.0), 0.5)
            tech["x_d3fend_tactic_mismatch"] = True
            kept.append(tech)

    print(f"[D3FEND-VAL] kept={len(kept)} dropped={dropped} "
          f"(text_tactics={len(text_tactics)}, strict={strict})")
    return kept
