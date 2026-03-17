"""
nlp_model.py — Shared spaCy model singleton

All modules import from here instead of calling spacy.load() directly.
This ensures the 560MB en_core_web_lg model is loaded exactly once.
"""

import spacy
from functools import lru_cache


@lru_cache(maxsize=1)
def get_nlp():
    """Load en_core_web_lg exactly once, cached for process lifetime."""
    return spacy.load("en_core_web_lg")


# Module-level alias for backward compatibility
nlp = get_nlp()
