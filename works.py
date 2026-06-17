"""
works.py — author/work-specific landing pages for SEO long-tail.

Each work is a substantial hub page that targets specific student
searches ("hamlet themes", "great gatsby symbolism") and links
heavily back to glossary.py entries.
"""
from __future__ import annotations
from html import escape

import glossary as _glossary


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

import json as _json
from pathlib import Path as _Path
WORKS = _json.loads((_Path(__file__).parent / "content_data" / "works.json").read_text(encoding="utf-8"))

_BY_SLUG: dict[str, dict] = {w["slug"]: w for w in WORKS}


def get(slug: str) -> dict | None:
    return _BY_SLUG.get(slug)


def all_works() -> list[dict]:
    return list(WORKS)


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────

def render_work(work: dict) -> str:
    """Render a single work page. Reuses glossary.py styling and head."""
    canonical = f"https://lexio.site/works/{work['slug']}"
    head = _glossary._head(work["title"], work["meta_description"], canonical)

    import json as _json
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": work["title"],
                "description": work["meta_description"],
                "url": canonical,
                "dateModified": work["updated"],
                "about": {
                    "@type": "Book",
                    "name": work["title"].split(" — ")[0],
                    "author": {"@type": "Person", "name": work["author"]},
                },
                "publisher": {
                    "@type": "Organization",
                    "name": "Lexio",
                    "logo": {"@type": "ImageObject", "url": "https://lexio.site/favicon-512.png"},
                },
                "mainEntityOfPage": canonical,
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Lexio", "item": "https://lexio.site/"},
                    {"@type": "ListItem", "position": 2, "name": "Works", "item": "https://lexio.site/works"},
                    {"@type": "ListItem", "position": 3, "name": work["title"].split(" — ")[0], "item": canonical},
                ],
            },
        ],
    }
    jsonld_tag = f'<script type="application/ld+json">{_json.dumps(jsonld, ensure_ascii=False)}</script>'

    # Build related-entries block from key_entries
    related_items = []
    for slug in work.get("key_entries", []):
        e = _glossary._BY_SLUG.get(slug)
        if not e:
            continue
        related_items.append(f"""
        <a class="related-item" href="/glossary/{escape(e['slug'])}">
          <div class="related-item-term">{escape(e['term'])}</div>
          <div class="related-item-context">in {escape(e['context'])}</div>
        </a>""")
    related_block = ""
    if related_items:
        related_block = f"""
  <div class="related">
    <div class="related-title">Key glossary entries</div>
    <div class="related-list">{''.join(related_items)}</div>
  </div>"""

    return f"""{head}
<body>
{jsonld_tag}
<div class="wrap">
  <a class="back" href="/glossary">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    Glossary
  </a>

  <span class="logo">Le<em>x</em>io</span>
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">Home</a> &nbsp;›&nbsp; <a href="/works">Works</a> &nbsp;›&nbsp; {escape(work['title'].split(' — ')[0])}
  </nav>
  <h1>{escape(work['h1'])}</h1>
  <p class="term-context"><em>{escape(work['author'])}</em> · {escape(work['year'])}</p>

  {work['body_html']}

  {related_block}

  {_glossary._cta_block()}

  <p class="closing">
    <em>Read deeper. Understand everything.</em><br>
    © 2026 Lexio · <a href="/privacy.html">Privacy</a> · <a href="/credits.html">Credits</a>
  </p>
</div>
</body>
</html>
"""


def render_index() -> str:
    """Hub page listing all works at /works."""
    canonical = "https://lexio.site/works"
    head = _glossary._head(
        "Lexio — Reader's Guides to Major Works",
        "In-depth guides to the vocabulary, themes, and concepts of major works of literature — Hamlet, The Great Gatsby, and more.",
        canonical,
    )

    cards = []
    for w in WORKS:
        cards.append(f"""
    <a class="entry-card" href="/works/{escape(w['slug'])}">
      <div class="entry-card-term">{escape(w['title'].split(' — ')[0])}</div>
      <div class="entry-card-context">{escape(w['author'])} · {escape(w['year'])}</div>
      <div class="entry-card-desc">{escape(w['meta_description'])}</div>
    </a>""")

    # Structured data — a CollectionPage of the guides (each an Article about a
    # Book) plus a BreadcrumbList, matching the glossary index.
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "name": "Lexio Reader's Guides",
                "description": "In-depth reader's guides to major works of literature.",
                "url": canonical,
                "hasPart": [
                    {
                        "@type": "Article",
                        "name": w["title"].split(" — ")[0],
                        "about": {
                            "@type": "Book",
                            "name": w["title"].split(" — ")[0],
                            "author": {"@type": "Person", "name": w["author"]},
                        },
                        "url": f"https://lexio.site/works/{w['slug']}",
                    }
                    for w in WORKS
                ],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://lexio.site/"},
                    {"@type": "ListItem", "position": 2, "name": "Reader's guides", "item": canonical},
                ],
            },
        ],
    }
    jsonld_tag = f'<script type="application/ld+json">{_json.dumps(jsonld, ensure_ascii=False)}</script>'

    return f"""{head}
<body>
{jsonld_tag}
<div class="wrap-wide">
  <a class="back" href="/">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    Back to Lexio
  </a>

  <span class="logo">Le<em>x</em>io</span>
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">Home</a> &nbsp;›&nbsp; Reader's guides
  </nav>
  <h1>Reader's guides</h1>
  <p class="intro">Substantial reader's guides to major works of literature — vocabulary, themes, and concepts, with links to in-depth glossary entries.</p>

  <div class="entry-grid">{''.join(cards)}</div>

  <p class="closing">
    <em>Read deeper. Understand everything.</em><br>
    © 2026 Lexio · <a href="/privacy.html">Privacy</a> · <a href="/credits.html">Credits</a>
  </p>
</div>
</body>
</html>
"""
