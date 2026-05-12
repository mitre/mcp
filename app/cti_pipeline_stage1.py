#!/usr/bin/env python3
"""
Phase 1 — CTI → Intermediate Representation (IR)

PURPOSE
-------
This module implements **Stage 1 execution only**:
    raw CTI → cleaned text → high-fidelity Intermediate Representation (IR)

It is intentionally:
    • Non-interactive
    • Deterministic
    • Parallelized (process-level)
    • Side-effect isolated per file

All orchestration, CLI flags, and pipeline routing
live in **cti_ingest_svc.py**.

DESIGN GUARANTEES
-----------------
• Each CTI document is processed in complete isolation
• No shared mutable state between workers
• spaCy + NLP models are loaded per worker
• Failures do not corrupt other files
• Output is always JSON-safe and resumable
"""

import json
import asyncio
import time
import os
import shutil
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# =============================================================
# Core Utilities
# =============================================================

from plugins.mcp.app.utilities.cti_raw_cleaner import clean_raw_directory
from plugins.mcp.app.utilities.cti_parsing import extract_ir, render_ir_summary
from plugins.mcp.app.utilities.cti_mitre_extract import extract_mitre_techniques, convert_sets
from plugins.mcp.app.utilities.cti_taxonomy_loader import build_normalized_attack_patterns
from plugins.mcp.app.utilities.cti_entity_validator import validate_entities, repair_entities

from plugins.mcp.app.utilities.cti_relationships import (
    normalize_and_qualify_behaviors,
    extract_all_relationships,
    REL_REJECTIONS,
)

from plugins.mcp.app.utilities.cti_linguistics import extract_dynamic_techniques, extract_commands, extract_hashes
from plugins.mcp.app.utilities.cti_extract_users import extract_users
from plugins.mcp.app.utilities.cti_extract_hosts import (
    extract_hosts,
    hosts_to_infrastructure_entries,
)
from plugins.mcp.app.utilities.cti_extract_domains import extract_domains
from plugins.mcp.app.utilities.cti_extract_software import extract_software
from plugins.mcp.app.utilities.cti_extract_services import (
    extract_services,
    services_to_infrastructure_entries,
)
from plugins.mcp.app.utilities.cti_ae_library_loader import (
    _extract_file_paths as extract_file_paths,
    _extract_registry as extract_registry_keys,
    _extract_subnets as extract_network_subnets,
)
from plugins.mcp.app.utilities.cti_technique_grounding import (
    ground_techniques,
    detect_platforms,
    filter_techniques_by_platform,
    collapse_parent_techniques,
)
from plugins.mcp.app.utilities.llm_client import get_llm_provenance


# =============================================================
# NLP Enhancement Layers
# =============================================================

from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import clean_ir_nlp_layer1
from plugins.mcp.app.utilities.nlp.cti_semantic_enrichment import clean_ir_nlp_layer2
from plugins.mcp.app.utilities.nlp.cti_behavior_expansion import recover_nominalized_behaviors

# =============================================================
# Directory Constants
# =============================================================

RAW_ROOT_DIR = "raw"
RAW_UPLOADS_DIR = "uploads"
RAW_PROCESSED_DIR = "processed"

CLEAN_DIR_NAME  = "clean"
OUTPUTS_IR_DIR  = "outputs_ir"
IMAGES_DIR_NAME = "images"


def _preload_thread_shared_nlp_resources():
    """Load lazy NLTK corpora before Stage 1 worker threads touch them."""
    try:
        from nltk.corpus import stopwords, wordnet  # type: ignore

        wordnet.ensure_loaded()
        wordnet.synsets("network")
        stopwords.words("english")
    except Exception as e:
        print(f"[WARN] NLTK pre-load skipped: {e}")

# =============================================================
# Directory Setup
# =============================================================

def ensure_dirs(base_dir: Path):
    """
    Create and return all directories required for Stage 1.

    Returns:
        (raw_dir, clean_dir, outputs_dir, images_dir)
    """
    raw_root      = base_dir / RAW_ROOT_DIR
    raw_uploads   = raw_root / RAW_UPLOADS_DIR
    raw_processed = raw_root / RAW_PROCESSED_DIR

    clean_dir = base_dir / CLEAN_DIR_NAME
    outputs   = base_dir / OUTPUTS_IR_DIR
    images    = base_dir / IMAGES_DIR_NAME

    for d in (raw_uploads, raw_processed, clean_dir, outputs, images):
        d.mkdir(parents=True, exist_ok=True)

    return raw_uploads, raw_processed, clean_dir, outputs, images

# =============================================================
# Stage 1.1 — Raw → Clean
# =============================================================

def step_raw_to_clean(base_dir: Path):
    """
    Convert raw CTI sources into normalized text.

    • HTML → extracted prose
    • PDF  → pdftotext
    • TXT  → copied
    • Images → copied

    No NLP occurs here.
    """
    raw_uploads, _, clean_dir, _, images_dir = ensure_dirs(base_dir)
    clean_raw_directory(base_dir, raw_uploads, clean_dir, images_dir)


def move_raw_to_processed(raw_path: Path, processed_dir: Path):
    target = processed_dir / raw_path.name
    if target.exists():
        return
    raw_path.rename(target)

# =============================================================
# Stage 1.2 — Clean → IR (PARALLEL)
# =============================================================

def step_parse_to_ir(base_dir: Path, stop_after: str | None = None):
    """
    Process all cleaned TXT files into IR + relationships + MITRE.

    Parallelism:
        • One OS process per file
        • Each worker loads its own NLP models
        • No shared state
    """
    start_time = time.perf_counter()
    _, _, clean_dir, outputs, _ = ensure_dirs(base_dir)



    ir_dir    = outputs / "debug_ir"
    final_dir = outputs / "complete"

    ir_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    files = list(clean_dir.glob("*.txt"))
    if not files:
        print("[!] No clean files found.")
        return
    if os.cpu_count() > 2:
        workers = max(1, (os.cpu_count() or 4) - 2)
    else:
        workers = 1
    _preload_thread_shared_nlp_resources()

    # Stage1 work is LLM/IO-bound, not CPU-bound: each file makes
    # remote calls to the AIP gateway, downloads embeddings, reads
    # taxonomy data, etc. Use ThreadPoolExecutor instead of
    # ProcessPoolExecutor so we don't fork-from-a-multithreaded
    # FastMCP process (which deadlocks the workers — they inherit
    # the FastMCP reader-thread locks but not the thread, and any
    # acquisition blocks forever). Threads share the GIL but
    # release it on every IO call, so the LLM round-trips overlap
    # cleanly. The original print message keeps the same shape so
    # operators don't see a behaviour change in the log.
    from concurrent.futures import ThreadPoolExecutor as _Executor
    print(f"[+] Stage1 starting: {len(files)} files | {workers} workers")

    # --------------------------------------------------
    # Submit ONE FILE PER PROCESS (no asyncio here)
    # --------------------------------------------------
    with _Executor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                process_one_file_sync,
                path,
                ir_dir,
                final_dir,
                stop_after,
            ): path
            for path in files
        }
        raw_uploads, raw_processed, _, _, _ = ensure_dirs(base_dir)
        for fut in as_completed(futures):
            clean_path = futures[fut]
            raw_path = None
            for p in raw_uploads.iterdir():
                if p.is_file() and p.stem == clean_path.stem:
                    raw_path = p
                    break
            try:
                fut.result()
                print(f"[OK] {clean_path.name}")

                # MOVE RAW INPUT ONLY AFTER SUCCESS
                if raw_path and raw_path.exists():
                    move_raw_to_processed(raw_path, raw_processed)

            except Exception as e:
                print(f"[ERR] {clean_path.name}: {e}")

    elapsed = time.perf_counter() - start_time
    print(f"\n[STAGE1] completed in {elapsed:.2f}s")

# =============================================================
# Per-File Pipeline
# =============================================================

async def process_file(
        path: Path,
        ir_dir: Path,
        final_dir: Path,
        stop_after: str | None,
    ):
    """
    Full Stage-1 pipeline for a single CTI document.

    Steps:
        1. IR extraction / resume
        2. NLP Layer 1 cleanup
        3. Behavior normalization & qualification
        4. Relationship extraction
        5. Entity validation
        6. MITRE ATT&CK mapping
        7. Final JSON + analyst summary output
    """
    REL_REJECTIONS.clear()
    print(f"\n[*] Processing {path.name}")

    text = path.read_text(errors="ignore")

    # ---------------------------------------------------------
    # 1. IR extraction
    # ---------------------------------------------------------
    ir = await load_or_extract_ir(path, text, ir_dir)
    if stop_after == "ir":
        return

    # ---------------------------------------------------------
    # 2. NLP Layer 1
    # ---------------------------------------------------------
    pre_beh = len(ir.get("behaviors", []))
    ir = clean_ir_nlp_layer1(ir, text)

    recovered = recover_nominalized_behaviors(text)
    if recovered:
        seen = {(b.get("verb"), b.get("object")) for b in ir["behaviors"]}
        for b in recovered:
            key = (b.get("verb"), b.get("object"))
            if key not in seen:
                ir["behaviors"].append(b)
                seen.add(key)

    if len(ir["behaviors"]) < pre_beh:
        raise RuntimeError("NLP Layer 1 removed behaviors (forbidden)")

    # ---------------------------------------------------------
    # 3. Behavior qualification
    # ---------------------------------------------------------
    normalized, qualified = normalize_and_qualify_behaviors(ir)
    ir["behaviors"] = normalized
    ir["qualified_behaviors"] = qualified

    high_conf = [b for b in qualified if b.get("confidence", 0) >= 0.5]
    low_conf  = [b for b in qualified if b.get("confidence", 0) < 0.5]

    # ---------------------------------------------------------
    # 4. Relationships
    # ---------------------------------------------------------
    raw_relationships = await extract_all_relationships(
        text, ir, high_conf
    ) or []
    ir["relationships"] = rag_safe_relationships(raw_relationships)
    ir["low_confidence_behaviors"] = low_conf

    # ---------------------------------------------------------
    # Commands Extraction (Linguistic)
    # ---------------------------------------------------------

    commands = extract_commands(text)
    if commands:
        for m in ir.get("malware", []):
            if m.get("name", "").lower() in text.lower():
                _merge_commands(m, commands)

        for t in ir.get("tools", []):
            if t.get("name", "").lower() in text.lower():
                _merge_commands(t, commands)

    # ---------------------------------------------------------
    # Hash Extraction (File Observables)
    # ---------------------------------------------------------
    hashes = extract_hashes(text)
    if hashes:
        if hashes:
            ir.setdefault("hashes", [])
            seen = {(h["hash_type"], h["hash"]) for h in ir["hashes"]}
            for h in hashes:
                key = (h["hash_type"], h["hash"])
                if key not in seen:
                    ir["hashes"].append(h)

    # ---------------------------------------------------------
    # User-account Extraction (AE-plan tables + inline prose)
    # ---------------------------------------------------------
    ir.setdefault("user_accounts", [])
    users = extract_users(text)
    if users:
        seen_users = {(u["username"].lower(), (u.get("domain") or "").lower())
                      for u in ir["user_accounts"]}
        for u in users:
            key = (u["username"].lower(), (u.get("domain") or "").lower())
            if key not in seen_users:
                ir["user_accounts"].append(u)
                seen_users.add(key)

    # ---------------------------------------------------------
    # Software + Version Extraction (AE-plan tooling tables +
    # filename-with-extension hits + ATT&CK-gated bare tokens)
    #
    # Distinct from ir["tools"]: ir["tools"] stays scoped to
    # ATT&CK-known offensive software, while ir["software"] is the
    # broader observed-software list -- INCLUDING versions and
    # non-ATT&CK entries -- needed by the range plugin's LLM deploy
    # step to pre-stage matching binaries via ansible.
    #
    # Pure ontology-driven: ATT&CK name_index for admission, OSV.dev
    # + nvdlib for optional external validation (gated behind
    # use_external_apis=False here; CI/unit tests stay offline).
    # ---------------------------------------------------------
    ir.setdefault("software", [])
    try:
        # Load the ATT&CK taxonomy lazily so software classification can
        # tag each candidate with attack_id / software_kind. The full
        # taxonomy is loaded again below for the MITRE technique pass
        # (step 6); both calls share the same on-disk bundle but the
        # extra parse is cheap relative to the rest of Stage 1.
        try:
            from plugins.mcp.app.utilities.cti_taxonomy_loader import load_mitre_taxonomy as _ldtax
            _sw_taxonomy = _ldtax()
        except Exception as _e:
            print(f"[SOFTWARE-EXTRACT][WARN] taxonomy unavailable: {_e}")
            _sw_taxonomy = None
        sw_entries = extract_software(text, taxonomy=_sw_taxonomy,
                                      use_external_apis=False)
    except Exception as e:
        print(f"[SOFTWARE-EXTRACT][WARN] {e}")
        sw_entries = []
    if sw_entries:
        seen_sw = {
            (s.get("name", "").lower(), (s.get("version") or "").lower())
            for s in ir["software"]
        }
        for s in sw_entries:
            key = (s["name"].lower(), (s.get("version") or "").lower())
            if key in seen_sw:
                continue
            ir["software"].append(s)
            seen_sw.add(key)
        print(f"[SOFTWARE-EXTRACT] added {len(sw_entries)} software entries")

    # ---------------------------------------------------------
    # Named-Host + IP Extraction (AE-plan tables + freeform prose)
    #
    # Recovers structured named hosts -- hostname/IP/role/OS -- which
    # the LLM IR step routinely flattens to generic "Internet-facing
    # RDP server" infrastructure entries. Pure ontology-driven: spaCy
    # NER, IPv4 regex, RFC 1123 hostnames, STIX infra-type-ov role
    # vocab + ATT&CK technique-name hints. No hostname->role tables.
    # ---------------------------------------------------------
    ir.setdefault("infrastructure", [])
    try:
        # Reuse the spaCy pipeline already loaded by cti_linguistics
        # (loaded once per worker process) for PROPN-aware hostname
        # candidate ranking. Fall back to regex-only if unavailable.
        try:
            from plugins.mcp.app.utilities.cti_linguistics import nlp as _nlp
        except Exception:
            _nlp = None
        named_hosts = extract_hosts(text, nlp=_nlp)
    except Exception as e:
        print(f"[HOST-EXTRACT][WARN] {e}")
        named_hosts = []
    if named_hosts:
        new_entries = hosts_to_infrastructure_entries(named_hosts)
        # Dedup by (hostname-lower, ip) against any existing infra entries.
        seen_infra = set()
        for inf in ir["infrastructure"]:
            if isinstance(inf, dict):
                key = (
                    (inf.get("name") or "").strip().lower(),
                    (inf.get("ip") or "").strip(),
                )
                seen_infra.add(key)
        for e in new_entries:
            key = (e["name"].lower(), e.get("ip", ""))
            if key in seen_infra:
                continue
            ir["infrastructure"].append(e)
            seen_infra.add(key)
        print(f"[HOST-EXTRACT] added {len(new_entries)} named hosts")

    # ---------------------------------------------------------
    # Service / Application Extraction (NEW: cti_extract_services)
    #
    # CTI reports name application-level services (Active Directory,
    # RDP, SMB, SQL Server, Exchange, KVM, NetBNMBackup, ...) that
    # downstream range provisioning needs to spin up. The new
    # extractor admits each candidate ONLY when one of these
    # ontology sources backs it:
    #   * IANA service registry (Python stdlib socket / /etc/services)
    #   * MITRE ATT&CK data-source vocabulary + technique-name
    #     phrase harvesting (Server Message Block, Remote Desktop
    #     Protocol, ...)
    # Each service is added to ir["services"] AND mirrored into
    # ir["infrastructure"] so stage2 emits a STIX infrastructure SDO.
    # ---------------------------------------------------------
    ir.setdefault("services", [])
    try:
        # Reuse taxonomy loaded above for the software pass.
        services = extract_services(text, taxonomy=_sw_taxonomy)
    except Exception as e:
        print(f"[SERVICE-EXTRACT][WARN] {e}")
        services = []
    if services:
        seen_services = {
            (s.get("name") or "").strip().lower()
            for s in ir["services"]
        }
        for s in services:
            key = (s.get("name") or "").strip().lower()
            if key in seen_services:
                continue
            ir["services"].append(s)
            seen_services.add(key)
        # Mirror into infrastructure[] so the stage2 builder
        # produces STIX `infrastructure` SDOs.
        svc_infra_entries = services_to_infrastructure_entries(services)
        seen_infra = {
            ((inf.get("name") or "").strip().lower(),
             (inf.get("ip") or "").strip())
            for inf in ir.get("infrastructure", [])
            if isinstance(inf, dict)
        }
        for e in svc_infra_entries:
            key = (e["name"].lower(), e.get("ip", ""))
            if key in seen_infra:
                continue
            ir["infrastructure"].append(e)
            seen_infra.add(key)
        print(f"[SERVICE-EXTRACT] added {len(services)} services "
              f"({len(svc_infra_entries)} infra entries)")

    # ---------------------------------------------------------
    # 5. Entity validation
    # ---------------------------------------------------------
    ir = await validate_entities(ir, destructive=False)
    ir = repair_entities(ir)

    # ---------------------------------------------------------
    # 6. MITRE ATT&CK
    # ---------------------------------------------------------
    techniques, lookup = build_normalized_attack_patterns()
    ir = clean_ir_nlp_layer2(ir, {"attack_patterns": techniques})

    ling = await extract_dynamic_techniques(
        text,
        techniques,
        ir.get("qualified_behaviors", []),
        limit=25,
    )

    mitre = extract_mitre_techniques(
        text,
        qualified,
        techniques,
        lookup,
    )

    # ---------------------------------------------------------
    # 6.5 Explicit-anchor technique grounding (NEW)
    #
    # Walk a set of STRUCTURAL ANCHORS (binary names, system
    # commands, narrative phrases) and resolve each to an ATT&CK
    # technique via the loaded taxonomy. No hardcoded T-id table:
    # each anchor's resolver-key is a technique-NAME fragment that
    # we look up against attack_id_index at runtime. Adds the
    # canonical Windows TTPs (PowerShell, LSASS, vssadmin, mstsc,
    # net.exe, mimikatz, ...) that the vector-based MITRE pass
    # routinely misses, and prefers non-revoked + exact-name
    # matches so we don't pick deprecated IDs (T1086 over
    # T1059.001).
    # ---------------------------------------------------------
    try:
        grounded = ground_techniques(text, taxonomy=_sw_taxonomy)
    except Exception as e:
        print(f"[TECHNIQUE-GROUND][WARN] {e}")
        grounded = []
    print(f"[TECHNIQUE-GROUND] grounded={len(grounded)} techniques from "
          f"structural anchors")

    seen = set()
    merged = []
    for t in ir.get("attack_patterns", []) + ling + mitre + grounded:
        if isinstance(t, dict) and t.get("id") and t["id"] not in seen:
            seen.add(t["id"])
            merged.append(t)

    # ---------------------------------------------------------
    # 6.6 Platform-attestation filter
    #
    # Drop techniques whose `x_mitre_platforms` doesn't overlap
    # the platform set attested in the source text. Stops
    # macOS-only / Linux-only techniques from polluting a
    # Windows-only CTI report. Platform vocabulary itself comes
    # from ATT&CK's `x_mitre_platforms` walks.
    # ---------------------------------------------------------
    try:
        attested = detect_platforms(text, taxonomy=_sw_taxonomy)
        if attested:
            before = len(merged)
            merged = filter_techniques_by_platform(merged, attested)
            print(f"[TECHNIQUE-FILTER] attested={sorted(attested)} "
                  f"kept={len(merged)} dropped={before - len(merged)}")
    except Exception as e:
        print(f"[TECHNIQUE-FILTER][WARN] {e}")

    # Parent-sub collapsing: keep T1059.001 over T1059 when both
    # appear -- ATT&CK consumers cite the most-specific reference.
    try:
        before = len(merged)
        merged = collapse_parent_techniques(merged)
        if before > len(merged):
            print(f"[TECHNIQUE-COLLAPSE] dropped {before - len(merged)} "
                  f"parents superseded by sub-techniques")
    except Exception as e:
        print(f"[TECHNIQUE-COLLAPSE][WARN] {e}")

    ir["attack_patterns"] = merged

    # ---------------------------------------------------------
    # 6b. Domain Extraction (AD topology signal)
    #
    # Pulls Windows AD / DNS domain names out of the cleaned prose so
    # downstream range deployment can provision a DC and join VMs.
    # Ontology-grounded: regex + spaCy ORG NER, gated by ATT&CK
    # technique IDs whose canonical names imply AD (T1003.006, T1558.*,
    # T1078.002, T1069.002, T1087.002, T1018, T1482, T1484, T1098.007,
    # T1207, T1556.001, T1550.002/3). No hardcoded CTI->domain map.
    # ---------------------------------------------------------
    ir.setdefault("domains", [])
    try:
        ap_ids = [
            ap.get("id") for ap in ir.get("attack_patterns", [])
            if isinstance(ap, dict) and ap.get("id")
        ]
        domains = extract_domains(text, attack_pattern_ids=ap_ids, nlp=None)
    except Exception as e:
        print(f"[DOMAIN-EXTRACT][WARN] {e}")
        domains = []
    if domains:
        seen_domains = {
            (d.get("name") or "").lower() for d in ir["domains"]
        }
        for d in domains:
            key = (d.get("name") or "").lower()
            # Allow multiple synthetic entries only if they have non-empty
            # signal sets that differ (defensive — shouldn't happen).
            if key and key in seen_domains:
                continue
            ir["domains"].append(d)
            if key:
                seen_domains.add(key)
        print(f"[DOMAIN-EXTRACT] added {len(domains)} domain entries")

    # ---------------------------------------------------------
    # 6c. Observable Surface Extraction
    #
    # Reuse the generic AE-library parsers for first-class observables
    # that matter to range fidelity: CIDR subnets, filesystem paths,
    # and Windows registry keys/values. These helpers are structural
    # regex extractors, not scenario-specific lists; Stage 2 turns the
    # resulting IR fields into STIX SCOs.
    # ---------------------------------------------------------
    observable_extractors = (
        ("network_subnets", extract_network_subnets),
        ("file_paths", extract_file_paths),
        ("registry_keys", extract_registry_keys),
    )
    for field, extractor in observable_extractors:
        ir.setdefault(field, [])
        try:
            values = extractor(text)
        except Exception as e:
            print(f"[OBSERVABLE-EXTRACT][WARN] {field}: {e}")
            values = []
        if not values:
            continue
        seen = {str(v).strip().lower() for v in ir[field] if str(v).strip()}
        added = 0
        for value in values:
            sval = str(value).strip()
            if not sval:
                continue
            key = sval.lower()
            if key in seen:
                continue
            ir[field].append(sval)
            seen.add(key)
            added += 1
        if added:
            print(f"[OBSERVABLE-EXTRACT] added {added} {field}")

    # ---------------------------------------------------------
    # 7. Output
    # ---------------------------------------------------------
    final = convert_sets(ir)
    final["provenance"] = ir.get("provenance")
    (final_dir / f"{path.stem}.json").write_text(
        json.dumps(final, indent=2),
        encoding="utf-8",
    )

    (final_dir / f"{path.stem}.txt").write_text(
        render_ir_summary(final),
        encoding="utf-8",
    )

# =============================================================
# Worker Entry Point (SYNC)
# =============================================================

def process_one_file_sync(path, ir_dir, final_dir, stop_after):
    """
    ProcessPoolExecutor-safe entry point.

    This function:
        • Runs in its own OS process
        • Loads NLP models locally
        • Executes the async pipeline via asyncio.run()
    """

    # Load spaCy per worker (MANDATORY)
    import spacy
    if not spacy.util.is_package("en_core_web_lg"):
        pass

    asyncio.run(process_file(path, ir_dir, final_dir, stop_after))

# =============================================================
# IR Resume / Extraction Helper
# =============================================================

async def load_or_extract_ir(path: Path, text: str, ir_dir: Path) -> dict:
    """
    Load cached IR if present; otherwise extract fresh IR.

    Guarantees:
        • Deterministic resume
        • JSON-safe output
    """
    ir_path = ir_dir / f"{path.stem}.ir-only.json"

    if ir_path.exists():
        with ir_path.open("r", encoding="utf-8") as f:
            cached_ir = json.load(f)

        cached_prov = cached_ir.get("provenance")
        current_prov = get_llm_provenance(profile="cti")

        if cached_prov == current_prov:
            print(f"[SKIP] IR up-to-date: {ir_path.name}")
            return cached_ir

        print(f"[REGEN] IR provenance changed: {ir_path.name}")

    ir = await extract_ir(text)
    ir = convert_sets(ir)
    ir["provenance"] = get_llm_provenance(profile="cti")
    ir_path.write_text(json.dumps(ir, indent=2), encoding="utf-8")
    (ir_dir / f"{path.stem}.ir-only.txt").write_text(
        render_ir_summary(ir),
        encoding="utf-8",
    )

    print(f"[IR] Extracted {path.stem}")
    return ir

def _merge_commands(entity, commands):
    existing = {c["command"] for c in entity.get("x_cti_commands", [])}
    for c in commands:
        if c["command"] not in existing:
            entity.setdefault("x_cti_commands", []).append(c)

def rag_safe_relationships(rels: list[dict], min_conf: float = 0.55) -> list[dict]:
    """
    Filter relationships for RAG suitability.

    Constraints:
      • confidence ≥ min_conf
      • source_context ∈ {behavior, sentence}
    """
    return [
        r for r in rels
        if r.get("confidence", 0.0) >= min_conf
        and r.get("source_context") in {"behavior", "sentence"}
    ]

def prepare_raw_uploads(base_dir: Path, selected: list[dict]):
    uploads = base_dir / "raw" / "uploads"
    inbox = base_dir / "raw" / "inbox"
    processed = base_dir / "raw" / "processed"
    SUPPORTED_EXTS = {".html", ".htm", ".pdf", ".txt", ".md"}


    uploads.mkdir(parents=True, exist_ok=True)

    for item in selected:
        name = item["name"]
        location = item["location"]

        src_root = inbox if location == "inbox" else processed
        src = src_root / name

        if not src.exists():
            continue

        if src.is_file():
            _copy_if_needed(src, uploads / src.name)

        elif src.is_dir():
            for f in src.rglob("*"):
                if f.suffix.lower() in SUPPORTED_EXTS:
                    _copy_if_needed(f, uploads / f.name)

def _copy_if_needed(src: Path, dst: Path):
    if dst.exists():
        return
    shutil.copy2(src, dst)
