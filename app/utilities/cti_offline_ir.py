"""
cti_offline_ir.py — Offline IR Extraction (No LLM Required)

Produces the same IR schema as cti_parsing.py but using only:
- spaCy NER for entity extraction
- MITRE ATT&CK taxonomy for entity classification
- Regex patterns for IOCs, T-numbers, tool names
- spaCy dependency parsing for behavior extraction

This is the "fast mode" / "offline mode" alternative to LLM-based
IR extraction. Trades ~15-20% recall for sub-second processing.
"""

import re
from functools import lru_cache

from plugins.mcp.app.utilities.nlp_model import nlp
from plugins.mcp.app.utilities.cti_linguistics import extract_hashes, extract_commands


# ============================================================
# MITRE ENTITY LOOKUP
# ============================================================

@lru_cache(maxsize=1)
def _build_mitre_entity_index():
    """
    Build a case-insensitive index of all MITRE-known entity names.
    Returns: {lowercase_name: (category, name, description)}
    """
    from plugins.mcp.app.utilities.cti_taxonomy_loader import load_mitre_taxonomy
    tax = load_mitre_taxonomy()

    index = {}

    for obj_id, obj in tax.get("tools", {}).items():
        name = obj.get("name", "").strip()
        desc = obj.get("description", "")[:200] if obj.get("description") else ""
        if name:
            index[name.lower()] = ("tools", name, desc)
            for alias in obj.get("x_mitre_aliases", []):
                index[alias.lower()] = ("tools", alias, desc)

    for obj_id, obj in tax.get("malware", {}).items():
        name = obj.get("name", "").strip()
        desc = obj.get("description", "")[:200] if obj.get("description") else ""
        if name:
            index[name.lower()] = ("malware", name, desc)
            for alias in obj.get("x_mitre_aliases", []):
                index[alias.lower()] = ("malware", alias, desc)

    for obj_id, obj in tax.get("groups", {}).items():
        name = obj.get("name", "").strip()
        desc = obj.get("description", "")[:200] if obj.get("description") else ""
        if name:
            index[name.lower()] = ("threat_actors", name, desc)
            for alias in obj.get("x_mitre_aliases", []):
                index[alias.lower()] = ("threat_actors", alias, desc)

    return index


# ============================================================
# WELL-KNOWN CTI ENTITY PATTERNS
# ============================================================

# Tools commonly seen in CTI that may not be in MITRE taxonomy
WELL_KNOWN_TOOLS = {
    "anydesk", "teamviewer", "megasync", "rclone", "winrar", "7zip",
    "winscp", "filezilla", "ngrok", "chisel", "ligolo", "rsync",
    "veeam", "acronis", "nmap", "masscan", "advanced ip scanner",
    "sharphound", "bloodhound", "rubeus", "seatbelt", "certutil",
    "bitsadmin", "wevtutil", "bcdedit", "vssadmin", "fsutil",
    "wmic", "net.exe", "sc.exe", "reg.exe", "tasklist",
    "procdump", "dumpert", "nanodump", "ppldump",
}

# Infrastructure patterns (regex)
INFRA_PATTERNS = [
    (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "IPv4 address"),
    (r"\b[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.[a-z]{2,}\b", "domain"),
    (r"\b(?:https?://\S+)\b", "URL"),
]


# ============================================================
# OFFLINE IR EXTRACTION
# ============================================================

def extract_ir_offline(text: str) -> dict:
    """
    Extract IR from CTI text without any LLM calls.

    Uses:
    1. spaCy NER for organizations and named entities
    2. MITRE taxonomy matching for tool/malware/group classification
    3. Regex for IOCs and infrastructure
    4. spaCy dependency parsing for behaviors

    Returns the same schema as cti_parsing.extract_ir().
    """
    print("[OFFLINE-IR] Starting offline extraction")

    mitre_index = _build_mitre_entity_index()

    ir = {
        "threat_actors": [],
        "malware": [],
        "tools": [],
        "infrastructure": [],
        "attack_patterns": [],
        "behaviors": [],
        "relationships": [],
    }

    seen_entities = set()
    text_lower = text.lower()

    # ---------------------------------------------------------
    # 1. MITRE taxonomy scan — find known entities in text
    # ---------------------------------------------------------
    for name_lower, (category, canonical_name, desc) in mitre_index.items():
        if len(name_lower) < 3:
            continue
        # Require word boundary match to avoid substring false positives
        pattern = r"\b" + re.escape(name_lower) + r"\b"
        if re.search(pattern, text_lower):
            key = (category, canonical_name.lower())
            if key not in seen_entities:
                seen_entities.add(key)
                ir[category].append({
                    "name": canonical_name,
                    "description": desc,
                    "source": "mitre-taxonomy",
                })

    # Promote malware that acts as actor names in text
    # (e.g., "BlackCat exploits..." → BlackCat is also an actor)
    doc = nlp(text[:nlp.max_length])
    malware_names = {m["name"].lower() for m in ir["malware"]}

    for sent in doc.sents:
        root = sent.root
        if root.pos_ != "VERB":
            continue
        # Check if subject is a known malware name used as agent
        for child in root.children:
            if child.dep_ in ("nsubj", "nsubjpass"):
                subj = child.text.strip().lower()
                if subj in malware_names or any(subj in m for m in malware_names):
                    # This malware is used as an actor in the text
                    for m in ir["malware"]:
                        if subj in m["name"].lower():
                            actor_key = ("threat_actors", m["name"].lower())
                            if actor_key not in seen_entities:
                                seen_entities.add(actor_key)
                                ir["threat_actors"].append({
                                    "name": m["name"],
                                    "description": f"Threat actor (inferred from malware name used as agent)",
                                    "source": "agent-inference",
                                })
                            break

    # Also add actors from title-case proper nouns near attack verbs
    ATTACK_VERBS = {"exploit", "deploy", "execute", "target", "compromise",
                    "attack", "encrypt", "exfiltrate", "disable", "leverage"}
    for sent in doc.sents:
        for tok in sent:
            if tok.lemma_.lower() in ATTACK_VERBS:
                for child in tok.children:
                    if child.dep_ == "nsubj" and child.text[0].isupper():
                        name = child.text.strip()
                        key = ("threat_actors", name.lower())
                        if key not in seen_entities and len(name) > 2:
                            seen_entities.add(key)
                            ir["threat_actors"].append({
                                "name": name,
                                "description": "",
                                "source": "verb-agent-inference",
                            })

    mitre_found = sum(len(ir[k]) for k in ("threat_actors", "malware", "tools"))
    print(f"[OFFLINE-IR] MITRE taxonomy matches: {mitre_found}")

    # ---------------------------------------------------------
    # 2. Well-known tools scan
    # ---------------------------------------------------------
    for tool in WELL_KNOWN_TOOLS:
        pattern = r"\b" + re.escape(tool) + r"\b"
        if re.search(pattern, text_lower):
            key = ("tools", tool)
            if key not in seen_entities:
                seen_entities.add(key)
                # Find the sentence containing the tool for description
                for sent in text.split("."):
                    if tool in sent.lower():
                        desc = sent.strip()[:150]
                        break
                else:
                    desc = ""
                ir["tools"].append({
                    "name": tool.title() if not any(c.isupper() for c in tool) else tool,
                    "description": desc,
                    "source": "well-known",
                })

    # ---------------------------------------------------------
    # 3. spaCy NER — catch entities MITRE/well-known missed
    # ---------------------------------------------------------
    doc = nlp(text[:nlp.max_length])

    for ent in doc.ents:
        if ent.label_ in ("ORG", "PRODUCT"):
            name = ent.text.strip()
            if len(name) < 3 or len(name) > 40:
                continue
            # Skip if already found
            name_lower_ent = name.lower()
            if any(name_lower_ent in k[1] for k in seen_entities):
                continue
            # Check if it looks like a CTI entity (not a media company, etc.)
            if _is_likely_cti_entity(name, text):
                key = ("tools", name_lower_ent)
                if key not in seen_entities:
                    seen_entities.add(key)
                    ir["tools"].append({
                        "name": name,
                        "description": "",
                        "source": "spacy-ner",
                    })

    # ---------------------------------------------------------
    # 4. Infrastructure extraction (regex)
    # ---------------------------------------------------------
    for pattern, infra_type in INFRA_PATTERNS:
        for match in re.finditer(pattern, text):
            value = match.group(0)
            # Skip common false positives
            if infra_type == "domain" and value in ("example.com", "attack.mitre.org"):
                continue
            if infra_type == "IPv4 address" and value.startswith(("0.", "127.", "255.")):
                continue
            key = ("infrastructure", value.lower())
            if key not in seen_entities:
                seen_entities.add(key)
                ir["infrastructure"].append({
                    "name": value,
                    "description": infra_type,
                    "source": "regex",
                })

    # ---------------------------------------------------------
    # 5. Behavior extraction (spaCy dependency parsing)
    # ---------------------------------------------------------
    for sent in doc.sents:
        root = sent.root
        if root.pos_ != "VERB":
            continue

        # Skip reporter verbs
        if root.lemma_.lower() in {
            "report", "describe", "note", "observe", "identify",
            "analyze", "assess", "document", "publish", "state",
        }:
            continue

        # Extract verb + object
        obj = None
        for child in root.children:
            if child.dep_ in ("dobj", "pobj", "attr"):
                obj = " ".join(t.text for t in child.subtree).strip()
                break

        if obj and len(obj) > 5:
            behavior = f"{root.lemma_} {obj}"
            ir["behaviors"].append({
                "description": behavior,
                "source": "spacy-dep",
            })

    # Dedupe behaviors by content
    seen_beh = set()
    unique_beh = []
    for b in ir["behaviors"]:
        key = b["description"].lower()
        if key not in seen_beh:
            seen_beh.add(key)
            unique_beh.append(b)
    ir["behaviors"] = unique_beh[:20]  # Cap at 20

    # ---------------------------------------------------------
    # 6. Attack pattern extraction from text
    # ---------------------------------------------------------
    # These are attack descriptions, not MITRE IDs (those come later)
    attack_indicators = [
        (r"(?:exploit|leverage)\w*\s+(?:vulnerabilit|CVE|flaw)\w*[^.]*", "vulnerability exploitation"),
        (r"(?:lateral\s+movement|move\s+laterally)[^.]*", "lateral movement"),
        (r"(?:exfiltrat|steal|theft)[^.]*data[^.]*", "data exfiltration"),
        (r"(?:encrypt|ransom)\w*[^.]*files?[^.]*", "file encryption"),
        (r"(?:credential|password)\s+(?:dump|harvest|steal|extract)[^.]*", "credential access"),
        (r"(?:disable|tamper|bypass)\w*\s+(?:security|defender|antivirus|av)[^.]*", "defense evasion"),
        (r"(?:shadow\s+cop(?:y|ies)|vssadmin)[^.]*(?:delet|remov)[^.]*", "recovery inhibition"),
        (r"(?:registry|reg\.exe)\s+(?:modif|set|add|change)[^.]*", "registry modification"),
        (r"(?:scheduled?\s+task|cron|at\s+job)[^.]*", "scheduled execution"),
    ]

    for pattern, label in attack_indicators:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for m in matches:
            ir["attack_patterns"].append({
                "description": m.group(0).strip()[:200],
                "source": "regex-pattern",
            })
            break  # One match per pattern

    total = sum(len(ir[k]) for k in ir if isinstance(ir[k], list))
    print(f"[OFFLINE-IR] Total entities: {total} "
          f"(actors={len(ir['threat_actors'])} malware={len(ir['malware'])} "
          f"tools={len(ir['tools'])} infra={len(ir['infrastructure'])} "
          f"behaviors={len(ir['behaviors'])} patterns={len(ir['attack_patterns'])})")

    return ir


def _is_likely_cti_entity(name: str, context: str) -> bool:
    """
    Heuristic: is this spaCy NER entity likely a CTI-relevant tool/malware?
    """
    name_lower = name.lower()

    # Skip common non-CTI organizations
    SKIP = {
        "palo alto", "symantec", "microsoft", "sophos", "cisco",
        "trend micro", "kroll", "group-ib", "varonis", "unit 42",
        "talos", "mitre", "nist",
    }
    for skip in SKIP:
        if skip in name_lower:
            return False

    # CTI-relevant if near attack-related words
    context_lower = context.lower()
    idx = context_lower.find(name_lower)
    if idx >= 0:
        window = context_lower[max(0, idx - 100):idx + len(name) + 100]
        cti_cues = ["malware", "tool", "ransomware", "exploit", "attack",
                    "deploy", "execute", "lateral", "credential", "encrypt"]
        if any(cue in window for cue in cti_cues):
            return True

    return False
