"""
Human-readable STIX bundle report generator.
Used by Phase 2 to produce <stem>.stix.txt.

The goal is to give analysts a simple overview of:
- Entities (malware, tools, actors, infra, TTPs)
- Relationships
- Object counts
- Bundle metadata
"""

import datetime


def render_section(title: str, lines: list) -> str:
    if not lines:
        return f"{title}:\n  (none)\n"
    out = [f"{title}:"]
    for line in lines:
        out.append(f"  - {line}")
    return "\n".join(out) + "\n"


def render_stix_report(bundle: dict, ir_name: str) -> str:
    objects = bundle.get("objects", [])
    now = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")

    malware = []
    tools = []
    actors = []
    infra = []
    ttp = []
    rels = []

    for o in objects:
        t = o.get("type")

        if t == "malware":
            malware.append(f"{o.get('name')}  ({o.get('id')})")
        elif t == "tool":
            tools.append(f"{o.get('name')}  ({o.get('id')})")
        elif t == "threat-actor":
            actors.append(f"{o.get('name')}  ({o.get('id')})")
        elif t == "infrastructure":
            infra.append(f"{o.get('name')}  ({o.get('id')})")
        elif t == "attack-pattern":
            ttp.append(f"{o.get('name')}  ({o.get('id')})")
        elif t == "relationship":
            rels.append(
                f"{o.get('source_ref')} --[{o.get('relationship_type')}]→ {o.get('target_ref')}"
            )

    out = []
    out.append("=" * 72)
    out.append("STIX 2.1 CONVERSION REPORT")
    out.append("=" * 72)
    out.append(f"Generated: {now}")
    out.append(f"Source IR File: {ir_name}")
    out.append(f"Bundle ID: {bundle.get('id')}")
    out.append(f"Total STIX Objects: {len(objects)}")
    out.append("")

    out.append(render_section("Malware", malware))
    out.append(render_section("Tools", tools))
    out.append(render_section("Threat Actors", actors))
    out.append(render_section("Infrastructure", infra))
    out.append(render_section("Attack Patterns (TTPs)", ttp))
    out.append(render_section("Relationships", rels))

    out.append("=" * 72)
    out.append("END OF REPORT")
    out.append("=" * 72)

    return "\n".join(out)
