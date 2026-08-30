"""
nlp_model.py - Shared spaCy model singleton

All modules import from here instead of calling spacy.load() directly.
This ensures the 425MB en_core_web_lg model is loaded exactly once.
"""

import threading

import spacy
from functools import lru_cache

# lru_cache is not single-flight: stage 1 runs a thread pool, and without
# this every worker that raced the first call would load its own 425MB copy.
_LOAD_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def _load():
    return spacy.load("en_core_web_lg")


def get_nlp():
    """Load en_core_web_lg exactly once, cached for process lifetime."""
    with _LOAD_LOCK:
        return _load()
