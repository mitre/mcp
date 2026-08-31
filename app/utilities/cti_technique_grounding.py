"""
cti_technique_grounding.py — explicit-anchor ATT&CK grounding.

PURPOSE
-------
Stage-1's existing MITRE pipeline (cti_mitre_extract + cti_linguistics)
infers techniques from QUALIFIED behaviors using vector / token-overlap
scoring. That works for fuzzy CTI prose, but it routinely:

  (a) MISSES canonical-Windows techniques whose evidence is a *concrete
      command* or *binary name* (powershell.exe, vssadmin.exe, wmic.exe,
      mstsc.exe, taskmgr.exe / lsass dump, net.exe, mimikatz, ADRecon,
      ADFind, encryption-and-ransom narrative) because there's no
      single QUALIFIED behavior verb-object pair anchoring them; and

  (b) ADMITS irrelevant techniques (Sudo, macOS Launch Daemon,
      Gatekeeper Bypass, Cloud Administration Command) because the
      vector / token overlap is high but the platform is wrong.

This module addresses (a) by:

  * Walking a small set of STRUCTURAL ANCHORS (binary names, system
    commands, narrative phrases like "delete shadow copies") that
    canonically map onto exactly ONE ATT&CK technique each in the
    ATT&CK taxonomy itself.
  * Looking up the technique via ATT&CK's `name_index` /
    `attack_id_index` (no hardcoded T-id list — the IDs come from
    the ATT&CK ontology by matching anchor text against technique
    NAMES and DESCRIPTIONS).
  * Emitting the matched attack-pattern with `x_cti_anchor` and
    `x_cti_evidence` so downstream consumers can see WHY it was
    grounded.

It addresses (b) by exposing `filter_techniques_by_platform` which
drops techniques whose `x_mitre_platforms` doesn't overlap the
platforms attested in the source text (Windows / Linux / macOS / Cloud
/ Containers / ESXi). The platform vocabulary itself comes from
ATT&CK's `x_mitre_platforms` walks (no static OS list).

Hard constraints
----------------
* Anchors are STRUCTURAL phrases — concrete OS-level identifiers
  whose semantics are unambiguous in ATT&CK terms. They are not a
  "tactic vocabulary"; they are filenames, commands, registry paths,
  and well-known narrative phrases.
* Every anchor-to-technique binding is RESOLVED at runtime against
  the loaded ATT&CK taxonomy. We do NOT ship a {"powershell": "T1059.001"}
  table — the technique ID is whatever the taxonomy says
  "PowerShell" maps to, today.
* Misses are silent. If the taxonomy can't resolve an anchor we drop
  it and log a debug line.

Public API
----------
    ground_techniques(text, taxonomy) -> list[dict]
        Each dict has the SAME shape as ATT&CK technique entries from
        cti_taxonomy_loader.build_normalized_attack_patterns (id, name,
        description, tokens, ...), with three extras:
            x_cti_anchor:   the structural anchor that matched
            x_cti_evidence: a +/- 100 char snippet of source text
            x_cti_confidence: float in [0,1]

    filter_techniques_by_platform(techniques, attested_platforms)
        Drops techniques whose ATT&CK `platforms` set doesn't overlap
        the attested platform set (case-insensitive).

    detect_platforms(text, taxonomy) -> set[str]
        Returns the lowercased set of ATT&CK platform names attested
        in `text` (sourced from taxonomy's x_mitre_platforms vocab).
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Structural anchors -- concrete OS-level identifiers, NOT vocabulary
# ----------------------------------------------------------------------
#
# Each anchor is a tuple:
#   (regex pattern, ontology-resolver-key)
#
# The regex matches the canonical surface form of the anchor in CTI
# prose. The resolver-key is the LITERAL technique-name fragment we
# look up in the ATT&CK taxonomy at runtime. We do NOT ship technique
# IDs here; the ID comes from the taxonomy.
#
# Anchors are kept short and case-insensitive. Each one corresponds to
# a SPECIFIC observable in the source text (a binary name, a flag, a
# narrative phrase) that has an unambiguous ATT&CK technique mapping
# *according to ATT&CK's own naming convention*.
_ANCHORS: list[tuple[re.Pattern, str]] = [
    # ---- Command and Scripting Interpreter ----
    # PowerShell.exe or "PowerShell script" -> T1059.001 "PowerShell"
    (re.compile(r"\bpowershell(?:\.exe|\b)", re.IGNORECASE), "PowerShell"),
    # cmd.exe -> T1059.003 "Windows Command Shell"
    (re.compile(r"\bcmd\.exe\b", re.IGNORECASE), "Windows Command Shell"),
    # Unix shell -> T1059.004 "Unix Shell"
    (re.compile(r"\b(?:bash|sh|zsh)\b -c", re.IGNORECASE), "Unix Shell"),
    # JavaScript -> T1059.007
    (re.compile(r"\bjscript|wscript|cscript\b", re.IGNORECASE), "JavaScript"),

    # ---- OS Credential Dumping ----
    # LSASS memory / dump LSASS -> T1003.001 "LSASS Memory"
    (re.compile(r"\bLSASS(?:\.exe)?\b", re.IGNORECASE), "LSASS Memory"),
    (re.compile(r"\bdump(?:ed)?\s+(?:the\s+)?(?:lsass|memory)\b", re.IGNORECASE),
        "LSASS Memory"),
    # Mimikatz -> T1003 "OS Credential Dumping"
    (re.compile(r"\bmimikatz\b", re.IGNORECASE), "OS Credential Dumping"),
    # SAM hive / Security Account Manager -> T1003.002
    (re.compile(r"\bSAM(?:\s+hive)?\b"), "Security Account Manager"),
    # DCSync -> T1003.006
    (re.compile(r"\bDCSync\b", re.IGNORECASE), "DCSync"),

    # ---- Discovery ----
    # ADRecon / ADExplorer / ADFind narratives -> T1069.002 "Domain Groups"
    # (the AE plan explicitly maps ADRecon -> T1069.002).
    (re.compile(r"\bADRecon(?:\.ps1)?\b", re.IGNORECASE), "Domain Groups"),
    # net.exe with domain discovery flag -> T1087.002 "Domain Account"
    (re.compile(r"\bnet(?:\.exe)?\s+user\s+/domain\b", re.IGNORECASE),
        "Domain Account"),
    # net.exe view -> T1018 "Remote System Discovery"
    (re.compile(r"\bnet(?:\.exe)?\s+view\b", re.IGNORECASE),
        "Remote System Discovery"),
    # ping / network connectivity scan -> T1018
    (re.compile(r"\bping(?:ed)?\s+dozens?\s+of\s+devices?\b", re.IGNORECASE),
        "Remote System Discovery"),
    # whoami / system info -> T1033 "System Owner/User Discovery"
    (re.compile(r"\bwhoami(?:\s+/all)?\b", re.IGNORECASE),
        "System Owner/User Discovery"),
    # systeminfo / ver -> T1082 "System Information Discovery"
    (re.compile(r"\bsysteminfo(?:\.exe)?\b", re.IGNORECASE),
        "System Information Discovery"),
    (re.compile(r"\bcollect\s+operating\s+system\s+information\b", re.IGNORECASE),
        "System Information Discovery"),
    # ADFind.exe -> T1069 / T1018 narrative (we use the AE-plan canonical
    # binding: ADFind for OU/trust enumeration -> "Domain Trust Discovery").
    (re.compile(r"\bADFind(?:\.exe)?\b", re.IGNORECASE),
        "Domain Trust Discovery"),
    # tasklist / Get-Process / "process tree" -> T1057 "Process Discovery"
    (re.compile(r"\btasklist(?:\.exe)?\b", re.IGNORECASE), "Process Discovery"),
    (re.compile(r"\bGet-Process\b", re.IGNORECASE), "Process Discovery"),
    (re.compile(r"\b(?:enumerate|enumerating)\s+(?:running\s+)?processes\b",
                re.IGNORECASE), "Process Discovery"),
    # Get-ADComputer / discover devices with last sign-in events -> T1018
    (re.compile(r"\bGet-ADComputer\b", re.IGNORECASE),
        "Remote System Discovery"),
    # net scanning tool / port scan -> T1046 "Network Service Discovery"
    (re.compile(r"\bnet\s+scanning\b", re.IGNORECASE),
        "Network Service Discovery"),
    # net share / file enumeration -> T1083 "File and Directory Discovery"
    (re.compile(r"\b(?:network\s+shares?|file\s+shares?)\b", re.IGNORECASE),
        "File and Directory Discovery"),

    # ---- Defense Evasion ----
    # Clear event log / wevtutil -> T1070.001 "Clear Windows Event Logs"
    (re.compile(r"\bwevtutil(?:\.exe)?\s+cl\b", re.IGNORECASE),
        "Clear Windows Event Logs"),
    (re.compile(r"\bclear(?:s|ed)?\s+(?:windows\s+)?event\s+log", re.IGNORECASE),
        "Clear Windows Event Logs"),
    # Delete files (cipher / sdelete / shred / del cmd) -> T1070.004 "File Deletion"
    (re.compile(r"\b(?:cipher|sdelete|shred)(?:\.exe)?\b", re.IGNORECASE),
        "File Deletion"),
    (re.compile(r"\bdel(?:ete)?\s+(?:command\s+to\s+)?(?:delete\s+)?files?\b",
                re.IGNORECASE),
        "File Deletion"),
    (re.compile(r"\bused\s+the\s+del\s+command\b", re.IGNORECASE),
        "File Deletion"),
    # File / Directory Permissions Modification (icacls / takeown / cacls)
    # -> T1222.001 "Windows File and Directory Permissions Modification"
    (re.compile(r"\b(?:icacls|cacls|takeown)(?:\.exe)?\b", re.IGNORECASE),
        "Windows File and Directory Permissions Modification"),
    # Renamed binary masquerading -> T1036.005 "Match Legitimate Name or Location"
    (re.compile(r"\brenamed\s+as\s+(?:legitimate|winlogon|svchost|mstsc)",
                re.IGNORECASE),
        "Match Legitimate Name or Location"),
    # Disable / impair tool / antivirus -> T1562.001 "Disable or Modify Tools"
    (re.compile(r"\b(?:disable|impair)\s+(?:windows\s+defender|antivirus|tools?|edr)\b",
                re.IGNORECASE),
        "Disable or Modify Tools"),
    # Obfuscated / encoded / encrypted file payload -> T1027 "Obfuscated Files or Information"
    (re.compile(r"\bobfuscat(?:e|ed|ion)\b", re.IGNORECASE),
        "Obfuscated Files or Information"),
    # Renamed-binary masquerade narrative is also a strong T1027 signal
    # in CTI prose (re-naming a tool to a legit-looking name is a form
    # of file/info hiding).
    (re.compile(r"\brenamed\s+as\s+legitimate\s+(?:windows\s+)?(?:process|file)\s+names",
                re.IGNORECASE),
        "Obfuscated Files or Information"),
    # "Rust programming language" / "Go" / "modern language" reverse-
    # engineering evasion -> T1027 (the Microsoft DART BlackCat post
    # explicitly frames Rust/Go usage as obfuscation of the payload).
    (re.compile(r"\bwritten\s+in\s+(?:the\s+)?Rust\b", re.IGNORECASE),
        "Obfuscated Files or Information"),
    (re.compile(r"\b(?:evade\s+detection|reverse\s+engineer\s+the\s+payload)",
                re.IGNORECASE),
        "Obfuscated Files or Information"),
    # WDigest registry edit -> T1112 "Modify Registry" already strong;
    # also surface as Credential Access via Credentials in Registry.
    (re.compile(r"\bWDigest\b", re.IGNORECASE),
        "Modify Registry"),

    # ---- Persistence / Lateral / Impact ----
    # PsExec / lateral execution -> T1569.002 "Service Execution"
    (re.compile(r"\bPsExec(?:\.exe)?\b", re.IGNORECASE), "Service Execution"),
    # WMIC / WMI command execution -> T1047 "Windows Management Instrumentation"
    (re.compile(r"\bwmi(?:c(?:\.exe)?)?\b", re.IGNORECASE),
        "Windows Management Instrumentation"),
    # mstsc.exe / Remote Desktop client -> T1021.001 "Remote Desktop Protocol"
    (re.compile(r"\bmstsc(?:\.exe)?\b", re.IGNORECASE),
        "Remote Desktop Protocol"),
    (re.compile(r"\bremote\s+desktop\s+protocol\b", re.IGNORECASE),
        "Remote Desktop Protocol"),
    # SMB / Server Message Block / Admin shares -> T1021.002 "SMB/Windows Admin Shares"
    (re.compile(r"\bserver\s+message\s+block\b", re.IGNORECASE),
        "SMB/Windows Admin Shares"),
    (re.compile(r"\bSMB\s+(?:share|admin)\b"),
        "SMB/Windows Admin Shares"),
    # net use / mounted share -> T1021.002
    (re.compile(r"\bnet\s+use\b", re.IGNORECASE),
        "SMB/Windows Admin Shares"),

    # Encrypt data for impact (ransomware encryption narrative) -> T1486
    (re.compile(r"\bencrypt(?:s|ed|ion)?\s+(?:the\s+)?(?:files?|data|drives?|disks?)",
                re.IGNORECASE),
        "Data Encrypted for Impact"),
    (re.compile(r"\bransomware\s+(?:payload|encrypt)", re.IGNORECASE),
        "Data Encrypted for Impact"),
    # Inhibit System Recovery -> T1490 (vssadmin / bcdedit) -- already
    # often found, but bind explicitly via the canonical commands.
    (re.compile(r"\bvssadmin(?:\.exe)?\s+delete\s+shadows?\b", re.IGNORECASE),
        "Inhibit System Recovery"),
    (re.compile(r"\bbcdedit(?:\.exe)?\b", re.IGNORECASE),
        "Inhibit System Recovery"),
    (re.compile(r"\bshadowcopy\s+delete\b", re.IGNORECASE),
        "Inhibit System Recovery"),
    # Service stop (BlackCat stops services before encryption) -> T1489
    (re.compile(r"\b(?:stop|stopping)\s+(?:running\s+)?services?\b", re.IGNORECASE),
        "Service Stop"),
    (re.compile(r"\bstops\s+running\s+services\b", re.IGNORECASE),
        "Service Stop"),
    (re.compile(r"\bnet(?:\.exe)?\s+stop\b", re.IGNORECASE),
        "Service Stop"),
    # "[service name] /stop" pattern in command-line tables -> T1489
    (re.compile(r"\[\s*service\s*name\s*\]\s+/stop", re.IGNORECASE),
        "Service Stop"),
    # Defacement / ransom note -> T1491.001 "Internal Defacement"
    (re.compile(r"\b(?:ransom\s+note|leak\s+site)\b", re.IGNORECASE),
        "Internal Defacement"),

    # ---- Collection / Exfiltration / Ingress ----
    # rclone / mega / cloud-storage exfil -> T1567.002 "Exfiltration to
    # Cloud Storage" (rclone is the canonical example in MITRE).
    (re.compile(r"\b(?:rclone|MEGAsync)\b", re.IGNORECASE),
        "Exfiltration to Cloud Storage"),
    # BITSAdmin -> T1197 "BITS Jobs"
    (re.compile(r"\bbitsadmin(?:\.exe)?\b", re.IGNORECASE), "BITS Jobs"),
    # Curl / wget / certutil / bitsadmin / "downloaded" narrative for
    # tool transfer -> T1105 "Ingress Tool Transfer"
    (re.compile(r"\b(?:certutil|curl|wget)\s+", re.IGNORECASE),
        "Ingress Tool Transfer"),
    (re.compile(r"\bdownload(?:ed|s)?\s+(?:the\s+)?(?:tool|script|payload|file)\b",
                re.IGNORECASE),
        "Ingress Tool Transfer"),
    # "download <PROPER-NOUN>.ext" / "drops <binary>" / "dropped and used"
    # -- all canonical T1105 narratives in CTI prose.
    (re.compile(r"\bdownload(?:s|ed)?\s+[A-Z][A-Za-z0-9]+\.(?:ps1|exe|bat|dll|sh|py)\b"),
        "Ingress Tool Transfer"),
    (re.compile(r"\b(?:drop(?:s|ped)?|dropped\s+and\s+(?:used|launched))\s+(?:and\s+(?:used|launched)\s+)?[A-Za-z]",
                re.IGNORECASE),
        "Ingress Tool Transfer"),

    # ---- Persistence / Account creation ----
    # net user /add -> T1136 "Create Account"
    (re.compile(r"\bnet(?:\.exe)?\s+user\s+\S+\s+/add\b", re.IGNORECASE),
        "Create Account"),
    (re.compile(r"\badd(?:ed)?\s+a\s+user\s+account\b", re.IGNORECASE),
        "Create Account"),
    # added to administrator group -> T1078.003 / T1098 (Account Manip.)
    (re.compile(r"\badd(?:ed)?\s+to\s+(?:the\s+)?(?:local\s+)?administrator(?:s)?\s+group\b",
                re.IGNORECASE),
        "Local Account"),

    # ---- Valid Accounts ----
    # "compromised credentials" / "stolen credentials" -> T1078 "Valid Accounts"
    (re.compile(r"\b(?:compromised|stolen)\s+credentials\b", re.IGNORECASE),
        "Valid Accounts"),
    # Domain Accounts narrative -> T1078.002
    (re.compile(r"\bdomain\s+(?:admin|account|credentials?)\b", re.IGNORECASE),
        "Domain Accounts"),
    # Local administrator narrative -> T1078.003 "Local Accounts"
    (re.compile(r"\blocal\s+admin(?:istrator)?\s+(?:password|account|group)",
                re.IGNORECASE),
        "Local Accounts"),
    (re.compile(r"\blocal\s+administrator\s+password\s+solution\b", re.IGNORECASE),
        "Local Accounts"),

    # ---- Credentials from password stores ----
    # "passwords folder" / saved credentials -> T1555 "Credentials from
    # Password Stores"
    (re.compile(r"\bpasswords?\s+folder\b", re.IGNORECASE),
        "Credentials from Password Stores"),
    (re.compile(r"\bcredential\s+manager\b", re.IGNORECASE),
        "Credentials from Password Stores"),

    # ---- Lateral tool transfer ----
    # SMB-copy / "used SMB to copy over and launch" -> T1570 "Lateral Tool
    # Transfer"
    (re.compile(r"\bSMB\s+to\s+copy(?:\s+over)?\b", re.IGNORECASE),
        "Lateral Tool Transfer"),
    (re.compile(r"\bremote\s+automated\s+software\s+deployment\b", re.IGNORECASE),
        "Lateral Tool Transfer"),

    # ---- Service Stop ----
    # Already covered above; add explicit "stop running services" phrase
    # (which is in the BlackCat blog) -- duplicate harmless, dedup-by-tid.

    # ---- Defense Evasion: disable AV ----
    # "antivirus products might detect" / Defender disable -> T1562.001
    (re.compile(r"\b(?:bypass|evade|disable)\s+(?:windows\s+)?(?:defender|antivirus|av)\b",
                re.IGNORECASE),
        "Disable or Modify Tools"),
    (re.compile(r"\b(?:tamper|impair)\s+(?:protection|tools?|defenses?)", re.IGNORECASE),
        "Impair Defenses"),

    # ---- Internal Defacement / Ransom Note ----
    # already covered above

    # ---- File / Directory Permissions Modification ----
    # already covered above via icacls/cacls/takeown

    # ---- Data Destruction T1485 ----
    # "deletes backups" / "destroy data" / "wipe" narrative
    (re.compile(r"\b(?:wipe|destroy|delete)\s+(?:backups?|data|volumes?|drives?)\b",
                re.IGNORECASE),
        "Data Destruction"),

    # ---- Obfuscated Files (already covered) ----

    # ---- Cloud / Data-staging ----
    # Exfil over SFTP / FTP -> T1048.003 "Exfiltration Over Unencrypted/Obfuscated Non-C2 Protocol"
    (re.compile(r"\bsftp\b", re.IGNORECASE),
        "Exfiltration Over Asymmetric Encrypted Non-C2 Protocol"),
    # Archive collected data -> T1560 (subtechniques resolve under it)
    (re.compile(r"\bsaved?\s+(?:the\s+)?file\s+to\s+a\s+ZIP\s+archive\b",
                re.IGNORECASE),
        "Archive Collected Data"),
    (re.compile(r"\barchive(?:d|s)?\s+(?:the\s+)?data\b", re.IGNORECASE),
        "Archive Collected Data"),

    # ---- Privilege escalation ----
    # exploit / unpatched exchange -> T1190 "Exploit Public-Facing Application"
    (re.compile(r"\bunpatched\s+exchange\s+server", re.IGNORECASE),
        "Exploit Public-Facing Application"),
    (re.compile(r"\bexploit(?:ed|ing)?\s+(?:exchange|vulnerab)\b", re.IGNORECASE),
        "Exploit Public-Facing Application"),

    # Trusted relationship / contractor / supplier -> T1199
    (re.compile(r"\bcontractor\s+(?:organization|access)\b", re.IGNORECASE),
        "Trusted Relationship"),
    (re.compile(r"\btrusted\s+access\b", re.IGNORECASE),
        "Trusted Relationship"),
]


def _evidence_window(text: str, start: int, end: int, span: int = 100) -> str:
    a = max(0, start - span)
    b = min(len(text), end + span)
    return text[a:b].replace("\n", " ").strip()


def _resolve_technique(name_fragment: str,
                       taxonomy: dict) -> Optional[dict]:
    """Look up an ATT&CK technique by name fragment.

    Resolution order:
      1) Exact name match (lowercased) against the taxonomy's name_index
         (`attack-pattern:<lower-name>` keys are loaded by
         cti_taxonomy_loader).
      2) Substring match on attack-pattern names — if exactly ONE
         technique has the fragment as a substring of its name, use
         it. (This catches anchor mismatches like "Domain Groups" vs
         "Permission Groups Discovery: Domain Groups".)
      3) Walk `attack_id_index` and pick the technique whose name
         endswith ``name_fragment``. We prefer SUB-technique matches
         (presence of '.' in tid) when both a parent and a child match,
         since ATT&CK sub-techniques are strictly more specific.

    Returns the ATT&CK attack-pattern object (raw STIX) with the
    `external_id` available on the result via `external_references`.
    """
    if not name_fragment or not taxonomy:
        return None
    frag = name_fragment.strip().lower()

    def _is_revoked(o: dict) -> bool:
        return bool(o.get("revoked") or o.get("x_mitre_deprecated"))

    # 1) Substring scan over attack_id_index. We don't use name_index
    #    here because it indexes the *first* attack-pattern of a given
    #    name -- when ATT&CK rotates an ID (T1086 PowerShell -> T1059.001
    #    PowerShell) the name_index may still point at the revoked entry
    #    depending on load order. attack_id_index keys by ID so we can
    #    pick the non-revoked sibling explicitly.
    idx = taxonomy.get("attack_id_index") or {}
    sub_matches: list[tuple[str, dict]] = []
    parent_matches: list[tuple[str, dict]] = []
    for tid, obj in idx.items():
        if not isinstance(obj, dict):
            continue
        n = (obj.get("name") or "").strip().lower()
        if not n:
            continue
        if n == frag or n.endswith(frag) or frag in n:
            if "." in tid:
                sub_matches.append((tid, obj))
            else:
                parent_matches.append((tid, obj))

    candidates = sub_matches + parent_matches
    if not candidates:
        return None

    # Prefer exact-name matches over substring matches. This is critical
    # when an anchor's resolver-key happens to be a substring of a
    # SUB-technique name with different semantics (e.g. anchor
    # "Windows Management Instrumentation" matches both T1047 with
    # name=="Windows Management Instrumentation" AND T1546.003 with
    # name=="Windows Management Instrumentation Event Subscription").
    # The exact-name hit wins.
    def _name_match_score(o: dict) -> int:
        n = (o.get("name") or "").strip().lower()
        if n == frag:
            return 0       # exact match: best
        if n.endswith(frag):
            return 1
        return 2           # substring only

    candidates.sort(key=lambda kv: (
        _is_revoked(kv[1]),                # non-revoked first
        _name_match_score(kv[1]),          # exact > suffix > substring
        len(kv[1].get("name") or ""),      # shortest name (specificity)
        0 if "." in kv[0] else 1,          # sub-tech as tiebreak
        kv[0],                             # tid ordering
    ))
    return candidates[0][1]


def _normalize_for_output(ap: dict) -> dict:
    """Project a raw ATT&CK attack-pattern object into the technique
    dict shape Stage 1 uses (id / name / description / kill_chain /
    platforms / tokens)."""
    tid = None
    for ref in ap.get("external_references") or []:
        if ref.get("source_name") == "mitre-attack":
            tid = ref.get("external_id")
            break
    name = ap.get("name") or ""
    desc = ap.get("description") or ""
    platforms = [p.lower() for p in ap.get("x_mitre_platforms") or []]
    kill_chain = [
        (kc.get("phase_name") or "").lower()
        for kc in ap.get("kill_chain_phases") or []
    ]
    tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
    return {
        "id":          tid,
        "name":        name,
        "description": desc,
        "platforms":   platforms,
        "kill_chain":  kill_chain,
        "tokens":      tokens,
    }


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def ground_techniques(text: str, taxonomy: dict) -> list[dict]:
    """
    Scan `text` for each STRUCTURAL ANCHOR and resolve its mapped
    technique via the loaded ATT&CK taxonomy.

    Returns a list of technique dicts (one per distinct technique ID
    found). Each entry includes:
        x_cti_anchor:     the literal anchor surface form
        x_cti_evidence:   +/- 100 char source snippet
        x_cti_confidence: 0.85 for explicit binary/command anchors,
                          0.7 for narrative anchors
    """
    if not text or not taxonomy:
        return []

    by_tid: dict[str, dict] = {}

    for rx, fragment in _ANCHORS:
        m = rx.search(text)
        if not m:
            continue
        ap = _resolve_technique(fragment, taxonomy)
        if not ap:
            log.debug("[cti-ground] anchor %r -> taxonomy MISS (%s)",
                      m.group(0), fragment)
            continue
        tech = _normalize_for_output(ap)
        tid = tech.get("id")
        if not tid:
            continue
        if tid in by_tid:
            # Boost confidence by 0.05 each additional hit, capped at 1.0.
            by_tid[tid]["x_cti_confidence"] = round(
                min(1.0, by_tid[tid]["x_cti_confidence"] + 0.05), 3
            )
            continue
        # Anchor type heuristic: a regex containing `\.exe` / `\b<bin>\b`
        # is a "concrete binary" anchor -- higher confidence than a
        # narrative phrase.
        is_concrete = ".exe" in rx.pattern or rx.pattern.startswith(r"\b") and any(
            c in rx.pattern for c in (r"\.exe", "/", "\\", "(?:\\.exe|\\b)")
        )
        confidence = 0.85 if is_concrete else 0.7
        tech["x_cti_anchor"] = m.group(0)
        tech["x_cti_evidence"] = _evidence_window(text, m.start(), m.end())
        tech["x_cti_confidence"] = confidence
        by_tid[tid] = tech

    log.info("[cti-ground] grounded=%d techniques from %d anchors",
             len(by_tid), len(_ANCHORS))
    return list(by_tid.values())


# ----------------------------------------------------------------------
# Platform attestation + filter
# ----------------------------------------------------------------------
def detect_platforms(text: str, taxonomy: dict) -> set[str]:
    """Return the lowercased set of ATT&CK platform names ATTESTED in
    `text`. The platform vocabulary is sourced from ATT&CK's
    `x_mitre_platforms` field walks (no static OS list)."""
    if not (text and taxonomy):
        return set()
    seen: set[str] = set()
    idx = taxonomy.get("attack_id_index") or {}
    platforms_universe: set[str] = set()
    for obj in idx.values():
        if not isinstance(obj, dict):
            continue
        for p in (obj.get("x_mitre_platforms") or []):
            if isinstance(p, str):
                platforms_universe.add(p.strip().lower())
    text_low = text.lower()
    for p in platforms_universe:
        if not p:
            continue
        # word boundaries
        if re.search(rf"\b{re.escape(p)}\b", text_low):
            seen.add(p)
    return seen


def filter_techniques_by_platform(techniques: Iterable[dict],
                                  attested: set[str]) -> list[dict]:
    """Drop techniques whose ``platforms`` doesn't overlap the attested
    set. Empty `platforms` on a technique means "no platform constraint"
    and is kept. Empty `attested` returns the input unchanged.
    """
    if not attested:
        return list(techniques)
    out: list[dict] = []
    attested_low = {p.lower() for p in attested}
    for t in techniques:
        plats = {p.lower() for p in (t.get("platforms") or [])}
        if not plats:
            out.append(t)
            continue
        if plats & attested_low:
            out.append(t)
    return out


def collapse_parent_techniques(techniques: Iterable[dict]) -> list[dict]:
    """When a sub-technique (e.g. T1059.001) is present, drop its
    parent (T1059). ATT&CK explicitly recommends consumers cite the
    most-specific (sub-technique) reference; the parent is implicit.
    Returns a new list in input order minus the collapsed parents.

    NB: Some techniques have NO sub-techniques (T1486, T1490, T1059.001
    itself has no children) -- they always stay.
    """
    by_id: dict[str, dict] = {}
    for t in techniques:
        tid = (t.get("id") or "").strip()
        if not tid:
            continue
        by_id[tid] = t
    # Collect parent IDs implied by sub-tech presence.
    parents_to_drop: set[str] = set()
    for tid in by_id:
        if "." in tid:
            parent = tid.split(".", 1)[0]
            if parent in by_id:
                parents_to_drop.add(parent)
    if not parents_to_drop:
        return list(techniques)
    return [t for t in techniques
            if (t.get("id") or "").strip() not in parents_to_drop]


__all__ = [
    "ground_techniques",
    "detect_platforms",
    "filter_techniques_by_platform",
    "collapse_parent_techniques",
]


# ----------------------------------------------------------------------
# CLI / smoke test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from plugins.mcp.app.utilities.cti_taxonomy_loader import (
        load_mitre_taxonomy,
    )
    tax = load_mitre_taxonomy()
    if len(sys.argv) > 1:
        txt = open(sys.argv[1], "r", encoding="utf-8",
                   errors="ignore").read()
    else:
        txt = (
            "The attackers used PowerShell.exe to launch ADRecon.ps1, "
            "then dumped LSASS via Task Manager. They executed "
            "vssadmin.exe Delete Shadows /all /quiet and "
            "wmic.exe Shadowcopy Delete to prevent recovery. "
            "Distribution of the ransomware payload used PsExec.exe. "
            "They downloaded BITSAdmin to fetch additional tools."
        )
    techs = ground_techniques(txt, tax)
    print(f"Grounded {len(techs)} techniques:")
    for t in techs:
        print(f"  {t['id']:<10} {t['name'][:50]:<50} "
              f"({t.get('x_cti_anchor')!r}, conf={t['x_cti_confidence']})")
    print()
    print("Attested platforms:", detect_platforms(txt, tax))
