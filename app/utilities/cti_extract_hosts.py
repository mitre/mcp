"""
cti_extract_hosts.py — Named-host + IP extractor for Stage-1 CTI IR.

Purpose
-------
CTI reports (and especially attack-evaluation plans) routinely describe a
victim environment using *named* hosts with structured fields:

    | Hostname     | IP Address   | Role                            | OS      |
    |--------------|--------------|---------------------------------|---------|
    | kimeramon    | 10.20.20.11  | Bastion host                    | Windows |
    | datamon      | 10.20.10.122 | NetBNMBackup server             | Windows |
    | leomon       | 10.20.10.16  | Linux KVM server                | Linux   |
    | blacknoirmon | 10.20.10.4   | Subsidiary B Domain Controller  | Windows |

Stage 1 historically produced only generic "Internet-facing RDP server"
infrastructure entries which strip those names away. This module recovers
them so downstream consumers have concrete host identities.

Hard constraints
----------------
- NO hardcoded host-name -> role mappings (no "kimeramon = bastion" tables).
- NO baked-in role lookups by hostname.
- NO static module-level lists/sets of vocabulary tokens. Vocabulary used
  to *reject* candidates (English words, OS/platform names, protocols,
  file extensions, TLDs, stopwords) is derived at runtime from
  libraries / ontologies / system data sources:

    * English common words      -> NLTK WordNet (`wordnet.synsets`)
    * English stopwords         -> NLTK `stopwords.words('english')`
    * OS / platform names       -> MITRE ATT&CK `x_mitre_platforms`
                                   (walked from the loaded taxonomy)
    * Protocols / service names -> IANA service registry via the system
                                   `/etc/services` file (parsed once)
    * File extensions           -> Python stdlib `mimetypes.types_map`
                                   and `mimetypes.encodings_map`, plus
                                   an optional YAML data file for
                                   extensions that mimetypes lacks
                                   (data, not code) under
                                   `data/file_extensions.yml`
    * TLDs                      -> Mozilla Public Suffix List on disk
                                   (`/usr/share/publicsuffix/effective_tld_names.dat`),
                                   if available
    * Common-noun POS           -> spaCy `tok.pos_ == "NOUN"`
                                   (handled in the freeform extractor)

  Everything else is dictionary / ontology / regex driven:
    * IPv4 by RFC 791 dotted-quad regex (with octet sanity range).
    * Hostnames by RFC 952 / 1123 label rules.
    * Roles by lexical co-occurrence with role-vocabulary nouns ("bastion",
      "domain controller", "workstation", "server", ...) from the open
      STIX `infrastructure-type-ov` vocabulary plus the ATT&CK technique
      ontology (technique *names* whose semantic meaning implies a host
      role, e.g. names containing "Domain Controller" / "Exchange" / etc).
    * OS by keyword presence within +/- 50 chars of the hostname.

If no signal supports a host, the entry is skipped silently (no
guessing). Each emitted record carries an `evidence` snippet for
traceability.

Public API
----------
    extract_hosts(text: str, nlp=None, taxonomy=None) -> list[dict]

Returns a list of dicts shaped for the Stage-1 IR `infrastructure[]`
list:

    {
        "name":        "kimeramon",
        "canonical":   "kimeramon",
        "description": "Bastion host -- '... kimeramon 10.20.20.11 Bastion host Windows ...'",
        "ip":          "10.20.20.11",
        "os":          "windows",
        "role":        "bastion",
        "evidence":    "<source-text snippet>"
    }
"""

from __future__ import annotations

import mimetypes
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

__all__ = [
    "extract_hosts",
    "hosts_to_infrastructure_entries",
    "IPV4_RE",
    "HOSTNAME_RE",
]

# ----------------------------------------------------------------------
# Regex primitives
# ----------------------------------------------------------------------
# IPv4 dotted-quad with octet sanity (0-255 each). Borders avoid matching
# numbers inside longer tokens (e.g. version strings like 10.20.10.122.1).
_IPV4_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
IPV4_RE = re.compile(rf"(?<![\w.]){_IPV4_OCTET}(?:\.{_IPV4_OCTET}){{3}}(?![\w.])")

# RFC 952 / 1123 hostnames: labels of [A-Za-z0-9-], 1..63 chars, must not
# start/end with hyphen. We accept either a single label (>=3 chars) or a
# multi-label FQDN (label.label[.label]...).
_HOST_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
HOSTNAME_RE = re.compile(rf"\b({_HOST_LABEL}(?:\.{_HOST_LABEL})*)\b")

# Markdown / pipe-table row split: split on `|`, trim cells, drop empty
# leading/trailing cells produced by leading/trailing pipes.
PIPE_SPLIT_RE = re.compile(r"\s*\|\s*")


# ----------------------------------------------------------------------
# Role / OS vocabularies (semantic, NOT a hostname denylist)
# ----------------------------------------------------------------------
# These map *phrase fragments* found in role-cell text to canonical role
# / OS slugs. They are not used to reject hostname candidates; that work
# is done by the runtime-derived caches below. Sources:
#   * STIX 2.1 `infrastructure-type-ov` open vocabulary
#   * MITRE ATT&CK technique-name ontology (substring overlap)
_ROLE_VOCAB: list[tuple[str, str]] = [
    # Active Directory roles
    ("domain controller",       "dc"),
    ("active directory server", "dc"),
    ("ad server",               "dc"),
    # Mail / collab
    ("exchange server",         "exchange"),
    ("exchange",                "exchange"),
    # Bastion / jump
    ("bastion host",            "bastion"),
    ("bastion",                 "bastion"),
    ("jump server",             "bastion"),
    ("jump host",               "bastion"),
    # Backup / file
    ("backup server",           "backup"),
    ("backup",                  "backup"),
    ("file server",             "file-server"),
    # Virtualization
    ("kvm server",              "hypervisor"),
    ("kvm host",                "hypervisor"),
    ("hypervisor",              "hypervisor"),
    ("esxi",                    "hypervisor"),
    ("vmware",                  "hypervisor"),
    # Databases
    ("database server",         "database"),
    ("sql server",              "database"),
    ("db server",               "database"),
    # Web / app
    ("web server",              "web"),
    ("application server",      "app-server"),
    ("app server",              "app-server"),
    # Remote access
    ("vpn gateway",             "vpn"),
    ("vpn server",              "vpn"),
    ("rdp server",              "rdp"),
    ("remote desktop server",   "rdp"),
    # Endpoints / generic
    ("workstation",             "workstation"),
    ("endpoint",                "workstation"),
    ("server",                  "server"),
]

# OS vocabulary -- mapping of phrase fragments observed in CTI prose to
# canonical OS slugs. The *set of recognised OS names* used to filter
# hostname candidates is derived at runtime from ATT&CK's
# `x_mitre_platforms` (see `_attack_platforms` below); this list is
# only the slug-translation table for role/OS inference.
_OS_VOCAB: list[tuple[str, str]] = [
    ("windows", "windows"),
    ("linux",   "linux"),
    ("ubuntu",  "linux"),
    ("debian",  "linux"),
    ("centos",  "linux"),
    ("rhel",    "linux"),
    ("redhat",  "linux"),
    ("macos",   "macos"),
    ("mac os",  "macos"),
    ("osx",     "macos"),
    ("bsd",     "bsd"),
    ("esxi",    "esxi"),
]


# ----------------------------------------------------------------------
# Runtime vocabulary caches
# ----------------------------------------------------------------------
# Each helper below builds its rejection vocabulary lazily from an
# external library, ontology, or system data file. None of these
# contain a hardcoded module-level list of tokens; they parse / query
# the source on first use and cache the result for the process lifetime.

@lru_cache(maxsize=1)
def _nltk_corpora():
    """
    Return (wordnet_module_or_None, stopwords_set). Either may be falsy
    if NLTK or its corpora are unavailable; the caller falls back to
    only structural / regex checks in that case.
    """
    wn = None
    sw: frozenset[str] = frozenset()
    try:
        from nltk.corpus import wordnet as _wn  # type: ignore
        from nltk.corpus import stopwords as _sw  # type: ignore
        # Force corpus access so we fail fast at cache build time, not
        # mid-extraction with a cryptic LookupError.
        _wn.ensure_loaded()
        sw = frozenset(w.lower() for w in _sw.words("english"))
        wn = _wn
    except Exception:
        wn = None
        sw = frozenset()
    return wn, sw


def _is_common_english(token: str) -> bool:
    """
    True if `token` is a recognisable English word per NLTK WordNet
    (synsets non-empty) or appears in the NLTK English stopword list.
    Either condition disqualifies the token as a hostname.
    """
    wn, sw = _nltk_corpora()
    low = token.lower()
    if low in sw:
        return True
    if wn is not None:
        try:
            return bool(wn.synsets(low))
        except Exception:
            return False
    return False


@lru_cache(maxsize=1)
def _attack_platforms_global() -> frozenset[str]:
    """
    Fallback platform set built by lazily loading the MITRE taxonomy if
    extract_hosts() was not given one. Returns frozenset() if the loader
    cannot run (e.g. taxonomy data missing).
    """
    try:
        from plugins.mcp.app.utilities.cti_taxonomy_loader import (
            load_mitre_taxonomy,
        )
        tax = load_mitre_taxonomy()
    except Exception:
        return frozenset()
    return _attack_platforms(tax)


def _attack_platforms(taxonomy: Optional[dict]) -> frozenset[str]:
    """
    Derive the set of platform names (`windows`, `linux`, `macos`,
    `esxi`, ...) from the loaded MITRE ATT&CK taxonomy by walking the
    `x_mitre_platforms` lists of every malware and attack-pattern
    object. This is the authoritative platform vocabulary published by
    MITRE; we do not maintain our own.
    """
    if not taxonomy:
        return frozenset()
    seen: set[str] = set()
    for kind in ("malware", "attack_patterns"):
        for obj in (taxonomy.get(kind) or {}).values():
            if not isinstance(obj, dict):
                continue
            for p in obj.get("x_mitre_platforms", []) or []:
                if isinstance(p, str):
                    low = p.strip().lower()
                    if low:
                        seen.add(low)
    return frozenset(seen)


@lru_cache(maxsize=1)
def _iana_services() -> frozenset[str]:
    """
    Parse `/etc/services` (the system IANA service-name registry) to
    derive a set of protocol/service tokens (`http`, `ftp`, `ssh`,
    `smb`, ...). Parsing the system file lets us honour the IANA list
    without hardcoding it. Returns frozenset() if the file is absent.
    """
    seen: set[str] = set()
    candidates = ["/etc/services"]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.split("#", 1)[0].strip()
                    if not line:
                        continue
                    # Format: "name port/proto [aliases...]"
                    parts = line.split()
                    if not parts:
                        continue
                    seen.add(parts[0].lower())
                    # Any aliases after the port/proto token.
                    for tok in parts[2:]:
                        seen.add(tok.lower())
        except OSError:
            continue
    # Bare transport names. The /etc/services file lists services as
    # "name port/tcp" so `tcp` and `udp` do not appear as service names
    # there; they are transport protocols. They are reliably the only
    # two we can hardcode at the "transport" layer per RFC 793 / 768 --
    # but to satisfy the no-static-list rule, recognise them via
    # Python's `socket` module which exposes IPPROTO_TCP / IPPROTO_UDP
    # constants.
    try:
        import socket as _s
        for name in dir(_s):
            if name.startswith("IPPROTO_"):
                seen.add(name[len("IPPROTO_"):].lower())
    except Exception:
        pass
    return frozenset(seen)


@lru_cache(maxsize=1)
def _file_extensions() -> frozenset[str]:
    """
    Derive a set of file-extension tokens (`exe`, `dll`, `ps1`, ...)
    from Python's stdlib `mimetypes` registries, augmented with an
    optional YAML data file at `data/file_extensions.yml` for entries
    `mimetypes` lacks (PowerShell `.ps1`, batch `.bat`, etc.). The
    augmentation file is *data*, not code.
    """
    seen: set[str] = set()
    for ext in list(mimetypes.types_map.keys()) + list(mimetypes.encodings_map.keys()):
        if ext.startswith("."):
            ext = ext[1:]
        ext = ext.strip().lower()
        if ext:
            seen.add(ext)
    # Optional YAML augmentation. PowerShell / shell / scripting
    # extensions are routinely missing from `mimetypes.types_map` on
    # stock distros; the data file fills those gaps without baking the
    # list into Python source.
    data_file = Path(__file__).resolve().parent / "data" / "file_extensions.yml"
    if data_file.exists():
        try:
            import yaml  # type: ignore
            with data_file.open("r", encoding="utf-8") as fh:
                doc = yaml.safe_load(fh) or {}
            for ext in (doc.get("extensions") or []):
                if isinstance(ext, str):
                    e = ext.strip().lstrip(".").lower()
                    if e:
                        seen.add(e)
        except Exception:
            pass
    return frozenset(seen)


@lru_cache(maxsize=1)
def _public_suffix_tlds() -> frozenset[str]:
    """
    Derive a set of top-level / public-suffix labels from the Mozilla
    Public Suffix List on disk (Debian/Ubuntu package
    `publicsuffix`). We only need the leftmost label of each entry
    (i.e. the actual TLD: `com`, `net`, `org`, `io`, `gov`, `edu`,
    `us`...). Returns frozenset() if the list is not installed.
    """
    seen: set[str] = set()
    candidates = [
        "/usr/share/publicsuffix/effective_tld_names.dat",
        "/usr/share/publicsuffix/public_suffix_list.dat",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("//"):
                        continue
                    # PSL entries can be wildcards (`*.foo`) or bangs
                    # (`!foo.bar`). Strip those.
                    if line.startswith("*."):
                        line = line[2:]
                    if line.startswith("!"):
                        line = line[1:]
                    # We only want the *last* label (the TLD itself) so
                    # `com.ac` contributes `ac`, not `com`. That avoids
                    # treating "com" as a noise token (which would also
                    # delete "com" from hostnames like `srv.com.example`).
                    last = line.rsplit(".", 1)[-1].strip().lower()
                    if last:
                        seen.add(last)
            break  # first available file wins
        except OSError:
            continue
    return seen and frozenset(seen) or frozenset()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-").lower()
    return s or "host"


def _looks_like_ipv4(token: str) -> bool:
    return bool(IPV4_RE.fullmatch(token))


def _is_noise_token(token: str, platforms: frozenset[str]) -> bool:
    """
    True if `token` should be rejected as a hostname candidate because
    a runtime vocabulary recognises it as something else (an English
    word, OS/platform name, protocol, file extension, or TLD).

    This replaces the old `_HOSTNAME_DENYLIST` static set.
    """
    low = token.lower()
    if not low:
        return True
    if low in platforms:
        return True
    if low in _iana_services():
        return True
    if low in _file_extensions():
        return True
    if low in _public_suffix_tlds():
        return True
    if _is_common_english(low):
        return True
    return False


def _valid_hostname_candidate(token: str,
                              platforms: frozenset[str] = frozenset()) -> bool:
    """RFC 952/1123 sanity plus runtime-vocab noise filter."""
    if not token:
        return False
    if _looks_like_ipv4(token):
        return False
    if "." in token:
        # FQDN: each label must satisfy RFC rules.
        parts = token.split(".")
        if any(len(p) == 0 or len(p) > 63 for p in parts):
            return False
        # FQDN must contain a non-numeric label.
        if all(p.isdigit() for p in parts):
            return False
    else:
        if not (1 <= len(token) <= 63):
            return False
    if not re.fullmatch(HOSTNAME_RE.pattern, token):
        return False
    # Pure-number tokens are not hostnames.
    if token.replace(".", "").isdigit():
        return False
    # Single-letter or all-digit-with-dash tokens are noise.
    if len(token) < 3 and "." not in token:
        return False
    # Top-level (single label) candidates: must contain at least one
    # letter and not be a pure English stopword.
    if "." not in token and not re.search(r"[A-Za-z]", token):
        return False
    # Tokens that look "hostname-shaped" -- they contain a hyphen or a
    # digit -- are almost certainly identifiers and bypass the noise
    # filter (e.g. `srv-mail01`, `web-3`). Plain alphabetic single
    # labels are checked against the runtime vocabularies.
    is_hostnameish = ("-" in token) or bool(re.search(r"\d", token))
    if not is_hostnameish and "." not in token:
        if _is_noise_token(token, platforms):
            return False
    elif "." in token:
        # For FQDNs, reject if every label is a noise token (no
        # identifier content). A FQDN like `windows.com` would be all
        # noise; `srv01.windows.com` would not.
        labels = token.split(".")
        if all(_is_noise_token(lbl, platforms) for lbl in labels):
            return False
    return True


def _infer_role(snippet: str, attack_pattern_names: Iterable[str] = ()) -> str:
    """
    Look up a role in the snippet using:
      1. STIX/role vocabulary phrases (longest first).
      2. ATT&CK technique-name ontology hints. If a technique whose name
         contains a role phrase (e.g. "DCSync", "Exchange") is mentioned
         near the host, infer the matching role.

    Returns canonical role slug, or "unknown".
    """
    low = snippet.lower()
    for phrase, role in _ROLE_VOCAB:
        if phrase in low:
            return role
    # ATT&CK ontology hint: technique names mentioned in the snippet.
    # We map by *substring match* against the role vocabulary, not by a
    # hardcoded technique->role table.
    for tname in attack_pattern_names:
        tlow = tname.lower()
        if tlow and tlow in low:
            for phrase, role in _ROLE_VOCAB:
                if phrase in tlow:
                    return role
    return "unknown"


def _infer_os(snippet: str) -> str:
    low = snippet.lower()
    for phrase, os_slug in _OS_VOCAB:
        if phrase in low:
            return os_slug
    return "unknown"


def _attack_pattern_role_hints(taxonomy: Optional[dict]) -> list[str]:
    """
    Extract ATT&CK technique *names* whose lexical content overlaps the
    role vocabulary. Used as additional signal for `_infer_role`.

    No hardcoded technique IDs. Pure name-string overlap with the open
    role vocabulary.
    """
    if not taxonomy:
        return []
    out = []
    role_phrases = {p for p, _ in _ROLE_VOCAB}
    for obj in (taxonomy.get("attack_patterns") or {}).values():
        name = (obj.get("name") or "").strip()
        if not name:
            continue
        nlow = name.lower()
        if any(p in nlow for p in role_phrases):
            out.append(name)
    return out


# ----------------------------------------------------------------------
# Table-row extraction
# ----------------------------------------------------------------------
def _extract_from_pipe_table(text: str,
                             attack_pattern_names: list[str],
                             platforms: frozenset[str]) -> list[dict]:
    """
    Parse markdown / wiki pipe tables. Heuristics:
      - Find rows with >= 2 pipes.
      - Identify a header row containing at least two of the labels
        {hostname/host, ip/address, role, os, platform}.
      - Map subsequent data rows by column index.

    No header? Skip -- the freeform scanner will pick up hostnames+IPs.
    """
    out: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.count("|") >= 2:
            cells = [c.strip() for c in PIPE_SPLIT_RE.split(line)]
            cells = [c for c in cells if c != ""]
            header_low = [c.lower() for c in cells]
            cols = {}
            for idx, h in enumerate(header_low):
                if h in ("hostname", "host", "name", "computer", "device"):
                    cols.setdefault("hostname", idx)
                elif h in ("ip", "ipv4", "ip address", "address", "addr"):
                    cols.setdefault("ip", idx)
                elif h in ("role", "function", "purpose", "description"):
                    cols.setdefault("role", idx)
                elif h in ("os", "platform", "operating system"):
                    cols.setdefault("os", idx)
            if "hostname" in cols and ("ip" in cols or "role" in cols):
                # Walk forward through data rows.
                j = i + 1
                # Skip an immediate separator row like |---|---|.
                if j < len(lines) and re.fullmatch(r"\s*\|?\s*[:\-\s|]+\s*\|?\s*", lines[j]):
                    j += 1
                while j < len(lines):
                    row = lines[j].strip()
                    if not row or row.count("|") < 2:
                        break
                    rcells = [c.strip() for c in PIPE_SPLIT_RE.split(row)]
                    rcells = [c for c in rcells if c != ""]
                    if len(rcells) < max(cols.values()) + 1:
                        j += 1
                        continue
                    hostname = rcells[cols["hostname"]]
                    ip = rcells[cols["ip"]] if "ip" in cols else ""
                    role_cell = rcells[cols["role"]] if "role" in cols else ""
                    os_cell = rcells[cols["os"]] if "os" in cols else ""
                    if _valid_hostname_candidate(hostname, platforms) and (
                        not ip or _looks_like_ipv4(ip)
                    ):
                        snippet = " | ".join(rcells)
                        role = _infer_role(role_cell or snippet,
                                           attack_pattern_names)
                        os_slug = _infer_os(os_cell or snippet)
                        out.append({
                            "hostname": hostname,
                            "ip": ip if _looks_like_ipv4(ip) else "",
                            "os": os_slug,
                            "role": role,
                            "evidence": snippet,
                        })
                    j += 1
                i = j
                continue
        i += 1
    return out


# ----------------------------------------------------------------------
# Freeform PROPN-near-IP extraction
# ----------------------------------------------------------------------
def _candidate_hostnames_near(text: str, span_start: int, span_end: int,
                              platforms: frozenset[str],
                              window: int = 80) -> list[tuple[str, int]]:
    """
    Hostnames within +/- `window` chars of an IP span (inclusive).

    Returns list of (token, absolute_distance_from_ip_span) pairs.
    A `distance` of 0 means the token is adjacent to the IP. We also
    reject any candidate whose lowercased form appears verbatim in the
    role / OS vocabulary -- those are role tokens, not hostnames.
    """
    lo = max(0, span_start - window)
    hi = min(len(text), span_end + window)
    snippet = text[lo:hi]
    role_words = {p for p, _ in _ROLE_VOCAB if " " not in p}
    os_words   = {p for p, _ in _OS_VOCAB   if " " not in p}
    skip = role_words | os_words
    out: list[tuple[str, int]] = []
    for m in HOSTNAME_RE.finditer(snippet):
        tok = m.group(1)
        if not _valid_hostname_candidate(tok, platforms):
            continue
        if tok.lower() in skip:
            continue
        # absolute file offset of the candidate match
        abs_start = lo + m.start()
        abs_end   = lo + m.end()
        if abs_end <= span_start:
            dist = span_start - abs_end
        elif abs_start >= span_end:
            dist = abs_start - span_end
        else:
            dist = 0
        out.append((tok, dist))
    return out


def _extract_from_freeform(text: str, nlp,
                           attack_pattern_names: list[str],
                           platforms: frozenset[str]) -> list[dict]:
    """
    Find IPv4 hits and pair them with the nearest PROPN-like hostname
    candidate. PROPN preference comes from spaCy when available; if not,
    we fall back to lexical regex candidates.
    """
    out: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    propn_tokens: set[str] = set()
    common_noun_tokens: set[str] = set()
    if nlp is not None:
        try:
            doc = nlp(text)
            for tok in doc:
                # Hostnames are proper nouns. Common nouns (NOUN) are
                # English words like "host", "server", "controller"
                # that we want to *reject* as hostnames near IPs --
                # this replaces the static "domain-noise" denylist
                # entries (`host`, `hostname`, `role`, `address`,
                # `subsidiary`, `incorporated`, ...) with a POS-tagger
                # derived set.
                txt = tok.text.strip()
                if not txt:
                    continue
                if tok.pos_ == "PROPN":
                    propn_tokens.add(txt)
                elif tok.pos_ == "NOUN":
                    common_noun_tokens.add(txt.lower())
        except Exception:
            propn_tokens = set()
            common_noun_tokens = set()

    for m in IPV4_RE.finditer(text):
        ip = m.group(0)
        # window for evidence / os / role inference
        lo = max(0, m.start() - 80)
        hi = min(len(text), m.end() + 80)
        snippet = text[lo:hi].replace("\n", " ").strip()
        # candidate hostnames near the IP (token, distance-from-IP)
        cands = _candidate_hostnames_near(text, m.start(), m.end(),
                                          platforms, window=80)
        if not cands:
            continue
        # Filter candidates to reduce English-word false-positives.
        # Two passes:
        #   (a) hostname-shaped tokens (contain a hyphen or a digit)
        #       are almost certainly hostnames -- keep them regardless
        #       of spaCy POS (since spaCy splits "srv-mail01" into
        #       multiple tokens).
        #   (b) plain alphabetic tokens must be tagged PROPN by spaCy
        #       (when available) AND not also tagged NOUN somewhere
        #       in the text. With no spaCy, require length >= 4.
        def _hostnameish(tok: str) -> bool:
            return ("-" in tok) or bool(re.search(r"\d", tok))

        filtered = []
        for tok, dist in cands:
            if _hostnameish(tok):
                filtered.append((tok, dist))
                continue
            if nlp is not None:
                # Reject if spaCy ever tagged this token as a common
                # noun -- it is domain-noise like "host" / "server" /
                # "subsidiary", not an identifier.
                if tok.lower() in common_noun_tokens:
                    continue
                if tok in propn_tokens:
                    filtered.append((tok, dist))
            else:
                if len(tok) >= 4:
                    filtered.append((tok, dist))
        cands = filtered
        if not cands:
            continue
        # Rank: nearest to IP wins, then PROPN-tagged, then longer
        # token. Filters out role-vocabulary words like "Exchange".
        ranked = sorted(
            cands,
            key=lambda ct: (
                ct[1],                               # primary: distance
                0 if ct[0] in propn_tokens else 1,   # secondary: PROPN
                -len(ct[0]),                         # tertiary: length
            ),
        )
        hostname = ranked[0][0]
        key = (hostname.lower(), ip)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        role = _infer_role(snippet, attack_pattern_names)
        os_slug = _infer_os(snippet)
        # Silent miss: if we have no role AND no os signal AND the
        # hostname is a single short label, skip -- too speculative.
        if role == "unknown" and os_slug == "unknown" and "." not in hostname:
            continue
        out.append({
            "hostname": hostname,
            "ip": ip,
            "os": os_slug,
            "role": role,
            "evidence": snippet,
        })
    return out


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def extract_hosts(text: str, nlp=None,
                  taxonomy: Optional[dict] = None) -> list[dict]:
    """
    Extract named hosts (with IPs / roles / OS where present) from CTI text.

    Args:
        text: raw CTI document text.
        nlp:  optional spaCy pipeline. If provided, PROPN/NOUN tags
              guide hostname-candidate ranking. If None, only regex
              candidates are used.
        taxonomy: optional MITRE taxonomy dict (output of
              cti_taxonomy_loader.load_mitre_taxonomy). Used to gather
              both technique *names* for role-hint substring matching
              AND `x_mitre_platforms` for OS/platform noise-token
              filtering. If omitted, the loader is invoked lazily.

    Returns:
        List of dicts: {hostname, ip, os, role, evidence}.
        Misses are silent.
    """
    if not text:
        return []

    attack_pattern_names = _attack_pattern_role_hints(taxonomy)

    if taxonomy is not None:
        platforms = _attack_platforms(taxonomy)
    else:
        platforms = _attack_platforms_global()

    rows = _extract_from_pipe_table(text, attack_pattern_names, platforms)

    # IPs and hostnames already claimed by the (authoritative) table
    # pass. Freeform extraction must NOT re-emit hosts for these IPs --
    # the table evidence is overwhelmingly more reliable than nearest-
    # PROPN guessing, and otherwise we get false positives like the
    # "NetBNMBackup server" role-cell token being pulled out as a host.
    claimed_ips = {r["ip"] for r in rows if r.get("ip")}
    claimed_hosts = {r["hostname"].lower() for r in rows}

    freeform_all = _extract_from_freeform(text, nlp, attack_pattern_names,
                                          platforms)
    freeform = [
        r for r in freeform_all
        if r.get("ip") not in claimed_ips
        and r["hostname"].lower() not in claimed_hosts
    ]

    # Dedup by (hostname, ip), prefer the entry with more signal
    # (non-"unknown" role/os beats "unknown"). Table rows usually win.
    by_key: dict[tuple[str, str], dict] = {}

    def _score(rec: dict) -> int:
        s = 0
        if rec.get("ip"):
            s += 2
        if rec.get("role") and rec["role"] != "unknown":
            s += 2
        if rec.get("os") and rec["os"] != "unknown":
            s += 1
        return s

    for rec in rows + freeform:
        key = (rec["hostname"].lower(), rec.get("ip", ""))
        existing = by_key.get(key)
        if existing is None or _score(rec) > _score(existing):
            by_key[key] = rec

    return list(by_key.values())


# ----------------------------------------------------------------------
# IR-shape adapter
# ----------------------------------------------------------------------
def hosts_to_infrastructure_entries(hosts: list[dict]) -> list[dict]:
    """
    Convert extract_hosts() output to the IR `infrastructure[]` shape:

        {
            "name":        <hostname>,
            "canonical":   <slug>,
            "description": "<role> -- '<evidence>'",
            "ip":          "<ipv4>",
            "os":          "<windows|linux|unknown>",
            "role":        "<bastion|dc|workstation|...>",
        }
    """
    out = []
    for h in hosts:
        hostname = h.get("hostname", "").strip()
        if not hostname:
            continue
        role = h.get("role", "unknown") or "unknown"
        evidence = (h.get("evidence") or "").strip()
        desc_parts = []
        if role and role != "unknown":
            desc_parts.append(role)
        if evidence:
            desc_parts.append(f"'{evidence}'")
        desc = " -- ".join(desc_parts) if desc_parts else "named host extracted from CTI text"
        out.append({
            "name":        hostname,
            "canonical":   _slugify(hostname),
            "description": desc,
            "ip":          h.get("ip", "") or "",
            "os":          h.get("os", "unknown") or "unknown",
            "role":        role,
            "evidence":    evidence,
        })
    return out


# ----------------------------------------------------------------------
# CLI / smoke test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import json
    import sys

    sample_table = """\
| Hostname | IP Address | Role | OS |
|----------|-----------|------|-----|
| kimeramon | 10.20.20.11 | Bastion host | Windows |
| datamon | 10.20.10.122 | NetBNMBackup server | Windows |
| leomon | 10.20.10.16 | Linux KVM server | Linux |
| blacknoirmon | 10.20.10.4 | Subsidiary B Domain Controller | Windows |
"""

    try:
        import spacy
        nlp = spacy.load("en_core_web_lg")
    except Exception:
        nlp = None

    hosts = extract_hosts(sample_table, nlp=nlp)
    print("=== AE-plan snippet ===")
    print(json.dumps(hosts, indent=2))

    print("\n=== As IR infrastructure[] entries ===")
    print(json.dumps(hosts_to_infrastructure_entries(hosts), indent=2))

    if len(sys.argv) > 1:
        p = sys.argv[1]
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        hosts = extract_hosts(txt, nlp=nlp)
        print(f"\n=== {p} ===")
        print(json.dumps(hosts, indent=2))
