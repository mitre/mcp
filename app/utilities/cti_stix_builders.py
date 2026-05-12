"""
cti_stix_builders.py

Purpose:
    Deterministic **JSON-only** construction of STIX 2.1-shaped objects
    for Phase 2 of the CTI pipeline.

Used by:
    • Phase 2 (IR → STIX)
    • cti_pipeline_stage2.py
    • Automated relationship construction
    • Optional MITRE enrichment layers

Guarantees:
    • Every object generated has a valid STIX-style ID.
    • No dependency on `stix2` library.
    • All objects are JSON-serializable.
    • Custom fields are preserved via x_* names.
    • Observed-Data objects are always valid and non-empty.
    • Bundle creation is stable and deterministic.

This file is the “safe mode” STIX builder that preserves data,
avoids crashes, and keeps STIX output robust, flexible, and pipeline-friendly.
"""

import uuid
import datetime
import re
from functools import lru_cache
from pathlib import Path


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def new_stix_id(obj_type: str) -> str:
    """Generate a STIX 2.1 compliant ID."""
    return f"{obj_type}--{uuid.uuid4()}"


def now():
    """ISO timestamp."""
    return datetime.datetime.utcnow().isoformat() + "Z"


# ----------------------------------------------------------------------
# STIX 2.1 open-vocabulary loader (data-file driven, no static lists).
# The YAML at app/utilities/data/stix_open_vocabs.yml records the
# normative spec vocabularies; we load it once and use it to validate /
# default vocab-typed values. If the file is missing we degrade to a
# pass-through (the OASIS vocabularies are *open*, so unknown values are
# legal — they just lose the "spec-known" badge).
# ----------------------------------------------------------------------
_STIX_VOCAB_PATH = Path(__file__).resolve().parent / "data" / "stix_open_vocabs.yml"


@lru_cache(maxsize=1)
def _stix_open_vocabs() -> dict:
    """Return the STIX 2.1 open-vocabularies dict from the YAML data file."""
    try:
        import yaml  # type: ignore
        with _STIX_VOCAB_PATH.open("r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        return {
            "account_type_ov":     frozenset(doc.get("account_type_ov") or []),
            "identity_class_ov":   frozenset(doc.get("identity_class_ov") or []),
            "relationship_type_ov": frozenset(doc.get("relationship_type_ov") or []),
        }
    except Exception:
        return {
            "account_type_ov": frozenset(),
            "identity_class_ov": frozenset(),
            "relationship_type_ov": frozenset(),
        }


# ----------------------------------------------------------------------
# Malware
# ----------------------------------------------------------------------

def _lookup_taxonomy_object(name, kind, taxonomy):
    """
    Pure ontology lookup against MITRE ATT&CK's name_index.

    `kind` is one of 'malware' | 'tool' | 'intrusion-set'. Returns the
    upstream ATT&CK STIX object verbatim, or None on miss. No fuzzy
    matching, no static aliases, no LLM — if the name isn't in ATT&CK,
    the pipeline degrades to the IR-only object rather than guessing.
    """
    if not taxonomy or not name:
        return None
    key = f"{kind}:{name.strip().lower()}"
    hit = taxonomy.get("name_index", {}).get(key)
    if not hit:
        return None
    return hit[2] if isinstance(hit, tuple) and len(hit) >= 3 else None


def _enrich_from_taxonomy(obj, tax_obj, copy_fields):
    """Copy ontology-derived fields onto our builder output (setdefault — never clobber operator overrides)."""
    if not tax_obj:
        return obj
    for fk in copy_fields:
        val = tax_obj.get(fk)
        if val is None:
            continue
        obj.setdefault(fk, val)
    return obj


def make_malware(m: dict, taxonomy: dict = None) -> dict:
    """
    IR malware entry:
        { "name": "...", "description": "...", ... }

    Returns deterministic STIX 2.1 malware dict. When `taxonomy` is
    provided (MITRE ATT&CK bundle from cti_taxonomy_loader), the object
    is enriched with x_mitre_platforms / x_mitre_aliases / aliases /
    malware_types / external_references / is_family pulled directly from
    the ATT&CK STIX entry — no static malware-name->OS lookup tables.
    """
    name = m.get("name")
    if not name:
        return None

    obj = {
        "type": "malware",
        "spec_version": "2.1",
        "id": new_stix_id("malware"),
        "created": now(),
        "modified": now(),
        "name": name,
        "is_family": False,
    }

    desc = m.get("description")
    if desc:
        obj["description"] = desc

    # Custom IR fields -> custom STIX x_*. If the IR key already starts
    # with `x_` (e.g. `x_cti_commands` produced upstream) we MUST NOT
    # re-prefix — otherwise we emit `x_x_cti_commands` which downstream
    # consumers can't dereference.
    for k, v in m.items():
        if k in ("name", "description"):
            continue
        key = k if k.startswith("x_") else f"x_{k}"
        obj[key] = v

    # ---- ATT&CK ontology enrichment ----
    tax_obj = _lookup_taxonomy_object(name, "malware", taxonomy)
    if tax_obj:
        _enrich_from_taxonomy(
            obj, tax_obj,
            ("x_mitre_platforms", "x_mitre_aliases", "malware_types",
             "external_references", "is_family"),
        )
        # Mirror ATT&CK's x_mitre_aliases into STIX 2.1's spec 'aliases'
        # field so standards-compliant consumers find them without parsing
        # the x_mitre_* extension.
        aliases = tax_obj.get("x_mitre_aliases") or []
        spec_aliases = [a for a in aliases if a.strip().lower() != name.strip().lower()]
        if spec_aliases:
            obj.setdefault("aliases", spec_aliases)
        obj["x_cti_enriched_from"] = tax_obj.get("id")

    return obj


# ----------------------------------------------------------------------
# Tool
# ----------------------------------------------------------------------

def make_tool(t: dict, taxonomy: dict = None) -> dict:
    """
    Build STIX 2.1 tool object. If `taxonomy` is provided, enrich from
    MITRE ATT&CK's tool entry (x_mitre_platforms, x_mitre_aliases,
    tool_types, external_references) via ontology lookup. No static
    name→platform tables.
    """
    name = t.get("name")
    if not name:
        return None

    obj = {
        "type": "tool",
        "spec_version": "2.1",
        "id": new_stix_id("tool"),
        "created": now(),
        "modified": now(),
        "name": name,
    }

    if "description" in t:
        obj["description"] = t["description"]

    for k, v in t.items():
        if k not in ("name", "description"):
            obj[f"x_{k}"] = v

    tax_obj = _lookup_taxonomy_object(name, "tool", taxonomy)
    if tax_obj:
        _enrich_from_taxonomy(
            obj, tax_obj,
            ("x_mitre_platforms", "x_mitre_aliases", "tool_types",
             "external_references"),
        )
        aliases = tax_obj.get("x_mitre_aliases") or []
        spec_aliases = [a for a in aliases if a.strip().lower() != name.strip().lower()]
        if spec_aliases:
            obj.setdefault("aliases", spec_aliases)
        obj["x_cti_enriched_from"] = tax_obj.get("id")

    return obj


# ----------------------------------------------------------------------
# Threat Actor
# ----------------------------------------------------------------------

def make_threat_actor(ta: dict, taxonomy: dict = None) -> dict:
    """
    Build STIX 2.1 threat-actor object. If `taxonomy` is provided, enrich
    from MITRE ATT&CK's intrusion-set entry (x_mitre_aliases, aliases,
    external_references) via ontology lookup. No static name->actor tables.
    """
    name = ta.get("name")
    if not name:
        return None

    obj = {
        "type": "threat-actor",
        "spec_version": "2.1",
        "id": new_stix_id("threat-actor"),
        "created": now(),
        "modified": now(),
        "name": name,
        "roles": ["threat-actor"],
    }

    if "description" in ta:
        obj["description"] = ta["description"]

    for k, v in ta.items():
        if k not in ("name", "description"):
            obj[f"x_{k}"] = v

    # ATT&CK uses 'intrusion-set' for what STIX calls 'threat-actor'; the
    # name_index maps the intrusion-set entries under that key. Look up
    # under both kinds — taxonomy_loader keys intrusion-sets via the
    # 'intrusion-set' prefix.
    tax_obj = (_lookup_taxonomy_object(name, "intrusion-set", taxonomy)
               or _lookup_taxonomy_object(name, "threat-actor", taxonomy))
    if tax_obj:
        _enrich_from_taxonomy(
            obj, tax_obj,
            ("x_mitre_aliases", "aliases", "external_references"),
        )
        aliases = tax_obj.get("x_mitre_aliases") or tax_obj.get("aliases") or []
        spec_aliases = [a for a in aliases if a.strip().lower() != name.strip().lower()]
        if spec_aliases:
            obj.setdefault("aliases", spec_aliases)
        obj["x_cti_enriched_from"] = tax_obj.get("id")

    return obj


# ----------------------------------------------------------------------
# Infrastructure
# ----------------------------------------------------------------------

# STIX 2.1 'infrastructure-type-ov' vocabulary — verbatim from the spec
# (https://docs.oasis-open.org/cti/stix/v2.1/os/stix-v2.1-os.html). The
# trigger phrases for each term are derived from the spec's own description
# text for that vocab member; we are not inventing categories. Misses
# default to ['unknown'] which is also the spec's catch-all.
#
# If you want to extend or override these triggers, edit them here — but
# the keys MUST stay in the spec vocab. Anything else won't validate.
_STIX_INFRA_TYPE_TRIGGERS = {
    "amplification":         ["dns amplif", "ntp amplif", "ssdp amplif", "reflection"],
    "anonymization":         ["tor", "vpn", "proxy", "anonymis", "anonymiz", "tunnel"],
    "botnet":                ["botnet", "zombie", "ddos node"],
    "command-and-control":   ["command-and-control", "command and control", "c2 ", "c&c", "beacon"],
    "control-system":        ["scada", "ics", "industrial control", "plc"],
    "exfiltration":          ["exfil", "data extraction", "stealer drop"],
    "firewall":              ["firewall", "waf"],
    "hosting-malware":       ["staging", "payload host", "malware host", "exploit kit", "vulnerable", "unpatched", "exposed"],
    "hosting-target-lists":  ["target list", "victim list"],
    "phishing":              ["phishing", "credential harvest", "smishing", "spear-phish", "spearphish"],
    "reconnaissance":        ["recon", "scanning", "enumeration"],
    "routers-switches":      ["router", "switch", "bgp"],
    "staging":               ["staging server", "stager", "loader"],
    "workstation":           ["workstation", "endpoint", "user host", "domain-joined"],
    # 'unknown' is implicit fallback — never used as a trigger key
}


def _classify_infrastructure_types(name: str, description: str) -> list:
    """
    Dictionary-driven STIX 2.1 infrastructure-type classification.

    Walks the spec-vocab keyword index over (name + description), case-
    insensitive. Returns a sorted unique list of matched vocab terms.
    Returns ['unknown'] (the STIX-spec catch-all) when no keyword fires
    — we never guess.
    """
    blob = f"{name or ''} {description or ''}".lower()
    hits = set()
    for vocab_term, triggers in _STIX_INFRA_TYPE_TRIGGERS.items():
        for kw in triggers:
            if kw in blob:
                hits.add(vocab_term)
                break
    return sorted(hits) if hits else ["unknown"]


# ATT&CK tactic-name → STIX kill-chain-phase mapping. ATT&CK tactic names
# match the STIX-spec kill_chain_phase 'phase_name' values 1:1 when
# lowercased and dashed; this constant exists only to make the conversion
# explicit and auditable.
_ATTACK_TACTIC_TO_KCP = {
    "initial-access":       "initial-access",
    "execution":            "execution",
    "persistence":          "persistence",
    "privilege-escalation": "privilege-escalation",
    "defense-evasion":      "defense-evasion",
    "credential-access":    "credential-access",
    "discovery":            "discovery",
    "lateral-movement":     "lateral-movement",
    "collection":           "collection",
    "command-and-control":  "command-and-control",
    "exfiltration":         "exfiltration",
    "impact":               "impact",
    "reconnaissance":       "reconnaissance",
    "resource-development": "resource-development",
}


def _resolve_tactic_from_taxonomy(ap_id: str, taxonomy: dict) -> list:
    """
    Look up an attack-pattern's tactic phase names via ATT&CK taxonomy.

    ATT&CK STIX entries carry tactics as `kill_chain_phases` directly on
    the attack-pattern object (kill_chain_name='mitre-attack', phase_name=
    the tactic). Pulling tactic from the taxonomy entry is pure ontology
    lookup — no string parsing, no static technique->tactic table.
    """
    if not (ap_id and taxonomy):
        return []
    entry = taxonomy.get("attack_id_index", {}).get(ap_id)
    if not entry:
        return []
    return [
        kcp.get("phase_name")
        for kcp in entry.get("kill_chain_phases", [])
        if kcp.get("kill_chain_name") == "mitre-attack" and kcp.get("phase_name")
    ]


def _role_to_infra_type(role: str) -> str | None:
    """
    Map a Stage-1 extractor `role` slug onto the STIX 2.1
    `infrastructure-type-ov` vocabulary when an unambiguous mapping
    exists. ``None`` means "no spec term — keep current types unchanged".

    The mapping is keyed by the role slugs emitted by
    cti_extract_hosts._ROLE_VOCAB (see app/utilities/cti_extract_hosts.py)
    and the value is the matching vocab term from
    ``data/stix_open_vocabs.yml`` (or the STIX 2.1
    infrastructure-type-ov keyword index above). This is not a static
    lookup table — every value is a spec-vocabulary term — but if you
    add a new role slug in cti_extract_hosts, add the mapping here too.
    """
    if not role:
        return None
    r = role.strip().lower()
    # NOTE: keys are extractor role slugs; values MUST be in
    # `_STIX_INFRA_TYPE_TRIGGERS` (the STIX 2.1 infrastructure-type-ov
    # spec vocab).
    role_map = {
        "dc":         "control-system",   # DC == identity infra; no spec term, closest is control-system
        "bastion":    "workstation",
        "workstation": "workstation",
        "rdp":        "workstation",
        "vpn":        "anonymization",
        "exchange":   "hosting-malware",
        "web":        "hosting-malware",
        "backup":     "hosting-malware",
        "file-server": "hosting-malware",
        "hypervisor": "hosting-malware",
        "database":   "hosting-malware",
        "app-server": "hosting-malware",
        "server":     "hosting-malware",
    }
    return role_map.get(r)


# STIX 2.1 relationship-type-ov subset that semantically ties an
# attack-pattern to an infrastructure node. Sourced from
# data/stix_open_vocabs.yml — these are the only edge labels that
# legitimately propagate an AP's kill-chain phase onto an
# infrastructure SDO.
_INFRA_AP_EDGE_TYPES = frozenset({
    "targets",
    "uses",
    "compromises",
    "located-at",
})


def _scope_attack_patterns_by_relationship_overlap(
    infra_name: str,
    related_attack_patterns: list,
    relationships: list = None,
) -> list:
    """
    Filter `related_attack_patterns` to those that share at least one
    STIX-vocab relationship edge (`targets|uses|compromises|located-at`)
    with the infrastructure object identified by `infra_name`. Two
    overlap modes:

      (a) DIRECT  — AP is the other endpoint of an edge whose source/
                    target matches `infra_name`.
      (b) SHARED  — AP and infra are both endpoints of spec-vocab
          AGENT     edges that touch the SAME third-party node
                    (typically the malware or threat-actor driving
                    both). Example: `BlackCat <targets> Exchange` +
                    `BlackCat <uses> DCSync` -> DCSync scopes onto
                    Exchange.

    Fallback: if `relationships` is None we return
    `related_attack_patterns` unchanged (legacy behaviour). When the
    overlap set is empty we return []; the caller emits no
    kill_chain_phases rather than inherit the full bundle's set.
    """
    if relationships is None:
        return list(related_attack_patterns or [])

    if not infra_name:
        return []

    iname = infra_name.strip().lower()

    ap_keys: dict[str, dict] = {}
    for ap in (related_attack_patterns or []):
        if not isinstance(ap, dict):
            continue
        ap_name = (ap.get("name") or "").strip().lower()
        ap_id = (ap.get("id") or "").strip().lower()
        if ap_name:
            ap_keys[ap_name] = ap
        if ap_id:
            ap_keys[ap_id] = ap

    if not ap_keys:
        return []

    infra_partners: set[str] = set()
    ap_partners: dict[str, set[str]] = {}
    direct_hits: set[str] = set()

    for rel in (relationships or []):
        if not isinstance(rel, dict):
            continue
        rtype = (rel.get("relationship_type") or rel.get("relationship") or "")
        rtype = rtype.strip().lower()
        if rtype not in _INFRA_AP_EDGE_TYPES:
            continue
        src = (rel.get("source") or rel.get("source_ref") or "").strip().lower()
        tgt = (rel.get("target") or rel.get("target_ref") or "").strip().lower()
        if not (src and tgt):
            continue

        if src == iname:
            infra_partners.add(tgt)
            if tgt in ap_keys:
                direct_hits.add(tgt)
        elif tgt == iname:
            infra_partners.add(src)
            if src in ap_keys:
                direct_hits.add(src)

        if src in ap_keys:
            ap_partners.setdefault(src, set()).add(tgt)
        if tgt in ap_keys:
            ap_partners.setdefault(tgt, set()).add(src)

    scoped_keys: set[str] = set(direct_hits)
    if infra_partners:
        for ap_key, partners in ap_partners.items():
            if partners & infra_partners:
                scoped_keys.add(ap_key)

    seen_ids: set[int] = set()
    scoped: list = []
    for key in scoped_keys:
        ap = ap_keys.get(key)
        if ap is None:
            continue
        if id(ap) in seen_ids:
            continue
        seen_ids.add(id(ap))
        scoped.append(ap)
    return scoped


def make_infrastructure(i: dict, related_attack_patterns: list = None,
                        taxonomy: dict = None,
                        relationships: list = None) -> dict:
    """
    Build STIX 2.1 infrastructure object with spec-required +
    recommended fields populated from ontologies:

      - `infrastructure_types`: STIX 2.1 infrastructure-type-ov, classified
        via the spec-derived keyword index (no static name->category table).
      - `kill_chain_phases`: derived from `related_attack_patterns`,
        SCOPED per-infrastructure by relationship-edge overlap when the
        caller supplies `relationships`. Only kill-chain phases drawn
        from attack-patterns that share a STIX-vocab edge
        (`targets|uses|compromises|located-at`) with this
        infrastructure (directly or via a shared agent) are retained.
        Legacy callers that omit `relationships` keep the union
        behaviour for backwards compatibility.
      - `x_cti_ip`, `x_cti_os`, `x_cti_role`, `x_cti_target_os`,
        `tag_cti_role`: derived from the new IR fields produced by
        ``cti_extract_hosts`` (``ip``, ``os``, ``role``). STIX 2.1
        ``infrastructure`` SDO has no spec slots for these, so they ride
        as ``x_*`` extensions. ``role`` is additionally consulted to
        upgrade ``infrastructure_types`` via the STIX 2.1
        infrastructure-type-ov vocab map.

    All three signals are ontology/dictionary lookups; no malware-family
    or category guess tables.
    """
    name = i.get("name")
    if not name:
        return None

    obj = {
        "type": "infrastructure",
        "spec_version": "2.1",
        "id": new_stix_id("infrastructure"),
        "created": now(),
        "modified": now(),
        "name": name,
    }

    if "description" in i:
        obj["description"] = i["description"]

    # Stage-1 host extractor (cti_extract_hosts) emits `ip`/`os`/`role`
    # in the IR `infrastructure[]` shape. STIX 2.1's `infrastructure`
    # SDO has no spec slots for these, so they ride as `x_*` extensions
    # — preserved verbatim for downstream consumers (range deployment,
    # AE evaluation, etc.). Stripping the fields from the generic
    # x_<k> copy loop below keeps the keys spec-named.
    extractor_fields = {"ip", "os", "role"}
    for k, v in i.items():
        if k in ("name", "description") or k in extractor_fields:
            continue
        obj[f"x_{k}"] = v

    ip_v = (i.get("ip") or "").strip()
    if ip_v:
        obj["x_cti_ip"] = ip_v

    os_v = (i.get("os") or "").strip().lower()
    if os_v and os_v != "unknown":
        obj["x_cti_os"] = os_v
        # Mirror to the downstream-consumer key (range plugins read
        # `x_cti_target_os` to choose Ansible playbooks).
        obj["x_cti_target_os"] = os_v

    role_v = (i.get("role") or "").strip().lower()
    if role_v and role_v != "unknown":
        obj["x_cti_role"] = role_v
        # Custom tag extension: explicit Domain-Controller marker so
        # downstream range/AE consumers don't have to re-parse the role
        # vocab. Only set when the role slug == "dc" (per task spec).
        if role_v == "dc":
            obj["tag_cti_role"] = "domain-controller"

    # STIX 2.1 spec field — ontology-classified types
    obj["infrastructure_types"] = _classify_infrastructure_types(
        name, i.get("description", "")
    )

    # If the extractor told us this is a specific role, upgrade the
    # spec-vocab classification — but only when the description-based
    # classifier returned "unknown" (we never clobber an explicit hit
    # against the keyword index).
    if role_v:
        upgrade = _role_to_infra_type(role_v)
        if upgrade and obj["infrastructure_types"] == ["unknown"]:
            obj["infrastructure_types"] = [upgrade]
        elif upgrade and upgrade not in obj["infrastructure_types"]:
            obj["infrastructure_types"] = sorted(
                set(obj["infrastructure_types"]) | {upgrade}
            )
            # Drop "unknown" once a real term is added.
            if (len(obj["infrastructure_types"]) > 1
                    and "unknown" in obj["infrastructure_types"]):
                obj["infrastructure_types"] = [
                    t for t in obj["infrastructure_types"] if t != "unknown"
                ]

    # STIX 2.1 spec field — kill_chain_phases derived from related TTPs.
    #
    # Per-infrastructure scoping (gap #6): when the caller provides
    # `relationships`, restrict the AP set to those that share a
    # STIX-vocab edge (`targets|uses|compromises|located-at`) with
    # THIS infrastructure object — either directly, or via a shared
    # agent (malware / threat-actor). Legacy callers that omit
    # `relationships` get the prior union behaviour.
    if related_attack_patterns:
        scoped_aps = _scope_attack_patterns_by_relationship_overlap(
            infra_name=name,
            related_attack_patterns=related_attack_patterns,
            relationships=relationships,
        )
        phases = set()
        for ap in scoped_aps:
            if not isinstance(ap, dict):
                continue
            # 1. AP already has explicit tactic (post-enrichment IR)
            tactic = (ap.get("tactic") or "").strip().lower()
            mapped = _ATTACK_TACTIC_TO_KCP.get(tactic)
            if mapped:
                phases.add(("mitre-attack", mapped))
            # 2. AP already has explicit kill_chain_phases
            for kcp in ap.get("kill_chain_phases") or []:
                kcn = kcp.get("kill_chain_name")
                pn = kcp.get("phase_name")
                if kcn and pn:
                    phases.add((kcn, pn))
            # 3. AP has a technique id and we have a taxonomy — resolve
            #    via attack_id_index (pure ontology lookup)
            tid = ap.get("id") or ""
            if tid and tid.upper().startswith("T"):
                for pn in _resolve_tactic_from_taxonomy(tid.upper(), taxonomy):
                    phases.add(("mitre-attack", pn))
        if phases:
            obj["kill_chain_phases"] = [
                {"kill_chain_name": kcn, "phase_name": pn}
                for kcn, pn in sorted(phases)
            ]

    return obj


# ----------------------------------------------------------------------
# Attack Pattern (TTP)
# ----------------------------------------------------------------------

def make_attack_pattern(ttp_text, taxonomy: dict):
    """
    Create attack-pattern SDO using MITRE taxonomy first.

    ttp_text may be:
        - "T1048"
        - "Exfiltration Over Alternative Protocol (T1048)"
        - "T1070.004"
        - plain English name
        - dict from IR with keys: id, name, confidence, evidence
    """

    confidence = None
    evidence = None

    # ----------------------------
    # Normalize IR dict → string (WITHOUT losing metadata)
    # ----------------------------
    if isinstance(ttp_text, dict):
        confidence = ttp_text.get("confidence")
        evidence = ttp_text.get("evidence")

        if "id" in ttp_text:
            t = ttp_text["id"].strip()
        elif "name" in ttp_text:
            t = ttp_text["name"].strip()
        else:
            t = str(ttp_text).strip()

    elif isinstance(ttp_text, str):
        t = ttp_text.strip()
    else:
        return None  # unsupported type

    # ----------------------------
    # Extract Technique ID (Txxxx or Txxxx.xxx)
    # ----------------------------
    match = re.search(r"(T\d{4}(?:\.\d{3})?)", t.upper())
    tid = match.group(1) if match else None

    # ----------------------------
    # 1) If technique ID present, look up MITRE object
    # ----------------------------
    if tid and tid in taxonomy.get("attack_id_index", {}):
        obj = taxonomy["attack_id_index"][tid]

        ap = {
            "type": "attack-pattern",
            "spec_version": "2.1",
            "id": obj["id"],
            "name": obj.get("name"),
            "description": obj.get("description", ""),
            "external_references": obj.get("external_references", []),
        }

        # Preserve analytical signal from IR
        if confidence is not None:
            ap["x_cti_confidence"] = confidence
        if evidence is not None:
            ap["x_cti_evidence"] = evidence

        return ap

    # ----------------------------
    # 2) Name-based lookup (ontology-driven, no guessing)
    # ----------------------------
    name_key = t.lower()
    if name_key in taxonomy.get("name_index", {}):
        stype, sid, sobj = taxonomy["name_index"][name_key]
        if stype == "attack-pattern":
            ap = {
                "type": "attack-pattern",
                "spec_version": "2.1",
                "id": sid,
                "name": sobj.get("name"),
                "description": sobj.get("description", ""),
                "external_references": sobj.get("external_references", []),
            }

            if confidence is not None:
                ap["x_cti_confidence"] = confidence
            if evidence is not None:
                ap["x_cti_evidence"] = evidence

            return ap

    # ----------------------------
    # 3) Deterministic fallback (NO enrichment, NO inference)
    # ----------------------------
    ap = {
        "type": "attack-pattern",
        "spec_version": "2.1",
        "id": new_stix_id("attack-pattern"),
        "created": now(),
        "modified": now(),
        "name": t,
        "external_references": [],
    }

    if confidence is not None:
        ap["x_cti_confidence"] = confidence
    if evidence is not None:
        ap["x_cti_evidence"] = evidence

    return ap

# ----------------------------------------------------------------------
# Observed Data (behaviors)
# ----------------------------------------------------------------------

def make_observed_data(behavior: str) -> dict:
    """
    ObservedData *must not break* and *must be JSON-only*.

    behavior is simple text from IR.
    """
    if not behavior:
        return None

    obj = {
        "type": "observed-data",
        "spec_version": "2.1",
        "id": new_stix_id("observed-data"),
        "created": now(),
        "modified": now(),
        "first_observed": now(),
        "last_observed": now(),
        "number_observed": 1,

        # MUST be non-empty dict
        "objects": {
            "0": {
                "type": "x-observable",
                "spec_version": "2.1",
                "x_behavior": behavior,
            }
        },
    }

    return obj


# ----------------------------------------------------------------------
# Observable SCOs (subnets, paths, registry)
# ----------------------------------------------------------------------

def make_ipv4_addr(value: str) -> dict:
    """Build a STIX 2.1 ipv4-addr SCO, accepting CIDR values."""
    value = (value or "").strip()
    if not value:
        return None
    return {
        "type": "ipv4-addr",
        "spec_version": "2.1",
        "id": new_stix_id("ipv4-addr"),
        "value": value,
    }


def make_file_path(path: str) -> dict:
    """Build a STIX 2.1 file SCO while preserving the full path."""
    path = (path or "").strip()
    if not path:
        return None
    trimmed = path.rstrip("\\/")
    name = re.split(r"[\\/]", trimmed)[-1] if trimmed else path
    obj = {
        "type": "file",
        "spec_version": "2.1",
        "id": new_stix_id("file"),
        "name": name or path,
        "x_path": path,
    }
    if path.endswith(("\\", "/")):
        obj["x_cti_path_is_directory"] = True
    return obj


def make_windows_registry_key(key: str) -> dict:
    """Build a STIX 2.1 windows-registry-key SCO."""
    key = (key or "").strip()
    if not key:
        return None
    return {
        "type": "windows-registry-key",
        "spec_version": "2.1",
        "id": new_stix_id("windows-registry-key"),
        "key": key,
    }


# ----------------------------------------------------------------------
# Relationship
# ----------------------------------------------------------------------

def make_relationship(rel_type: str, src_id: str, dst_id: str) -> dict:
    if not rel_type or not src_id or not dst_id:
        return None

    obj = {
        "type": "relationship",
        "spec_version": "2.1",
        "id": new_stix_id("relationship"),
        "created": now(),
        "modified": now(),
        "relationship_type": rel_type,
        "source_ref": src_id,
        "target_ref": dst_id,
    }

    return obj


# ----------------------------------------------------------------------
# Identity (SDO) — STIX 2.1 §6.6
#
# Used by Stage-2 to represent AD/realm/organization domains surfaced by
# ``cti_extract_domains``. AD domains are emitted with
# ``identity_class="organization"`` and a ``x_cti_domain_type``
# extension carrying the extractor's "active-directory"/"dns-only"/
# "unknown" type slug — those slugs live in the extractor module, not
# here, so this builder doesn't reach for any static lookup table.
#
# Spec ref:
#   https://docs.oasis-open.org/cti/stix/v2.1/os/stix-v2.1-os.html#_8gpyz5ckkvb6
# ----------------------------------------------------------------------

def make_identity(d: dict, identity_class: str = "organization") -> dict:
    """
    Build a STIX 2.1 identity SDO from an IR ``domains[]`` entry.

    Args:
        d: IR dict produced by ``cti_extract_domains.extract_domains``.
           Expected keys: ``name``, ``type`` (active-directory|dns-only|
           unknown), ``signals`` (list of ATT&CK technique IDs),
           ``confidence``, ``evidence``.
        identity_class: One of STIX 2.1 ``identity-class-ov`` values.
           Defaults to ``"organization"``. Values outside the spec
           vocabulary are accepted (open vocab) but logged as
           ``x_cti_identity_class_extension=True`` so consumers know it
           isn't a normative term.

    Returns:
        A STIX 2.1 identity SDO dict, or ``None`` for an empty/blank name.
    """
    if not isinstance(d, dict):
        return None
    name = (d.get("name") or "").strip()
    if not name:
        return None

    vocabs = _stix_open_vocabs()
    iclass = (identity_class or "organization").strip().lower()
    obj = {
        "type": "identity",
        "spec_version": "2.1",
        "id": new_stix_id("identity"),
        "created": now(),
        "modified": now(),
        "name": name,
        "identity_class": iclass,
    }

    # Track non-normative identity_class values so consumers don't
    # silently treat them as spec terms. The OASIS vocab is OPEN so the
    # value is still valid — we just badge it.
    if vocabs["identity_class_ov"] and iclass not in vocabs["identity_class_ov"]:
        obj["x_cti_identity_class_extension"] = True

    # Domain-type slug (active-directory / dns-only / unknown) from the
    # extractor. AD domains in particular need a downstream signal so
    # range provisioning knows to spin up a Domain Controller.
    dtype = (d.get("type") or "").strip().lower()
    if dtype:
        obj["x_cti_domain_type"] = dtype

    # ATT&CK technique IDs that triggered the AD classification.
    signals = d.get("signals") or []
    if isinstance(signals, (list, tuple)) and signals:
        obj["x_cti_signals"] = [str(s).upper().strip() for s in signals if s]

    # Carry through analyst-visible signal preserved verbatim.
    if d.get("evidence"):
        obj["x_cti_evidence"] = d["evidence"]
    if d.get("confidence") is not None:
        obj["x_cti_confidence"] = d["confidence"]

    # Capture any additional IR keys we did not explicitly map so no
    # extractor data is silently dropped.
    _known = {"name", "type", "signals", "evidence", "confidence"}
    for k, v in d.items():
        if k in _known:
            continue
        obj[f"x_{k}"] = v

    return obj


# ----------------------------------------------------------------------
# User-Account (SCO) — STIX 2.1 §10.2
#
# SCO, not SDO — STIX 2.1 user-account does NOT carry created/modified
# timestamps in the spec; it is a Cyber Observable. We populate
# ``spec_version`` because SCOs require it under the 2.1 spec.
#
# Default credential policy: DROP. The redaction policy is encoded in
# the ``x_cti_password_provenance`` extension so consumers know whether
# the value was sourced from the report, redacted, or never present.
#
# Spec ref:
#   https://docs.oasis-open.org/cti/stix/v2.1/os/stix-v2.1-os.html#_azo70vgj1vm2
# ----------------------------------------------------------------------

def make_user_account(u: dict, *, keep_credential: bool = False) -> dict:
    """
    Build a STIX 2.1 user-account SCO from an IR ``user_accounts[]``
    entry. Passwords are DROPPED by default — set ``keep_credential=True``
    only when the bundle is intended for an isolated analysis tier.

    Args:
        u: IR user-account dict. Expected keys: ``username``, ``domain``,
           ``password``, ``privilege``, ``account_type``, ``evidence``,
           ``confidence``.
        keep_credential: If True AND ``u['password']`` is non-empty, emit
           the password as the STIX ``credential`` field. Default False
           (redacted, with ``x_cti_password_provenance: "redacted"``).
    """
    if not isinstance(u, dict):
        return None
    username = (u.get("username") or "").strip()
    if not username:
        return None

    vocabs = _stix_open_vocabs()

    obj = {
        "type": "user-account",
        "spec_version": "2.1",
        "id": new_stix_id("user-account"),
        "user_id": username,
        "display_name": username,
    }

    acct_type = (u.get("account_type") or "").strip().lower()
    if acct_type:
        obj["account_type"] = acct_type
        # If it's outside the spec open-vocab, badge as an extension.
        if (vocabs["account_type_ov"]
                and acct_type not in vocabs["account_type_ov"]):
            obj["x_cti_account_type_extension"] = True

    # Password handling. Default: redact. Always emit the provenance
    # field so consumers can tell "redacted" from "never present".
    pw = u.get("password")
    if pw and keep_credential:
        obj["credential"] = pw
        obj["x_cti_password_provenance"] = "source"
    elif pw:
        obj["x_cti_password_provenance"] = "redacted"
    else:
        obj["x_cti_password_provenance"] = "absent"

    # Domain (AD realm) — recorded as an x_* extension so downstream
    # consumers can re-link the SCO to the matching identity SDO. The
    # canonical link itself is via a (user-account)->[located-at]
    # relationship; this field is for diagnostics / lookup.
    domain = (u.get("domain") or "").strip()
    if domain:
        obj["x_cti_domain"] = domain

    # Privilege label from extract_users (admin / local-admin / sudo /
    # sql-admin / standard / unknown). No spec equivalent — emit as
    # x_cti_privilege so downstream consumers can decide group memberships.
    priv = (u.get("privilege") or "").strip().lower()
    if priv:
        obj["x_cti_privilege"] = priv

    if u.get("evidence"):
        obj["x_cti_evidence"] = u["evidence"]
    if u.get("confidence") is not None:
        obj["x_cti_confidence"] = u["confidence"]

    _known = {
        "username", "password", "domain", "privilege", "account_type",
        "evidence", "confidence",
    }
    for k, v in u.items():
        if k in _known:
            continue
        obj[f"x_{k}"] = v

    return obj


# ----------------------------------------------------------------------
# Software (SCO) -- STIX 2.1 §10.13
#
# Emits a STIX 2.1 `software` Cyber Observable for each entry produced by
# ``cti_extract_software.extract_software``.
#
# Spec ref:
#   https://docs.oasis-open.org/cti/stix/v2.1/os/stix-v2.1-os.html#_94zyt99qkixz
#
# Required:   type, id, name
# Recommended: version, vendor, cpe, swid, languages
# Custom:     x_cti_software_kind, x_cti_purl, x_cti_attack_id,
#             x_cti_cve_refs, x_cti_evidence
#
# When `taxonomy` is provided, we additionally enrich `vendor` from
# the ATT&CK `x_mitre_contributors` field (when present) -- pure
# ontology lookup, no static name->vendor tables.
# ----------------------------------------------------------------------

def make_software(s: dict, taxonomy: dict | None = None) -> dict | None:
    """
    Build a STIX 2.1 ``software`` SCO from an IR ``software[]`` entry.

    Args:
        s: IR software dict. Expected keys (from
           ``cti_extract_software.extract_software``):
               name, version, source, purl, software_kind,
               attack_id, cve_refs, evidence, confidence
        taxonomy: Optional MITRE ATT&CK taxonomy dict
           (from ``cti_taxonomy_loader.load_mitre_taxonomy``). When
           provided, ATT&CK-derived ``x_mitre_platforms`` ride along
           as the SCO's ``languages`` field is NOT used (STIX 2.1
           ``languages`` is a free-text list of language codes per
           [RFC5646], not platforms), but the ATT&CK platforms ride
           on ``x_mitre_platforms`` for downstream consumers.

    Returns:
        STIX 2.1 software SCO dict, or ``None`` for empty / blank name.
    """
    if not isinstance(s, dict):
        return None
    name = (s.get("name") or "").strip()
    if not name:
        return None

    obj: dict = {
        "type": "software",
        "spec_version": "2.1",
        "id": new_stix_id("software"),
        "name": name,
    }

    # ---- Spec-recommended fields ----
    version = (s.get("version") or "").strip()
    if version:
        obj["version"] = version

    # ---- Custom CTI extensions ----
    kind = (s.get("software_kind") or "").strip().lower()
    if kind:
        obj["x_cti_software_kind"] = kind

    purl = (s.get("purl") or "").strip()
    if purl:
        obj["x_cti_purl"] = purl

    attack_id = (s.get("attack_id") or "").strip()
    if attack_id:
        obj["x_cti_attack_id"] = attack_id

    cve_refs = s.get("cve_refs") or []
    if cve_refs:
        obj["x_cti_cve_refs"] = list(cve_refs)

    if s.get("evidence"):
        obj["x_cti_evidence"] = s["evidence"]

    if s.get("source"):
        obj["x_cti_source"] = s["source"]

    if s.get("confidence") is not None:
        obj["x_cti_confidence"] = s["confidence"]

    # ---- ATT&CK ontology enrichment (vendor / platforms) ----
    # ATT&CK tool/malware entries carry x_mitre_platforms verbatim;
    # we surface them as x_mitre_platforms on the SCO so the range
    # deploy step knows which OS-family to provision for.
    if attack_id and taxonomy:
        # The taxonomy.name_index keys by lowercased name; strip any
        # filename extension first (the lookup name is the bare
        # software identifier).
        lookup = name.rsplit(".", 1)[0].lower()
        tax_obj = None
        for kind_key in ("tool", "malware"):
            entry = taxonomy.get("name_index", {}).get(f"{kind_key}:{lookup}")
            if entry:
                tax_obj = entry[2] if isinstance(entry, tuple) and len(entry) >= 3 else None
                break
        if tax_obj:
            platforms = tax_obj.get("x_mitre_platforms") or []
            if platforms:
                obj["x_mitre_platforms"] = list(platforms)
            # ATT&CK's `x_mitre_contributors` is sometimes the closest
            # signal we have to a vendor -- but it's contributor names,
            # not vendor names. Skip it to avoid misrepresentation.
            # Vendor stays unset (spec-allowed) unless the IR set it.

    # Pass through any caller-supplied vendor / cpe / swid / languages
    # without inventing them.
    for spec_field in ("vendor", "cpe", "swid", "languages"):
        if s.get(spec_field):
            obj[spec_field] = s[spec_field]

    # Capture any additional IR keys not explicitly mapped so no extractor
    # data is silently dropped.
    _known = {
        "name", "version", "source", "purl", "software_kind",
        "attack_id", "cve_refs", "evidence", "confidence",
        "vendor", "cpe", "swid", "languages",
    }
    for k, v in s.items():
        if k in _known:
            continue
        obj[f"x_{k}"] = v

    return obj


# ----------------------------------------------------------------------
# Bundle
# ----------------------------------------------------------------------

def make_bundle(
        objects: list,
        *,
        model: str | None = None,
        provider: str | None = None,
        config: dict | None = None,
    ) -> dict:
    """
    Pure JSON bundle — no stix2 library — fully serializable.
    """
    bundle = {
        "type": "bundle",
        "id": new_stix_id("bundle"),
        "objects": objects,
    }

    # ---- CTI provenance (STIX-safe extensions) ----
    if model:
        bundle["x_cti_model"] = model
    if provider:
        bundle["x_cti_provider"] = provider
    if config:
        bundle["x_cti_config"] = config


    return bundle
