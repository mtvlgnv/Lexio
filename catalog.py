"""
catalog.py — the in-app book catalog.

A curated set of public-domain books (built by scripts/build_catalog.py from
Project Gutenberg) that the iOS reading app lists and imports into a user's
library. Metadata lives in catalog_data/manifest.json; the full text of each
book lives in catalog_data/texts/<slug>.txt and is loaded lazily and cached.

Everything here is public domain — legal to redistribute. See CLAUDE.md.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_DATA = _ROOT / "catalog_data"
_MANIFEST = _DATA / "manifest.json"
_TEXTS = _DATA / "texts"

# Display names for the language codes used across Lexio.
LANG_NAMES: dict[str, str] = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "ru": "Russian", "ja": "Japanese",
    "zh": "Chinese", "ko": "Korean", "ar": "Arabic",
}


@lru_cache(maxsize=1)
def _manifest() -> list[dict]:
    if not _MANIFEST.exists():
        return []
    with _MANIFEST.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _by_slug() -> dict[str, dict]:
    return {b["slug"]: b for b in _manifest()}


def all_books(lang: str | None = None) -> list[dict]:
    """Catalog metadata (no text). Optionally filter by language code."""
    books = _manifest()
    if lang and lang != "all":
        books = [b for b in books if b["language"] == lang]
    return books


def languages() -> list[dict]:
    """Languages present in the catalog, with display names and counts."""
    counts: dict[str, int] = {}
    for b in _manifest():
        counts[b["language"]] = counts.get(b["language"], 0) + 1
    out = [
        {"code": code, "name": LANG_NAMES.get(code, code.upper()), "count": n}
        for code, n in counts.items()
    ]
    out.sort(key=lambda x: x["name"])
    return out


def get(slug: str) -> dict | None:
    """Metadata for one book, or None if unknown."""
    return _by_slug().get(slug)


@lru_cache(maxsize=64)
def text(slug: str) -> str | None:
    """Full cleaned text for one book, or None if missing."""
    if slug not in _by_slug():
        return None
    path = _TEXTS / f"{slug}.txt"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
