#!/usr/bin/env python3
"""
build_catalog.py — download a curated set of public-domain books from Project
Gutenberg, strip the PG boilerplate, and write a catalog the Lexio backend can
serve as JSON.

Why a curated seed (not a live API/scrape)?
  - Quality: hand-picked, recognizable classics across the languages Lexio
    supports — ideal reading material for language learners.
  - Legality: everything here is public domain on Project Gutenberg.
  - Robustness: no fragile runtime dependency on a third-party API. We download
    once at build/deploy time and serve static files thereafter.

Run:  python scripts/build_catalog.py
Output (next to the repo root):
  catalog_data/manifest.json        # list of book metadata (no text)
  catalog_data/texts/<slug>.txt     # cleaned full text, one file per book

Entries that fail to download or clean are skipped and reported; the manifest
only ever contains books we actually have text for.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "catalog_data"
TEXT_DIR = OUT_DIR / "texts"

UA = "LexioCatalogBuilder/1.0 (+https://lexio.site)"

# ─────────────────────────────────────────────────────────────────────────────
# Curated seed. `gid` is the Project Gutenberg ebook id.
# `lang` matches Lexio's language codes (see ios/.../Models/Language.swift).
# Keep titles/authors in the work's own language where natural.
# ─────────────────────────────────────────────────────────────────────────────
SEED: list[dict] = [
    # English
    {"gid": 1342,  "lang": "en", "title": "Pride and Prejudice",            "author": "Jane Austen",            "year": "1813"},
    {"gid": 1661,  "lang": "en", "title": "The Adventures of Sherlock Holmes","author": "Arthur Conan Doyle",   "year": "1892"},
    {"gid": 84,    "lang": "en", "title": "Frankenstein",                   "author": "Mary Shelley",           "year": "1818"},
    {"gid": 345,   "lang": "en", "title": "Dracula",                        "author": "Bram Stoker",            "year": "1897"},
    {"gid": 11,    "lang": "en", "title": "Alice's Adventures in Wonderland","author": "Lewis Carroll",         "year": "1865"},
    {"gid": 2701,  "lang": "en", "title": "Moby-Dick; or, The Whale",       "author": "Herman Melville",        "year": "1851"},
    {"gid": 98,    "lang": "en", "title": "A Tale of Two Cities",           "author": "Charles Dickens",        "year": "1859"},
    {"gid": 1080,  "lang": "en", "title": "A Modest Proposal",              "author": "Jonathan Swift",         "year": "1729"},
    {"gid": 64317, "lang": "en", "title": "The Great Gatsby",               "author": "F. Scott Fitzgerald",    "year": "1925"},
    {"gid": 2542,  "lang": "en", "title": "A Doll's House",                 "author": "Henrik Ibsen",           "year": "1879"},

    # French
    {"gid": 17989, "lang": "fr", "title": "Le Comte de Monte-Cristo, Tome I","author": "Alexandre Dumas",       "year": "1844"},
    {"gid": 13951, "lang": "fr", "title": "Les Trois Mousquetaires",        "author": "Alexandre Dumas",        "year": "1844"},
    {"gid": 4650,  "lang": "fr", "title": "Candide",                        "author": "Voltaire",               "year": "1759"},
    {"gid": 14155, "lang": "fr", "title": "Madame Bovary",                  "author": "Gustave Flaubert",       "year": "1857"},
    {"gid": 5097,  "lang": "fr", "title": "Du côté de chez Swann",          "author": "Marcel Proust",          "year": "1913"},

    # German
    {"gid": 2229,  "lang": "de", "title": "Faust: Der Tragödie erster Teil","author": "Johann Wolfgang von Goethe","year": "1808"},
    {"gid": 22367, "lang": "de", "title": "Die Verwandlung",               "author": "Franz Kafka",            "year": "1915"},
    {"gid": 7205,  "lang": "de", "title": "Also sprach Zarathustra",        "author": "Friedrich Nietzsche",    "year": "1883"},

    # Spanish
    {"gid": 2000,  "lang": "es", "title": "Don Quijote",                    "author": "Miguel de Cervantes",    "year": "1605"},
    {"gid": 49836, "lang": "es", "title": "Niebla",                         "author": "Miguel de Unamuno",      "year": "1914"},

    # Italian
    {"gid": 28732, "lang": "it", "title": "Le avventure di Pinocchio",      "author": "Carlo Collodi",          "year": "1883"},
    {"gid": 1012,  "lang": "it", "title": "La Divina Commedia: Inferno",    "author": "Dante Alighieri",        "year": "1320"},

    # Portuguese
    {"gid": 55752, "lang": "pt", "title": "Dom Casmurro",                   "author": "Machado de Assis",       "year": "1899"},
    {"gid": 3333,  "lang": "pt", "title": "Os Lusíadas",                    "author": "Luís de Camões",         "year": "1572"},

    # Russian
    {"gid": 28054, "lang": "ru", "title": "Братья Карамазовы",             "author": "Фёдор Достоевский",      "year": "1880"},

    # Japanese
    {"gid": 776,   "lang": "ja", "title": "こころ",                          "author": "夏目漱石",                "year": "1914"},
]

START_RE = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*",
                      re.IGNORECASE)
END_RE = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*",
                    re.IGNORECASE)


def text_urls(gid: int) -> list[str]:
    """Candidate plain-text URLs for a Gutenberg ebook, best first."""
    return [
        f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt",
        f"https://www.gutenberg.org/files/{gid}/{gid}-0.txt",
        f"https://www.gutenberg.org/files/{gid}/{gid}.txt",
    ]


def fetch(url: str, timeout: int = 60) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as e:  # noqa: BLE001 — report and move on
        print(f"      ! {url} -> {e}")
        return None
    # Gutenberg plain text is UTF-8 for modern files.
    return raw.decode("utf-8", errors="replace")


def strip_boilerplate(text: str) -> str:
    """Remove the PG license header/footer, keeping just the work itself."""
    start = START_RE.search(text)
    if start:
        text = text[start.end():]
    end = END_RE.search(text)
    if end:
        text = text[:end.start()]
    # A short "Produced by ..." line sometimes survives right after START.
    text = re.sub(r"^\s*Produced by .*?\n", "", text, count=1)
    return text.strip() + "\n"


def slugify(title: str, gid: int) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    s = s[:48].strip("-")
    # Non-Latin titles (Japanese, Cyrillic, …) reduce to an empty string here —
    # fall back to the Gutenberg id so the slug is meaningful and never begins
    # with a stray dash. Otherwise suffix the id for uniqueness/stability.
    if not s:
        return f"pg{gid}"
    return f"{s}-{gid}"


def word_count(text: str) -> int:
    return len(text.split())


def build() -> int:
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    ok = 0

    for i, book in enumerate(SEED, 1):
        gid = book["gid"]
        print(f"[{i}/{len(SEED)}] {book['title']} ({book['author']}) — gid {gid}")
        raw = None
        for url in text_urls(gid):
            raw = fetch(url)
            if raw and "PROJECT GUTENBERG" in raw.upper():
                print(f"      ✓ {url}")
                break
            raw = None
        if not raw:
            print("      SKIP — no usable text found")
            continue

        cleaned = strip_boilerplate(raw)
        if word_count(cleaned) < 500:
            print("      SKIP — suspiciously short after cleaning")
            continue

        slug = slugify(book["title"], gid)
        (TEXT_DIR / f"{slug}.txt").write_text(cleaned, encoding="utf-8")

        manifest.append({
            "slug": slug,
            "gutenberg_id": gid,
            "title": book["title"],
            "author": book["author"],
            "language": book["lang"],
            "year": book.get("year", ""),
            "word_count": word_count(cleaned),
            "source": f"https://www.gutenberg.org/ebooks/{gid}",
        })
        ok += 1
        time.sleep(0.5)  # be polite to Gutenberg

    # Sort manifest by language then title for stable, browsable order.
    manifest.sort(key=lambda b: (b["language"], b["title"]))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDone: {ok}/{len(SEED)} books written to {OUT_DIR}")
    langs = sorted({b['language'] for b in manifest})
    print(f"Languages: {', '.join(langs)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
