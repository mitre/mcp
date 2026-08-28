"""Map a stage 2 STIX bundle onto CALDERA facts.

CALDERA seeds an operation from a Source of facts. Without one an
operation runs on placeholder values, so this is what makes a run
grounded in the report rather than generic.

Trait names are the ones stockpile abilities actually reference, not
invented ones. Anything the bundle does not name is omitted; nothing is
synthesized to fill a gap.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Iterable, Optional

# Traits, by descending use across plugins/stockpile/data/abilities.
TRAIT_HOST_FQDN = "remote.host.fqdn"
TRAIT_HOST_NAME = "remote.host.name"
TRAIT_HOST_IP = "remote.host.ip"
TRAIT_DOMAIN_USER = "domain.user.name"
TRAIT_DOMAIN_PASSWORD = "domain.user.password"
TRAIT_HOST_USER = "host.user.name"
TRAIT_ORG_DOMAIN = "target.org.domain"

# Passwords are case-sensitive; usernames are treated as such too, since a
# report distinguishing Administrator from administrator may mean it.
_CASE_SENSITIVE = frozenset({
    TRAIT_DOMAIN_USER, TRAIT_HOST_USER, TRAIT_DOMAIN_PASSWORD,
})

_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")

# RFC 952/1123: letters, digits, hyphen and dot. Extractors also surface
# descriptions like "Internet-facing Exchange server", which expand into a
# command as prose and break it, so anything not name-shaped is dropped.
_HOSTNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}[A-Za-z0-9]$")


def _clean(value) -> str:
    return str(value or "").strip()


def _is_hostname(name: str) -> bool:
    return bool(_HOSTNAME.match(name))


def _is_fqdn(name: str) -> bool:
    """A dotted name that is not an address. Decides fqdn vs bare name."""
    return "." in name and not _IPV4.match(name)


def _host_facts(obj: dict) -> Iterable[tuple]:
    name = _clean(obj.get("name"))
    if name and _is_hostname(name):
        trait = TRAIT_HOST_FQDN if _is_fqdn(name) else TRAIT_HOST_NAME
        yield trait, name

    ip = _clean(obj.get("x_cti_ip"))
    if ip and _IPV4.match(ip):
        yield TRAIT_HOST_IP, ip


def _user_facts(obj: dict) -> Iterable[tuple]:
    username = _clean(obj.get("user_id")) or _clean(obj.get("display_name"))
    if not username:
        return

    # x_cti_domain is set only when the report tied the account to a domain.
    if _clean(obj.get("x_cti_domain")):
        yield TRAIT_DOMAIN_USER, username
    else:
        yield TRAIT_HOST_USER, username

    # Only a password the report actually stated. "redacted" and "absent"
    # provenance mean there is no usable value.
    if _clean(obj.get("x_cti_password_provenance")) == "source":
        password = _clean(obj.get("credential"))
        if password:
            yield TRAIT_DOMAIN_PASSWORD, password


def _domain_facts(obj: dict) -> Iterable[tuple]:
    """AD domains only. A dns-only identity is not somewhere to authenticate."""
    if _clean(obj.get("identity_class")) != "organization":
        return
    if _clean(obj.get("x_cti_domain_type")) != "active-directory":
        return
    name = _clean(obj.get("name"))
    if name and _is_hostname(name):
        yield TRAIT_ORG_DOMAIN, name


def is_routable(value: str) -> bool:
    """True for a publicly routable address.

    remote.host.ip is a live target: stockpile nmaps it and SMB-mounts it.
    A report names the attacker's C2 and other victims alongside the estate,
    so these are surfaced for review rather than seeded silently.

    is_global excludes private, loopback, link-local, CGNAT and reserved space
    in one predicate, and covers IPv6.
    """
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def routable_addresses(facts: list[dict]) -> list[str]:
    return [f["value"] for f in facts
            if f["trait"] == TRAIT_HOST_IP and is_routable(f["value"])]


def bundle_to_facts(bundle: dict) -> list[dict]:
    """Return ``[{trait, value}]``, deduplicated by trait and value.

    Hostnames and domains are compared case-insensitively because DNS is,
    so CONTOSO and contoso are one fact. The first spelling seen wins.
    """
    seen: set = set()
    facts: list[dict] = []

    handlers = {
        "infrastructure": _host_facts,
        "user-account": _user_facts,
        "identity": _domain_facts,
    }

    for obj in bundle.get("objects") or []:
        handler = handlers.get(obj.get("type"))
        if handler is None:
            continue
        for trait, value in handler(obj):
            # Usernames stay case-sensitive; names resolved by DNS do not.
            comparable = value if trait in _CASE_SENSITIVE else value.lower()
            key = (trait, comparable)
            if key in seen:
                continue
            seen.add(key)
            facts.append({"trait": trait, "value": value})

    return facts


def build_source(bundle: dict, name: str, source_id: Optional[str] = None):
    """Build a CALDERA Source from a bundle.

    Imported lazily: the mapping above is pure and testable without a
    running CALDERA, and only this adapter needs the core objects.
    """
    from app.objects.c_source import Source
    from app.objects.secondclass.c_fact import Fact, OriginType

    facts = [
        Fact(
            trait=f["trait"],
            value=f["value"],
            origin_type=OriginType.IMPORTED,
            source=name,
        )
        for f in bundle_to_facts(bundle)
    ]
    return Source(name=name, id=source_id or "", facts=facts, plugin="mcp")
