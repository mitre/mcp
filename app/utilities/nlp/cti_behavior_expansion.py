"""
NLP Layer 2 — Nominalized / Implicit Behavior Recovery

Purpose:
- Recover operational behaviors expressed as noun phrases
- NEVER invent verbs
- NEVER promote to qualified behaviors
- Emit low-confidence behavior candidates only
"""

import spacy
from nltk.corpus import wordnet as wn

nlp = spacy.load("en_core_web_lg")


def recover_nominalized_behaviors(text: str) -> list[dict]:
    """
    Returns LOW-CONFIDENCE behavior candidates inferred from
    noun-phrase constructions.

    Output format matches IR["behaviors"] entries.
    """
    results = []
    doc = nlp(text)

    for chunk in doc.noun_chunks:
        head = chunk.root

        # --------------------------------------------
        # Structural gate 1: noun must be deverbal
        # --------------------------------------------
        synsets = wn.synsets(head.lemma_, pos=wn.NOUN)
        if not synsets:
            continue

        # Require verb origin (deverbal noun)
        has_verb_origin = any(
            wn.synsets(syn.lemmas()[0].name(), pos=wn.VERB)
            for syn in synsets
        )
        if not has_verb_origin:
            continue

        # --------------------------------------------
        # Structural gate 2: operational context
        # --------------------------------------------
        # Require prepositional attachment or object
        if not any(
            c.dep_ in ("prep", "pobj", "compound")
            for c in head.children
        ):
            continue

        phrase = chunk.text.strip()
        if len(phrase.split()) < 2:
            continue

        results.append({
            "description": phrase,
            "source": "nlp-layer2",
            "confidence": 0.35,   # intentionally low
            "recovered_from": "noun_chunk"
        })

    return results
