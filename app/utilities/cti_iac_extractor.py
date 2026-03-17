"""
cti_iac_extractor.py — Infrastructure-as-Code Extraction from CTI

Extracts infrastructure requirements from STIX bundles and source text
to produce deployable environment specifications for adversary emulation.

Data sources:
1. ATT&CK technique platforms (x_mitre_platforms) → OS requirements
2. D3FEND digital artifact taxonomy → infrastructure components
3. Source text regex → explicit services, ports, OS mentions
4. Tool requirements → what the adversary tools need to run

Output: infrastructure spec suitable for Terraform/Vagrant/Docker deployment.
"""

import json
import re
from pathlib import Path
from functools import lru_cache
from collections import Counter, defaultdict


# ============================================================
# ATT&CK PLATFORM EXTRACTION
# ============================================================

@lru_cache(maxsize=1)
def _load_technique_platforms():
    """Load platform requirements per ATT&CK technique."""
    bundle_path = Path(__file__).resolve().parent / "cti_taxonomy" / "enterprise_attack.json"
    bundle = json.loads(bundle_path.read_text())

    platforms = {}
    for obj in bundle["objects"]:
        if obj.get("type") != "attack-pattern":
            continue
        tid = None
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == "mitre-attack":
                tid = ref["external_id"]
                break
        if tid:
            platforms[tid] = obj.get("x_mitre_platforms", [])

    return platforms


# ============================================================
# SERVICE/PROTOCOL DETECTION FROM TEXT
# ============================================================

SERVICE_PATTERNS = {
    "rdp": {
        "pattern": r"\bRDP\b|Remote Desktop Protocol|Remote Desktop|port\s*3389",
        "port": "3389/tcp",
        "os": "Windows",
        "service": "Remote Desktop Services",
    },
    "smb": {
        "pattern": r"\bSMB\b|Server Message Block|port\s*445|network share|admin\$",
        "port": "445/tcp",
        "os": "Windows",
        "service": "SMB File Sharing",
    },
    "ssh": {
        "pattern": r"\bSSH\b|Secure Shell|port\s*22\b|OpenSSH",
        "port": "22/tcp",
        "os": "Linux",
        "service": "SSH Server",
    },
    "http": {
        "pattern": r"\bHTTP\b|web server|port\s*80\b|Apache|Nginx|IIS",
        "port": "80/tcp",
        "os": None,
        "service": "Web Server",
    },
    "https": {
        "pattern": r"\bHTTPS\b|SSL|TLS|port\s*443\b",
        "port": "443/tcp",
        "os": None,
        "service": "HTTPS/TLS",
    },
    "ldap": {
        "pattern": r"\bLDAP\b|Active Directory|Domain Controller|port\s*389",
        "port": "389/tcp",
        "os": "Windows",
        "service": "Active Directory Domain Services",
    },
    "dns": {
        "pattern": r"\bDNS\b|domain name.*server|port\s*53\b",
        "port": "53/udp",
        "os": None,
        "service": "DNS Server",
    },
    "winrm": {
        "pattern": r"\bWinRM\b|Windows Remote Management|port\s*5985|WS-Management",
        "port": "5985/tcp",
        "os": "Windows",
        "service": "Windows Remote Management",
    },
    "sql": {
        "pattern": r"\bSQL\b|database.*server|MSSQL|MySQL|port\s*1433|port\s*3306",
        "port": "1433/tcp",
        "os": None,
        "service": "Database Server",
    },
    "exchange": {
        "pattern": r"\bExchange\b|mail server|SMTP|port\s*25\b|OWA",
        "port": "443/tcp",
        "os": "Windows",
        "service": "Microsoft Exchange",
    },
    "vpn": {
        "pattern": r"\bVPN\b|virtual private network|AnyConnect|FortiOS|Citrix.*Gateway",
        "port": "443/tcp",
        "os": None,
        "service": "VPN Gateway",
    },
    "kerberos": {
        "pattern": r"\bKerberos\b|krbtgt|TGT|Ticket Granting|port\s*88\b",
        "port": "88/tcp",
        "os": "Windows",
        "service": "Kerberos KDC",
    },
    "esxi": {
        "pattern": r"\bESXi\b|vSphere|VMware|hypervisor|vCenter",
        "port": "443/tcp",
        "os": "ESXi",
        "service": "VMware ESXi",
    },
}

# OS detection patterns
OS_PATTERNS = {
    "Windows": r"\bWindows\b|Win(?:10|11|Server|dows)|NTLM|Active Directory|PowerShell|cmd\.exe|registry|Group Policy",
    "Linux": r"\bLinux\b|Ubuntu|CentOS|Debian|RedHat|RHEL|/etc/passwd|bash|chmod|cron",
    "macOS": r"\bmacOS\b|Mac OS|Apple|Darwin|Objective-C|LaunchAgent",
    "ESXi": r"\bESXi\b|vSphere|VMware.*hypervisor|vim-cmd|esxcli",
}

# Tool → infrastructure requirements
TOOL_INFRA = {
    "mimikatz": {"os": "Windows", "requires": ["LSASS process", "SeDebugPrivilege"]},
    "psexec": {"os": "Windows", "requires": ["SMB (445/tcp)", "Admin shares"]},
    "cobalt strike": {"os": "Windows", "requires": ["HTTP/HTTPS C2", "SMB lateral"]},
    "impacket": {"os": "Linux", "requires": ["Python", "SMB/WMI connectivity"]},
    "bloodhound": {"os": "Windows", "requires": ["Active Directory", "LDAP"]},
    "rclone": {"os": None, "requires": ["Internet access", "Cloud storage endpoint"]},
    "procdump": {"os": "Windows", "requires": ["LSASS process"]},
    "adrecon": {"os": "Windows", "requires": ["Active Directory", "PowerShell"]},
    "adfind": {"os": "Windows", "requires": ["Active Directory", "LDAP"]},
    "certutil": {"os": "Windows", "requires": ["Certificate services"]},
    "wevtutil": {"os": "Windows", "requires": ["Windows Event Log service"]},
    "vssadmin": {"os": "Windows", "requires": ["Volume Shadow Copy Service"]},
}


# ============================================================
# MAIN EXTRACTION
# ============================================================

def extract_infrastructure(ir: dict, source_text: str) -> dict:
    """
    Extract infrastructure requirements from IR and source text.

    Returns a deployment specification:
    {
        "platforms": {"Windows": {...}, "Linux": {...}},
        "services": [{"name": "...", "port": "...", "os": "..."}],
        "network": {"segments": [...], "c2_channels": [...]},
        "accounts": [{"type": "domain_admin", ...}],
        "tools_required": [...],
        "deployment_notes": [...]
    }
    """
    spec = {
        "platforms": {},
        "services": [],
        "network": {"segments": [], "c2_channels": [], "external_ips": []},
        "accounts": [],
        "tools_required": [],
        "deployment_notes": [],
    }

    text_lower = source_text.lower()

    # ---------------------------------------------------------
    # 1. OS platforms from ATT&CK techniques
    # ---------------------------------------------------------
    tech_platforms = _load_technique_platforms()
    platform_counter = Counter()

    for ap in ir.get("attack_patterns", []):
        tid = ap.get("id", "") if isinstance(ap, dict) else ""
        platforms = tech_platforms.get(tid, [])
        for p in platforms:
            if p not in ("PRE", "SaaS", "Office Suite", "Identity Provider"):
                platform_counter[p] += 1

    # ---------------------------------------------------------
    # 2. OS from source text (explicit mentions)
    # ---------------------------------------------------------
    for os_name, pattern in OS_PATTERNS.items():
        if re.search(pattern, source_text, re.IGNORECASE):
            platform_counter[os_name] += 10  # strong signal from text

    # Build platform specs
    for platform, weight in platform_counter.most_common():
        if weight < 2:
            continue
        spec["platforms"][platform] = {
            "required": weight >= 5,
            "technique_count": weight,
            "confidence": "high" if weight >= 10 else "medium" if weight >= 5 else "low",
        }

    # ---------------------------------------------------------
    # 3. Services from source text
    # ---------------------------------------------------------
    seen_services = set()
    for svc_name, svc_info in SERVICE_PATTERNS.items():
        if re.search(svc_info["pattern"], source_text, re.IGNORECASE):
            if svc_name not in seen_services:
                seen_services.add(svc_name)
                spec["services"].append({
                    "name": svc_info["service"],
                    "port": svc_info["port"],
                    "os": svc_info["os"],
                    "detected_by": "source_text",
                })

    # ---------------------------------------------------------
    # 4. Tool infrastructure requirements
    # ---------------------------------------------------------
    for tool in ir.get("tools", []):
        tool_name = (tool.get("name") or "").lower()
        infra = TOOL_INFRA.get(tool_name)
        if infra:
            spec["tools_required"].append({
                "tool": tool.get("name"),
                "os": infra["os"],
                "requires": infra["requires"],
            })
            # Add implied services
            for req in infra["requires"]:
                if "SMB" in req and "smb" not in seen_services:
                    seen_services.add("smb")
                    spec["services"].append({
                        "name": "SMB File Sharing",
                        "port": "445/tcp",
                        "os": "Windows",
                        "detected_by": f"tool:{tool.get('name')}",
                    })
                if "Active Directory" in req and "ldap" not in seen_services:
                    seen_services.add("ldap")
                    spec["services"].append({
                        "name": "Active Directory Domain Services",
                        "port": "389/tcp",
                        "os": "Windows",
                        "detected_by": f"tool:{tool.get('name')}",
                    })

    # ---------------------------------------------------------
    # 5. Network infrastructure from IR
    # ---------------------------------------------------------
    for infra in ir.get("infrastructure", []):
        name = (infra.get("name") or "").strip()
        desc = (infra.get("description") or "").lower()

        if re.match(r"\d+\.\d+\.\d+\.\d+", name):
            spec["network"]["external_ips"].append(name)
        elif "c2" in desc or "command" in desc or "control" in desc:
            spec["network"]["c2_channels"].append(name)
        elif re.match(r"[a-z0-9-]+\.[a-z]{2,}", name) and not name.startswith("CVE"):
            # Only add as C2 if it looks like a real domain (has valid TLD)
            spec["network"]["c2_channels"].append(name)

    # ---------------------------------------------------------
    # 6. Account types from text and techniques
    # ---------------------------------------------------------
    account_patterns = {
        "domain_admin": r"domain\s*admin|DA\s+account|enterprise\s+admin",
        "local_admin": r"local\s*admin|administrator\s+account|admin\s+priv",
        "service_account": r"service\s+account|SQL\s+service|svc\$",
        "user_account": r"user\s+account|valid\s+account|compromised\s+account",
    }
    for acct_type, pattern in account_patterns.items():
        if re.search(pattern, source_text, re.IGNORECASE):
            spec["accounts"].append({"type": acct_type, "detected_by": "source_text"})

    # ---------------------------------------------------------
    # 7. Network topology from text
    # ---------------------------------------------------------
    topology = {"hosts": [], "segments": [], "perimeter": []}

    # Detect multi-host requirement
    if re.search(r"lateral\s+movement|move\s+laterally|spread|propagat", text_lower):
        topology["hosts"].append("Multiple internal hosts (lateral movement target)")
    if re.search(r"domain\s+controller|active\s+directory", text_lower):
        topology["hosts"].append("Domain Controller (Windows Server)")
    if re.search(r"workstation|endpoint|client\s+machine", text_lower):
        topology["hosts"].append("Workstation(s) (domain-joined)")
    if re.search(r"file\s+server|share|backup\s+server", text_lower):
        topology["hosts"].append("File/Backup Server")
    if re.search(r"mail\s+server|exchange", text_lower):
        topology["hosts"].append("Mail Server (Exchange)")
    if re.search(r"web\s+server|public.facing|internet.facing", text_lower):
        topology["hosts"].append("Web Server (public-facing)")
    if re.search(r"database|sql\s+server", text_lower):
        topology["hosts"].append("Database Server")

    # Network segments
    if re.search(r"DMZ|demilitarized", text_lower):
        topology["segments"].append("DMZ (public-facing services)")
    if re.search(r"internal\s+network|corporate\s+network|intranet", text_lower):
        topology["segments"].append("Internal corporate network")
    if re.search(r"segment|isolat|separate\s+network", text_lower):
        topology["segments"].append("Segmented network zones")

    # Perimeter
    if re.search(r"VPN|remote\s+access|external\s+remote", text_lower):
        topology["perimeter"].append("VPN/Remote access gateway")
    if re.search(r"firewall", text_lower):
        topology["perimeter"].append("Firewall")
    if re.search(r"proxy", text_lower):
        topology["perimeter"].append("Proxy server")

    spec["topology"] = topology

    # ---------------------------------------------------------
    # 8. Kill chain ordering (deployment sequence)
    # ---------------------------------------------------------
    kill_chain = []
    phase_signals = [
        ("initial_access", r"initial\s+access|exploit.*public|phishing|drive.by|VPN.*exploit|brute\s+force",
         "Perimeter/initial access host (VPN gateway, web server, or mail server)"),
        ("execution", r"execut|PowerShell|cmd\.exe|scripting|scheduled\s+task",
         "Execution environment on compromised host"),
        ("persistence", r"persist|backdoor|implant|scheduled\s+task|registry.*run|autostart",
         "Persistence mechanisms on foothold host"),
        ("credential_access", r"credential|password|LSASS|dump|mimikatz|hash|kerberos",
         "Credential stores (LSASS, SAM, NTDS.dit on DC)"),
        ("discovery", r"discover|enumerat|scan|reconnaissance|ADRecon|network\s+scan",
         "Network/AD discovery targets"),
        ("lateral_movement", r"lateral|remote\s+desktop|RDP|PsExec|WMI|SMB.*spread",
         "Additional hosts for lateral movement"),
        ("collection", r"collect|stage|compress|archive|sensitive\s+data",
         "Data staging location"),
        ("exfiltration", r"exfiltrat|upload|cloud\s+storage|MEGA|rclone",
         "Exfiltration endpoint (cloud storage or C2)"),
        ("impact", r"encrypt|ransom|wipe|destruct|defac|shadow\s+copy|wallpaper",
         "Impact targets (file servers, databases, backups)"),
    ]

    for phase, pattern, infra_need in phase_signals:
        if re.search(pattern, text_lower):
            kill_chain.append({"phase": phase, "infrastructure": infra_need})

    spec["kill_chain"] = kill_chain

    # ---------------------------------------------------------
    # 9. Security controls to deploy (for purple team/detection testing)
    # ---------------------------------------------------------
    security_controls = []
    control_patterns = [
        (r"antivirus|anti.virus|Windows\s+Defender|AV\b", "Antivirus/EDR (Windows Defender)"),
        (r"EDR|endpoint\s+detection", "Endpoint Detection and Response"),
        (r"firewall|Windows\s+Firewall", "Host/Network Firewall"),
        (r"event\s+log|logging|wevtutil|syslog", "Event Logging (Windows Event Log, Syslog)"),
        (r"SmartScreen", "Windows SmartScreen"),
        (r"multi.?factor|MFA|two.?factor|2FA", "Multi-Factor Authentication"),
        (r"intrusion\s+detection|IDS|IPS", "IDS/IPS"),
        (r"SIEM|security\s+information", "SIEM"),
    ]
    for pattern, name in control_patterns:
        if re.search(pattern, source_text, re.IGNORECASE):
            security_controls.append(name)

    spec["security_controls"] = security_controls

    # ---------------------------------------------------------
    # 10. Data to stage (bait data for realistic emulation)
    # ---------------------------------------------------------
    staged_data = []
    data_patterns = [
        (r"credential|password|stored\s+password", "Credential files / password stores"),
        (r"configuration|network\s+config", "Network configuration files"),
        (r"document|sensitive\s+data|PII", "Sensitive documents"),
        (r"database|SQL\s+data", "Database records"),
        (r"email|mailbox", "Email/mailbox data"),
        (r"backup", "Backup files"),
        (r"source\s+code|repository", "Source code repositories"),
        (r"certificate|private\s+key", "Certificates/private keys"),
        (r"operating\s+procedure|SOP|policy", "SOPs/policy documents"),
    ]
    for pattern, name in data_patterns:
        if re.search(pattern, source_text, re.IGNORECASE):
            staged_data.append(name)

    spec["staged_data"] = staged_data

    # ---------------------------------------------------------
    # 11. CVEs mentioned (for future vulnerable software deployment)
    # ---------------------------------------------------------
    cves = sorted(set(re.findall(r"CVE-\d{4}-\d+", source_text)))
    if cves:
        spec["cves"] = cves

    # ---------------------------------------------------------
    # 12. Deployment notes
    # ---------------------------------------------------------
    if "Windows" in spec["platforms"] and "ldap" in seen_services:
        spec["deployment_notes"].append("Active Directory domain required")
    if "ESXi" in spec["platforms"]:
        spec["deployment_notes"].append("VMware ESXi hypervisor needed for VM targeting techniques")
    if any("C2" in str(c) or "c2" in str(c) for c in spec["network"]["c2_channels"]):
        spec["deployment_notes"].append("External C2 channel simulation needed")
    if spec["network"]["external_ips"]:
        spec["deployment_notes"].append(f"Block/simulate {len(spec['network']['external_ips'])} external IPs")

    # Count summary
    n_svc = len(spec["services"])
    n_plat = len(spec["platforms"])
    n_tools = len(spec["tools_required"])
    print(f"[IAC] Extracted: {n_plat} platforms, {n_svc} services, "
          f"{n_tools} tool requirements, {len(spec['accounts'])} account types")

    return spec


def render_iac_summary(spec: dict) -> str:
    """Render infrastructure spec as human-readable deployment guide."""
    lines = ["# Infrastructure Requirements for Adversary Emulation\n"]

    # Platforms
    lines.append("## Target Platforms")
    for platform, info in spec.get("platforms", {}).items():
        conf = info.get("confidence", "?")
        req = "REQUIRED" if info.get("required") else "recommended"
        lines.append(f"  - **{platform}** ({req}, {conf} confidence, "
                     f"{info.get('technique_count', 0)} techniques)")

    # Services
    lines.append("\n## Services Required")
    for svc in spec.get("services", []):
        lines.append(f"  - {svc['name']} ({svc['port']})"
                     f"{' on ' + svc['os'] if svc.get('os') else ''}")

    # Accounts
    if spec.get("accounts"):
        lines.append("\n## Account Types Needed")
        for acct in spec["accounts"]:
            lines.append(f"  - {acct['type'].replace('_', ' ').title()}")

    # Tools
    if spec.get("tools_required"):
        lines.append("\n## Adversary Tools (deploy on attacker host)")
        for tool in spec["tools_required"]:
            reqs = ", ".join(tool.get("requires", []))
            lines.append(f"  - {tool['tool']}"
                        f"{' (' + tool['os'] + ')' if tool.get('os') else ''}"
                        f": needs {reqs}")

    # Topology
    topo = spec.get("topology", {})
    if topo.get("hosts") or topo.get("segments"):
        lines.append("\n## Network Topology")
        if topo.get("perimeter"):
            lines.append("  Perimeter:")
            for p in topo["perimeter"]:
                lines.append(f"    - {p}")
        if topo.get("segments"):
            lines.append("  Segments:")
            for s in topo["segments"]:
                lines.append(f"    - {s}")
        if topo.get("hosts"):
            lines.append("  Hosts:")
            for h in topo["hosts"]:
                lines.append(f"    - {h}")

    # Kill Chain (deployment order)
    kc = spec.get("kill_chain", [])
    if kc:
        lines.append("\n## Deployment Order (Kill Chain)")
        for i, phase in enumerate(kc, 1):
            lines.append(f"  {i}. [{phase['phase']}] {phase['infrastructure']}")

    # Security Controls
    if spec.get("security_controls"):
        lines.append("\n## Security Controls to Deploy (detection testing)")
        for ctrl in spec["security_controls"]:
            lines.append(f"  - {ctrl}")

    # Data to Stage
    if spec.get("staged_data"):
        lines.append("\n## Data to Stage (bait for exfil testing)")
        for data in spec["staged_data"]:
            lines.append(f"  - {data}")

    # CVEs
    if spec.get("cves"):
        lines.append("\n## CVEs Referenced (deploy vulnerable versions)")
        for cve in spec["cves"]:
            lines.append(f"  - {cve}")

    # Network
    net = spec.get("network", {})
    if net.get("c2_channels") or net.get("external_ips"):
        lines.append("\n## Network/C2 Requirements")
        for c2 in net.get("c2_channels", []):
            lines.append(f"  - C2 channel: {c2}")
        if net.get("external_ips"):
            lines.append(f"  - {len(net['external_ips'])} external IPs to simulate/block")

    # Notes
    if spec.get("deployment_notes"):
        lines.append("\n## Deployment Notes")
        for note in spec["deployment_notes"]:
            lines.append(f"  - {note}")

    return "\n".join(lines)
