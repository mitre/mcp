"""
cti_text_extract.py - structural text extractors for the AE-library loader

Regex extractors the loader uses when it lowers an AE plan into a measuring
stick. Kept out of the loader so runtime code never has to reach into a dev
tool's private names. Structural only: no scenario-specific vocabulary.
"""

import re

# CIDR subnet
_CIDR_RE = re.compile(r"\b((?:\d{1,3}\.){3}\d{1,3}/\d{1,2})\b")

# Windows registry key (HKLM\..., HKCU\..., HKEY_..\..)
_REG_KEY_RE = re.compile(
    r"\b(HK(?:LM|CU|CR|U|CC)|HKEY_(?:LOCAL_MACHINE|CURRENT_USER|CLASSES_ROOT|USERS|CURRENT_CONFIG))\\[\\\w]+",
    re.IGNORECASE,
)
# Specific registry value names mentioned with surrounding context
_REG_VALNAME_RE = re.compile(r"\b(WDigest|MaxMpxCt|UseLogonCredential|Real-time protection)\b")

# File paths: Windows %ENV%\..., Windows C:\..., Unix-style /path/...
_WIN_PATH_RE = re.compile(r"%[A-Za-z]+%\\[\w.\\$-]+", re.IGNORECASE)
_WIN_ABS_PATH_RE = re.compile(r"[A-Z]:\\[\w\\$. -]+", re.IGNORECASE)
_UNIX_PATH_RE = re.compile(r"(?<![\w/])(/(?:srv|tmp|var|etc|usr|opt|home|root)/[\w/.\-]+)")


def extract_network_subnets(text: str) -> list[str]:
    """Explicit CIDR mentions plus /24 subnets derived from each IPv4
    host address found in the text.

    A report sometimes gives the subnet explicitly ("10.20.20.0/24") and
    sometimes only an individual host ("raremon (10.30.10.4)") -- the
    derivation step surfaces the subnet even when it is never spelled out.
    """
    out: set[str] = {m.group(1) for m in _CIDR_RE.finditer(text)}
    for ip_match in re.finditer(r"\b((\d{1,3})\.(\d{1,3})\.(\d{1,3})\.\d{1,3})\b", text):
        octs = ip_match.group(1).split(".")
        if len(octs) != 4:
            continue
        try:
            i0 = int(octs[0])
        except ValueError:
            continue
        # RFC1918 only; skip 0.x / 127.x / 169.254 etc.
        if i0 not in (10,) and not (
            i0 == 172 and 16 <= int(octs[1]) <= 31
        ) and not (i0 == 192 and int(octs[1]) == 168):
            continue
        cidr = f"{octs[0]}.{octs[1]}.{octs[2]}.0/24"
        out.add(cidr)
    return sorted(out)


def extract_file_paths(text: str) -> list[str]:
    out: set[str] = set()
    for r in (_WIN_PATH_RE, _WIN_ABS_PATH_RE, _UNIX_PATH_RE):
        for m in r.finditer(text):
            val = m.group(0).strip().rstrip(".,;:!)")
            if val and len(val) >= 4:
                out.add(val)
    return sorted(out)


def extract_registry_keys(text: str) -> list[str]:
    out: set[str] = set()
    for m in _REG_KEY_RE.finditer(text):
        out.add(m.group(0).rstrip(".,;:"))
    for m in _REG_VALNAME_RE.finditer(text):
        out.add(m.group(1))
    return sorted(out)
