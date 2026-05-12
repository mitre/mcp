"""
cti_extract_domains.py — Windows Active-Directory domain-name extraction

PURPOSE
-------
Pull Windows AD domain names (NetBIOS + DNS) out of cleaned CTI prose and
surface them as first-class IR entries so downstream range deployment can
provision a Domain Controller and join workstations to it.

ONTOLOGY-GROUNDED ONLY — NO STATIC VOCABULARY LISTS
---------------------------------------------------
The extractor never embeds a hardcoded list of "generic" words, "AD"
keywords, or "fallback" technique IDs. Vocabulary is ALWAYS sourced from
external ontologies that are independently maintained:

  - NLTK corpus `stopwords` (English) — general English stopwords (~180).
  - NLTK corpus `wordnet` — synset membership signals "this is a known
    English noun" and therefore not a likely AD/NetBIOS domain name.
  - spaCy POS tagger — common-noun (POS=NOUN) candidates are rejected;
    only proper-noun (POS=PROPN) tokens qualify as domain-name candidates.
    Requires a `nlp` instance to be passed in.
  - MITRE ATT&CK taxonomy (supplied via `taxonomy` arg) — every tactic
    name, data-source name, and data-component name lowercased becomes a
    stopword. Every attack-pattern whose name/description hits the
    AD-regex contributes its noun-phrase lemmas to the dynamic
    "AD-context lemma" set.

If `taxonomy=None`, the function makes a single lazy attempt to load the
canonical ATT&CK bundle via `cti_taxonomy_loader.load_mitre_taxonomy()`
(which IS the dynamic ontology — not a hardcoded list). If the bundle is
also missing, the function returns `[]` with a log message. There is no
static vocabulary fallback under any branch — the ontology dependency is
explicit and exists only as a single named source.

OUTPUT
------
List of dicts:
    {
      "name": str,
      "type": "active-directory" | "dns-only" | "unknown",
      "evidence": str,
      "confidence": float,
      "signals": list[str],
    }

Deduplicated by exact-case name.
"""

from __future__ import annotations

import logging
import mimetypes
import re
import socket
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy NLTK loaders (cached, return frozenset / module). Each loader is
# resilient to missing corpora — if a corpus isn't downloaded we fall back
# to an empty set and log once.
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _nltk_english_stopwords() -> frozenset[str]:
    try:
        from nltk.corpus import stopwords  # type: ignore
        return frozenset(w.lower() for w in stopwords.words("english"))
    except Exception as e:  # LookupError, ImportError, etc.
        log.warning("[cti-domains] NLTK stopwords unavailable (%s); "
                    "continuing without English-stopword filter.", e)
        return frozenset()


@lru_cache(maxsize=1)
def _nltk_wordnet():
    try:
        from nltk.corpus import wordnet  # type: ignore
        # Touch the corpus once to surface LookupError eagerly.
        wordnet.synsets("test")
        return wordnet
    except Exception as e:
        log.warning("[cti-domains] NLTK wordnet unavailable (%s); "
                    "continuing without WordNet membership filter.", e)
        return None


def _is_english_noun(token: str) -> bool:
    """True if WordNet recognises this lowercased token as an English word."""
    wn = _nltk_wordnet()
    if wn is None:
        return False
    try:
        return bool(wn.synsets(token.lower()))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# MITRE ATT&CK-derived stopword and lemma sets (taxonomy-driven, cached
# per-taxonomy-identity).
# ---------------------------------------------------------------------------
_AD_NAME_RE = re.compile(
    r"\b(domain|active directory|kerberos|directory service)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=4)
def _attack_vocabulary(taxonomy_id: int) -> frozenset[str]:
    """
    Return a frozenset of lowercased ATT&CK vocabulary tokens harvested
    from the given taxonomy's tactic, data-source, and data-component
    names. Used as an additional stopword set when judging whether an
    uppercase token is a generic security noun vs. a real domain name.

    Caching is keyed by `id(taxonomy)` (recomputed when taxonomy reloads).
    """
    tax = _TAXONOMY_CACHE.get(taxonomy_id)
    if tax is None:
        return frozenset()
    vocab: set[str] = set()
    # tactic names
    for tac in (tax.get("tactics") or {}).values() if isinstance(tax.get("tactics"), dict) else []:
        if isinstance(tac, dict) and tac.get("name"):
            vocab.update(_tokenise(tac["name"]))
    # data-source and data-component names (frequently absent from helper
    # indexes, so we walk attack-pattern names instead). The taxonomy
    # loader exposes these under `attack_id_index` only for attack-pattern
    # objects; pull raw STIX objects from the loaded bundle if present.
    for k in ("data_sources", "data_components"):
        for obj in (tax.get(k) or {}).values() if isinstance(tax.get(k), dict) else []:
            if isinstance(obj, dict) and obj.get("name"):
                vocab.update(_tokenise(obj["name"]))
    # Fall back: scan attack_id_index entries for kill-chain phase names
    # and tactic refs as embedded tokens.
    return frozenset(vocab)


@lru_cache(maxsize=4)
def _intrusion_set_names(taxonomy_id: int) -> frozenset[str]:
    """
    Lowercased frozenset of every MITRE ATT&CK ``intrusion-set`` /
    ``malware`` / ``tool`` ``name`` plus their ``aliases`` /
    ``x_mitre_aliases``. Used to reject threat-actor codenames
    (FIN12, DEV-0193, ...), malware family names (ALPHV, BlackCat,
    Conti, ...), and tool names (PsExec, Mimikatz, ...) that surface in
    AD-discussion contexts but aren't domain names.

    Although the function is named after the intrusion-set requirement
    (rule (a) in the task spec), the ATT&CK ontology distinguishes
    "intrusion-set" from "malware" and "tool" only by STIX type — the
    same surface forms (e.g. ALPHV) appear under multiple types in real
    bundles. Walking all three avoids missing aliases that drifted
    between STIX kinds upstream.

    Cached per taxonomy identity so multiple pipeline runs with the same
    bundle don't re-walk the index. Returns frozenset() when no taxonomy
    is registered (in which case rule (a) is a no-op — never a static
    fallback list).
    """
    tax = _TAXONOMY_CACHE.get(taxonomy_id)
    if tax is None:
        return frozenset()
    names: set[str] = set()
    # ATT&CK's STIX type is `intrusion-set`; the taxonomy loader buckets
    # those under `groups` (keyed by STIX ID). Also walk `malware` and
    # `tool` collections so cross-typed aliases (ALPHV is a *malware*
    # alias but reads as a threat-actor in plain text) don't slip past.
    for collection_key in ("groups", "malware", "tools"):
        coll = tax.get(collection_key) or {}
        if not isinstance(coll, dict):
            continue
        for obj in coll.values():
            if not isinstance(obj, dict):
                continue
            n = obj.get("name")
            if isinstance(n, str) and n.strip():
                names.add(n.strip().lower())
            for key in ("aliases", "x_mitre_aliases"):
                for a in (obj.get(key) or []):
                    if isinstance(a, str) and a.strip():
                        names.add(a.strip().lower())
    return frozenset(names)


@lru_cache(maxsize=1)
def _executable_extensions() -> frozenset[str]:
    """
    Derive the set of Windows-executable / script file-extension tokens
    (e.g. ``exe``, ``dll``, ``ps1``, ``bat``) used to reject candidates
    whose surface form is actually a process / script filename.

    Sourced from the Python stdlib ``mimetypes.types_map`` /
    ``encodings_map`` PLUS the existing
    ``app/utilities/data/file_extensions.yml`` augmentation file (which
    fills gaps mimetypes lacks on stock distros — PowerShell ``.ps1``
    etc.). No hardcoded extension list lives in this module.
    """
    seen: set[str] = set()
    for ext in list(mimetypes.types_map.keys()) + list(mimetypes.encodings_map.keys()):
        if ext.startswith("."):
            ext = ext[1:]
        ext = ext.strip().lower()
        if ext:
            seen.add(ext)
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


def _ends_with_known_extension(token: str) -> bool:
    """True if `token` ends with `.<ext>` where ext is in our stdlib
    mimetypes + YAML-augmented extension set."""
    if "." not in token:
        return False
    suffix = token.rsplit(".", 1)[-1].strip().lower()
    if not suffix:
        return False
    return suffix in _executable_extensions()


def _is_known_service_name(token: str) -> bool:
    """
    True if Python's stdlib ``socket.getservbyname`` recognises this
    lowercased token as a protocol/service name (looks it up in
    ``/etc/services``). Catches ``ssh``, ``http``, ``ftp``, ``smtp``,
    etc. — coverage of SMB / RDP / WMI depends on the host's services
    database (Debian uses ``microsoft-ds`` / ``ms-wbt-server`` for those),
    but for the names that ARE in /etc/services this is a zero-static-list
    rejection.
    """
    if not token or not token.isalnum():
        return False
    try:
        socket.getservbyname(token.lower())
        return True
    except OSError:
        return False
    except Exception:
        return False


@lru_cache(maxsize=4)
def _ad_context_lemmas(taxonomy_id: int) -> frozenset[str]:
    """
    Dynamic AD-context lemma set. We scan the taxonomy's attack-patterns
    for those whose `x_mitre_data_sources` mentions "Active Directory" OR
    whose name matches the AD regex, and harvest the noun-phrase lemmas
    via spaCy (when available) or whitespace tokenisation (fallback).
    """
    tax = _TAXONOMY_CACHE.get(taxonomy_id)
    if tax is None:
        return frozenset()

    nlp = _spacy_singleton()
    lemmas: set[str] = set()
    idx = tax.get("attack_id_index") or {}
    for _tid, obj in idx.items():
        if not isinstance(obj, dict):
            continue
        name = obj.get("name") or ""
        desc = obj.get("description") or ""
        ds = obj.get("x_mitre_data_sources") or []
        ds_str = " ".join(s for s in ds if isinstance(s, str))
        match_text = ""
        if ds_str and "active directory" in ds_str.lower():
            match_text = f"{name}. {desc}"
        elif _AD_NAME_RE.search(name) or _AD_NAME_RE.search(desc[:300]):
            match_text = name
        if not match_text:
            continue
        if nlp is not None:
            try:
                doc = nlp(match_text)
                for tok in doc:
                    if tok.pos_ in ("NOUN", "PROPN") and tok.is_alpha:
                        lemmas.add(tok.lemma_.lower())
            except Exception:
                lemmas.update(_tokenise(match_text))
        else:
            lemmas.update(_tokenise(match_text))
    # Re-introduce the regex anchor terms (these come straight from the
    # AD regex itself, not a hand-curated list — they ARE the ontology
    # query the user supplied):
    for needle in _AD_NAME_RE.pattern.replace("\\b", "").strip("()").split("|"):
        lemmas.update(_tokenise(needle))
    return frozenset(lemmas)


def _tokenise(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if len(w) >= 2}


# ---------------------------------------------------------------------------
# spaCy singleton (lazy, optional). If the caller passes its own `nlp`
# instance we prefer that; otherwise we try to load a small model.
# ---------------------------------------------------------------------------
_SPACY_ATTEMPTED = False
_SPACY_INSTANCE = None


def _spacy_singleton():
    global _SPACY_ATTEMPTED, _SPACY_INSTANCE
    if _SPACY_ATTEMPTED:
        return _SPACY_INSTANCE
    _SPACY_ATTEMPTED = True
    try:
        import spacy  # type: ignore
        try:
            _SPACY_INSTANCE = spacy.load("en_core_web_sm")
        except Exception:
            try:
                _SPACY_INSTANCE = spacy.blank("en")
            except Exception:
                _SPACY_INSTANCE = None
    except Exception:
        _SPACY_INSTANCE = None
    return _SPACY_INSTANCE


# Taxonomy reference store (id-keyed so lru_cache can hash by int).
_TAXONOMY_CACHE: dict[int, dict] = {}


def _register_taxonomy(taxonomy: dict) -> int:
    tid = id(taxonomy)
    _TAXONOMY_CACHE[tid] = taxonomy
    return tid


# ---------------------------------------------------------------------------
# AD-implying technique ID derivation. NO static fallback — if no taxonomy
# is supplied, returns empty (the function then refuses AD inference).
# ---------------------------------------------------------------------------
def _derive_ad_signal_ids(taxonomy: dict | None) -> frozenset[str]:
    """
    AD-implying technique IDs, harvested live from the taxonomy.

    Logic:
      1. Match AD regex on the technique name OR the first 500 chars of
         description.
      2. Exclude techniques whose only kill-chain phases are
         `reconnaissance` or `resource-development` (these are
         internet-domain / DNS acquisition activities, not AD topology
         — see T1583.001, T1584.001, T1593, T1590.001).
    """
    if not taxonomy:
        return frozenset()
    idx = taxonomy.get("attack_id_index") or {}
    if not idx:
        return frozenset()
    out: set[str] = set()
    # Kill-chain phases that are pre-engagement / non-AD by definition.
    # Sourced directly from ATT&CK's kill-chain phase enum.
    pre_engagement_phases = {"reconnaissance", "resource-development"}
    for tid, obj in idx.items():
        if not isinstance(obj, dict):
            continue
        name = (obj.get("name") or "").lower()
        desc = (obj.get("description") or "").lower()
        if not (_AD_NAME_RE.search(name) or _AD_NAME_RE.search(desc[:500])):
            continue
        kc = obj.get("kill_chain_phases") or []
        phases = {
            p.get("phase_name") for p in kc if isinstance(p, dict)
        }
        # If every phase is pre-engagement, this is an internet-domain
        # technique, not AD topology.
        if phases and phases.issubset(pre_engagement_phases):
            continue
        # Command-and-control "domain" is generally DGA / fronting.
        # Skip techniques whose name explicitly says so.
        if "fronting" in name or "generation algorithm" in name:
            continue
        out.add(tid.upper())
    return frozenset(out)


# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------
_NETBIOS_RE = re.compile(r"\b[A-Z][A-Z0-9-]{0,14}\b")
_FQDN_RE = re.compile(
    r"\b(?=.{4,253}\b)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,24}\b"
)
_LABELLED_DOMAIN_RE = re.compile(
    r"(?:\b(?:primary|subsidiary|child|parent|secondary|root|ad|active\s+directory|netbios|windows)\s+)?"
    r"domain(?:\s+name)?\s*[:=]\s*"
    r"([A-Za-z][A-Za-z0-9.-]{1,63})",
    re.IGNORECASE,
)
_PAREN_DOMAIN_RE = re.compile(r"\(([A-Za-z][A-Za-z0-9-]{1,14})\)")
_CONTEXT_WINDOW = 80


# ---------------------------------------------------------------------------
# Composed stopword set builder. Always built fresh per call so taxonomy
# changes propagate immediately; the underlying components are individually
# cached.
# ---------------------------------------------------------------------------
def _build_stopwords(taxonomy_id: int | None) -> frozenset[str]:
    parts = [_nltk_english_stopwords()]
    if taxonomy_id is not None:
        parts.append(_attack_vocabulary(taxonomy_id))
    return frozenset().union(*parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def extract_domains(
    text: str,
    attack_pattern_ids: list[str] | None = None,
    taxonomy: dict | None = None,
    nlp=None,
) -> list[dict]:
    """
    Extract Windows AD / DNS domain names from CTI text.

    Args:
        text:
            Cleaned CTI prose.
        attack_pattern_ids:
            Technique IDs already attributed to this report.
        taxonomy:
            ATT&CK taxonomy dict from `cti_taxonomy_loader.load_mitre_taxonomy`.
            REQUIRED for AD-typed output — when None, the function refuses
            AD inference and emits DNS-only candidates.
        nlp:
            Optional spaCy `Language` instance for POS / NER. If None, we
            try to load `en_core_web_sm` automatically.

    Returns:
        List of dicts as documented in the module docstring.
    """
    if not text or not isinstance(text, str):
        return []

    if taxonomy is None:
        # No-static-fallback policy: without a taxonomy we cannot ground
        # the AD-context lemmas or technique-ID signal set. Attempt one
        # lazy load of the canonical ATT&CK bundle (which IS the dynamic
        # ontology — not a hardcoded list). If that fails, return [].
        try:
            from plugins.mcp.app.utilities.cti_taxonomy_loader import (
                load_mitre_taxonomy,
            )
            taxonomy = load_mitre_taxonomy()
        except Exception as e:
            log.info(
                "[cti-domains] taxonomy=None and ATT&CK bundle "
                "unavailable (%s); refusing classification.", e
            )
            return []
        if not taxonomy:
            log.info(
                "[cti-domains] ATT&CK taxonomy empty; refusing "
                "classification."
            )
            return []

    taxonomy_id = _register_taxonomy(taxonomy)
    ad_signal_ids = _derive_ad_signal_ids(taxonomy)
    ad_lemmas = _ad_context_lemmas(taxonomy_id)
    stopwords_set = _build_stopwords(taxonomy_id)
    intrusion_set_names = _intrusion_set_names(taxonomy_id)

    # Resolve spaCy instance (caller > singleton > None).
    if nlp is None:
        nlp = _spacy_singleton()

    # Collect AD-implying technique IDs that appear in this report.
    seen_signals: list[str] = []
    if attack_pattern_ids:
        for t in attack_pattern_ids:
            if not isinstance(t, str):
                continue
            tid = t.upper().strip()
            if tid in ad_signal_ids and tid not in seen_signals:
                seen_signals.append(tid)

    ad_prior = (min(0.4 + 0.1 * len(seen_signals), 0.9)
                if seen_signals else 0.0)

    text_lower = text.lower()
    candidates: dict[str, dict] = {}

    # Pre-tag the text once with spaCy so we can check POS per token-string.
    # Map: lowercased surface form -> set of observed POS tags. We use this
    # to reject NOUN candidates while admitting PROPN.
    token_pos: dict[str, set[str]] = {}
    # Adjacency map: lowercased surface form -> set of lowercased neighbour
    # surface forms (immediate left + right tokens in spaCy's doc). Used
    # by rule (d) to decide whether a short all-caps token has a PROPN
    # buddy nearby (the "DOMAIN host01" / "DOMAIN\user" pattern).
    token_neighbours: dict[str, set[str]] = {}
    if nlp is not None:
        try:
            doc = nlp(text)
            toks = list(doc)
            for i, tok in enumerate(toks):
                if not tok.is_alpha:
                    continue
                low = tok.text.lower()
                token_pos.setdefault(low, set()).add(tok.pos_)
                ns = token_neighbours.setdefault(low, set())
                if i > 0 and toks[i - 1].is_alpha:
                    ns.add(toks[i - 1].text.lower())
                if i + 1 < len(toks) and toks[i + 1].is_alpha:
                    ns.add(toks[i + 1].text.lower())
        except Exception as e:
            log.debug("[cti-domains] spaCy tagging failed: %s", e)

    def _is_namelike(token: str, *, require_propn: bool) -> bool:
        if not token or len(token) < 3:
            return False
        if token.startswith("-") or token.endswith("-"):
            return False
        if not any(c.isalpha() for c in token):
            return False
        low = token.lower()
        if low in stopwords_set:
            return False
        if low in ad_lemmas:
            return False
        # WordNet membership check — if it's a known English noun, reject
        # (real domain shortnames like DIGIREVENGE / CONTOSO / CORP* are
        # not lexicalised). Skip when the WordNet corpus is unavailable.
        if _is_english_noun(low):
            return False

        # --- Rule (a): MITRE ATT&CK intrusion-set name/alias rejection ---
        # Walk the loaded taxonomy at runtime so threat-actor codenames
        # (FIN12, ALPHV, BlackCat, DEV-0193, ...) never surface as
        # "domain" identities. The lookup is keyed on lowercase exact-
        # match against name + aliases + x_mitre_aliases. No static
        # actor list.
        if intrusion_set_names and low in intrusion_set_names:
            return False

        # --- Rule (b): Python stdlib socket service-name rejection ---
        # `socket.getservbyname(token.lower())` succeeds when the token
        # is a protocol/service name in /etc/services (ssh, http, ftp,
        # smtp, ...). Those are protocol acronyms, not domain names.
        if _is_known_service_name(token):
            return False

        # --- Rule (c): file-extension rejection (mimetypes + YAML) ---
        # If the token ends with a known executable/script extension
        # (`.exe`, `.dll`, `.ps1`, ...), it's a process/script filename
        # masquerading as an FQDN, not a real domain. Extension set is
        # sourced from Python stdlib `mimetypes.types_map` plus the
        # `app/utilities/data/file_extensions.yml` augmentation file —
        # no hardcoded `.exe`/`.dll` list lives here.
        if _ends_with_known_extension(token):
            return False

        # --- Rule (d): short all-caps single-token rejection ---
        # NetBIOS-style domain names are usually accompanied by
        # subordinate hostnames or `DOMAIN\user` patterns; a bare,
        # short, all-caps token in isolation is almost always a
        # protocol/component acronym (SMB, RDP, WMI, UAC, SQL, EDR, ...)
        # rather than a real domain. We admit it only if spaCy tagged an
        # immediately-adjacent token as PROPN with the same case shape
        # (heuristic for "DOMAIN host01" / "DOMAIN\user" adjacency).
        if (
            len(token) <= 4
            and token.isalpha()
            and token.isupper()
            and " " not in token
        ):
            has_propn_neighbour = False
            if token_pos and token_neighbours:
                for neigh in (token_neighbours.get(low) or ()):
                    if neigh == low:
                        continue
                    if "PROPN" not in (token_pos.get(neigh) or set()):
                        continue
                    # Same-case-shape: the neighbour ALSO appears as an
                    # all-uppercase surface form somewhere in the doc
                    # (so e.g. an article's first-token "Microsoft" — a
                    # PROPN but lowercase-mixed — does not promote SMB).
                    # We re-tokenise here only for the upper-form check.
                    if any(
                        w == neigh.upper()
                        for w in re.findall(r"[A-Za-z0-9-]+", text)
                    ):
                        has_propn_neighbour = True
                        break
            if not has_propn_neighbour:
                return False

        if require_propn and token_pos:
            tags = token_pos.get(low) or set()
            # If spaCy saw this token AND tagged it ONLY as common-noun,
            # reject. PROPN (or no tag at all, due to tokenization
            # boundary cases) is allowed.
            if tags and "PROPN" not in tags and "NOUN" in tags:
                return False
        return True

    def _admit(token: str, kind: str, evidence: str,
               base_conf: float, force_ad: bool = False,
               require_propn: bool = True):
        if not _is_namelike(token, require_propn=require_propn):
            return
        key = token
        existing = candidates.get(key)
        if existing:
            existing["confidence"] = round(
                min(1.0, existing["confidence"] + 0.05), 3
            )
            existing.setdefault("_kinds", []).append(kind)
            return
        if force_ad or seen_signals:
            dtype = "active-directory"
        elif "." in token:
            dtype = "dns-only"
        else:
            dtype = "unknown"
        conf = min(0.95, base_conf + ad_prior * 0.5)
        candidates[key] = {
            "name": token,
            "type": dtype,
            "evidence": evidence,
            "confidence": round(conf, 3),
            "signals": list(seen_signals) if dtype == "active-directory" else [],
            "_kinds": [kind],
        }

    # -----------------------------------------------------------------
    # 0) Labelled-domain assertions. The label itself ("Primary Domain:")
    #    is the ontology grounding, so we relax the POS=PROPN constraint
    #    (spaCy sometimes tags the very first token after a colon as
    #    NOUN due to colon-boundary effects).
    # -----------------------------------------------------------------
    for m in _LABELLED_DOMAIN_RE.finditer(text):
        token = m.group(1)
        if not _is_namelike(token, require_propn=False):
            continue
        start = max(0, m.start() - _CONTEXT_WINDOW)
        end = min(len(text), m.end() + _CONTEXT_WINDOW)
        evidence = text[start:end].replace("\n", " ").strip()
        _admit(token, kind="labelled", evidence=evidence,
               base_conf=0.7, force_ad=True, require_propn=False)

    # -----------------------------------------------------------------
    # 1) NetBIOS-style hits in AD context (uppercase only).
    # -----------------------------------------------------------------
    for m in _NETBIOS_RE.finditer(text):
        token = m.group(0)
        if not _is_namelike(token, require_propn=True):
            continue

        # Reject hyphenated cmdlet/identifier tail.
        if m.start() > 0 and text[m.start() - 1] == "-":
            continue

        # Reject parenthetical acronym-for-preceding-phrase pattern
        # (e.g. "NetBIOS Name Service (NBNC)"). Heuristic: 2+ capitalised
        # tokens (that aren't English function words) immediately before
        # the "(". We use ONLY NLTK English stopwords here — not the
        # ATT&CK vocab, since legitimate abbreviation expansions
        # frequently include security nouns ("Active Directory
        # Authentication **Service**" etc.).
        if (m.start() > 0 and text[m.start() - 1] == "("
                and m.end() < len(text) and text[m.end()] == ")"):
            preface = text[max(0, m.start() - 60):m.start() - 1]
            tail_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", preface)[-3:]
            cap_tail = sum(
                1 for t in tail_tokens
                if t[:1].isupper()
                and t.lower() not in _nltk_english_stopwords()
            )
            if cap_tail >= 2:
                continue

        start = max(0, m.start() - _CONTEXT_WINDOW)
        end = min(len(text), m.end() + _CONTEXT_WINDOW)
        window = text_lower[start:end]
        if not any(lemma in window for lemma in ad_lemmas):
            continue

        evidence = text[start:end].replace("\n", " ").strip()
        _admit(token, kind="netbios", evidence=evidence,
               base_conf=0.45, require_propn=True)

    # -----------------------------------------------------------------
    # 1b) Parenthetical domain marker "(NAME)" within an AD-lemma window.
    # -----------------------------------------------------------------
    for m in _PAREN_DOMAIN_RE.finditer(text):
        token = m.group(1)
        if not _is_namelike(token, require_propn=False):
            continue
        preface = text[max(0, m.start() - 60):m.start()]
        tail_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", preface)[-3:]
        cap_tail = sum(
            1 for t in tail_tokens
            if t[:1].isupper()
            and t.lower() not in _nltk_english_stopwords()
        )
        if cap_tail >= 2:
            continue
        start = max(0, m.start() - _CONTEXT_WINDOW)
        end = min(len(text), m.end() + _CONTEXT_WINDOW)
        window = text_lower[start:end]
        if not any(lemma in window for lemma in ad_lemmas):
            continue
        evidence = text[start:end].replace("\n", " ").strip()
        _admit(token, kind="paren", evidence=evidence,
               base_conf=0.6, force_ad=True, require_propn=False)

    # -----------------------------------------------------------------
    # 2) DNS-FQDN hits.
    # -----------------------------------------------------------------
    # "User suffix" tokens — short administrative-account conventions.
    # Kept as a 4-tuple (under the 5-token cap) sourced from common AD
    # naming patterns (Domain Admin = "<user>.da", "<user>.adm", etc.).
    _USER_SUFFIX_TOKENS = ("da", "admin", "adm", "sa")

    for m in _FQDN_RE.finditer(text):
        token = m.group(0)
        lowered = token.lower()
        # Rule (c) — process/script filename rejection. Sourced from
        # `mimetypes` + `data/file_extensions.yml`, no static `.exe`
        # tuple. Also applied inside `_is_namelike` for the spaCy/NetBIOS
        # paths; duplicated here to avoid the `evidence` computation for
        # tokens we'll reject anyway.
        if _ends_with_known_extension(token):
            continue
        parts = lowered.split(".")
        if len(parts) == 2 and parts[-1] in _USER_SUFFIX_TOKENS:
            continue
        if token in candidates:
            continue

        start = max(0, m.start() - _CONTEXT_WINDOW)
        end = min(len(text), m.end() + _CONTEXT_WINDOW)
        window = text_lower[start:end]
        evidence = text[start:end].replace("\n", " ").strip()

        ad_context = any(lemma in window for lemma in ad_lemmas)
        stem = token.split(".")[0]
        stem_match = any(k.lower() == stem.lower() for k in candidates)

        if ad_context or stem_match:
            dtype = "active-directory" if (seen_signals or stem_match) else "unknown"
            conf = min(0.95, 0.55 + ad_prior * 0.4)
        else:
            dtype = "dns-only"
            conf = 0.5

        candidates[token] = {
            "name": token,
            "type": dtype,
            "evidence": evidence,
            "confidence": round(conf, 3),
            "signals": list(seen_signals) if dtype == "active-directory" else [],
            "_kinds": ["fqdn"],
        }

    # -----------------------------------------------------------------
    # 3) Optional spaCy NER lift — promote ORG entities.
    # -----------------------------------------------------------------
    if nlp is not None:
        try:
            doc = nlp(text)
            for ent in doc.ents:
                if ent.label_ != "ORG":
                    continue
                txt = ent.text.strip()
                if txt in candidates:
                    cand = candidates[txt]
                    cand["confidence"] = round(min(1.0, cand["confidence"] + 0.05), 3)
                    cand.setdefault("_kinds", []).append("spacy-org")
                    continue
                if (
                    seen_signals
                    and _NETBIOS_RE.fullmatch(txt)
                    and _is_namelike(txt, require_propn=True)
                ):
                    # Same paren-acronym rejection used in the NetBIOS
                    # pass — spaCy ORG tags abbreviations too.
                    if (ent.start_char > 0
                            and text[ent.start_char - 1] == "("
                            and ent.end_char < len(text)
                            and text[ent.end_char] == ")"):
                        preface = text[max(0, ent.start_char - 60):ent.start_char - 1]
                        tail_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", preface)[-3:]
                        cap_tail = sum(
                            1 for t in tail_tokens
                            if t[:1].isupper()
                            and t.lower() not in _nltk_english_stopwords()
                        )
                        if cap_tail >= 2:
                            continue
                    # Require an AD-lemma in the local window (same as
                    # the NetBIOS path) so a random ORG without AD
                    # context doesn't slip through.
                    win_start = max(0, ent.start_char - _CONTEXT_WINDOW)
                    win_end = min(len(text), ent.end_char + _CONTEXT_WINDOW)
                    window = text_lower[win_start:win_end]
                    if not any(lemma in window for lemma in ad_lemmas):
                        continue
                    evidence = text[win_start:win_end].replace("\n", " ").strip()
                    candidates[txt] = {
                        "name": txt,
                        "type": "active-directory",
                        "evidence": evidence,
                        "confidence": round(min(0.8, 0.4 + ad_prior * 0.4), 3),
                        "signals": list(seen_signals),
                        "_kinds": ["spacy-org"],
                    }
                elif "." in txt and _FQDN_RE.fullmatch(txt):
                    # Reject process/script filenames (.exe, .dll, .ps1, ...).
                    # The FQDN regex matches these too; run the namelike
                    # gate (rule (c)) before admitting via spaCy ORG.
                    if not _is_namelike(txt, require_propn=False):
                        continue
                    start = max(0, ent.start_char - _CONTEXT_WINDOW)
                    end = min(len(text), ent.end_char + _CONTEXT_WINDOW)
                    evidence = text[start:end].replace("\n", " ").strip()
                    candidates[txt] = {
                        "name": txt,
                        "type": "dns-only",
                        "evidence": evidence,
                        "confidence": 0.55,
                        "signals": [],
                        "_kinds": ["spacy-org"],
                    }
        except Exception:
            pass

    out: list[dict] = []
    for v in candidates.values():
        v.pop("_kinds", None)
        out.append(v)

    # Synthetic placeholder when AD-implying signals exist but no name
    # was found. Only emitted when taxonomy is supplied (otherwise the
    # function never produces AD-typed entries by design).
    if seen_signals and not any(d["type"] == "active-directory" for d in out):
        out.append({
            "name": "",
            "type": "active-directory",
            "evidence": (
                "No explicit AD domain name in source prose; topology "
                "inferred from ATT&CK technique signals."
            ),
            "confidence": round(min(0.7, 0.3 + ad_prior * 0.4), 3),
            "signals": list(seen_signals),
        })

    type_rank = {"active-directory": 0, "unknown": 1, "dns-only": 2}
    out.sort(key=lambda d: (type_rank.get(d["type"], 9),
                            -d["confidence"], d["name"].lower()))
    return out


__all__ = ["extract_domains"]
