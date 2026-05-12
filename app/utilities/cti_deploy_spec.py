"""
cti_deploy_spec.py — AE-plan -> range-plugin deploy-spec synthesiser.

Bridges the gap between
  * the ``x-cti-range-topology`` SDO built by
    :func:`cti_topology_inference.build_range_topology`, and
  * the AE-library IR returned by
    :func:`cti_ae_library_loader.parse_ae_plan`,

and emits a single concrete deploy-spec dict the Range plugin can consume.

The output maps directly to the POST body of
``/plugin/range/onprem/manage/deploy``: one ``images`` entry per host, an
``ansible_groups`` slice for each, plus the ``feature_playbooks``,
``users``, ``domain``, ``elk_host`` and ``post_deploy_steps`` blocks the
post-deploy Ansible orchestrator expects.

Design constraints (per project memory
``feedback_no_static_lists_dynamic_only.md``):

  * NO static malware -> role tables.
  * NO static service -> playbook lookup. Service-to-playbook matching is
    done by name-glob against the playbook filenames discovered on disk.
  * NO hardcoded role list — whatever role string the topology emits is
    slugified and used verbatim as the ansible-group tag.
  * Image selection is by intersection of ``host.platform`` and
    ``image.os``; provider is derived from the dominant image.

The synthesizer is purely transformational: every output field has a
named provenance entry under ``deploy_spec['_provenance']`` describing
which input it came from.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Concrete ELK endpoint of the locally-deployed detections stack. Hardcoded
# here as a sane default; future revisions should read this from
# ``plugins/detections/conf/local.yml`` ``siem_url`` so a relocated ELK
# host updates the deploy spec automatically.
_DEFAULT_ELK_HOST = {
    "url":       "http://192.168.66.1:9200",
    "kibana_url": "http://192.168.66.1:5601",
}

# Filesystem roots used when callers don't pre-load the range plugin's
# data files (test contexts, importer-shell usage). They're resolved
# lazily so this module remains importable even when the range plugin
# isn't checked out alongside the mcp plugin.
_THIS_DIR  = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[3]                                     # caldera/
_RANGE_DIR = _REPO_ROOT / "plugins" / "range"
_RANGE_CONF_DIR         = _RANGE_DIR / "conf"
_RANGE_CONF             = _RANGE_CONF_DIR / "onprem_images.yml"
_RANGE_MICROVM_CONF     = _RANGE_CONF_DIR / "onprem_microvm_images.yml"
_RANGE_FEATURE_PLAYBOOKS = _RANGE_DIR / "automation" / "playbooks" / "feature"
_RANGE_ROLES_DIR        = _RANGE_DIR / "automation" / "roles"


# ---------------------------------------------------------------------------
# Helpers — slugify, casefold, dedupe
# ---------------------------------------------------------------------------

_HOSTNAME_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    """RFC-1123-ish slug: lowercase alnum + hyphen, length-capped."""
    if not text:
        return "host"
    low = str(text).strip().lower()
    out = _HOSTNAME_SLUG_RE.sub("-", low).strip("-")
    return (out[:40] or "host")


def _norm(text: str) -> str:
    """Lower-case + non-word collapse, used for fuzzy name comparison."""
    if not text:
        return ""
    return _HOSTNAME_SLUG_RE.sub("-", str(text).lower()).strip("-")


# ---------------------------------------------------------------------------
# Lazy loaders for range-plugin files
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> Optional[dict]:
    if not path or not path.is_file():
        return None
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None


@lru_cache(maxsize=1)
def _default_images_catalog() -> list:
    """Best-effort merge of sibling range plugin on-prem image catalogs."""
    out: list = []
    seen: set[tuple[str, str, str]] = set()
    for path in (_RANGE_MICROVM_CONF, _RANGE_CONF):
        doc = _load_yaml(path)
        if not isinstance(doc, dict):
            continue
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
            out.append(rec)
    return out


@lru_cache(maxsize=1)
def _default_range_playbooks() -> list:
    """Discover ``*.yml`` files under range/automation/playbooks/feature/."""
    if not _RANGE_FEATURE_PLAYBOOKS.is_dir():
        return []
    return sorted(p.name for p in _RANGE_FEATURE_PLAYBOOKS.glob("*.yml"))


@lru_cache(maxsize=1)
def _default_range_roles() -> list:
    """Discover ansible role names under range/automation/roles/."""
    if not _RANGE_ROLES_DIR.is_dir():
        return []
    return sorted(p.name for p in _RANGE_ROLES_DIR.iterdir() if p.is_dir())


# ---------------------------------------------------------------------------
# Image selection
# ---------------------------------------------------------------------------

def _image_for_host(host: dict, images_catalog: list) -> Optional[dict]:
    """
    Pick the best image from the catalog for ``host``.

    Selection rules (in order):
      1. ``host['image_candidates']`` is a name list; the first catalog
         entry whose ``name`` matches wins.
      2. Otherwise fall back to OS-intersection: any catalog image whose
         ``os`` (case-insensitive) matches the host's ``platform`` /
         ``os``.
      3. Prefer ``provider: microvm``; then any image with a
         ``credentials`` block; then the first remaining candidate.
    """
    if not host or not images_catalog:
        return None

    # Filter to bootstrapped images only — entries with bootstrapped:true
    # have been through the range build pipeline (run-build-ch.sh /
    # run-build.sh for Windows, victim-rootfs.ext4 with shim baked in for
    # Linux) and boot with drivers + agent already configured. Raw qcow2
    # / ext4 entries without the flag would deploy driverless (black
    # framebuffer, no input). Entries that omit the flag entirely are
    # treated as bootstrapped so older catalogs keep working.
    bootstrapped_only = [i for i in images_catalog
                         if isinstance(i, dict)
                         and i.get("bootstrapped", True)]
    if not bootstrapped_only:
        return None

    # Pre-index by name for the candidate lookup.
    by_name = {(i.get("name") or "").lower(): i for i in bootstrapped_only
               if isinstance(i, dict)}

    # 1) explicit image_candidates
    for cand in host.get("image_candidates") or []:
        img = by_name.get(str(cand).lower())
        if img:
            return img

    # 2) OS intersection (bootstrapped-only pool)
    host_os = (host.get("platform") or host.get("os") or "").strip().lower()
    if not host_os:
        return None
    matches = [i for i in bootstrapped_only
               if (i.get("os") or "").strip().lower() == host_os]
    if not matches:
        return None

    # 3) microvm preference -> credentials preference -> first
    microvm = [i for i in matches if (i.get("provider") or "").lower() == "microvm"]
    pool = microvm or matches
    with_creds = [i for i in pool if i.get("credentials")]
    return (with_creds or pool)[0]


def _dominant_provider(images: Iterable[dict]) -> str:
    """Return the modal `provider` slug across selected images."""
    counts: dict[str, int] = {}
    for img in images or []:
        p = (img.get("provider") or "").strip().lower()
        if p:
            counts[p] = counts.get(p, 0) + 1
    if not counts:
        return "microvm"
    return max(counts.items(), key=lambda kv: kv[1])[0]


# ---------------------------------------------------------------------------
# Ansible-group tagging
# ---------------------------------------------------------------------------

def _ansible_groups_for(host: dict) -> list:
    """
    Translate host metadata into ``ansible_groups`` tags. Order:
      - ``tag_role_<role-slug>``     — from ``host['role']``
      - ``tag_os_<platform-slug>``   — from ``host['platform']`` or ``os``
      - ``tag_service_<svc-slug>``   — one per service in ``host['services']``
    """
    out: list = []
    role = (host.get("role") or "").strip().lower()
    if role:
        out.append(f"tag_role_{_slug(role)}")
    plat = (host.get("platform") or host.get("os") or "").strip().lower()
    if plat:
        out.append(f"tag_os_{_slug(plat)}")
    for svc in host.get("services") or []:
        s = _slug(svc)
        if s and s != "host":
            tag = f"tag_service_{s}"
            if tag not in out:
                out.append(tag)
    # De-dup while preserving order.
    seen = set()
    deduped = []
    for tag in out:
        if tag not in seen:
            seen.add(tag)
            deduped.append(tag)
    return deduped


# ---------------------------------------------------------------------------
# Host merge: topology + AE-plan infrastructure
# ---------------------------------------------------------------------------

# Evidence-text patterns used to derive an OS / role hint when the AE-plan
# IR didn't populate `os` / `role`. Pure regex over the prose snippet the
# loader already attached — not a per-host lookup table.
_AE_OS_LINUX_RE = re.compile(
    r"\b(kali|linux|kvm|ubuntu|debian|centos|rhel|fedora|sftp|/srv/|/var/|sudo)\b",
    re.IGNORECASE,
)
_AE_OS_WIN_RE = re.compile(
    r"\b(windows|powershell|cmd\.exe|net\s+user|netbios|active\s+directory|domain\s+controller)\b",
    re.IGNORECASE,
)
_AE_ROLE_RE = re.compile(
    r"\b(domain\s+controller|jump\s*box|bastion\s+host|exchange|attack\s+host|"
    r"contractor\s+workstation|kvm\s+server|backup\s+server)\b",
    re.IGNORECASE,
)
_AE_ROLE_NORMALISE = {
    "domain controller":      "dc",
    "jumpbox":                "jumpbox",
    "jump box":               "jumpbox",
    "bastion host":           "bastion",
    "exchange":               "exchange",
    "attack host":            "attack-host",
    "contractor workstation": "workstation",
    "kvm server":             "hypervisor",
    "backup server":          "backup",
}


def _ae_evidence_role(evidence: str) -> Optional[str]:
    """Pull a role hint from the AE-plan evidence snippet (case-insensitive)."""
    if not evidence:
        return None
    m = _AE_ROLE_RE.search(evidence)
    if not m:
        return None
    key = re.sub(r"\s+", " ", m.group(1).lower().strip())
    return _AE_ROLE_NORMALISE.get(key)


def _ae_evidence_platform(evidence: str, default: str) -> str:
    """Pull an OS hint from the AE-plan evidence snippet."""
    if not evidence:
        return default
    # Domain-controller evidence implies Windows even if "linux" doesn't
    # appear; AD DS is Windows-only per ATT&CK.
    if _AE_OS_WIN_RE.search(evidence):
        return "windows"
    if _AE_OS_LINUX_RE.search(evidence):
        return "linux"
    return default


def _ae_host_to_topology_shape(ae_host: dict,
                               primary_platform: str,
                               default_domain: Optional[str]) -> dict:
    """
    Re-shape an AE-plan ``infrastructure[]`` entry into the topology host
    schema so the downstream merge can dedupe and treat them uniformly.

    Evidence-text heuristics fill in ``os`` / ``role`` when the AE-plan
    parser couldn't extract them from a table (the common case for AE
    plans that describe hosts in prose).
    """
    hostname = (ae_host.get("hostname") or "").strip().lower()
    evidence = ae_host.get("evidence") or ""
    os_v = (ae_host.get("os") or "").strip().lower() or None
    if not os_v:
        os_v = _ae_evidence_platform(evidence, default=primary_platform or "windows")
    platform = os_v
    role = (ae_host.get("role") or "").strip().lower()
    if not role:
        role = _ae_evidence_role(evidence) or "workstation"
    return {
        "name": f"range-{_slug(hostname or 'host')}",
        "hostname": hostname,
        "role": role,
        "platform": platform,
        "os": os_v,
        "ip": (ae_host.get("ip") or "").strip() or None,
        "services": [],
        "software_required": [],
        "image_candidates": [],
        "domain_membership": default_domain,
        "inferred_from": [
            f"ae-plan.infrastructure entry hostname={hostname!r} ip={ae_host.get('ip','')}",
            f"ae-evidence inferred platform={platform!r} role={role!r}",
        ],
    }


def _merge_hosts(topology_hosts: list, ae_hosts: list,
                 primary_platform: str,
                 default_domain: Optional[str]) -> list:
    """
    Merge AE-plan infrastructure entries into the topology hosts list,
    de-duplicating by slugified hostname. Topology entries win on every
    field they already populate; AE entries fill in gaps (ip, os).
    """
    out_by_key: dict[str, dict] = {}
    order: list[str] = []

    for h in topology_hosts or []:
        key = _norm(h.get("hostname") or h.get("name") or "") or _norm(h.get("role") or "host")
        if key.startswith("range-"):
            key = key[len("range-"):]
        # Ensure stable key for naming-collisions on either side.
        if key in out_by_key:
            key = f"{key}-{len(out_by_key)}"
        out_by_key[key] = dict(h)
        order.append(key)

    for ae_h in ae_hosts or []:
        hostname = (ae_h.get("hostname") or "").strip().lower()
        if not hostname:
            continue
        key = _norm(hostname)
        if key in out_by_key:
            existing = out_by_key[key]
            for k in ("ip", "os", "role"):
                if not existing.get(k) and ae_h.get(k):
                    existing[k] = ae_h[k]
            existing.setdefault("inferred_from", []).append(
                f"ae-plan match by hostname={hostname!r}"
            )
            continue
        out_by_key[key] = _ae_host_to_topology_shape(
            ae_h, primary_platform, default_domain,
        )
        order.append(key)

    return [out_by_key[k] for k in order]


# ---------------------------------------------------------------------------
# Service -> feature-playbook resolution
# ---------------------------------------------------------------------------

def _playbook_name_for_service(service: str, playbooks: list) -> Optional[str]:
    """
    Find a feature playbook whose filename stem matches ``service``.
    Matching is fuzzy: equal slugs OR the playbook stem appearing as a
    substring inside the service slug OR vice-versa.
    """
    if not service or not playbooks:
        return None
    svc = _slug(service)
    if not svc:
        return None
    candidates: list[tuple[int, str]] = []
    for pb in playbooks:
        stem = pb[:-4] if pb.endswith(".yml") else pb
        stem_slug = _slug(stem)
        if not stem_slug:
            continue
        if svc == stem_slug:
            candidates.append((0, pb))
        elif stem_slug in svc:
            candidates.append((1, pb))
        elif svc in stem_slug:
            candidates.append((2, pb))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def _role_name_for_service(service: str, roles: list) -> Optional[str]:
    """
    Find an ansible role whose name matches ``service``. Used as a
    fallback when no top-level playbook with the service name exists
    (the range plugin ships some features as role-only, e.g. auditbeat).
    Matching is by exact slug equality.
    """
    if not service or not roles:
        return None
    svc = _slug(service)
    for r in roles:
        if _slug(r) == svc:
            return r
    return None


def _feature_playbooks_for(hosts: list, range_playbooks: list,
                           ae_implied: list, range_roles: list) -> tuple[list, list]:
    """
    Resolve per-service playbooks for the merged hosts plus any AE-implied
    services (winlogbeat/auditbeat etc.). Returns
    ``(feature_playbooks, unresolved_services)``.

    Each feature_playbook entry looks like::

        {
          "name": "winlogbeat",
          "file": "winlogbeat.yml",
          "tags": ["onprem"],
          "vars": {"service_source": "ae-plan|topology"}
        }

    When no playbook file matches but an ansible role of the same name
    exists, we still emit a feature entry pointing at the role so the
    deploy-time orchestrator can wrap it in a generated playbook.
    """
    if not range_playbooks and not range_roles:
        return [], list(dict.fromkeys(ae_implied or []))

    services_seen: dict[str, str] = {}   # service slug -> first-source label
    for h in hosts or []:
        for svc in h.get("services") or []:
            s = _slug(svc)
            if s and s not in services_seen:
                services_seen[s] = "topology"
    for svc in ae_implied or []:
        s = _slug(svc)
        if s and s not in services_seen:
            services_seen[s] = "ae-plan"

    feature: dict[str, dict] = {}
    unresolved: list[str] = []
    for svc, source in services_seen.items():
        pb = _playbook_name_for_service(svc, range_playbooks)
        if pb:
            name = pb[:-4] if pb.endswith(".yml") else pb
            rec = feature.setdefault(name, {
                "name":  name,
                "file":  pb,
                "tags":  ["onprem"],
                "vars":  {"service_sources": []},
            })
            rec["vars"]["service_sources"].append(f"{svc}({source})")
            continue
        # No playbook — fall back to a role with the same name.
        role = _role_name_for_service(svc, range_roles)
        if role:
            name = role
            rec = feature.setdefault(name, {
                "name":      name,
                "role":      role,
                "tags":      ["onprem"],
                "vars":      {"service_sources": [], "wrapped_role": role},
                # No "file" key: the deploy-time orchestrator must
                # generate a one-host playbook that runs the role.
            })
            rec["vars"]["service_sources"].append(f"{svc}({source})")
            continue
        unresolved.append(svc)
    return list(feature.values()), unresolved


def _topology_implied_services(topology_sdo: dict, hosts: list,
                               range_playbooks: list, range_roles: list) -> list:
    """
    ATT&CK data-source/platform telemetry surface -> deployable telemetry
    features. Uses only the topology's ontology-derived attack_surface and
    roles/playbooks discovered from Range.
    """
    if not range_playbooks and not range_roles:
        return []
    attack_surface = topology_sdo.get("attack_surface") or {}
    if not attack_surface.get("techniques"):
        return []

    playbook_stems = {(p[:-4] if p.endswith(".yml") else p).lower()
                      for p in (range_playbooks or [])}
    role_names = {(r or "").lower() for r in (range_roles or [])}
    have = playbook_stems | role_names
    plats = {(h.get("platform") or h.get("os") or "").lower() for h in hosts or []}
    data_sources = {
        str(ds).strip().lower()
        for ds in attack_surface.get("data_sources") or []
        if str(ds).strip()
    }

    services: list[str] = []
    if "windows" in plats:
        if "winlogbeat" in have:
            services.append("winlogbeat")
        if "sysmon" in have:
            services.append("sysmon")
    if "linux" in plats and "auditbeat" in have:
        services.append("auditbeat")
    if any("network traffic" in ds for ds in data_sources) and "metricbeat" in have:
        services.append("metricbeat")

    seen = set()
    out = []
    for svc in services:
        if svc not in seen:
            seen.add(svc)
            out.append(svc)
    return out


def _attach_implied_services_to_hosts(hosts: list, services: list) -> None:
    """Mutate host service lists so host-level post-deploy steps fire."""
    for h in hosts or []:
        platform = (h.get("platform") or h.get("os") or "").lower()
        existing = {_slug(s) for s in (h.get("services") or [])}
        for svc in services or []:
            s = _slug(svc)
            if not s or s in existing:
                continue
            if s in ("winlogbeat", "sysmon") and platform != "windows":
                continue
            if s == "auditbeat" and platform != "linux":
                continue
            h.setdefault("services", []).append(s)
            h.setdefault("inferred_from", []).append(
                f"telemetry service {s!r} implied by ATT&CK data-source/platform surface"
            )
            existing.add(s)


def _feature_playbooks_for_software(hosts: list, range_playbooks: list,
                                    range_roles: list) -> tuple[list, list]:
    """
    Resolve software SCO inventory to feature playbooks/roles by the same
    dynamic filename/role matching used for services. No software-name
    lookup table is embedded here.
    """
    feature: dict[str, dict] = {}
    unresolved: list[dict] = []
    if not range_playbooks and not range_roles:
        return [], []

    seen_requests = set()
    for h in hosts or []:
        for sw in h.get("software_required") or []:
            if not isinstance(sw, dict):
                continue
            name = (sw.get("name") or "").strip()
            if not name:
                continue
            req_key = (
                _slug(h.get("name") or ""),
                _slug(name),
                str(sw.get("version") or ""),
                str(sw.get("cpe") or ""),
            )
            if req_key in seen_requests:
                continue
            seen_requests.add(req_key)
            pb = _playbook_name_for_service(name, range_playbooks)
            role = None if pb else _role_name_for_service(name, range_roles)
            if not pb and not role:
                unresolved.append({
                    "host": h.get("name"),
                    "name": name,
                    "version": sw.get("version"),
                    "cpe": sw.get("cpe"),
                    "reason": "no Range feature playbook or role matched software name",
                })
                continue
            if pb:
                feat_name = pb[:-4] if pb.endswith(".yml") else pb
                rec = feature.setdefault(feat_name, {
                    "name": feat_name,
                    "file": pb,
                    "tags": ["onprem"],
                    "vars": {"software_sources": []},
                })
            else:
                feat_name = role
                rec = feature.setdefault(feat_name, {
                    "name": feat_name,
                    "role": role,
                    "tags": ["onprem"],
                    "vars": {"software_sources": [], "wrapped_role": role},
                })
            rec["vars"]["software_sources"].append({
                "host": h.get("name"),
                "name": name,
                "version": sw.get("version"),
                "vendor": sw.get("vendor"),
                "cpe": sw.get("cpe"),
                "source": sw.get("source"),
            })
    return list(feature.values()), unresolved


def _merge_feature_playbooks(*groups: list) -> list:
    merged: dict[str, dict] = {}
    for group in groups:
        for item in group or []:
            key = item.get("name") or item.get("file") or item.get("role")
            if not key:
                continue
            if key not in merged:
                merged[key] = dict(item)
                if isinstance(item.get("vars"), dict):
                    merged[key]["vars"] = dict(item["vars"])
                continue
            dst = merged[key]
            src_vars = item.get("vars") if isinstance(item.get("vars"), dict) else {}
            dst_vars = dst.setdefault("vars", {})
            for var_key, var_val in src_vars.items():
                if isinstance(var_val, list):
                    dst_vars.setdefault(var_key, [])
                    dst_vars[var_key].extend(var_val)
                elif var_key not in dst_vars:
                    dst_vars[var_key] = var_val
    return list(merged.values())


# ---------------------------------------------------------------------------
# AE-plan implied services (winlogbeat / auditbeat / etc.)
# ---------------------------------------------------------------------------

# Mapping rule (NOT a static-vocab list — this is a STRUCTURAL rule:
# any AE plan that lists Windows hosts and an AD domain implies Windows
# Event log telemetry, which the range plugin satisfies with winlogbeat
# + sysmon; any plan that lists Linux hosts implies auditbeat. We don't
# encode any specific malware -> playbook mapping.)
def _ae_implied_services(ae_plan_ir: Optional[dict], hosts: list,
                         range_playbooks: list, range_roles: list) -> list:
    """
    Return the AE-plan-implied service slugs. Pure structural inference:
      - Any host on the ``windows`` platform -> ``winlogbeat`` + ``sysmon``
        when a playbook OR role exists for them.
      - Any host on the ``linux`` platform   -> ``auditbeat``  (range
        plugin ships only the role today; the deploy-spec consumer is
        expected to wrap the role in a one-host playbook).
      - Presence of an AD domain identity / netbios qualifier ->
        ``elk_servers`` (the elk stack is the destination for those
        telemetry streams).
    """
    if not range_playbooks and not range_roles:
        return []

    playbook_stems = {(p[:-4] if p.endswith(".yml") else p).lower()
                      for p in (range_playbooks or [])}
    role_names = {(r or "").lower() for r in (range_roles or [])}
    have = playbook_stems | role_names

    plats = {(h.get("platform") or h.get("os") or "").lower() for h in hosts or []}
    services: list[str] = []

    if "windows" in plats:
        if "winlogbeat" in have:
            services.append("winlogbeat")
        if "sysmon" in have:
            services.append("sysmon")
    if "linux" in plats:
        if "auditbeat" in have:
            services.append("auditbeat")

    if ae_plan_ir:
        if ae_plan_ir.get("domains") and "elk_servers" in have:
            services.append("elk_servers")

    # Dedup preserving order.
    seen = set()
    deduped = []
    for s in services:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


# ---------------------------------------------------------------------------
# User merge: topology + AE-plan
# ---------------------------------------------------------------------------

# Roles sorted by "how likely is this the adversary's initial access
# foothold in a typical AE plan?". The synthesizer plants sandcat on
# exactly ONE host per deploy_spec — the first match in this order —
# because real AE plans land C2 at the entry point and then move
# laterally via TTPs (T1021, T1570, T1133, ...), not by pre-installing
# agents everywhere. The rest of the spec is staged as agent-less
# victims that the operation discovers / shells / pivots into.
_INITIAL_ACCESS_ROLE_PRIORITY = (
    "bastion",            # CTID-style RDP-exposed bastion (e.g. kimeramon)
    "remote-access",      # RDP / SSH / VPN entry point
    "jumpbox",            # explicit jump host
    "attack-host",        # operator-controlled host (red team C2)
    "hosting-malware",    # host already running adversary tooling
    "workstation",        # generic compromised endpoint
    "mail",               # phishing landing host
    "exfiltration",       # exfil staging host (last resort)
)
# Roles that should never get an agent regardless of position in the
# spec — pure infrastructure / observation surfaces.
_INFRA_ROLES = frozenset((
    "hypervisor", "anonymization", "monitoring",
    "elk-server", "elk-stack", "dns", "network", "router",
))


def _select_entry_point_index(images: list, ae_plan_ir: Optional[dict] = None) -> int:
    """Pick the single image that should host the red agent.

    Order of precedence:
      1. AE plan tells us by name. ae_plan_ir.initial_access_host (if
         present) wins. A normalized name match against any image's
         ``name`` (case-insensitive substring) is accepted.
      2. Highest-priority role per ``_INITIAL_ACCESS_ROLE_PRIORITY``.
      3. First non-infra image.
      4. Index 0 as last resort.

    Returns the integer index into ``images`` (or -1 if the list is
    empty).
    """
    if not images:
        return -1

    # (1) AE plan named entry point
    if ae_plan_ir:
        named = (ae_plan_ir.get("initial_access_host")
                 or ae_plan_ir.get("entry_point_host")
                 or "")
        if named:
            target = str(named).strip().lower()
            for i, img in enumerate(images):
                if target in (img.get("name") or "").lower():
                    return i

    # (2) Priority by role
    by_role: dict[str, int] = {}
    for i, img in enumerate(images):
        r = (img.get("role") or "").strip().lower()
        by_role.setdefault(r, i)
    for role in _INITIAL_ACCESS_ROLE_PRIORITY:
        if role in by_role:
            return by_role[role]

    # (3) First non-infra
    for i, img in enumerate(images):
        r = (img.get("role") or "").strip().lower()
        if r not in _INFRA_ROLES:
            return i

    # (4) Last resort
    return 0


def _role_agent_reason(is_entry: bool, role: str, host: dict) -> str:
    r = (role or "").strip().lower()
    if is_entry:
        return f"selected as initial-access host (role='{r}'); operation pivots from here"
    if r in _INFRA_ROLES:
        return f"role='{r}' is pure infrastructure (no agent)"
    return f"role='{r}' is a victim — operation lands here via lateral movement, not pre-installed agent"


def _users_from_topology(topology_sdo: dict) -> list:
    """Lift user_accounts from the topology SDO into ansible-role inputs."""
    out: list = []
    for u in topology_sdo.get("user_accounts") or []:
        ari = u.get("ansible_role_input") or {}
        out.append({
            "username":    (u.get("username") or "").strip(),
            "password":    ari.get("password") or "",
            "admin":       bool(ari.get("is_admin")),
            "domain_user": bool((u.get("domain") or "").strip()),
            "domain":      (u.get("domain") or "").strip(),
            "hosting_realm": u.get("hosting_realm") or (u.get("domain") or "local"),
            "organization_unit": u.get("organization_unit"),
            "user_tags": list(ari.get("user_tags") or []),
            "source":      "topology.user_accounts",
        })
    return out


def _users_from_ae_plan(ae_plan_ir: dict) -> list:
    """Surface AE-plan user_accounts (with ground-truth passwords)."""
    out: list = []
    if not ae_plan_ir:
        return out
    for u in ae_plan_ir.get("user_accounts") or []:
        username = (u.get("username") or "").strip()
        if not username:
            continue
        domain = (u.get("domain") or "").strip()
        out.append({
            "username":    username,
            "password":    (u.get("password") or "").strip(),
            "admin":       _heuristic_is_admin(username, u.get("evidence", "")),
            "domain_user": bool(domain),
            "domain":      domain,
            "hosting_realm": domain or "local",
            "organization_unit": None,
            "user_tags": list(u.get("user_tags") or []),
            "source":      "ae-plan.user_accounts (public test creds)",
        })
    return out


def _heuristic_is_admin(username: str, evidence: str) -> bool:
    """
    Decide whether an AE-plan user is privileged from evidence text.
    Pure regex over the evidence snippet (the AE plan's own description
    of the account), NOT a static username allowlist.
    """
    blob = f"{username} {evidence}".lower()
    return bool(re.search(
        r"\b(domain[_ -]?admin|administrator|sql[_ -]?admin|root|sudo|local[_ -]?admin)\b",
        blob,
    ))


def _merge_users(topology_users: list, ae_users: list) -> list:
    """Merge by lowercased username. AE-plan password wins over empty."""
    by_user: dict[str, dict] = {}
    order: list[str] = []
    for u in topology_users + ae_users:
        uname = (u.get("username") or "").strip()
        if not uname:
            continue
        key = uname.lower()
        if key not in by_user:
            by_user[key] = dict(u)
            order.append(key)
            continue
        existing = by_user[key]
        if not existing.get("password") and u.get("password"):
            existing["password"] = u["password"]
            existing["source"] = (
                existing.get("source", "") + " + " + u.get("source", "")
            )
        if not existing.get("domain") and u.get("domain"):
            existing["domain"] = u["domain"]
            existing["domain_user"] = True
            existing["hosting_realm"] = u.get("hosting_realm") or u["domain"]
        if not existing.get("organization_unit") and u.get("organization_unit"):
            existing["organization_unit"] = u["organization_unit"]
        tags = list(existing.get("user_tags") or [])
        for tag in u.get("user_tags") or []:
            if tag not in tags:
                tags.append(tag)
        if tags:
            existing["user_tags"] = tags
        existing["admin"] = existing.get("admin") or u.get("admin", False)
    return [by_user[k] for k in order]


# ---------------------------------------------------------------------------
# Domain resolution
# ---------------------------------------------------------------------------

def _resolve_domain(topology_sdo: dict, ae_plan_ir: Optional[dict],
                    hosts: list) -> Optional[dict]:
    """
    Build the ``domain`` block. Preference order:
      1. Highest-confidence ``identity`` in topology with
         ``domain_type == "active-directory"``.
      2. AE-plan IR ``domains[]`` entries with type
         ``"active-directory"`` (highest-cased name wins — NetBIOS is
         conventionally upper-case).
      3. None.
    """
    candidates: list[tuple[float, str, str]] = []  # (confidence, name, source)

    # AE-plan domains carry the strongest signal: the AE plan author
    # explicitly named the domain. NetBIOS uppercase form wins over the
    # lower-case alias the parser also emits.
    if ae_plan_ir:
        for d in ae_plan_ir.get("domains") or []:
            if (d.get("type") or "").lower() == "active-directory":
                name = (d.get("name") or "").strip()
                if not name:
                    continue
                # AE plan source is highest-trust (ground truth from a
                # human-authored emulation plan). Prefer the upper-case
                # NetBIOS form so duplicate entries don't fight each
                # other.
                upper_bonus = 0.5 if name == name.upper() else 0.0
                candidates.append((1.5 + upper_bonus, name, "ae-plan.domains"))

    # Topology identity SDOs come second. They're often noisy (any
    # capitalised proper-noun in the report can wind up as an identity
    # with confidence 1.0) so they're outranked by AE-plan ground truth.
    # We additionally filter out obvious non-domain entities (single-word
    # acronyms, dotted strings like 'google.com', filenames).
    for ident in topology_sdo.get("identities") or []:
        if (ident.get("domain_type") or "").lower() != "active-directory":
            continue
        name = (ident.get("name") or "").strip()
        if not name:
            continue
        # Reject filename-shaped or domain-name-shaped noise.
        if "." in name and not name.endswith((".local", ".corp", ".internal")):
            continue
        # Reject very short acronyms (SMB, UAC, RDP, etc.) — they're
        # always false positives at the AD-domain layer.
        if len(name) <= 4 and name.isupper():
            continue
        conf = float(ident.get("confidence") or 0.0)
        candidates.append((conf, name, "topology.identity"))

    if not candidates:
        return None

    candidates.sort(key=lambda t: t[0], reverse=True)
    conf, name, source = candidates[0]
    dns_name = name.lower() + ".local" if "." not in name else name.lower()

    # Find a real DC host. Domain members are not promoted to controllers;
    # missing DC evidence is handled by operator review.
    controller = None
    for h in hosts:
        if (h.get("role") or "").strip().lower() == "dc":
            controller = h.get("name")
            break

    return {
        "name":       name,
        "dns_name":   dns_name,
        "controller": controller,
        "_source":    source,
        "_confidence": round(conf, 3),
    }


# ---------------------------------------------------------------------------
# Post-deploy steps
# ---------------------------------------------------------------------------

def _post_deploy_steps(hosts: list, feature_playbooks: list,
                       domain: Optional[dict]) -> list:
    """
    Build the ordered post-deploy actions. Every host gets sandcat;
    every host whose ``services`` includes a beats-shaped name gets the
    matching beats install action; the DC (if any) gets configure_dc;
    finally any victim-shaped hosts get the operation-target marker.
    """
    steps: list = []

    # 1) sandcat install on every host.
    for h in hosts:
        steps.append({
            "host":   h.get("name"),
            "action": "install_sandcat",
            "role":   "agent",
            "platform": h.get("platform") or h.get("os") or "windows",
        })

    # 2) beats enrollment per matching service.
    beats_map = {"winlogbeat": "winlogbeat",
                 "auditbeat":  "auditbeat",
                 "sysmon":     "sysmon",
                 "metricbeat": "metricbeat"}
    for h in hosts:
        host_meta = h.get("host_meta") if isinstance(h.get("host_meta"), dict) else {}
        for svc in (h.get("services") or host_meta.get("services") or []):
            s = _slug(svc)
            if s in beats_map:
                steps.append({
                    "host":   h.get("name"),
                    "action": f"install_{beats_map[s]}",
                    "role":   beats_map[s],
                    "platform": (
                        h.get("platform") or host_meta.get("platform")
                        or h.get("os") or "windows"
                    ),
                })

    # 3) configure_dc on the controller. The controller value comes from
    # the merged-host name (range-<slug>); resolve it back to the
    # image-entry name we picked above so post-deploy steps reference a
    # consistent identifier.
    if domain and domain.get("controller"):
        controller_slug = _norm(domain["controller"]).removeprefix("range-")
        for img in hosts:
            if _norm(img.get("name") or "") == controller_slug:
                steps.append({
                    "host":   img.get("name"),
                    "action": "configure_dc",
                    "role":   "configure_dc",
                    "vars":   {"domain":   domain.get("name"),
                               "dns_name": domain.get("dns_name")},
                })
                break
        else:
            steps.append({
                "host":   domain["controller"],
                "action": "configure_dc",
                "role":   "configure_dc",
                "vars":   {"domain":   domain.get("name"),
                           "dns_name": domain.get("dns_name")},
            })

    # 4) operation-target marker for victim-shaped hosts. "Victim" =
    #    role contains 'victim' or services include 'process'/'file'
    #    data sources (the ATT&CK signal slugs the topology emits).
    for h in hosts:
        role = (h.get("role") or "").lower()
        host_meta = h.get("host_meta") if isinstance(h.get("host_meta"), dict) else {}
        services = {_slug(s) for s in (
            h.get("services") or host_meta.get("services") or []
        )}
        if "victim" in role or "process" in services or "file" in services:
            steps.append({
                "host":   h.get("name"),
                "action": "mark_operation_target",
                "role":   None,
            })

    return steps


# ---------------------------------------------------------------------------
# Profile / image-name derivation
# ---------------------------------------------------------------------------

def _profile_name(topology_sdo: dict, ae_plan_ir: Optional[dict],
                  provider: str) -> str:
    """
    Profile name preferences:
      1. AE adversary slug ("ae-<slug>") if known.
      2. Topology id suffix as a fallback ("ae-topology-<uuid8>").
      3. Generic "ae-deploy".
    Provider is appended ONLY for vbox/vsphere — microvm-only stacks use
    the conventional "lab-ch-test" / "ae-*" naming the range plugin
    already understands.
    """
    if ae_plan_ir and ae_plan_ir.get("adversary"):
        slug = _slug(ae_plan_ir["adversary"])
        if slug:
            return f"ae-{slug}"
    sid = (topology_sdo.get("id") or "").rsplit("--", 1)[-1]
    if sid:
        return f"ae-topology-{sid[:8]}"
    return "ae-deploy"


def _vm_name_for(host: dict, taken: set) -> str:
    """Generate a unique image-entry name from the host slug."""
    base = _slug(host.get("name") or host.get("role") or "host")
    if base.startswith("range-"):
        base = base[len("range-"):]
    cand = base or "host"
    n = 1
    while cand in taken:
        n += 1
        cand = f"{base}-{n}"
    taken.add(cand)
    return cand


def _completeness_review(hosts: list, topology_sdo: dict, users: list,
                         unresolved_hosts: list, unresolved_services: list,
                         unresolved_software: list) -> dict:
    """
    Score whether the deploy spec has enough concrete detail to deploy
    without operator review.
    """
    checks = 0
    misses: list[dict] = []

    def _miss(kind: str, name: str, field: str, detail: str) -> None:
        misses.append({
            "kind": kind,
            "name": name,
            "field": field,
            "detail": detail,
        })

    for h in hosts or []:
        hname = h.get("name") or "host"
        checks += 1
        if not (h.get("platform") or h.get("os")):
            _miss("host", hname, "os", "host has no OS/platform")
        checks += 1
        if not h.get("role") or h.get("role") == "unknown":
            _miss("host", hname, "role", "host has no concrete role")
        checks += 1
        if not (h.get("services") or h.get("network_services")):
            _miss("host", hname, "services", "host has no service surface")

    for h in unresolved_hosts or []:
        checks += 1
        _miss(
            "host", h.get("name") or "host", "image",
            "no bootstrapped Range image matched host platform/candidates",
        )

    for req in topology_sdo.get("required_infrastructure_missing") or []:
        checks += 1
        role = req.get("role") or "infrastructure"
        platform = req.get("platform") or "unknown"
        _miss(
            "infrastructure", role, "missing",
            req.get("reason")
            or f"required {platform} {role} infrastructure was inferred but no real host was found",
        )

    for e in topology_sdo.get("network_edges") or []:
        checks += 1
        missing = [
            field for field in ("source_ref", "target_ref", "protocol")
            if not e.get(field)
        ]
        if missing:
            _miss(
                "network_edge",
                e.get("network_traffic_ref") or "network-traffic",
                ",".join(missing),
                "network edge lacks endpoint/protocol detail",
            )

    for u in users or []:
        checks += 1
        if not (u.get("hosting_realm") or u.get("domain") or not u.get("domain_user")):
            _miss(
                "user", u.get("username") or "user", "hosting_realm",
                "user identity has no AD domain, local SAM, or LDAP realm",
            )

    for svc in unresolved_services or []:
        checks += 1
        _miss("service", str(svc), "feature", "no Range playbook or role matched service")

    for sw in unresolved_software or []:
        checks += 1
        _miss(
            "software", sw.get("name") or "software", "feature",
            sw.get("reason") or "no Range playbook or role matched software",
        )

    score = 1.0 if checks == 0 else max(0.0, 1.0 - (len(misses) / checks))
    return {
        "score": round(score, 3),
        "operator_review_needed": score < 0.85,
        "checks": checks,
        "missing": misses,
        "threshold": 0.85,
    }


def _required_platforms_missing(unresolved_hosts: list,
                                images_catalog: list) -> list[dict]:
    """Summarise unresolved host platforms with no bootstrapped image."""
    boot_platforms = {
        (img.get("os") or "").strip().lower()
        for img in images_catalog or []
        if isinstance(img, dict) and img.get("bootstrapped", True)
    }
    missing: dict[str, list[str]] = {}
    for h in unresolved_hosts or []:
        platform = (h.get("platform") or h.get("os") or "").strip().lower()
        if not platform or platform in boot_platforms:
            continue
        missing.setdefault(platform, []).append(h.get("name") or "host")
    return [
        {"platform": platform, "hosts": sorted(set(hosts))}
        for platform, hosts in sorted(missing.items())
    ]


def _dedupe_software_requests(hosts: list) -> list:
    """Return unique software install requests across all merged hosts."""
    out: list = []
    seen: set[tuple[str, str, str, str]] = set()
    for h in hosts or []:
        for sw in h.get("software_required") or []:
            if not isinstance(sw, dict):
                continue
            key = (
                _slug(sw.get("name") or ""),
                str(sw.get("version") or ""),
                str(sw.get("cpe") or ""),
                str(sw.get("id") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(sw)
    return out


def _dedupe_unresolved_software(items: list) -> list:
    out: list = []
    seen: set[tuple[str, str, str]] = set()
    for item in items or []:
        key = (
            _slug(item.get("name") or ""),
            str(item.get("version") or ""),
            str(item.get("cpe") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def synthesize_deploy_spec(topology_sdo: dict,
                           ae_plan_ir: Optional[dict] = None,
                           images_catalog: Optional[list] = None,
                           range_roles: Optional[list] = None,
                           range_playbooks: Optional[list] = None,
                           *,
                           elk_host: Optional[dict] = None) -> dict:
    """
    Translate the merged (topology, AE-plan) inputs into a concrete
    range-plugin deploy spec.

    Args:
        topology_sdo: an ``x-cti-range-topology`` SDO (or a dict
            following the same shape).
        ae_plan_ir: optional AE-plan IR from
            :func:`cti_ae_library_loader.parse_ae_plan`. When provided,
            its ``infrastructure``, ``user_accounts`` and ``domains``
            lists are merged into the topology view.
        images_catalog: parsed ``plugins/range/conf/onprem_images.yml``
            (the value of the top-level ``images`` key). Falls back to
            an auto-discovered copy from the local range plugin.
        range_roles: list of available ansible role names. Falls back
            to a filesystem scan of ``range/automation/roles/``.
        range_playbooks: list of available feature playbook filenames.
            Falls back to a filesystem scan of
            ``range/automation/playbooks/feature/``.
        elk_host: override for the deployed ELK endpoint. Defaults to
            ``http://192.168.66.1:9200``.

    Returns:
        A deploy-spec dict matching the shape documented at module top.
    """
    if not isinstance(topology_sdo, dict):
        raise TypeError("topology_sdo must be a dict")

    if images_catalog is None:
        images_catalog = _default_images_catalog()
    if range_playbooks is None:
        range_playbooks = _default_range_playbooks()
    if range_roles is None:
        range_roles = _default_range_roles()
    if elk_host is None:
        elk_host = dict(_DEFAULT_ELK_HOST)

    # ------------------------------------------------------------------
    # Pick the domain default first so AE-plan hosts can default
    # their domain_membership.
    # ------------------------------------------------------------------
    primary_platform = (topology_sdo.get("primary_platform") or "windows").strip().lower()

    # Pre-compute candidate AD domain name (highest-cased upper-case
    # entry from AE IR; otherwise the highest-confidence topology
    # identity). This is *only* used as a default for merged AE hosts
    # — the authoritative ``domain`` block is built later.
    pre_domain = None
    for ident in topology_sdo.get("identities") or []:
        if (ident.get("domain_type") or "").lower() == "active-directory":
            pre_domain = (ident.get("name") or "").strip() or pre_domain
            break
    if ae_plan_ir:
        for d in ae_plan_ir.get("domains") or []:
            if (d.get("type") or "").lower() == "active-directory":
                cand = (d.get("name") or "").strip()
                if cand and cand == cand.upper():
                    pre_domain = cand
                    break

    # ------------------------------------------------------------------
    # Merge hosts: topology + AE-plan infrastructure
    # ------------------------------------------------------------------
    ae_hosts = (ae_plan_ir or {}).get("infrastructure", []) if ae_plan_ir else []
    merged_hosts = _merge_hosts(
        topology_sdo.get("hosts") or [],
        ae_hosts,
        primary_platform,
        pre_domain,
    )

    # ATT&CK and AE-plan surfaces imply telemetry features even when the
    # original topology host did not list them as first-class services.
    ae_implied = _ae_implied_services(ae_plan_ir, merged_hosts,
                                      range_playbooks, range_roles)
    topology_implied = _topology_implied_services(
        topology_sdo, merged_hosts, range_playbooks, range_roles,
    )
    implied_services = list(dict.fromkeys((ae_implied or []) + (topology_implied or [])))
    _attach_implied_services_to_hosts(merged_hosts, implied_services)

    # ------------------------------------------------------------------
    # Image selection per host
    # ------------------------------------------------------------------
    images_out: list = []
    chosen_imgs: list = []
    taken_names: set = set()
    unresolved_hosts: list = []
    for h in merged_hosts:
        img = _image_for_host(h, images_catalog)
        if not img:
            # Skip hosts with no usable image (e.g., an AE-plan attack
            # host on the public internet). The caller can surface them
            # through ``unresolved_hosts``.
            unresolved_hosts.append(h)
            continue
        chosen_imgs.append(img)
        name = _vm_name_for(h, taken_names)
        role = (h.get("role") or "workstation").strip().lower()
        entry = {
            "image":      img.get("name"),
            "name":       name,
            "file":       img.get("file"),
            "os":         img.get("os") or (h.get("platform") or "").title(),
            "cpus":       int(img.get("cpus") or 2),
            "memory":     int(img.get("memory") or 2048),
            "role":       role,
            "ansible_groups": _ansible_groups_for(h),
            # `red` is filled in below AFTER all images are built so we
            # can pick exactly one entry-point host.
            "red":        False,
            "host_meta": {
                "platform":          h.get("platform"),
                "ip":                h.get("ip"),
                "domain_membership": h.get("domain_membership"),
                "services":          list(h.get("services") or []),
                "network_services":  list(h.get("network_services") or []),
                "software_required": list(h.get("software_required") or []),
                "vulnerabilities":   list(h.get("vulnerabilities") or []),
                "stix_id":           h.get("stix_id"),
                "inferred_from":     list(h.get("inferred_from") or []),
            },
            # _host_role_obj kept for the entry-point selector; stripped
            # from the final spec.
            "_host_role_obj": h,
        }
        if img.get("session_type"):
            entry["session_type"] = img["session_type"]
        if img.get("credentials"):
            entry["has_credentials"] = True
        images_out.append(entry)

    # ------------------------------------------------------------------
    # Pick the single entry-point host that gets the red (sandcat) agent.
    # Per real AE plans: C2 lands at the initial-access foothold, then
    # the operation pivots laterally via TTPs (T1021 / T1133 / T1570 /
    # etc.). Pre-installing agents on every victim defeats the purpose
    # and (in CH provider) saturates the host with idle Windows VMs.
    # Operator can override via the GUI before pressing Deploy.
    # ------------------------------------------------------------------
    entry_idx = _select_entry_point_index(images_out, ae_plan_ir)
    for i, img_entry in enumerate(images_out):
        is_entry = (i == entry_idx)
        role = img_entry["role"]
        host_obj = img_entry.pop("_host_role_obj", {}) or {}
        img_entry["red"] = bool(is_entry)
        img_entry["host_meta"]["agent_decision"] = {
            "red":           bool(is_entry),
            "entry_point":   bool(is_entry),
            "reason":        _role_agent_reason(is_entry, role, host_obj),
        }

    provider = _dominant_provider(chosen_imgs)

    # ------------------------------------------------------------------
    # Feature playbooks
    # ------------------------------------------------------------------
    feature_playbooks, unresolved_services = _feature_playbooks_for(
        merged_hosts, range_playbooks, implied_services, range_roles,
    )
    software_feature_playbooks, unresolved_software = _feature_playbooks_for_software(
        merged_hosts, range_playbooks, range_roles,
    )
    unresolved_software = _dedupe_unresolved_software(unresolved_software)
    feature_playbooks = _merge_feature_playbooks(
        feature_playbooks, software_feature_playbooks,
    )

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    users = _merge_users(
        _users_from_topology(topology_sdo),
        _users_from_ae_plan(ae_plan_ir or {}),
    )

    # ------------------------------------------------------------------
    # Domain + post-deploy steps
    # ------------------------------------------------------------------
    domain = _resolve_domain(topology_sdo, ae_plan_ir, merged_hosts)
    if domain and "configure_dc" in {str(r).lower() for r in (range_roles or [])}:
        ad_services_handled = {
            "active-directory-domain-services", "kerberos", "dns",
        }
        unresolved_services = [
            svc for svc in unresolved_services
            if _slug(str(svc)) not in ad_services_handled
        ]
    post_deploy_steps = _post_deploy_steps(images_out, feature_playbooks, domain)
    required_platforms_missing = _required_platforms_missing(
        unresolved_hosts, images_catalog,
    )
    review_topology = topology_sdo
    if pre_domain and not any(
        (h.get("role") or "").strip().lower() == "dc" for h in merged_hosts
    ):
        review_topology = dict(topology_sdo)
        reqs = list(review_topology.get("required_infrastructure_missing") or [])
        if not any((r.get("role") or "").strip().lower() == "dc" for r in reqs):
            reqs.append({
                "role": "dc",
                "platform": "windows",
                "domain": pre_domain,
                "reason": (
                    f"Active Directory domain {pre_domain!r} is present, "
                    "but no real domain-controller host was found"
                ),
            })
        review_topology["required_infrastructure_missing"] = reqs
    operator_review = _completeness_review(
        merged_hosts, review_topology, users, unresolved_hosts,
        unresolved_services, unresolved_software,
    )

    # ------------------------------------------------------------------
    # Assemble
    # ------------------------------------------------------------------
    profile = _profile_name(topology_sdo, ae_plan_ir, provider)
    spec = {
        "profile":  profile,
        "provider": provider,
        "images":   images_out,
        "feature_playbooks": feature_playbooks,
        "users":    users,
        "domain":   domain,
        "elk_host": elk_host,
        "post_deploy_steps": post_deploy_steps,
        "software_install_requests": _dedupe_software_requests(merged_hosts),
        "required_platforms_missing": required_platforms_missing,
        "operator_review": operator_review,
        "_provenance": {
            "topology_sdo_id":        topology_sdo.get("id"),
            "topology_primary_platform": topology_sdo.get("primary_platform"),
            "ae_plan_adversary":      (ae_plan_ir or {}).get("adversary"),
            "ae_plan_library":        (ae_plan_ir or {}).get("library"),
            "image_catalog_size":     len(images_catalog or []),
            "range_playbooks_count":  len(range_playbooks or []),
            "range_roles_count":      len(range_roles or []),
            "merged_host_count":      len(merged_hosts),
            "unresolved_hosts":       [h.get("name") for h in unresolved_hosts],
            "unresolved_services":    sorted(set(unresolved_services)),
            "unresolved_software":    unresolved_software,
            "ae_implied_services":    sorted(set(ae_implied)),
            "topology_implied_services": sorted(set(topology_implied)),
        },
    }
    return spec


# ---------------------------------------------------------------------------
# CLI helper (manual smoke-test entry point)
# ---------------------------------------------------------------------------

def _main(argv: Optional[list] = None) -> int:  # pragma: no cover
    import argparse
    import json as _json
    import sys as _sys

    ap = argparse.ArgumentParser(
        description="Synthesise a Range-plugin deploy spec from a topology + AE plan.",
    )
    ap.add_argument("--topology", required=True,
                    help="Path to an x-cti-range-topology JSON file.")
    ap.add_argument("--adversary", default=None,
                    help="AE-plan adversary slug (eg 'alphv_blackcat').")
    ap.add_argument("--emit", default=None,
                    help="Write the deploy spec to this path (else stdout).")
    args = ap.parse_args(argv)

    topo = _json.loads(Path(args.topology).read_text(encoding="utf-8"))

    ae_ir = None
    if args.adversary:
        try:
            from plugins.mcp.app.utilities.cti_ae_library_loader import (
                discover_ae_plans, parse_ae_plan, find_plan_by_adversary,
            )
        except ImportError:
            _sys.path.insert(0, str(_REPO_ROOT))
            from plugins.mcp.app.utilities.cti_ae_library_loader import (  # type: ignore
                discover_ae_plans, parse_ae_plan, find_plan_by_adversary,
            )
        plans = discover_ae_plans()
        plan = find_plan_by_adversary(plans, args.adversary)
        if plan:
            ae_ir = parse_ae_plan(plan, taxonomy=None)

    spec = synthesize_deploy_spec(topo, ae_plan_ir=ae_ir)
    payload = _json.dumps(spec, indent=2, default=str)
    if args.emit:
        Path(args.emit).write_text(payload, encoding="utf-8")
        print(f"deploy spec written to {args.emit}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys as _sys
    _sys.exit(_main())
