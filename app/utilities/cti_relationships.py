"""
cti_relationships.py — Unified Relationship Extraction & Classification

AUTHORITATIVE relationship logic for Stage 1 and Stage 2.

Key guarantees:
- Verbs are ONLY taken from observed text (never invented)
- One internal extraction path
- Deterministic role + direction enforcement
- Mandatory confidence and evidence
- Backward compatible with cti_pipeline_stage1.py
"""

import spacy, re
from functools import lru_cache
from pathlib import Path
from nltk.corpus import wordnet as wn

from plugins.mcp.app.utilities.cti_mitre_extract import cosine_sim
from plugins.mcp.app.utilities.cti_linguistics import normalize_behavior_text, canonicalize_relationship_endpoints

# ============================================================
# NLP MODEL (GLOBAL, SINGLE LOAD)
# ============================================================

nlp = spacy.load("en_core_web_lg")

# ============================================================
# VECTOR CACHE (PERFORMANCE CRITICAL)
# ============================================================

@lru_cache(maxsize=4096)
def vectorize(text: str):
    return nlp(text).vector

# ============================================================
# RELATIONSHIP CLASSES (OBSERVED VERBS ONLY)
# ============================================================

RELATIONSHIP_CLASSES = set()
MIN_REL_CONFIDENCE = 0.6
REL_REJECTIONS: list[dict] = []

# ============================================================
# STIX 2.1 relationship-type-ov LOADER (data-file driven, no static lists)
# ============================================================
#
# The normative STIX 2.1 `relationship-type-ov` vocabulary lives in
# `app/utilities/data/stix_open_vocabs.yml`. We load it once and use it
# as the ONLY admissible value set for SRO `relationship_type`. Raw
# extracted verbs are normalized into this vocab via WordNet synonym
# expansion + spaCy vector cosine similarity (threshold 0.6). When no
# vocab term reaches threshold the relationship is dropped rather than
# emitted with a non-spec verb.

_STIX_VOCAB_PATH = (
    Path(__file__).resolve().parent / "data" / "stix_open_vocabs.yml"
)


@lru_cache(maxsize=1)
def _stix_relationship_type_ov() -> tuple[str, ...]:
    """
    Return the STIX 2.1 `relationship_type_ov` tuple (data-driven).

    Cached. Falls back to an empty tuple on any I/O / parse failure —
    callers MUST treat an empty vocab as "drop everything" so the
    pipeline never emits non-spec verbs.
    """
    try:
        import yaml  # type: ignore
        with _STIX_VOCAB_PATH.open("r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        vocab = doc.get("relationship_type_ov") or []
        return tuple(str(v).strip().lower() for v in vocab if v)
    except Exception:
        return tuple()


@lru_cache(maxsize=4096)
def _normalize_verb_to_stix_vocab(verb_lemma: str) -> str | None:
    """
    Map an observed verb lemma to the closest STIX 2.1
    `relationship-type-ov` term via WordNet synset expansion + spaCy
    vector cosine similarity. Threshold 0.6. Returns None when no vocab
    term reaches threshold (callers MUST drop the relationship rather
    than emit a non-spec verb).

    Algorithm:
      1. Build the surface-form set for the observed verb: its lemma
         PLUS every WordNet synset lemma name (under-scores stripped).
      2. For every STIX vocab term, score it as
         max(cos(form_vec, term_vec)) over all forms.
      3. Return the highest-scoring term if score >= 0.6, else None.

    No static verb-to-STIX table. Vocab loads from
    `stix_open_vocabs.yml`. Synonyms come from WordNet.
    """
    if not verb_lemma:
        return None

    vocab = _stix_relationship_type_ov()
    if not vocab:
        return None

    lemma = verb_lemma.strip().lower()
    if not lemma:
        return None

    # Already a spec-vocab term — accept verbatim (handles infinitive
    # forms like "uses", "targets", etc. that already appear in text).
    if lemma in vocab:
        return lemma

    # Build surface-form set: observed lemma + WordNet synset lemmas.
    forms = {lemma}
    for syn in wn.synsets(lemma, pos=wn.VERB):
        for syn_lemma in syn.lemmas():
            name = syn_lemma.name().replace("_", " ").strip().lower()
            if name:
                forms.add(name)

    # For each STIX vocab term, score against every form. Because the
    # spec vocab includes hyphenated multi-word terms (e.g.
    # `exfiltrates-to`, `attributed-to`, `located-at`,
    # `communicates-with`) which have weak single-token vectors, we
    # ALSO score the head word of the term (the lexical anchor) and
    # its spaCy lemma so that `exfiltrate -> exfiltrates-to` and
    # `attribute -> attributed-to` resolve correctly.
    best_term, best_score = None, 0.0
    for term in vocab:
        term_keys = {term}
        head = term.split("-", 1)[0]
        if head and head != term:
            term_keys.add(head)
            head_doc = nlp(head)
            if head_doc and len(head_doc) > 0:
                head_lemma = head_doc[0].lemma_.lower()
                if head_lemma and head_lemma != head:
                    term_keys.add(head_lemma)
        for tk in term_keys:
            tk_vec = vectorize(tk)
            for form in forms:
                sim = cosine_sim(vectorize(form), tk_vec)
                if sim > best_score:
                    best_score = sim
                    best_term = term

    if best_term is not None and best_score >= 0.6:
        return best_term
    return None


def infer_relationship_intent(verb_lemma: str) -> str | None:
    """
    Legacy intent shim — now delegates to the STIX-vocab normalizer so
    callers continue to receive a spec-grade term (not an arbitrary
    WordNet lemma).
    """
    return _normalize_verb_to_stix_vocab(verb_lemma)

# ============================================================
# ENTITY ROLE INFERENCE (IR-GROUNDED)
# ============================================================

def infer_entity_roles(entity_name: str, ir: dict) -> set[str]:
    roles = set()
    if not entity_name:
        return roles

    name_l = entity_name.lower()

    for group, role in (
        ("threat_actors", "actor"),
        ("malware", "malware"),
        ("tools", "tool"),
        ("infrastructure", "infrastructure"),
        ("data", "data"),
    ):
        for ent in ir.get(group, []):
            if ent.get("name","").lower() == name_l:
                roles.add(role)
    # Explicit placeholder handling (text-grounded, not inferred)
    # '>' is from our inserted values in previous steps
    if name_l.startswith("<") and name_l.endswith(">"):
        return {"unknown"}
    # No inferred role is NOT invalid — it is unknown
    if not roles:
        return {"unknown"}
    return roles

# ============================================================
# BEHAVIOR NORMALIZATION + QUALIFICATION
# ============================================================

def qualify_behaviors(behaviors: list[dict]) -> list[dict]:
    qualified = []

    for b in behaviors:
        text = b.get("text") or b.get("description")
        if not text:
            continue

        doc = nlp(text)

        if not any(t.pos_ == "VERB" for t in doc):
            continue
        if not any(t.dep_ in ("dobj", "pobj") for t in doc):
            continue
        if any(t.text.lower() in {"we", "researchers", "analysts"} for t in doc):
            continue

        qualified.append(b)

    return qualified


def normalize_and_qualify_behaviors(ir: dict):
    normalized = []
    qualified = []

    for b in ir.get("behaviors", []):
        text = b.get("description") or b.get("text")
        if not text:
            continue

        doc = nlp(text)

        entry = {
        "description": text,
        "source": b.get("source", "unknown"),
        "confidence": b.get("confidence", 0.6),
        }

        verbs = [
            t for t in doc
            if t.pos_ == "VERB"
            and not is_reporter_or_analyst_verb(t.lemma_.lower())
        ]

        if not verbs:
            continue

        if not any(t.dep_ in ("dobj", "pobj", "attr") for t in doc):
            continue

        if any(t.text.lower() in {"we", "researchers", "analysts"} for t in doc):
            continue

        # Only keep behaviors that can plausibly drive CTI
        drives_cti = False

        # heuristic: must contain verb + object AND be >= 4 tokens
        if len(text.split()) >= 4:
            drives_cti = True

        if not drives_cti:
            continue

        # --------------------------------------------------
        # Reject deictic / placeholder object behaviors
        # --------------------------------------------------
        if any(t.pos_ == "PRON" for t in doc):
            continue
        normalized.append(entry)
        qualified.append(entry)

    return normalized, qualified

# ============================================================
# RELATIONSHIP CLASS MATCHING
# ============================================================

def match_relationship_class(token) -> str | None:
    """
    Return an observed verb lemma suitable for relationship use.

    Accepts:
    - spaCy Token (preferred)
    - str (already-extracted observed verb)

    Rejects:
    - Non-verbs
    - Aux / modal verbs
    - Short / non-alphabetic noise
    """

    # --------------------------------------------------
    # Case 1: spaCy Token
    # --------------------------------------------------
    if hasattr(token, "pos_"):
        if token.pos_ != "VERB":
            return None

        if token.tag_ in ("MD", "AUX"):
            return None

        lemma = token.lemma_.lower()

    # --------------------------------------------------
    # Case 2: already-extracted verb string
    # --------------------------------------------------
    elif isinstance(token, str):
        lemma = token.lower()

    # --------------------------------------------------
    # Case 3: unsupported input
    # --------------------------------------------------
    else:
        return None

    # --------------------------------------------------
    # Shared validation
    # --------------------------------------------------
    if not lemma.isalpha() or len(lemma) < 3:
        return None

    # observed verb ONLY — no mapping
    return lemma

# ============================================================
# ADMISSIBILITY + CONFIDENCE
# ============================================================

def relationship_allowed(src_roles, verb, tgt_roles, rel_class=None, explicit_joint=False):
    """
    Analyst-grade admissibility gate.

    Rules:
    - Observed verb only
    - Role-based, not intent-dependent
    - Prefer admitting low-confidence relationships over dropping defensible ones
    """

    # default source role
    if not src_roles:
        src_roles = {"actor"}

    if tgt_roles & {"infrastructure", "data"}:
        return True

    # actors may perform any observed action
    if "actor" in src_roles:
        return True

    # tools / malware may act when a verb exists
    if src_roles & {"tool", "malware"}:
        return True

    # Unknown targets allowed ONLY if semantically aligned with verb
    if tgt_roles == {"unknown"}:
        return True

    return False

def score_relationship(src, rel, tgt, sentence, source_context):
    """
    Evidence-based relationship confidence scoring.

    Scoring principles:
    - Reward explicit textual grounding
    - Reward structural clarity
    - Penalize weak or indirect context
    - NO semantic intent inference
    """

    score = 0.35 if source_context == "behavior" else 0.25

    sent = (sentence or "").lower()

    # Explicit uncertainty handling
    if tgt == "<unspecified>":
        return 0.45

    # Source context weighting
    if source_context == "behavior":
        score += 0.10
    elif source_context == "sentence":
        score += 0.05
    elif source_context == "llm":
        score -= 0.10

    # Explicit textual grounding
    if src.lower() in sent:
        score += 0.15

    if tgt.lower() in sent:
        score += 0.20

    # Structural richness heuristic
    if sentence and len(sentence.split()) >= 10:
        score += 0.10

    # Observed-text semantic coherence (no intent labels, no prototypes)
    try:
        rel_vec = vectorize(rel)
        sent_vec = vectorize(sentence)
        sim = cosine_sim(rel_vec, sent_vec)
        if sim > 0.40:
            score += min(sim * 0.20, 0.20)
    except Exception:
        pass

    return min(round(score, 2), 0.95)

# ============================================================
# CORE EXTRACTION (SINGLE AUTHORITY)
# ============================================================

def _resolve_subject_for_verb(tok, ir: dict) -> list[str]:
    """
    Resolve the actual sentence subject for a verb token, not the
    nearest-tool fallback.

    Resolution order (first hit wins):

      1. Walk the spaCy dependency tree from `tok` upward through
         conjunction / clausal-complement chains, collecting any
         `nsubj`/`nsubjpass` head whose surface form (lemma OR full
         subtree) matches a known IR entity name.

      2. If the dep-tree subject doesn't match any IR entity, scan
         `tok.sent.ents` for the closest preceding NER entity whose
         label is NOT `PRODUCT|TOOL`-shaped (filter out "Tool"-typed
         entities so we don't anchor on PsExec when the real subject
         is BlackCat / DEV-0504 / etc.). Match by IR entity-name
         containment so we resolve to a canonical IR name.

      3. If still no match, fall back to the closest preceding entity
         of ANY label that names an IR threat_actor / malware (the
         agent classes — never a tool, never an infrastructure).

    Returns a list of canonical IR entity names (lowercased
    name-match preserved as-is in the IR-cased form).
    """
    sentence = tok.sent
    sentence_l = sentence.text.lower()

    # Pre-compute name -> canonical-name maps per IR group so we never
    # invent a name.
    actor_names = [
        e["name"] for e in (ir.get("threat_actors") or [])
        if isinstance(e, dict) and e.get("name")
    ]
    malware_names = [
        e["name"] for e in (ir.get("malware") or [])
        if isinstance(e, dict) and e.get("name")
    ]
    tool_names = [
        e["name"] for e in (ir.get("tools") or [])
        if isinstance(e, dict) and e.get("name")
    ]

    agent_names = actor_names + malware_names + tool_names  # priority order
    agent_l = [n.lower() for n in agent_names]
    tool_names_l = {n.lower() for n in tool_names}

    def _match_phrase_to_agent(phrase: str) -> str | None:
        p = (phrase or "").strip().lower()
        if not p:
            return None
        # Exact / containment match (agent-name appears in phrase OR
        # vice-versa for short heads).
        for canon, low in zip(agent_names, agent_l):
            if not low:
                continue
            if low == p or low in p or p in low:
                return canon
        return None

    # ---- Step 1: walk the dependency tree to find nsubj ----
    cursor = tok
    visited = set()
    while cursor is not None and id(cursor) not in visited:
        visited.add(id(cursor))

        # Direct nsubj/nsubjpass child of the cursor verb
        for child in cursor.children:
            if child.dep_ in ("nsubj", "nsubjpass"):
                subj_phrase = " ".join(t.text for t in child.subtree).strip()
                match = _match_phrase_to_agent(subj_phrase)
                if match:
                    return [match]
                # Bare head text fallback
                match = _match_phrase_to_agent(child.text)
                if match:
                    return [match]

        # Climb to head for conjunctions / clausal complements
        if cursor.dep_ in ("conj", "xcomp", "ccomp", "advcl", "relcl"):
            cursor = cursor.head
            continue
        break

    # ---- Step 2: closest preceding NER entity that isn't a tool ----
    verb_idx = tok.i
    candidates = [
        ent for ent in sentence.ents
        if ent.end <= verb_idx
    ]
    # Closest first (rightmost preceding)
    candidates.sort(key=lambda e: e.end, reverse=True)
    for ent in candidates:
        ent_text_l = ent.text.strip().lower()
        if ent_text_l in tool_names_l:
            continue
        # spaCy `PRODUCT`/`ORG`/`PERSON`/`NORP` labels are all valid
        # agent labels here; we drop tool-typed entities by IR name
        # rather than by label so we don't depend on spaCy's tag table.
        match = _match_phrase_to_agent(ent.text)
        if match:
            return [match]

    # ---- Step 3: closest preceding IR-named agent in sentence text ----
    # Scan agent_names by token position in the sentence (left-to-right
    # along the original sentence string), keep those whose surface
    # form appears BEFORE the verb token's character offset.
    verb_char_start = tok.idx - sentence.start_char
    found_with_pos: list[tuple[int, str]] = []
    for canon, low in zip(agent_names, agent_l):
        if not low:
            continue
        pos = sentence_l.find(low)
        if 0 <= pos < verb_char_start:
            found_with_pos.append((pos, canon))
    if found_with_pos:
        # Rightmost preceding wins (closest to verb).
        found_with_pos.sort(key=lambda x: x[0], reverse=True)
        return [found_with_pos[0][1]]

    # No defensible subject — caller will reject.
    return []


def _extract_relationships_from_doc(doc, ir, source_label):
    results = []

    for tok in doc:
        rel_class_raw = match_relationship_class(tok)
        if not rel_class_raw:
            continue
        print(f"[REL][CANDIDATE] verb={tok.lemma_} sentence='{tok.sent.text}'")

        # Normalize the observed verb against STIX 2.1
        # relationship-type-ov via WordNet + spaCy vectors. Drop the
        # candidate if no spec-vocab term clears the 0.6 threshold —
        # we never emit a non-spec relationship_type.
        rel_class = _normalize_verb_to_stix_vocab(rel_class_raw)
        if not rel_class:
            REL_REJECTIONS.append({
                "reason": "verb_not_in_stix_vocab",
                "verb": rel_class_raw,
                "evidence": tok.sent.text,
                "source_context": source_label,
            })
            print(
                f"[REL][REJECTED][NON_STIX_VERB] verb={rel_class_raw} "
                f"sentence='{tok.sent.text}'"
            )
            continue

        sentence = tok.sent.text
        sentence_l = sentence.lower()

        # ---------- SUBJECT RESOLUTION ----------
        # Use the dependency-tree walk + preceding-NER fallback so we
        # bind the verb to the ACTUAL sentence subject instead of
        # anchoring on the nearest-tool name match (the bug that made
        # every SRO use PsExec as source_ref).
        sources = _resolve_subject_for_verb(tok, ir)

        if not sources:
            REL_REJECTIONS.append({
                "reason": "no_source_in_sentence",
                "verb": tok.lemma_.lower(),
                "rel_class": rel_class,
                "target": None,
                "evidence": sentence,
                "source_context": source_label,
            })
            print(
                f"[REL][REJECTED][NO_SOURCE] verb={tok.lemma_.lower()} "
                f"rel_class={rel_class} sentence='{sentence}'"
            )
            continue

        targets = [
            ent["name"]
            for g in ("malware", "tools", "infrastructure")
            for ent in ir.get(g, [])
            if ent.get("name") and ent["name"].lower() in sentence_l
        ]

        if not targets:
            recovered = []

            # 1) direct objects / attributes / prepositional objects attached to the verb
            for c in tok.children:
                if c.dep_ in ("dobj", "pobj", "attr", "dative"):
                    phrase = " ".join(t.text for t in c.subtree).strip().lower()
                    if phrase:
                        recovered.append(phrase)

            # 2) if still nothing, try noun chunks governed by this verb only
            if not recovered:
                for ch in tok.subtree:
                    if hasattr(ch, "pos_") and ch.pos_ in ("NOUN", "PROPN"):
                        phrase = " ".join(t.text for t in ch.subtree).strip().lower()
                        if phrase:
                            recovered.append(phrase)

            # dedupe while preserving order
            seen = set()
            recovered = [x for x in recovered if not (x in seen or seen.add(x))]

            if recovered:
                targets = [normalize_behavior_text(t) for t in recovered]
                # Filter recovered targets to noun-headed phrases only
                filtered = []
                for phrase in targets:
                    doc_t = nlp(phrase)
                    if any(t.pos_ in ("NOUN", "PROPN") for t in doc_t):
                        filtered.append(phrase)

                if not filtered:
                    REL_REJECTIONS.append({
                        "reason": "recovered_target_not_nominal",
                        "verb": tok.lemma_.lower(),
                        "candidate_targets": targets,
                        "evidence": sentence,
                        "source_context": source_label,
                    })
                    continue

                targets = filtered
            else:
                REL_REJECTIONS.append({
                    "reason": "no_target_recovered",
                    "verb": tok.lemma_.lower(),
                    "rel_class": rel_class,
                    "target": None,
                    "evidence": sentence,
                    "source_context": source_label,
                })
                continue

        for src in sources:
            src_roles = infer_entity_roles(src, ir)
            for tgt in targets:
                tgt_roles = infer_entity_roles(tgt, ir) or {"unknown"}
                print(
                    f"[REL][CHECK] src={src} roles={src_roles} "
                    f"verb={rel_class} tgt={tgt} tgt_roles={tgt_roles}"
                )
                if not relationship_allowed(
                    src_roles,
                    tok.lemma_.lower(),
                    tgt_roles,
                    rel_class=rel_class,
                    explicit_joint=(src.lower() in sentence_l and tgt.lower() in sentence_l)
                ):
                    REL_REJECTIONS.append({
                        "reason": "relationship_allowed_failed",
                        "source": src,
                        "verb": tok.lemma_.lower(),
                        "rel_class": rel_class,
                        "target": tgt,
                        "sentence": sentence,
                        "source_context": source_label,
                    })
                    print(
                        f"[REL][REJECTED] src={src} verb={rel_class} tgt={tgt}"
                    )
                    continue
                # Removing and make seperate
                # # Attempt protocol infrastructure materialization (non-destructive)
                # for tok_child in tok.children:
                #     maybe_emit_protocol_infrastructure(tok_child, ir, sentence)
                conf = score_relationship(src, rel_class, tgt, sentence, source_label)
                threshold = MIN_REL_CONFIDENCE
                if source_label in ("behavior", "behavior_dependency_recovery"):
                    threshold = 0.45

                status = None
                resolution_status = None
                if conf < threshold:
                    status = "abstract-nominal"
                    resolution_status = "pending"

                candidate = {
                    "source": src,
                    "relationship": rel_class,
                    "target": tgt,
                    "confidence": conf,
                    "evidence": sentence,
                    "source_context": source_label,
                }

                if status:
                    candidate["status"] = status
                if resolution_status:
                    candidate["x_cti_resolution_status"] = resolution_status

                if not is_actionable_relationship(candidate):
                    REL_REJECTIONS.append({
                        "reason": "non_actionable_relationship",
                        "candidate": candidate,
                    })
                    continue

                results.append(candidate)

    return results

# ============================================================
# PUBLIC APIs
# ============================================================

async def semantic_relationships(text: str, ir: dict) -> list[dict]:
    MAX_CHARS = int(nlp.max_length * 0.8)
    results = []

    for i in range(0, len(text), MAX_CHARS):
        doc = nlp(text[i:i + MAX_CHARS])
        results.extend(_extract_relationships_from_doc(doc, ir, "sentence"))

    print(f"[REL] semantic={len(results)}")
    return results

def relationships_from_behaviors(behaviors, ir):
    results = []
    last_agent = None

    # Resolve implicit tool agent once (non-brittle)
    tool_agent = None
    tools = ir.get("tools") or []
    if len(tools) == 1 and isinstance(tools[0], dict):
        tool_agent = tools[0].get("name")

    for b in behaviors:
        text = b.get("description") or b.get("text")
        if not text:
            continue
        # Split on newlines to prevent cross-line verb/target binding
        chunks = [c.strip() for c in re.split(r"(?:\r?\n)+", text) if c.strip()]

        docs = [nlp(c) for c in chunks] if chunks else [nlp(text)]

        before = len(results)
        for doc in docs:
            results.extend(_extract_relationships_from_doc(doc, ir, "behavior"))
        after = len(results)

        # Update agent memory when explicitly present
        tas = ir.get("threat_actors") or []
        tools = ir.get("tools") or []

        if len(tools) == 1:
            last_agent = tools[0].get("name")
        elif len(tas) == 1:
            last_agent = tas[0].get("name")

        # --------------------------------------------------
        # Dynamic recovery using dependency structure
        # --------------------------------------------------
        if after == before:
            # Try recovery per chunk; stop on first valid recovery
            for doc in docs:
                verb_tok = None
                verb = None
                obj = None
                obj_token = None

                # 1️⃣ Extract observed verb (never invented)
                for tok in doc:
                    if tok.pos_ == "VERB" and any(c.dep_ in ("dobj", "pobj", "attr") for c in tok.children):
                        verb_tok = tok
                        verb = tok.lemma_.lower()
                        break

                # 2️⃣ Extract syntactic object / pobj / attr
                for tok in doc:
                    if tok.pos_ != "VERB":
                        continue

                    for c in tok.children:
                        if c.dep_ in ("pobj", "dobj", "attr"):
                            obj_token = c
                            obj = " ".join(t.text for t in c.subtree).strip().lower()
                            break

                    if obj:
                        break

                if not verb or not obj:
                    continue

                # Normalize the observed verb to STIX 2.1 vocab — drop
                # if no spec term clears the 0.6 threshold.
                stix_verb = _normalize_verb_to_stix_vocab(verb)
                if not stix_verb:
                    REL_REJECTIONS.append({
                        "reason": "verb_not_in_stix_vocab",
                        "verb": verb,
                        "evidence": doc.text.strip(),
                        "source_context": "behavior-recovery",
                    })
                    continue

                # 3️⃣ Subject resolution — prefer the dep-tree nsubj,
                # fall back to single-tool/threat-actor ONLY when the
                # sentence has no defensible subject. This kills the
                # "every SRO source_ref == PsExec" anchoring bug.
                source = None
                if verb_tok is not None:
                    resolved = _resolve_subject_for_verb(verb_tok, ir)
                    if resolved:
                        source = resolved[0]

                if not source:
                    source = tool_agent
                if not source:
                    tas = ir.get("threat_actors") or []
                    if len(tas) == 1 and isinstance(tas[0], dict):
                        source = tas[0].get("name")

                if not source:
                    continue

                candidate = {
                    "source": source,
                    "relationship": stix_verb,
                    "target": obj,
                    "confidence": 0.55,
                    "evidence": [doc.text.strip()],
                    "source_context": "behavior-recovery",
                    "status": "abstract-nominal",
                }

                if not is_actionable_relationship(candidate):
                    REL_REJECTIONS.append({
                        "reason": "non_actionable_relationship",
                        "candidate": candidate,
                    })
                    continue

                results.append(candidate)
        results.extend(materialize_configuration_infrastructure(ir, b))
    print(f"[REL] behavior={len(results)}")
    return results

async def extract_all_relationships(text, ir, qualified):
    """
    Single authority aggregator.
    Runs relationship extraction on QUALIFIED behaviors only,
    canonicalizes endpoints, then dedupes with evidence hygiene.
    """
    start_rej_idx = len(REL_REJECTIONS)
    rel_text = "\n".join(
        (b.get("description") or b.get("text") or "").strip()
        for b in qualified
        if isinstance(b, dict)
    ).strip()

    rel_sem = await semantic_relationships(rel_text, ir) if rel_text else []
    rel_beh = relationships_from_behaviors(qualified, ir) if qualified else []
    seq_edges = emit_ir_sequence_edges(qualified)
    combined = canonicalize_relationship_endpoints(
        ir,
        rel_sem + rel_beh + seq_edges
    )

    print(
        f"[REL] semantic={len(rel_sem)} "
        f"behavior={len(rel_beh)} "
        f"combined_pre_dedup={len(combined)}"
    )

    deduped = dedup_relationships(combined)

    # Summarize only rejections generated during this call
    new_rejections = REL_REJECTIONS[start_rej_idx:]

    buckets = {}
    for r in new_rejections:
        buckets[r.get("reason", "unknown")] = buckets.get(r.get("reason", "unknown"), 0) + 1

    print(f"[REL][REJECT_SUMMARY] {buckets}")
    print(f"[REL] final_deduped={len(deduped)}")
    return deduped

def dedup_relationships(rels: list[dict]) -> list[dict]:
    """
    Deduplicate by (source, relationship, target).
    Merges evidence into a set and slightly boosts confidence on independent corroboration.
    """
    dedup: dict[tuple[str, str, str], dict] = {}

    for r in rels or []:
        src = r.get("source")
        rel = r.get("relationship")
        tgt = r.get("target")
        if not (src and rel and tgt):
            continue

        status = r.get("status", "concrete")
        key = (src, rel, tgt, status)
        ev = r.get("evidence")

        # Normalize evidence to iterable of strings
        if isinstance(ev, list):
            ev_items = [e for e in ev if isinstance(e, str)]
        elif isinstance(ev, str):
            ev_items = [ev]
        else:
            ev_items = []

        if key not in dedup:
            rr = dict(r)
            rr["evidence"] = set(ev_items)
            dedup[key] = rr
            continue

        for e in ev_items:
            if e not in dedup[key]["evidence"]:
                dedup[key]["evidence"].add(e)
                try:
                    dedup[key]["confidence"] = min(
                        float(dedup[key].get("confidence", 0.0)) + 0.05,
                        0.95
                    )
                except Exception:
                    pass

    # convert evidence set back to list to keep JSON-safe behavior later
    out = []
    for v in dedup.values():
        vv = dict(v)
        if isinstance(vv.get("evidence"), set):
            vv["evidence"] = sorted(vv["evidence"])
        out.append(vv)

    return out

# ============================================================
# THREAT ACTOR INFERENCE
# ============================================================

def infer_threat_actors(ir: dict) -> list[dict]:
    if not ir.get("relationships"):
        return []

    malicious = {
        e["name"].lower()
        for g in ("malware", "tools", "infrastructure")
        for e in ir.get(g, [])
        if e.get("name")
    }

    sources = {
        r["source"].lower()
        for r in ir["relationships"]
        if r["target"].lower() in malicious
    }

    return [
        a for a in ir.get("threat_actors", [])
        if a.get("name","").lower() in sources
    ]

# ==============================================================
# Helper Functions
# ==============================================================

def is_reporter_or_analyst_verb(verb: str) -> bool:
    """
    Returns True if the verb represents analyst / reporter speech,
    cognition, or perception rather than an adversary action.

    Dynamic, WordNet-backed, non-brittle.
    """
    if not verb:
        return False

    for syn in wn.synsets(verb, pos=wn.VERB):
        lex = syn.lexname()

        # Analyst / reporter classes
        if lex in {
            "verb.communication",   # report, describe, note
            "verb.cognition",       # analyze, identify, assess
            "verb.perception",      # observe, notice
        }:
            return True

    return False

def is_abstract_noun(noun_phrase: str) -> bool:
    """
    Returns True if the noun phrase represents an abstract concept
    rather than a concrete CTI-relevant entity.

    Uses WordNet hypernyms + spaCy POS.
    """
    if not noun_phrase:
        return False

    doc = nlp(noun_phrase)

    # Require at least one NOUN/PROPN
    nouns = [t for t in doc if t.pos_ in ("NOUN", "PROPN")]
    if not nouns:
        return True

    # Check WordNet abstraction
    for t in nouns:
        for syn in wn.synsets(t.lemma_, pos=wn.NOUN):
            # Abstract concepts in WordNet
            if syn.lexname() in {
                "noun.cognition",     # idea, suspicion, belief
                "noun.communication",# report, statement
                "noun.attribute",    # factor, property
                "noun.state",        # condition, status
                "noun.feeling",      # concern, fear
            }:
                return True

    return False

def is_actionable_relationship(rel: dict) -> bool:
    """
    Analyst-equivalent, dynamic actionability gate.

    Drops relationships a senior analyst would ignore,
    using linguistic ontologies instead of static lists.
    """

    verb = (rel.get("relationship") or "").lower()
    tgt = (rel.get("target") or "").lower()
    ctx = rel.get("source_context")

    # 1️⃣ Analyst / reporter verbs (dynamic)
    if is_reporter_or_analyst_verb(verb):
        return False

    # 2️⃣ Abstract noun targets (dynamic)
    if is_abstract_noun(tgt):
        rel["x_cti_resolution_status"] = "pending"
        rel["x_cti_target_kind"] = "abstract"
        return True

    # 3️⃣ Must originate from defensible context
    # if ctx not in {"behavior", "sentence"}:
    #     return False

    # 4️⃣ Evidence must be non-trivial
    ev = rel.get("evidence")
    if not ev or (isinstance(ev, str) and len(ev.split()) < 5):
        return False

    return True

def is_temporal_modifier(tok):
    for pos in (wn.ADV, wn.ADP):
        for syn in wn.synsets(tok.lemma_, pos=pos):
            if "time" in syn.definition():
                return True
    return False

def emit_ir_sequence_edges(behaviors: list[dict]) -> list[dict]:
    """
    Create behavior→behavior sequencing edges
    based ONLY on IR order and explicit temporal modifiers
    already attached to behaviors.

    No sentence scanning. No inference.
    """
    seq_edges = []

    for i in range(len(behaviors) - 1):
        b1 = behaviors[i]
        b2 = behaviors[i + 1]

        # Require explicit sequencing metadata only
        seq_meta = b1.get("x_cti_sequence")
        if not seq_meta:
            continue

        edge = {
            "source": b1.get("description"),
            "relationship": "precedes",
            "target": b2.get("description"),
            "confidence": min(
                b1.get("confidence", 0.5),
                b2.get("confidence", 0.5),
            ),
            "evidence": b1.get("evidence"),
            "source_context": "behavior",
            "x_cti_sequence": seq_meta,
        }

        seq_edges.append(edge)

    return seq_edges

def materialize_configuration_infrastructure(ir: dict, behavior: dict) -> list[dict]:
    """
    Convert explicit behavior configuration into
    infrastructure nodes + relationships.

    No extraction. No guessing.
    """
    out = []
    cfg = behavior.get("x_cti_configuration")
    if not cfg:
        return out

    src = None
    tas = ir.get("threat_actors") or []
    tools = ir.get("tools") or []

    if len(tools) == 1:
        src = tools[0].get("name")
    elif len(tas) == 1:
        src = tas[0].get("name")

    if not src:
        return out

    for k, v in cfg.items():
        infra_name = f"{v}"

        ir.setdefault("infrastructure", []).append({
            "name": infra_name,
            "type": k,
        })

        out.append({
            "source": src,
            "relationship": "uses",
            "target": infra_name,
            "confidence": behavior.get("confidence", 0.6),
            "evidence": behavior.get("evidence"),
            "source_context": "behavior",
        })

    return out
