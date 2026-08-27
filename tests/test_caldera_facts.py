"""STIX bundle to CALDERA facts."""

from plugins.mcp.app.utilities.cti_caldera_facts import bundle_to_facts


def _bundle(*objects):
    return {"type": "bundle", "id": "bundle--1", "objects": list(objects)}


def test_dotted_host_name_becomes_an_fqdn_bare_name_does_not():
    facts = bundle_to_facts(_bundle(
        {"type": "infrastructure", "id": "infrastructure--1", "name": "mail.contoso.com"},
        {"type": "infrastructure", "id": "infrastructure--2", "name": "DC01"},
    ))
    by_trait = {f["trait"]: f["value"] for f in facts}
    assert by_trait["remote.host.fqdn"] == "mail.contoso.com"
    assert by_trait["remote.host.name"] == "DC01"


def test_ip_is_emitted_and_is_not_mistaken_for_an_fqdn():
    facts = bundle_to_facts(_bundle(
        {"type": "infrastructure", "id": "infrastructure--1",
         "name": "10.0.0.5", "x_cti_ip": "10.0.0.5"},
    ))
    traits = {f["trait"] for f in facts}
    assert "remote.host.ip" in traits
    assert "remote.host.fqdn" not in traits, "a dotted quad is not an fqdn"


def test_domain_account_and_local_account_get_different_traits():
    facts = bundle_to_facts(_bundle(
        {"type": "user-account", "id": "user-account--1",
         "user_id": "svc_backup", "x_cti_domain": "CONTOSO"},
        {"type": "user-account", "id": "user-account--2", "user_id": "localadmin"},
    ))
    by_value = {f["value"]: f["trait"] for f in facts}
    assert by_value["svc_backup"] == "domain.user.name"
    assert by_value["localadmin"] == "host.user.name"


def test_only_a_password_the_report_stated_is_emitted():
    facts = bundle_to_facts(_bundle(
        {"type": "user-account", "id": "user-account--1", "user_id": "a",
         "x_cti_domain": "D", "credential": "hunter2",
         "x_cti_password_provenance": "source"},
        {"type": "user-account", "id": "user-account--2", "user_id": "b",
         "x_cti_domain": "D", "credential": "REDACTED",
         "x_cti_password_provenance": "redacted"},
    ))
    passwords = [f["value"] for f in facts if f["trait"] == "domain.user.password"]
    assert passwords == ["hunter2"], "a redacted credential is not a usable fact"


def test_only_active_directory_identities_become_a_domain():
    facts = bundle_to_facts(_bundle(
        {"type": "identity", "id": "identity--1", "name": "contoso.com",
         "identity_class": "organization", "x_cti_domain_type": "active-directory"},
        {"type": "identity", "id": "identity--2", "name": "evil.example",
         "identity_class": "organization", "x_cti_domain_type": "dns-only"},
    ))
    domains = [f["value"] for f in facts if f["trait"] == "target.org.domain"]
    assert domains == ["contoso.com"]


def test_nothing_is_invented_from_an_empty_or_unrelated_bundle():
    assert bundle_to_facts(_bundle()) == []
    assert bundle_to_facts(_bundle(
        {"type": "malware", "id": "malware--1", "name": "BlackCat"},
        {"type": "attack-pattern", "id": "attack-pattern--1", "name": "T1078"},
    )) == []


def test_duplicate_facts_are_collapsed():
    facts = bundle_to_facts(_bundle(
        {"type": "infrastructure", "id": "infrastructure--1", "name": "DC01"},
        {"type": "infrastructure", "id": "infrastructure--2", "name": "DC01"},
    ))
    assert len(facts) == 1


def test_prose_descriptions_are_not_treated_as_hostnames():
    """Extractors surface phrases like this; they would expand into a
    command as prose and break it."""
    facts = bundle_to_facts(_bundle(
        {"type": "infrastructure", "id": "infrastructure--1",
         "name": "Internet-facing Microsoft Exchange server"},
        {"type": "infrastructure", "id": "infrastructure--2", "name": "EXCH01"},
    ))
    assert [f["value"] for f in facts] == ["EXCH01"]


def test_names_resolved_by_dns_dedupe_case_insensitively():
    facts = bundle_to_facts(_bundle(
        {"type": "identity", "id": "identity--1", "name": "CONTOSO",
         "identity_class": "organization", "x_cti_domain_type": "active-directory"},
        {"type": "identity", "id": "identity--2", "name": "contoso",
         "identity_class": "organization", "x_cti_domain_type": "active-directory"},
    ))
    assert [f["value"] for f in facts] == ["CONTOSO"], "first spelling wins"


def test_usernames_stay_case_sensitive():
    facts = bundle_to_facts(_bundle(
        {"type": "user-account", "id": "user-account--1", "user_id": "Administrator"},
        {"type": "user-account", "id": "user-account--2", "user_id": "administrator"},
    ))
    assert len(facts) == 2
