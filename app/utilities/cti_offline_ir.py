"""
cti_offline_ir.py - Offline IR Extraction (No LLM Required)

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

from plugins.mcp.app.utilities.nlp_model import get_nlp


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
    # 1. MITRE taxonomy scan - find known entities in text
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

    # ---------------------------------------------------------
    # Actor inference: use MITRE entity frequency + title + first paragraph
    # The most frequently mentioned MITRE malware/group is the primary actor
    # ---------------------------------------------------------
    from collections import Counter as _Counter

    # Only MITRE intrusion sets are candidates. Ransomware families are the
    # most repeated name in a report, so including malware here made the
    # adversary get named after the payload rather than the actor.
    group_set = set()
    for obj in mitre_index.values():
        if obj[0] == "threat_actors":
            group_set.add(obj[1].lower())

    actor_freq = _Counter()
    for name in group_set:
        if len(name) < 3:
            continue
        pattern = r"\b" + re.escape(name) + r"\b"
        count = len(re.findall(pattern, text_lower))
        if count > 0:
            actor_freq[name] = count

    # Title bonus: entities in the first line get a boost
    first_line = text.strip().split("\n")[0].lower()
    for name in actor_freq:
        if name in first_line:
            actor_freq[name] += 3  # title mention is strong signal

    # First paragraph bonus
    first_para = text.strip().split("\n\n")[0].lower() if "\n\n" in text else text_lower[:500]
    for name in actor_freq:
        if name in first_para:
            actor_freq[name] += 1

    # Add top actors (by frequency) that aren't already in IR
    for name, count in actor_freq.most_common(3):
        if count < 2:
            continue
        key = ("threat_actors", name)
        if key not in seen_entities:
            seen_entities.add(key)
            canonical, description = name, ""
            entry = mitre_index.get(name)
            if entry:
                canonical, description = entry[1], entry[2]
            ir["threat_actors"].append({
                "name": canonical,
                "description": description,
                "source": "frequency-inference",
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
    # 3. spaCy NER - catch entities MITRE/well-known missed
    # ---------------------------------------------------------
    nlp = get_nlp()
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

    total = sum(len(ir[k]) for k in ir if isinstance(ir[k], list))
    print(f"[OFFLINE-IR] Total entities: {total} "
          f"(actors={len(ir['threat_actors'])} malware={len(ir['malware'])} "
          f"tools={len(ir['tools'])} infra={len(ir['infrastructure'])} "
          f"behaviors={len(ir['behaviors'])})")

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
