#!/usr/bin/env python3
"""
Phase 4 — Range Topology Inference + AE-Library Cross-Reference
================================================================

For every finalised STIX 2.1 bundle written by stage 2 (and optionally
enriched by stage 3), this stage:

  1. Loads the bundle and the MITRE ATT&CK taxonomy.
  2. Discovers the matching Adversary Emulation (AE) plan by matching
     the bundle's malware / threat-actor / intrusion-set names against
     the vendored AE plan adversary slugs.
  3. Loads the on-prem image catalog (``plugins/range/conf/onprem_images.yml``)
     and builds an ``x-cti-range-topology`` SDO via
     :func:`cti_topology_inference.build_range_topology`.
  4. When a matching AE plan exists, parses it into an IR with
     :func:`cti_ae_library_loader.parse_ae_plan` and uses the IR to
     enrich every host's ``inferred_from`` provenance trail with
     AE-plan-grounded citations (matching ATT&CK technique IDs,
     hostnames, OS, role, subnets).
  5. Writes the topology SDO to ``data/outputs_topology/<stem>.topology.json``.
  6. Appends the topology SDO to the original bundle and re-serialises
     ``data/outputs_stix/<stem>.stix.json`` so the bundle stays
     canonical (single source of truth).

No static lookup tables — every ontology decision is driven by the
taxonomy, the AE-plan IR, the STIX vocab, or the YAML data files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from plugins.mcp.app.utilities.cti_topology_inference import (
    build_range_topology,
)
from plugins.mcp.app.utilities.cti_ae_library_loader import (
    discover_ae_plans,
    find_plan_by_adversary,
    parse_ae_plan,
)
from plugins.mcp.app.utilities.cti_taxonomy_loader import (
    load_mitre_taxonomy,
    load_mitre_bundle,
)
from plugins.mcp.app.utilities.paths import get_mcp_root


# -----------------------------------------------------------
# Directory constants (relative to base_dir)
# -----------------------------------------------------------
OUTPUTS_STIX_DIR = "outputs_stix"
OUTPUTS_TOPOLOGY_DIR = "outputs_topology"


# Path to the on-prem image catalog YAML. Optional — when missing,
# image_candidates simply comes back empty (no hard failure).
def _onprem_images_catalog_path() -> Path:
    mcp_root = get_mcp_root()
    # plugins/mcp -> plugins/range/conf/onprem_images.yml
    range_conf = mcp_root.parent / "range" / "conf" / "onprem_images.yml"
    return range_conf


def _log(msg: str) -> None:
    print(f"[STAGE4][TOPOLOGY] {msg}")


# -----------------------------------------------------------
# Helpers
# -----------------------------------------------------------

def _load_images_catalog() -> list:
    """Merge available on-prem image catalogs and return ``images``."""
    mcp_root = get_mcp_root()
    range_conf = mcp_root.parent / "range" / "conf"
    paths = [
        range_conf / "onprem_microvm_images.yml",
        range_conf / "onprem_images.yml",
    ]
    images: list = []
    seen: set[tuple[str, str, str]] = set()
    try:
        import yaml  # type: ignore
    except Exception as e:
        _log(f"cannot parse image catalogs without yaml: {e}")
        return []
    for path in paths:
        if not path.exists():
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for img in doc.get("images") or []:
                if not isinstance(img, dict):
                    continue
                key = (
                    str(img.get("name") or "").lower(),
                    str(img.get("provider") or "").lower(),
                    str(img.get("file") or "").lower(),
                )
                if key in seen:
                    continue
                seen.add(key)
                rec = dict(img)
                rec.setdefault("_source_catalog", str(path))
                images.append(rec)
        except Exception as e:
            _log(f"failed to parse {path}: {e}")
    if not images:
        _log(f"image catalogs absent under {range_conf}; image_candidates will be empty")
    return images


def _adversary_candidates_from_bundle(bundle: dict,
                                      stem_hint: str = "") -> list:
    """
    Extract candidate adversary identifiers from the bundle. Walk
    threat-actor, intrusion-set, and malware SDOs (plus declared
    aliases) and order them by likely specificity.

    Ordering rules:
      1. ``stem_hint``-derived tokens come first. When the source file
         stem (e.g. ``e2e-run-20260510T154539Z-blackcat-microsoft``)
         mentions one of the bundle's adversary names, surface that
         name before the rest — the operator's filename is the most
         direct attribution signal we have.
      2. Threat-actor > intrusion-set > malware (more specific
         attribution kinds first).
      3. Within each tier, prefer longer names (more specific tokens
         outrank short shared ones).
    """
    if not isinstance(bundle, dict):
        return []
    objects = bundle.get("objects") or []

    ta_names: list[str] = []
    is_names: list[str] = []
    mal_names: list[str] = []

    for o in objects:
        t = o.get("type") if isinstance(o, dict) else None
        nm = (o.get("name") or "").strip() if isinstance(o, dict) else ""
        aliases: list[str] = []
        if isinstance(o, dict):
            for k in ("aliases", "x_mitre_aliases"):
                v = o.get(k)
                if isinstance(v, list):
                    aliases.extend([str(x).strip() for x in v if x])
        if not nm:
            continue
        if t == "threat-actor":
            ta_names.append(nm)
            ta_names.extend(aliases)
        elif t == "intrusion-set":
            is_names.append(nm)
            is_names.extend(aliases)
        elif t == "malware":
            mal_names.append(nm)
            mal_names.extend(aliases)

    def _sort_key(n: str):
        return (-len(n), n.lower())

    ordered: list = []
    seen: set = set()

    # 1) Stem-hint preference: any bundle name whose lower-cased,
    #    non-alphanumeric-stripped token appears in the stem wins first
    #    place. This is a STRUCTURAL match, not a static name list —
    #    the stem and the bundle names are both data.
    import re as _re
    stem_low = _re.sub(r"[^a-z0-9]+", "", (stem_hint or "").lower())
    if stem_low:
        for tier in (ta_names, is_names, mal_names):
            for n in sorted(tier, key=_sort_key):
                key = n.lower()
                tok = _re.sub(r"[^a-z0-9]+", "", key)
                if tok and tok in stem_low and key not in seen:
                    seen.add(key)
                    ordered.append(n)

    # 2) Tier-ordered fallback.
    for tier in (ta_names, is_names, mal_names):
        for n in sorted(tier, key=_sort_key):
            key = n.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(n)
    return ordered


def _technique_ids_in_bundle(bundle: dict) -> set:
    """Return the set of ATT&CK technique IDs referenced in the bundle."""
    out: set = set()
    for o in (bundle.get("objects") or []):
        if not isinstance(o, dict):
            continue
        if o.get("type") != "attack-pattern":
            continue
        for er in o.get("external_references", []) or []:
            if er.get("source_name") == "mitre-attack":
                tid = (er.get("external_id") or "").upper().strip()
                if tid:
                    out.add(tid)
    return out


def _norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def _host_key(value: str) -> str:
    key = _norm_key(value)
    if key.startswith("range-"):
        key = key[len("range-"):]
    return key


def _image_candidates_for_os(os_name: str, images_catalog: list) -> list:
    os_key = (os_name or "").strip().lower()
    if not os_key:
        return []
    out = []
    for img in images_catalog or []:
        if (img.get("os") or "").strip().lower() == os_key:
            name = img.get("name")
            if name and name not in out:
                out.append(name)
    return out


_AE_ROLE_PATTERNS = (
    (re.compile(r"\bdomain\s+controller\b", re.I), "dc"),
    (re.compile(r"\bkali\s+attack\s+host\b|\battack\s+host\b", re.I), "attack-host"),
    (re.compile(r"\bjump\s*box\b", re.I), "jumpbox"),
    (re.compile(r"\bbastion\s+host\b", re.I), "bastion"),
    (re.compile(r"\bcontractor\s+workstation\b", re.I), "workstation"),
    (re.compile(r"\b\w*backup\w*\s+server\b|\bbackup\s+server\b", re.I), "backup"),
    (re.compile(r"\bkvm\s+server\b|\bhypervisor\b", re.I), "hypervisor"),
)


def _ae_role_from_evidence(evidence: str,
                           hostname: Optional[str] = None) -> Optional[str]:
    if hostname:
        m = re.search(
            rf"[^`\n]{{0,100}}`{re.escape(hostname)}`?[^`\n]{{0,100}}",
            evidence or "",
            re.I,
        )
        if m:
            scoped = _ae_role_from_evidence(m.group(0))
            if scoped:
                return scoped
    matches = []
    for pattern, role in _AE_ROLE_PATTERNS:
        m = pattern.search(evidence or "")
        if m:
            matches.append((m.start(), role))
    if not matches:
        return None
    return sorted(matches, key=lambda item: item[0])[0][1]


def _ae_os_from_evidence(evidence: str, role: Optional[str],
                         default: str = "windows") -> str:
    blob = evidence or ""
    if role in {"dc", "bastion", "jumpbox", "workstation", "backup"}:
        return "windows"
    if not role and re.search(
        r"\bfollowing hostnames\b|\bfolder whose name begins\b",
        blob,
        re.I,
    ):
        return default
    if re.search(r"\b(kali|linux|kvm|ubuntu|debian|/srv/|/tmp/|sudo|ssh|scp)\b", blob, re.I):
        return "linux"
    if role == "dc" or re.search(
        r"\b(windows|rdp|powershell|cmd\.exe|active directory|domain controller)\b",
        blob,
        re.I,
    ):
        return "windows"
    return default


def _ae_topology_host(ae_host: dict, images_catalog: list,
                      default_domain: Optional[str]) -> dict:
    hostname = (ae_host.get("hostname") or "").strip().lower()
    os_name = (ae_host.get("os") or "").strip().lower()
    evidence = ae_host.get("evidence") or ""
    role = (ae_host.get("role") or "").strip().lower() or "workstation"
    if role == "workstation":
        role = _ae_role_from_evidence(evidence, hostname=hostname) or role
    os_name = os_name or _ae_os_from_evidence(evidence, role, default="windows")
    return {
        "name": f"range-{_host_key(hostname or 'host')}",
        "hostname": hostname,
        "ip": (ae_host.get("ip") or "").strip() or None,
        "role": role,
        "platform": os_name,
        "os": os_name,
        "services": [],
        "network_services": [],
        "software_required": [],
        "vulnerabilities": [],
        "image_candidates": _image_candidates_for_os(os_name, images_catalog),
        "domain_membership": default_domain,
        "inferred_from": [
            f"AE-plan infrastructure hostname={hostname!r} ip={ae_host.get('ip', '')!r}",
            "materialized from matched AE-library plan",
        ],
    }


def _append_unique_strings(target: list, values: list) -> None:
    seen = {str(v).lower() for v in target if str(v).strip()}
    for value in values or []:
        sval = str(value).strip()
        if not sval or sval.lower() in seen:
            continue
        target.append(sval)
        seen.add(sval.lower())


def _enrich_topology_with_ae_plan(
    topology: dict,
    ae_plan_meta: dict,
    ae_ir: dict,
    bundle_tids: set,
    images_catalog: Optional[list] = None,
) -> dict:
    """
    Cross-reference the AE-plan IR against the topology SDO and append
    AE-plan-grounded entries to every host's ``inferred_from`` list.

    The provenance entries are deliberately structural — they record
    matching attack-pattern technique IDs, AE-plan host names, OS, role,
    and subnets. No static name lists; each entry traces back to a
    field in the parsed AE IR.
    """
    adv_slug = (ae_plan_meta.get("adversary") or "").strip()
    lib = (ae_plan_meta.get("library") or "").strip()
    plan_dir = ae_plan_meta.get("plan_dir")
    plan_dir_str = str(plan_dir) if plan_dir is not None else ""

    try:
        from plugins.mcp.app.utilities.cti_ae_library_loader import parse_ae_plan
        emulation_ir = parse_ae_plan(ae_plan_meta, taxonomy=None)
    except Exception:
        emulation_ir = ae_ir

    # --- AE-plan technique IDs ---
    ae_tids = {
        (ap.get("id") or "").upper().strip()
        for ap in (ae_ir.get("attack_patterns") or [])
        if isinstance(ap, dict) and ap.get("id")
    }
    shared_tids = sorted(bundle_tids & ae_tids)
    emulation_tids = {
        (ap.get("id") or "").upper().strip()
        for ap in (emulation_ir.get("attack_patterns") or [])
        if isinstance(ap, dict) and ap.get("id")
    }
    ae_software = sorted({
        (item.get("name") or "").strip().lower()
        for field in ("software", "malware", "tools")
        for item in (emulation_ir.get(field) or [])
        if isinstance(item, dict) and (item.get("name") or "").strip()
    })
    ae_usernames = sorted({
        (u.get("username") or "").strip().lower()
        for u in emulation_ir.get("user_accounts") or []
        if isinstance(u, dict) and (u.get("username") or "").strip()
    })

    # --- AE-plan host inventory (lower-cased hostname / role / os) ---
    ae_hosts = []
    for h in (ae_ir.get("infrastructure") or []):
        if not isinstance(h, dict):
            continue
        evidence = h.get("evidence") or ""
        role = (h.get("role") or "").strip().lower()
        role = role or _ae_role_from_evidence(
            evidence, hostname=(h.get("hostname") or "").strip().lower(),
        ) or ""
        os_name = (h.get("os") or "").strip().lower()
        os_name = os_name or _ae_os_from_evidence(evidence, role or None, default="windows")
        ae_hosts.append({
            "hostname": (h.get("hostname") or "").strip().lower(),
            "ip": (h.get("ip") or "").strip(),
            "role": role,
            "os": os_name,
            "evidence": evidence,
        })

    ae_subnets = list(ae_ir.get("network_subnets") or [])
    ae_domains = [
        d for d in (ae_ir.get("domains") or [])
        if isinstance(d, dict) and (d.get("name") or "").strip()
    ]
    default_domain = None
    for d in ae_domains:
        name = (d.get("name") or "").strip()
        if name and name == name.upper():
            default_domain = name
            break
    if default_domain is None and ae_domains:
        default_domain = (ae_domains[0].get("name") or "").strip() or None
    ae_domain_keys = {
        (d.get("name") or "").strip().lower()
        for d in ae_domains
        if (d.get("name") or "").strip()
    }

    # --- Bundle-level AE-plan provenance (always appended when matched) ---
    bundle_provenance = (
        f"AE-library plan match: adversary={adv_slug!r}, library={lib!r}; "
        f"plan_dir={plan_dir_str}"
    )
    topology["emulation_plan"] = {
        "source": "ae-library",
        "adversary": adv_slug,
        "library": lib,
        "plan_dir": plan_dir_str,
        "techniques": sorted(emulation_tids or ae_tids),
        "software": ae_software,
        "users": ae_usernames,
    }

    # --- Host-level AE enrichment ---
    hosts = topology.setdefault("hosts", [])
    hosts_by_key = {
        _host_key(h.get("hostname") or h.get("name") or ""): h
        for h in hosts if isinstance(h, dict)
    }
    for host in hosts:
        if not isinstance(host, dict):
            continue
        inferred = host.setdefault("inferred_from", [])

        # 1) Always cite the AE-plan match itself.
        inferred.append(bundle_provenance)

        # 2) When AE-plan TIDs intersect the bundle TIDs, surface that.
        if shared_tids:
            inferred.append(
                f"AE-plan attack_patterns intersect bundle techniques: "
                f"{shared_tids}"
            )

        # 3) Attempt to map the host to an AE-plan host by name / IP / role.
        host_name = (host.get("name") or "").strip().lower()
        host_ip = (host.get("ip") or "").strip()
        host_os = (host.get("os") or host.get("platform") or "").strip().lower()
        host_role = (host.get("role") or "").strip().lower()

        for ae_h in ae_hosts:
            ae_name = ae_h["hostname"]
            ae_ip = ae_h["ip"]
            ae_role = ae_h["role"]
            ae_os = ae_h["os"]
            matched_on = []
            # Name substring match (range-<slug> may contain AE name)
            if ae_name and ae_name in host_name:
                matched_on.append(f"name={ae_name}")
            # IP exact
            if ae_ip and host_ip and ae_ip == host_ip:
                matched_on.append(f"ip={ae_ip}")
            # Role match
            if ae_role and host_role and ae_role == host_role:
                matched_on.append(f"role={ae_role}")
            strong_match = bool(matched_on)
            # OS match
            if strong_match and ae_os and host_os and (ae_os == host_os or ae_os in host_os):
                matched_on.append(f"os={ae_os}")
            if strong_match:
                if ae_name:
                    host["hostname"] = ae_name
                    hosts_by_key[_host_key(ae_name)] = host
                if ae_ip and not host.get("ip"):
                    host["ip"] = ae_ip
                if ae_os:
                    host["platform"] = ae_os
                    host["os"] = ae_os
                    if images_catalog is not None:
                        host["image_candidates"] = _image_candidates_for_os(
                            ae_os, images_catalog,
                        )
                if ae_role and (
                    not host.get("role")
                    or host.get("role") in {"unknown", "workstation"}
                    or any(m.startswith(("name=", "ip=")) for m in matched_on)
                ):
                    host["role"] = ae_role
                current_domain = (host.get("domain_membership") or "").strip().lower()
                if default_domain and (
                    not current_domain
                    or (ae_domain_keys and current_domain not in ae_domain_keys)
                ):
                    host["domain_membership"] = default_domain
                inferred.append(
                    f"AE-plan host correlation ({', '.join(matched_on)}); "
                    f"plan_dir={plan_dir_str}"
                )
                break  # one match per host is enough provenance

        # 4) AE-plan subnet provenance.
        if ae_subnets:
            inferred.append(
                f"AE-plan network_subnets: {ae_subnets[:8]}"
                + (" ..." if len(ae_subnets) > 8 else "")
            )

    # --- Materialize AE-plan hosts absent from the STIX-derived topology ---
    for ae_h in ae_hosts:
        ae_name = ae_h["hostname"]
        if not ae_name:
            continue
        key = _host_key(ae_name)
        if key in hosts_by_key:
            continue
        host = _ae_topology_host(ae_h, images_catalog or [], default_domain)
        host.setdefault("inferred_from", []).append(bundle_provenance)
        if shared_tids:
            host["inferred_from"].append(
                f"AE-plan attack_patterns intersect bundle techniques: {shared_tids}"
            )
        hosts.append(host)
        hosts_by_key[key] = host

    # --- Materialize AE-plan users/domains/networks/artifacts ---
    users = topology.setdefault("user_accounts", [])
    ae_usernames = set(ae_usernames)
    if ae_usernames:
        topology["user_accounts"] = [
            u for u in users
            if not isinstance(u, dict)
            or (
                (u.get("username") or u.get("user_id") or "")
                .strip()
                .lower()
                in ae_usernames
            )
        ]
        users = topology["user_accounts"]
    existing_users = {
        (u.get("username") or u.get("user_id") or "").strip().lower()
        for u in users if isinstance(u, dict)
    }
    for u in ae_ir.get("user_accounts") or []:
        if not isinstance(u, dict):
            continue
        username = (u.get("username") or "").strip()
        if not username or username.lower() in existing_users:
            continue
        domain = (u.get("domain") or "").strip() or None
        privilege = "admin" if re.search(
            r"\b(admin|administrator|root|sudo)\b",
            f"{username} {u.get('evidence', '')}",
            re.I,
        ) else None
        users.append({
            "username": username,
            "account_type": "windows-domain" if domain else None,
            "privilege": privilege,
            "domain": domain,
            "hosting_realm": domain or "local",
            "targeted_identity": False,
            "organization_unit": domain if domain else None,
            "ansible_role_input": {
                "username": username,
                "is_admin": bool(privilege),
                "password": (u.get("password") or "").strip(),
            },
            "source": "ae-plan.user_accounts",
        })
        existing_users.add(username.lower())

    identities = topology.setdefault("identities", [])
    if ae_domain_keys:
        topology["identities"] = [
            ident for ident in identities
            if not isinstance(ident, dict)
            or not ident.get("domain_type")
            or (ident.get("name") or "").strip().lower() in ae_domain_keys
            or ident.get("targeted")
        ]
        identities = topology["identities"]
    existing_domains = {
        (d.get("name") or "").strip().lower()
        for d in identities if isinstance(d, dict)
    }
    for d in ae_domains:
        name = (d.get("name") or "").strip()
        key = name.lower()
        if not name or key in existing_domains:
            continue
        identities.append({
            "id": None,
            "name": name,
            "identity_class": "organization",
            "domain_type": (d.get("type") or "active-directory").lower(),
            "signals": [],
            "confidence": 1.0,
            "targeted": False,
            "source": "ae-plan.domains",
        })
        existing_domains.add(key)

    networks = topology.setdefault("networks", [])
    existing_cidrs = {
        n.get("cidr") for n in networks
        if isinstance(n, dict) and n.get("cidr")
    }
    for cidr in ae_subnets:
        if cidr in existing_cidrs:
            continue
        networks.append({
            "name": _norm_key(cidr) + "-net",
            "cidr": cidr,
            "members": [],
            "anchor_identity": None,
            "source": "ae-plan.network_subnets",
        })
        existing_cidrs.add(cidr)

    _append_unique_strings(topology.setdefault("file_paths", []),
                           ae_ir.get("file_paths") or [])
    _append_unique_strings(topology.setdefault("registry_keys", []),
                           ae_ir.get("registry_keys") or [])

    # --- Top-level cross-reference summary ---
    topology["x_ae_library_match"] = {
        "adversary": adv_slug,
        "library": lib,
        "plan_dir": plan_dir_str,
        "scenario_md": str(ae_plan_meta.get("scenario_md_path") or ""),
        "shared_attack_pattern_ids": shared_tids,
        "ae_attack_pattern_count": len(ae_tids),
        "bundle_attack_pattern_count": len(bundle_tids),
        "ae_host_count": len(ae_hosts),
        "ae_subnet_count": len(ae_subnets),
        "ae_user_count": len(ae_ir.get("user_accounts") or []),
        "ae_domain_count": len(ae_domains),
        "ae_file_path_count": len(ae_ir.get("file_paths") or []),
        "ae_registry_key_count": len(ae_ir.get("registry_keys") or []),
    }

    return topology


# -----------------------------------------------------------
# Per-bundle pipeline
# -----------------------------------------------------------

def _process_bundle(stix_path: Path,
                    topology_dir: Path,
                    taxonomy: dict,
                    plans: list,
                    images_catalog: list) -> Optional[Path]:
    """
    Build + persist the topology SDO for a single bundle. Returns the
    path the topology file was written to (or None on skip / error).
    """
    try:
        bundle = json.loads(stix_path.read_text(encoding="utf-8"))
    except Exception as e:
        _log(f"failed to load {stix_path.name}: {e}")
        return None

    if not isinstance(bundle, dict) or bundle.get("type") != "bundle":
        _log(f"skip {stix_path.name}: not a STIX bundle")
        return None

    # AE-plan discovery (by adversary candidates from the bundle). The
    # file stem is also fed in as a hint: filenames like
    # "...-blackcat-microsoft.stix.json" carry the analyst's chosen
    # attribution and should win over alphabetical / longest-name ties.
    stem_hint = stix_path.stem
    if stem_hint.endswith(".stix"):
        stem_hint = stem_hint[: -len(".stix")]
    candidates = _adversary_candidates_from_bundle(bundle, stem_hint=stem_hint)
    plan_match = None
    matched_candidate = None
    for cand in candidates:
        m = find_plan_by_adversary(plans, cand)
        if m:
            plan_match = m
            matched_candidate = cand
            break

    if plan_match:
        _log(
            f"AE-plan match for {stix_path.name}: candidate={matched_candidate!r} "
            f"-> {plan_match.get('library')}/{plan_match.get('adversary')}"
        )
    else:
        _log(
            f"no AE-plan match for {stix_path.name} "
            f"(candidates tried: {candidates[:6]}{' ...' if len(candidates) > 6 else ''})"
        )

    # Build the topology SDO.
    topology = build_range_topology(
        bundle, taxonomy, images_catalog=images_catalog,
    )

    # Cross-reference with AE library IR when a plan matched.
    if plan_match is not None:
        try:
            ae_ir = parse_ae_plan(plan_match, taxonomy=taxonomy)
            bundle_tids = _technique_ids_in_bundle(bundle)
            topology = _enrich_topology_with_ae_plan(
                topology, plan_match, ae_ir, bundle_tids, images_catalog,
            )
        except Exception as e:
            _log(f"AE-plan IR enrichment failed for {stix_path.name}: {e}")

    # ----- Persist topology SDO -----
    stem = stix_path.stem
    if stem.endswith(".stix"):
        stem = stem[: -len(".stix")]
    topology_path = topology_dir / f"{stem}.topology.json"
    topology_dir.mkdir(parents=True, exist_ok=True)
    topology_path.write_text(
        json.dumps(topology, indent=2, default=str), encoding="utf-8",
    )
    _log(f"wrote topology -> {topology_path}")

    try:
        from plugins.mcp.app.utilities.cti_knowledge_graph import (
            persist_bundle_topology,
        )
        kg = persist_bundle_topology(bundle, topology)
        _log(f"updated CTI knowledge graph -> {kg.get('db_path')}")
    except Exception as e:
        _log(f"knowledge graph persistence skipped: {e}")

    # ----- Append to the bundle and re-serialise -----
    objects = bundle.setdefault("objects", [])
    # Remove any pre-existing topology SDO (idempotent re-run).
    objects[:] = [o for o in objects
                  if not (isinstance(o, dict)
                          and o.get("type") == "x-cti-range-topology")]
    objects.append(topology)
    stix_path.write_text(
        json.dumps(bundle, indent=2, default=str), encoding="utf-8",
    )
    _log(f"appended topology SDO -> {stix_path}")

    return topology_path


# -----------------------------------------------------------
# Public entry point
# -----------------------------------------------------------

def run_phase4_topology(base_dir: Path) -> list:
    """
    Run stage 4 over every STIX bundle in ``<base_dir>/outputs_stix``.

    Returns the list of topology paths produced (for caller logging /
    smoke tests).
    """
    base_dir = Path(base_dir)
    stix_dir = base_dir / OUTPUTS_STIX_DIR
    topology_dir = base_dir / OUTPUTS_TOPOLOGY_DIR

    if not stix_dir.is_dir():
        _log(f"no outputs_stix dir at {stix_dir}; nothing to do")
        return []

    stix_files = sorted(p for p in stix_dir.glob("*.stix.json") if p.is_file())
    if not stix_files:
        _log(f"no *.stix.json files in {stix_dir}; nothing to do")
        return []

    # One-time loads.
    _log("loading MITRE ATT&CK taxonomy ...")
    taxonomy = load_mitre_taxonomy()
    # Attach raw objects so cti_topology_inference can walk the
    # data-component / detection-strategy graph without re-loading.
    try:
        raw_bundle = load_mitre_bundle()
        taxonomy["_raw_objects"] = raw_bundle.get("objects", []) or []
    except Exception as e:
        _log(f"could not attach _raw_objects to taxonomy: {e}")

    _log("discovering AE-library plans ...")
    plans = discover_ae_plans()
    _log(f"  discovered {len(plans)} AE plans")

    _log("loading on-prem images catalog ...")
    images_catalog = _load_images_catalog()
    _log(f"  images_catalog entries: {len(images_catalog)}")

    produced: list = []
    for stix_path in stix_files:
        out = _process_bundle(
            stix_path, topology_dir, taxonomy, plans, images_catalog,
        )
        if out is not None:
            produced.append(out)

    _log(f"stage 4 complete: {len(produced)} topology file(s) produced")
    return produced


# -----------------------------------------------------------
# CLI
# -----------------------------------------------------------

def _main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Run CTI pipeline stage 4 (topology).")
    ap.add_argument("--base-dir", type=Path, required=True,
                    help="MCP data directory (the one containing outputs_stix/).")
    args = ap.parse_args()
    run_phase4_topology(args.base_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
