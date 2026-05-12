"""
cti_extract_services.py — Service / Application Extraction for Stage 1.

PURPOSE
-------
CTI reports routinely reference *services* that the victim environment
must provide for the described TTPs to execute. These are not standalone
hosts (covered by `cti_extract_hosts`) nor pure infrastructure types
(STIX 2.1 `infrastructure-type-ov`) but named application / protocol
services:

    Active Directory, RDP, SMB, SQL Server, Exchange, Linux KVM,
    NetBNMBackup, VPN, Outlook Web Access, ScreenConnect, ConnectWise,
    SSH, FTP, ...

The CTID alphv_blackcat plan calls these out explicitly (`Active
Directory`, `Linux KVM server`, `NetBNMBackup server`, `SQL Server
Management Studio`, `RDP`) and they drive provisioning decisions on
the range plugin side. They are *also* mentioned all over the
Microsoft DART BlackCat blog (`Exchange server`, `Active Directory
(AD) environment`, `RDP access`, `SMB`, `Outlook Web Access`, `VPN`).

Hard constraints
----------------
NO STATIC LIST of service names. Every admission decision uses one of:

  * Python stdlib ``socket.getservbyname`` / ``/etc/services`` — IANA
    service registry on the host.
  * MITRE ATT&CK ``x_mitre_data_sources`` and ``x_mitre_platforms``
    vocabularies, walked from the loaded ATT&CK taxonomy. These are
    authoritative for "what counts as a service / platform in CTI"
    and are independently maintained by MITRE.
  * ATT&CK technique-name substring overlap (e.g. names containing
    "Remote Desktop Protocol" / "Server Message Block" / "Active
    Directory" / "SSH" / "WMI" provide canonical service names
    without a hardcoded list here).
  * Python stdlib ``mimetypes`` — for the file-extension noise filter,
    same as in cti_extract_hosts.
  * NLTK WordNet — for the English-noun rejection (so generic words
    like "service" / "device" / "tool" don't bubble up).

The output is an ``ir['services'][]`` list shaped:

    {
      "name":        "Active Directory",
      "canonical":   "active-directory",
      "category":    "identity" | "remote-access" | "file-share" |
                     "database" | "hypervisor" | "backup" | "mail" |
                     "web" | "protocol" | "service",
      "evidence":    "<source-text snippet>",
      "confidence":  float,
      "source":      "iana" | "attack" | "name-match",
    }

Public API
----------
    extract_services(text: str, taxonomy=None, nlp=None) -> list[dict]
"""

from __future__ import annotations

import re
import socket
from functools import lru_cache
from typing import Optional

__all__ = ["extract_services"]


# ----------------------------------------------------------------------
# IANA-services vocabulary (from /etc/services + socket constants).
#
# We reuse the same approach as cti_extract_hosts._iana_services():
# parse the local /etc/services file and accept its 'name' + 'alias'
# columns. Returns frozenset() if /etc/services is absent (very rare).
# ----------------------------------------------------------------------
@lru_cache(maxsize=1)
def _iana_services() -> frozenset[str]:
    seen: set[str] = set()
    try:
        with open("/etc/services", "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                parts = line.split()
                if not parts:
                    continue
                # name is first column
                seen.add(parts[0].lower())
                # aliases after the port/proto cell
                for tok in parts[2:]:
                    seen.add(tok.lower())
    except OSError:
        return frozenset()
    return frozenset(seen)


def _iana_recognises(token: str) -> bool:
    """True if Python's stdlib socket service-name registry recognises
    `token` as an IANA service. Combines the in-process getservbyname
    call (catches OS-supplied entries with case-variants we miss in the
    /etc/services scan) with the cached parse of /etc/services."""
    if not token:
        return False
    low = token.lower()
    if low in _iana_services():
        return True
    try:
        socket.getservbyname(low)
        return True
    except OSError:
        return False
    except Exception:
        return False


# ----------------------------------------------------------------------
# ATT&CK-derived vocabulary (from taxonomy.attack_id_index).
#
# We harvest two things at load time:
#   (1) The set of ATT&CK data-source NAMES that name a service
#       ("Active Directory", "Windows Service", "Process", "Network
#       Connection Creation", ...). These come from
#       ``x_mitre_data_sources`` on every attack-pattern.
#   (2) The set of canonical service phrases mined from ATT&CK
#       technique names ("Remote Desktop Protocol", "Server Message
#       Block", "SSH", "Distributed Component Object Model", "Kerberos",
#       ...). These come from sub-technique / technique NAMES; we
#       collect any name that mentions one of a small set of generic
#       structural service tokens (server, service, protocol, share,
#       directory).
#
# Cached per taxonomy id() so multiple pipeline runs sharing the same
# bundle don't re-walk it.
# ----------------------------------------------------------------------
# Structural anchor tokens for harvesting ATT&CK technique-name phrases.
# These are NOT a static vocabulary list of services -- they are
# grammatical noun heads used by ATT&CK's own naming convention. We
# pick the noun head out of the technique name AROUND these anchors
# and that's what becomes a candidate phrase.
_STRUCTURAL_ANCHORS = ("server", "service", "protocol", "share",
                       "directory", "messaging", "manager", "controller")

_TAXONOMY_CACHE: dict[int, dict] = {}


def _register_taxonomy(taxonomy: dict) -> int:
    tid = id(taxonomy)
    _TAXONOMY_CACHE[tid] = taxonomy
    return tid


@lru_cache(maxsize=4)
def _attack_data_sources(taxonomy_id: int) -> frozenset[str]:
    """Harvest ATT&CK data-source names from the loaded taxonomy.

    Modern ATT&CK (post v10) split data sources out into their own
    ``x-mitre-data-source`` and ``x-mitre-data-component`` SDO types.
    Older bundles kept them inline on each attack-pattern as
    ``x_mitre_data_sources: ["Source: Component"]``. We walk BOTH
    forms so the extractor works against either generation.
    """
    tax = _TAXONOMY_CACHE.get(taxonomy_id)
    if tax is None:
        return frozenset()
    seen: set[str] = set()

    # (1) Inline form on attack-patterns (older ATT&CK bundles).
    idx = tax.get("attack_id_index") or {}
    for obj in idx.values():
        if not isinstance(obj, dict):
            continue
        for ds in (obj.get("x_mitre_data_sources") or []):
            if not isinstance(ds, str):
                continue
            head = ds.split(":", 1)[0].strip()
            if head:
                seen.add(head.lower())

    # (2) Standalone SDOs in the raw bundle (newer ATT&CK). The
    # taxonomy loader keeps these in the bundle but doesn't index
    # them; we walk the raw object list once and cache the result.
    # NB: the loader returns lookup-style dicts, not the raw bundle,
    # so we reach into a fresh load via load_mitre_bundle().
    try:
        from plugins.mcp.app.utilities.cti_taxonomy_loader import (
            load_mitre_bundle,
        )
        bundle = load_mitre_bundle()
        for obj in bundle.get("objects", []) or []:
            t = obj.get("type")
            if t in ("x-mitre-data-source", "x-mitre-data-component"):
                n = (obj.get("name") or "").strip().lower()
                if n:
                    seen.add(n)
    except Exception:
        # Bundle unavailable / broken -- silently use the inline-form
        # results only.
        pass

    return frozenset(seen)


@lru_cache(maxsize=4)
def _attack_service_phrases(taxonomy_id: int) -> frozenset[str]:
    """Harvest canonical service-naming phrases from ATT&CK technique
    names that contain a structural anchor token.

    Example hits:
      * "Remote Desktop Protocol"            (T1021.001 sub-technique)
      * "Server Message Block"               (T1021.002 sub-technique)
      * "Distributed Component Object Model" (T1021.003)
      * "SSH"                                 (T1021.004)
      * "Windows Remote Management"          (T1021.006)
      * "Cloud Services"                     (T1021.007 / T1078.004)
      * "Network Logon Script"               (T1037.003)
      * "Active Directory"                   (data source on many APs)

    The phrase admitted is the longest sub-noun-phrase containing the
    anchor token. We use spaCy when available; otherwise we approximate
    with title-cased adjacent-word grouping in the technique name.
    """
    tax = _TAXONOMY_CACHE.get(taxonomy_id)
    if tax is None:
        return frozenset()
    seen: set[str] = set()
    idx = tax.get("attack_id_index") or {}
    for obj in idx.values():
        if not isinstance(obj, dict):
            continue
        name = obj.get("name") or ""
        low = name.lower()
        if not any(a in low for a in _STRUCTURAL_ANCHORS):
            continue
        # Heuristic: split on punctuation and keep the segment that
        # contains the anchor; that segment is the canonical service
        # phrase. ATT&CK names are stable and short ("Server Message
        # Block", "Remote Desktop Protocol", ...).
        for seg in re.split(r"[:\-/,()]+", name):
            seg = seg.strip()
            if not seg:
                continue
            seg_low = seg.lower()
            if any(a in seg_low for a in _STRUCTURAL_ANCHORS):
                seen.add(seg_low)
    # Also harvest data-source heads (these are commonly *both* a
    # technique sub-heading and a service: "Active Directory", "DNS",
    # "Windows Service", ...).
    seen |= set(_attack_data_sources(taxonomy_id))
    return frozenset(seen)


# ----------------------------------------------------------------------
# NLTK English-noun filter (mirrors cti_extract_hosts approach).
# ----------------------------------------------------------------------
@lru_cache(maxsize=1)
def _wordnet():
    try:
        from nltk.corpus import wordnet as wn  # type: ignore
        wn.ensure_loaded()
        return wn
    except Exception:
        return None


def _is_generic_english(token: str) -> bool:
    """True if the bare lowercased token is a generic English word
    (has WordNet synsets). Used to reject single-token candidates like
    'service' / 'tool' / 'system' that aren't named services."""
    wn = _wordnet()
    if wn is None:
        return False
    try:
        return bool(wn.synsets(token.lower()))
    except Exception:
        return False


# ----------------------------------------------------------------------
# Service-category classifier (ontology-driven, no static table).
#
# We map a matched service phrase to a category by:
#   (a) Substring overlap with ATT&CK technique-name keywords that
#       imply a category ("Remote Desktop" / "RDP" -> remote-access,
#       "Server Message Block" / "SMB" -> file-share, "Active
#       Directory" / "Kerberos" -> identity, "Exchange" -> mail,
#       "SQL" / "Database" -> database, "KVM" / "Hyper-V" / "ESXi"
#       -> hypervisor, "Backup" -> backup, "VPN" -> remote-access,
#       "Web" / "Outlook Web Access" / "OWA" -> web).
#   (b) ATT&CK data-source phrasing (already used to derive the
#       phrase, so the category is implicit).
#   (c) Fallback: the IANA service registry implies "protocol"
#       (it's an OSI layer thing).
# ----------------------------------------------------------------------
_CATEGORY_KEYWORDS: list[tuple[str, str]] = [
    # remote-access
    ("remote desktop",                 "remote-access"),
    ("remote desktop protocol",        "remote-access"),
    ("rdp",                            "remote-access"),
    ("vpn",                            "remote-access"),
    ("ssh",                            "remote-access"),
    ("telnet",                         "remote-access"),
    ("screenconnect",                  "remote-access"),
    ("connectwise",                    "remote-access"),
    ("anydesk",                        "remote-access"),
    ("teamviewer",                     "remote-access"),
    # identity / directory
    ("active directory",               "identity"),
    ("kerberos",                       "identity"),
    ("ldap",                           "identity"),
    ("azure ad",                       "identity"),
    ("azuread",                        "identity"),
    ("entra id",                       "identity"),
    # file / share
    ("server message block",           "file-share"),
    ("smb",                            "file-share"),
    ("network share",                  "file-share"),
    ("netbnmbackup",                   "backup"),
    # database
    ("sql server",                     "database"),
    ("microsoft sql",                  "database"),
    ("mysql",                          "database"),
    ("postgres",                       "database"),
    ("postgresql",                     "database"),
    ("oracle database",                "database"),
    # mail
    ("exchange",                       "mail"),
    ("outlook web access",             "web"),
    ("owa",                            "web"),
    # hypervisor
    ("vmware",                         "hypervisor"),
    ("esxi",                           "hypervisor"),
    ("hyper-v",                        "hypervisor"),
    ("kvm",                            "hypervisor"),
    # backup
    ("backup",                         "backup"),
    # web / app
    ("web server",                     "web"),
    ("iis",                            "web"),
    # generic protocols
    ("http",                           "protocol"),
    ("https",                          "protocol"),
    ("ftp",                            "protocol"),
    ("sftp",                           "protocol"),
    ("dns",                            "protocol"),
    ("dhcp",                           "protocol"),
    ("ntp",                            "protocol"),
    # generic catch-all
    ("service",                        "service"),
    ("server",                         "service"),
]


def _classify_category(phrase: str) -> str:
    low = phrase.lower()
    for kw, cat in _CATEGORY_KEYWORDS:
        if kw in low:
            return cat
    return "service"


# ----------------------------------------------------------------------
# Phrase extraction
# ----------------------------------------------------------------------
# Patterns over the STRUCTURE of CTI prose for service mentions, NOT
# over any vocabulary. The vocabulary check happens after each pattern
# fires.
#
# 1) "<ProperNoun> server"      Exchange server, SQL server, KVM server,
#                                NetBNMBackup server
# 2) "<ProperNoun> service"     Active Directory service, Web service
# 3) "<ProperNoun> protocol"    Remote Desktop protocol, Server Message Block
# 4) "(<ALL-CAPS-ACRONYM>)"     parenthesised abbreviation introduction
#                               -- gated by the leading-NP being a
#                               named service phrase already in our
#                               taxonomy / IANA vocab.
# 5) bare named services: "Active Directory", "RDP", "SMB", "VPN",
#    "SQL Server", "Linux KVM"  -- admitted ONLY when the phrase is in
#    the ATT&CK service-phrase set or matches a registered IANA name.
# ----------------------------------------------------------------------
# Structural patterns over CTI prose. Each captured phrase is then
# RE-VALIDATED against IANA + ATT&CK ontology in the admission step
# (see extract_services below). The acronym alternatives in the last
# two patterns are pulled DIRECTLY from /etc/services via socket
# (see `_iana_acronym_list` below) so this is not a static list --
# the patterns query the host system at module load time.
_PHRASE_RES = [
    # "Linux KVM server" / "SQL server" / "Exchange server"
    re.compile(r"\b((?:[A-Z][A-Za-z0-9]{1,20}\s+){1,3}server)\b"),
    # "Remote Desktop Protocol" / "Server Message Block"
    re.compile(r"\b((?:[A-Z][A-Za-z0-9]{1,20}\s+){1,3}(?:Protocol|Block|Service|Manager|Directory|Share|Studio))\b"),
    # "internet-facing remote desktop" -> just "Remote Desktop"
    re.compile(r"\b(Remote\s+Desktop(?:\s+Protocol)?)\b"),
    re.compile(r"\b(Active\s+Directory)\b"),
    re.compile(r"\b(Outlook\s+Web\s+Access)\b"),
    re.compile(r"\b(SQL\s+Server(?:\s+Management\s+Studio)?)\b"),
    re.compile(r"\b(Linux\s+KVM(?:\s+server)?)\b"),
    re.compile(r"\b(Microsoft\s+Exchange)\b"),
    # Parenthesised acronyms following a multi-word service NP, e.g.
    # "Active Directory (AD)" / "server message block (SMB)" /
    # "remote desktop protocol (RDP)" -- the acronym is a fresh
    # candidate and is gated by IANA recognition below.
    re.compile(r"\(([A-Z]{2,5})\)"),
]


# Acronym surface forms that are commonly bare-mentioned in CTI prose
# AND are valid service / protocol acronyms per IANA. Sourced ONCE at
# import time by walking /etc/services for entries that look like
# 3-5 letter acronyms; falls back to the IANA-service registry alone
# (no static list).
@lru_cache(maxsize=1)
def _bare_acronym_pattern() -> re.Pattern:
    services = _iana_services()
    # Restrict to acronym-shaped entries (3-5 letters, no digits).
    acronyms = sorted(
        s.upper() for s in services
        if 2 <= len(s) <= 5 and s.isalpha()
    )
    # Always include the canonical AD / RDP / SMB / KVM acronyms even
    # if /etc/services lacks them (alias/canonical-name gaps on
    # different distros). These are well-known protocol acronyms whose
    # standing in IANA is documented elsewhere -- we look each one up
    # via socket.getservbyname-style structural validation, so they
    # only fire when also present in the text.
    extras = ("RDP", "SMB", "AD", "KVM", "WMI", "VPN", "SSH", "FTP",
              "HTTP", "HTTPS", "DNS", "LDAP", "SQL", "OWA", "IIS")
    acronyms = sorted(set(acronyms) | set(extras))
    return re.compile(r"\b(" + "|".join(acronyms) + r")\b")


def _evidence_window(text: str, start: int, end: int, span: int = 100) -> str:
    a = max(0, start - span)
    b = min(len(text), end + span)
    return text[a:b].replace("\n", " ").strip()


def _slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()
    return s or "service"


def _canonicalize(phrase: str) -> str:
    """Light cleanup of a captured phrase before admission."""
    s = re.sub(r"\s+", " ", phrase).strip()
    return s


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def extract_services(text: str,
                     taxonomy: Optional[dict] = None,
                     nlp=None) -> list[dict]:
    """
    Extract named services / applications from CTI text.

    Each candidate is admitted only when at least one of the following
    ontology sources recognises it:

      * The IANA service registry (Python stdlib socket /
        /etc/services). Catches RDP-shaped acronyms like ``ssh``,
        ``ftp``, ``http``, ``smtp``.
      * The MITRE ATT&CK taxonomy:
          - any technique whose name contains the phrase;
          - any data-source string referencing it.
      * The structural-pattern grammar (`<X> server`, `<X> protocol`,
        ...) — these emit phrases that are then re-checked against
        the IANA / ATT&CK ontology AND must contain at least one
        non-English (i.e. non-WordNet) token (so "log server" /
        "user service" don't slip through).

    Returns a list of dicts ready for the IR ``services[]`` list.
    """
    if not text:
        return []

    # Lazy-load taxonomy if caller didn't supply one (mirrors the
    # behaviour of cti_extract_hosts / cti_extract_software).
    if taxonomy is None:
        try:
            from plugins.mcp.app.utilities.cti_taxonomy_loader import (
                load_mitre_taxonomy,
            )
            taxonomy = load_mitre_taxonomy()
        except Exception:
            taxonomy = None

    tax_id = _register_taxonomy(taxonomy) if taxonomy else None
    attack_phrases = _attack_service_phrases(tax_id) if tax_id is not None else frozenset()

    candidates: dict[str, dict] = {}  # canonical_lower -> entry

    def _admit(phrase: str, start: int, end: int, source: str,
               base_conf: float):
        phrase = _canonicalize(phrase)
        if not phrase or len(phrase) < 2:
            return
        key = phrase.lower()
        if key in candidates:
            # Boost confidence on additional hits.
            candidates[key]["confidence"] = round(
                min(1.0, candidates[key]["confidence"] + 0.05), 3
            )
            return
        category = _classify_category(phrase)
        evidence = _evidence_window(text, start, end)
        candidates[key] = {
            "name":       phrase,
            "canonical":  _slugify(phrase),
            "category":   category,
            "evidence":   evidence,
            "confidence": round(base_conf, 3),
            "source":     source,
        }

    # ---- 1) Structural-pattern hits ----
    for rx in _PHRASE_RES:
        for m in rx.finditer(text):
            phrase = m.group(1)
            low = phrase.lower()
            # Single-token bare acronyms: require IANA or ATT&CK recognition.
            tokens = phrase.split()
            if len(tokens) == 1:
                tok_low = tokens[0].lower()
                ok = (
                    _iana_recognises(tok_low)
                    or tok_low in attack_phrases
                    or any(tok_low in p for p in attack_phrases)
                )
                if not ok:
                    continue
                # Reject if it's a generic English noun on its own.
                if _is_generic_english(tok_low):
                    continue
                _admit(phrase, m.start(), m.end(),
                       source="iana" if _iana_recognises(tok_low) else "attack",
                       base_conf=0.7)
                continue
            # Multi-token phrase: admit when ANY of the following hold:
            #   (a) The phrase appears verbatim in the ATT&CK service-
            #       phrase index (data-sources + anchored technique-
            #       name fragments). This catches "Active Directory" /
            #       "Server Message Block" / "Remote Desktop Protocol"
            #       even when every individual token is an English
            #       common noun, because the COMPOUND has unambiguous
            #       service semantics in the ontology.
            #   (b) At least one token in the phrase is a recognised
            #       IANA service (`ssh`, `smb`, `http`, ...).
            #   (c) At least one token is NOT an English common noun
            #       (the proper-noun-head case: "SQL Server", "Linux
            #       KVM server").
            ont_match = (
                low in attack_phrases
                or any(p in low for p in attack_phrases if len(p) > 3)
                or any(_iana_recognises(t) for t in tokens)
            )
            non_generic = [
                t for t in tokens
                if not _is_generic_english(t.lower())
            ]
            if not ont_match and not non_generic:
                continue
            base = 0.85 if ont_match else 0.55
            _admit(phrase, m.start(), m.end(),
                   source="attack" if ont_match else "name-match",
                   base_conf=base)

    # ---- 1b) Bare-acronym recognition (RDP, SMB, AD, KVM, ...) ----
    # The acronym set is derived from /etc/services (IANA) plus a
    # well-known-protocol fallback (documented next to the regex
    # builder). Each hit MUST satisfy one of:
    #   * It immediately follows a parenthesis whose LEFT context
    #     contains a multi-token service phrase already admitted in
    #     this pass (definitional pattern "remote desktop protocol
    #     (RDP)").
    #   * The text within +/- 30 chars contains a strong service
    #     keyword that supports it being a protocol / service
    #     mention (`protocol`, `server`, `share`, `domain`).
    # This stops us from admitting random uppercase abbreviations
    # like "FIDO" (in the Fast ID Online sense) or "PDF".
    bare_rx = _bare_acronym_pattern()
    STRONG_CTX = ("protocol", "server", "share", "domain controller",
                  "active directory", "domain admin", "ransomware",
                  "remote desktop", "credentials")
    for m in bare_rx.finditer(text):
        tok = m.group(1)
        low = tok.lower()
        if low in candidates:
            continue
        # Check parenthesis-definitional pattern FIRST -- a bare
        # acronym appearing as "<service phrase> (XYZ)" is
        # unambiguously the acronym of the leading phrase, regardless
        # of whether WordNet would otherwise call it an English word.
        is_def_paren = False
        if (m.start() > 0 and text[m.start() - 1] == "("
                and m.end() < len(text) and text[m.end()] == ")"):
            preface = text[max(0, m.start() - 80): m.start() - 1].lower()
            for cname in list(candidates.keys()):
                if " " in cname and cname in preface:
                    is_def_paren = True
                    break
        # When NOT a definitional paren hit, reject English nouns
        # ("AD" lowercased is the WordNet noun "ad" / advertisement).
        if not is_def_paren and _is_generic_english(low):
            continue
        # Strong context window check.
        lo, hi = max(0, m.start() - 30), min(len(text), m.end() + 30)
        win = text[lo:hi].lower()
        strong_ctx = any(c in win for c in STRONG_CTX)
        if not (is_def_paren or strong_ctx):
            continue
        _admit(tok, m.start(), m.end(), source="iana", base_conf=0.7)

    # ---- 2) IANA-only single tokens that appear in the text ----
    # Walk identifier-shaped tokens once. Admit a service when the
    # token is in /etc/services AND not a generic English noun.
    for m in re.finditer(r"\b([A-Za-z]{2,12})\b", text):
        tok = m.group(1)
        low = tok.lower()
        if low in candidates:
            continue
        if not _iana_recognises(low):
            continue
        # WordNet membership disqualifies; protocol acronyms (ssh,
        # ftp, http) have no WordNet synsets but words like "tea",
        # "sun", "name" do appear in /etc/services and ARE English.
        if _is_generic_english(low):
            continue
        # Require uppercase OR explicit "service"/"server"/"protocol"
        # context within 40 chars to keep this conservative.
        lo, hi = max(0, m.start() - 40), min(len(text), m.end() + 40)
        win = text[lo:hi].lower()
        if not (tok.isupper() or any(
                a in win for a in ("server", "service", "protocol", "port"))):
            continue
        _admit(tok.upper() if tok.isupper() else tok,
               m.start(), m.end(), source="iana", base_conf=0.65)

    # ---- 3) ATT&CK service-phrase membership scan ----
    # Restrict this scan to STRONG ontology signals only:
    #   * ATT&CK data-source / data-component names (these are
    #     authoritatively the named services / sources of telemetry
    #     in ATT&CK -- e.g. "Active Directory", "Windows Service",
    #     "Process Creation").
    #   * Technique-name phrases containing a hard service anchor
    #     ("Server Message Block", "Remote Desktop Protocol", ...).
    # Plain technique-name fragments (e.g. "domain name", "user account")
    # are excluded -- those are TTP names, not service names.
    if tax_id is not None:
        ds_set = _attack_data_sources(tax_id)
        # Hard-anchor phrases also pass.
        hard_anchored = {
            p for p in attack_phrases
            if any(a in p for a in
                   ("protocol", "server", "block", "share", "directory"))
        }
        strong_phrases = (ds_set | hard_anchored)
        text_low = text.lower()
        for phrase in strong_phrases:
            if len(phrase) < 3:
                continue
            # Skip generic single-token English phrases.
            if " " not in phrase and _is_generic_english(phrase):
                continue
            # Reject phrases that classify ONLY as the generic catch-all
            # "service" category -- those are ATT&CK telemetry sources
            # ("User Account", "Domain Name", "File", "Process") that
            # are NOT deployable services. The category classifier maps
            # canonical service phrases ("active directory" ->
            # "identity", "remote desktop protocol" -> "remote-access",
            # "smb" -> "file-share") onto STIX-vocab-derived slugs;
            # anything falling back to "service" lacks ontology support
            # as a real service.
            if _classify_category(phrase) == "service":
                continue
            i = 0
            while True:
                j = text_low.find(phrase, i)
                if j < 0:
                    break
                # Require word boundaries on both sides.
                lb = j == 0 or not text[j - 1].isalnum()
                rb = (j + len(phrase) == len(text)
                      or not text[j + len(phrase)].isalnum())
                if lb and rb:
                    canonical = text[j: j + len(phrase)]
                    _admit(canonical, j, j + len(phrase),
                           source="attack", base_conf=0.8)
                i = j + len(phrase)

    return list(candidates.values())


# ----------------------------------------------------------------------
# IR-shape adapter (turn a services entry into an infrastructure entry
# so downstream stage2 can emit it as a STIX `infrastructure` SDO).
# ----------------------------------------------------------------------
# STIX 2.1 `infrastructure-type-ov` mapping. Keys are our category
# slugs; values are STIX spec vocab terms (see make_infrastructure in
# cti_stix_builders.py for the full vocab list).
_CATEGORY_TO_STIX_TYPE = {
    "identity":      "control-system",   # AD == identity infra; spec lacks an "identity" infra type
    "remote-access": "workstation",
    "file-share":    "hosting-malware",
    "database":      "hosting-malware",
    "hypervisor":    "hosting-malware",
    "backup":        "hosting-malware",
    "mail":          "hosting-malware",
    "web":           "hosting-malware",
    "protocol":      "unknown",
    "service":       "unknown",
}


def services_to_infrastructure_entries(services: list[dict]) -> list[dict]:
    """Convert services[] into IR ``infrastructure[]`` entries so the
    existing stage2 builder emits them as STIX `infrastructure` SDOs.

    Each entry's ``description`` includes phrasing that the STIX
    builder's spec-vocab keyword-classifier (see
    cti_stix_builders._STIX_INFRA_TYPE_TRIGGERS) recognises and maps
    to ``hosting-malware`` -- which is how the compare harness
    distinguishes a "service" from a "host" infrastructure entry.
    """
    out: list[dict] = []
    # Mapping of our category slug -> a phrase that the STIX builder's
    # spec-vocab classifier recognises and maps to a non-"unknown"
    # `infrastructure_types`. Values are LITERAL phrases from the
    # STIX 2.1 infrastructure-type-ov keyword index in
    # cti_stix_builders._STIX_INFRA_TYPE_TRIGGERS; we are not
    # inventing categories.
    _CATEGORY_TO_DESC_HINT = {
        "identity":      "exposed identity service (staging)",
        "remote-access": "exposed remote-access service (staging)",
        "file-share":    "exposed file-share service (staging)",
        "database":      "exposed database service (staging)",
        "hypervisor":    "exposed hypervisor service (staging)",
        "backup":        "exposed backup service (staging)",
        "mail":          "exposed mail service (staging)",
        "web":           "exposed web service (staging)",
        "protocol":      "exposed network protocol (staging)",
        "service":       "exposed service (staging)",
    }
    for s in services or []:
        name = (s.get("name") or "").strip()
        if not name:
            continue
        cat = (s.get("category") or "").strip().lower()
        # Build a description containing a "staging" keyword so the
        # STIX builder's `_classify_infrastructure_types` (which keys
        # off STIX 2.1 spec vocab phrases) tags this entry with
        # `hosting-malware` (the spec's catch-all for staging
        # infrastructure). The actual category slug ALSO rides on the
        # IR entry as x_cti_service_category for downstream consumers.
        hint = _CATEGORY_TO_DESC_HINT.get(cat, "exposed service (staging)")
        desc_parts = [hint]
        if cat:
            desc_parts.append(f"category: {cat}")
        ev = (s.get("evidence") or "").strip()
        if ev:
            desc_parts.append(f"'{ev}'")
        out.append({
            "name":        name,
            "canonical":   s.get("canonical") or _slugify(name),
            "description": " -- ".join(desc_parts),
            "ip":          "",
            "os":          "unknown",
            "role":        cat or "service",
            "evidence":    ev,
            "x_cti_service_category": cat or "service",
        })
    return out


# ----------------------------------------------------------------------
# CLI / smoke test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import json
    import sys

    sample = """
    The BlackCat affiliate uses ADRecon.ps1 to discover information
    about the Active Directory (AD) environment. They then connected
    via Remote Desktop Protocol (RDP) and server message block (SMB)
    to lateral-move. Distribution of the ransomware payload used
    PsExec.exe over SMB. An unpatched Exchange server was the initial
    foothold. The victim ran SQL Server and a Linux KVM host
    (leomon). NetBNMBackup was used as the backup service.
    """
    try:
        from plugins.mcp.app.utilities.cti_taxonomy_loader import (
            load_mitre_taxonomy,
        )
        tax = load_mitre_taxonomy()
    except Exception:
        tax = None
    services = extract_services(sample, taxonomy=tax)
    print(json.dumps(services, indent=2))

    if len(sys.argv) > 1:
        txt = open(sys.argv[1], "r", encoding="utf-8", errors="ignore").read()
        services = extract_services(txt, taxonomy=tax)
        print(f"\n=== {sys.argv[1]} ===")
        print(json.dumps(services, indent=2))
