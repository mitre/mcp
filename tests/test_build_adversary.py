"""Tests for cti_pipeline_build_adversary in mcp_server.py.

No CALDERA instance required: the abilities and agents REST reads are the
only external calls, and both are stubbed.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from plugins.mcp import mcp_server as srv  # noqa: E402


def _bundle(technique_ids, actor=None):
    objects = []
    if actor:
        objects.append({"type": "threat-actor", "name": actor})
    for tid in technique_ids:
        objects.append({
            "type": "attack-pattern",
            "name": tid,
            "external_references": [
                {"source_name": "mitre-attack", "external_id": tid}
            ],
        })
    return {"type": "bundle", "objects": objects}


def _ability(ability_id, technique_id, platforms=("windows",)):
    return {
        "ability_id": ability_id,
        "technique_id": technique_id,
        "executors": [{"platform": p} for p in platforms],
    }


@pytest.fixture
def stub_caldera(monkeypatch):
    """Stub the two REST reads build_adversary makes."""
    state = {"abilities": [], "agents": []}

    class _Resp:
        def __init__(self, payload):
            self.status = 200
            self._payload = payload

        async def text(self):
            return json.dumps(self._payload)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _Session:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def get(self, url, **k):
            key = "agents" if url.rstrip("/").endswith("agents") else "abilities"
            return _Resp(state[key])

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", _Session)
    monkeypatch.setattr(srv, "_caldera_base_url", lambda: "http://stub/api/v2/")
    monkeypatch.setattr(srv, "_caldera_headers", lambda: {})
    return state


def _write(tmp_path, bundle):
    p = tmp_path / "report.stix.json"
    p.write_text(json.dumps(bundle), encoding="utf-8")
    return str(p)


@pytest.mark.asyncio
async def test_matches_abilities_by_technique(stub_caldera, tmp_path):
    stub_caldera["abilities"] = [
        _ability("ab-1", "T1059.001"),
        _ability("ab-2", "T1486"),
        _ability("ab-3", "T9999"),
    ]
    path = _write(tmp_path, _bundle(["T1059.001", "T1486"]))

    r = await srv.build_adversary(path, platforms=["windows"])

    assert sorted(r["matched"]) == ["ab-1", "ab-2"]
    assert r["unmatched_techniques"] == []
    assert r["ability_count"] == 2
    assert r["committed"] is False


@pytest.mark.asyncio
async def test_reports_techniques_with_no_ability(stub_caldera, tmp_path):
    stub_caldera["abilities"] = [_ability("ab-1", "T1486")]
    path = _write(tmp_path, _bundle(["T1486", "T1490", "T1489"]))

    r = await srv.build_adversary(path, platforms=["windows"])

    assert r["matched"] == ["ab-1"]
    assert r["unmatched_techniques"] == ["T1489", "T1490"]


@pytest.mark.asyncio
async def test_parent_and_sub_techniques_match(stub_caldera, tmp_path):
    # The report names the parent, the stockpile carries the sub-technique.
    stub_caldera["abilities"] = [_ability("ab-1", "T1059.003")]
    path = _write(tmp_path, _bundle(["T1059"]))

    r = await srv.build_adversary(path, platforms=["windows"])

    assert r["matched"] == ["ab-1"]
    assert r["unmatched_techniques"] == []


@pytest.mark.asyncio
async def test_platform_excluded_is_separate_from_unmatched(stub_caldera, tmp_path):
    stub_caldera["abilities"] = [_ability("ab-linux", "T1486", platforms=("linux",))]
    path = _write(tmp_path, _bundle(["T1486"]))

    r = await srv.build_adversary(path, platforms=["windows"])

    assert r["matched"] == []
    assert r["platform_excluded"] == ["T1486"]
    assert r["unmatched_techniques"] == []


@pytest.mark.asyncio
async def test_no_agents_and_no_platforms_is_an_error(stub_caldera, tmp_path):
    stub_caldera["abilities"] = [_ability("ab-1", "T1486")]
    stub_caldera["agents"] = []
    path = _write(tmp_path, _bundle(["T1486"]))

    r = await srv.build_adversary(path)

    assert "error" in r
    assert "no agents" in r["error"].lower()


@pytest.mark.asyncio
async def test_platforms_default_to_live_agents(stub_caldera, tmp_path):
    stub_caldera["agents"] = [{"paw": "abc", "platform": "linux"}]
    stub_caldera["abilities"] = [
        _ability("ab-win", "T1486", platforms=("windows",)),
        _ability("ab-nix", "T1486", platforms=("linux",)),
    ]
    path = _write(tmp_path, _bundle(["T1486"]))

    r = await srv.build_adversary(path)

    assert r["platforms"] == ["linux"]
    assert r["matched"] == ["ab-nix"]


@pytest.mark.asyncio
async def test_name_comes_from_the_threat_actor(stub_caldera, tmp_path):
    stub_caldera["abilities"] = [_ability("ab-1", "T1486")]
    path = _write(tmp_path, _bundle(["T1486"], actor="BlackCat"))

    r = await srv.build_adversary(path, platforms=["windows"])

    assert r["name"] == "BlackCat"


@pytest.mark.asyncio
async def test_name_falls_back_to_the_file_stem(stub_caldera, tmp_path):
    stub_caldera["abilities"] = [_ability("ab-1", "T1486")]
    path = _write(tmp_path, _bundle(["T1486"]))

    r = await srv.build_adversary(path, platforms=["windows"])

    assert r["name"] == "report"


@pytest.mark.asyncio
async def test_bundle_without_techniques_is_an_error(stub_caldera, tmp_path):
    path = _write(tmp_path, {"type": "bundle", "objects": []})

    r = await srv.build_adversary(path, platforms=["windows"])

    assert "error" in r
    assert "no ATT&CK techniques" in r["error"]


@pytest.mark.asyncio
async def test_missing_bundle_is_an_error(stub_caldera, tmp_path):
    r = await srv.build_adversary(str(tmp_path / "nope.stix.json"), platforms=["windows"])
    assert "error" in r


@pytest.mark.asyncio
async def test_caps_abilities_per_technique_and_reports_the_total(stub_caldera, tmp_path):
    # A single technique can have 90+ implementations; an uncapped adversary
    # runs for hours.
    stub_caldera["abilities"] = [_ability(f"ab-{i:02d}", "T1112") for i in range(10)]
    path = _write(tmp_path, _bundle(["T1112"]))

    r = await srv.build_adversary(path, platforms=["windows"], max_per_technique=3)

    assert len(r["matched"]) == 3
    assert r["ability_count_available"] == 10
    assert r["unmatched_techniques"] == []


@pytest.mark.asyncio
async def test_selection_is_deterministic(stub_caldera, tmp_path):
    stub_caldera["abilities"] = [_ability(f"ab-{i:02d}", "T1112") for i in range(10)]
    path = _write(tmp_path, _bundle(["T1112"]))

    first = await srv.build_adversary(path, platforms=["windows"], max_per_technique=3)
    second = await srv.build_adversary(path, platforms=["windows"], max_per_technique=3)

    assert first["matched"] == second["matched"]


@pytest.mark.asyncio
async def test_sub_technique_in_report_matches_parent_ability(stub_caldera, tmp_path):
    # Modern CTI cites sub-techniques while much of the stockpile is tagged
    # with the bare parent. Losing this direction reports the stockpile as
    # having no coverage when it does.
    stub_caldera["abilities"] = [_ability("ab-1", "T1059")]
    path = _write(tmp_path, _bundle(["T1059.001"]))

    r = await srv.build_adversary(path, platforms=["windows"])

    assert r["matched"] == ["ab-1"]
    assert r["unmatched_techniques"] == []


@pytest.mark.asyncio
async def test_abilities_run_in_kill_chain_order(stub_caldera, tmp_path):
    # atomic_ordering is executed top to bottom. Impact must not precede the
    # persistence and credential access it depends on.
    stub_caldera["abilities"] = [
        _ability("z-impact", "T1486"),       # impact
        _ability("a-persist", "T1547.001"),  # persistence
        _ability("m-creds", "T1003.001"),    # credential-access
    ]
    path = _write(tmp_path, _bundle(["T1486", "T1547.001", "T1003.001"]))

    r = await srv.build_adversary(path, platforms=["windows"])

    assert r["matched"] == ["a-persist", "m-creds", "z-impact"], (
        "ordering must come from the ATT&CK kill chain, not ability id"
    )


@pytest.mark.asyncio
async def test_ordering_survives_calderas_own_tactic_vocabulary(stub_caldera, tmp_path):
    # CALDERA's three most common tactic values (multiple, stealth,
    # defense-impairment) have no ATT&CK counterpart, so ranking on `tactic`
    # dropped 43 percent of the stockpile into an unordered tail.
    impact = _ability("a-impact", "T1486")
    impact["tactic"] = "impact"
    stealth = _ability("z-stealth", "T1070.001")
    stealth["tactic"] = "stealth"
    stub_caldera["abilities"] = [impact, stealth]
    path = _write(tmp_path, _bundle(["T1486", "T1070.001"]))

    r = await srv.build_adversary(path, platforms=["windows"])

    assert r["matched"] == ["z-stealth", "a-impact"], (
        "defense-evasion must precede impact regardless of CALDERA tactic names"
    )


@pytest.mark.asyncio
async def test_sibling_sub_techniques_do_not_match(stub_caldera, tmp_path):
    # T1059.001 is PowerShell and T1059.003 is the Windows command shell.
    # Folding them together would run the wrong technique.
    stub_caldera["abilities"] = [_ability("ab-cmd", "T1059.003")]
    path = _write(tmp_path, _bundle(["T1059.001"]))

    r = await srv.build_adversary(path, platforms=["windows"])

    assert r["matched"] == []
    assert r["unmatched_techniques"] == ["T1059.001"]


@pytest.mark.asyncio
async def test_cap_is_per_technique_not_per_first_match(stub_caldera, tmp_path):
    # A bundle naming a parent and two of its children must not let one child
    # consume the whole budget and starve the other.
    stub_caldera["abilities"] = [
        _ability(f"{tid}-{i}", tid)
        for tid in ("T1059.001", "T1059.003")
        for i in range(5)
    ]
    path = _write(tmp_path, _bundle(["T1059", "T1059.001", "T1059.003"]))

    r = await srv.build_adversary(path, platforms=["windows"], max_per_technique=3)

    assert any(a.startswith("T1059.001") for a in r["matched"])
    assert any(a.startswith("T1059.003") for a in r["matched"])
    assert r["unmatched_techniques"] == []
