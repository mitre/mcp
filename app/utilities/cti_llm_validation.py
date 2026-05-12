"""Small validation helpers used by CTI LLM extraction tests."""

from __future__ import annotations

import json
import re
from typing import Any


def _strip_json_fence(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_json_array(raw: str) -> list[dict[str, Any]] | None:
    """Parse an LLM-returned JSON array, tolerating markdown fences."""
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except Exception:
        return None
    if not isinstance(parsed, list):
        return None
    return parsed


def _quote_exists_in_text(quote: str, text: str) -> bool:
    """Return True when a quote is exact or has strong token overlap."""
    if not quote or not text:
        return False
    quote_low = quote.lower().strip()
    text_low = text.lower()
    if quote_low in text_low:
        return True

    quote_tokens = set(re.findall(r"[a-z0-9]{3,}", quote_low))
    text_tokens = set(re.findall(r"[a-z0-9]{3,}", text_low))
    if not quote_tokens:
        return False
    overlap = len(quote_tokens & text_tokens) / len(quote_tokens)
    return overlap >= 0.60
