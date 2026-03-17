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
    # 7. Deployment notes
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

    # Network
    net = spec.get("network", {})
    if net.get("c2_channels") or net.get("external_ips"):
        lines.append("\n## Network Requirements")
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
