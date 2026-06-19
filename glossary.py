"""
Lexio Glossary — SEO long-tail content pages.

Each entry targets a real search like "what does [word] mean in [book]".
The pages are rendered server-side from this module, so adding a new entry
is just appending a dict to ENTRIES.

Internal contract per entry:
    slug             : URL slug (kebab-case)
    term             : the word/phrase being defined
    context          : short context line ("Baudelaire's poetry")
    title            : <title> tag content (no site suffix; we append " — Lexio")
    meta_description : <meta description> (target ~150–160 chars)
    h1               : <h1> page heading
    body_html        : main article body (already-rendered HTML; safe to embed)
    related          : list of slugs for the "Related entries" footer
    updated          : YYYY-MM-DD (used as <lastmod>)
"""

from __future__ import annotations
from typing import Iterable
from html import escape


# ── Entries ──────────────────────────────────────────────────────────────────
# Add a new entry by appending a dict here — the index page, sitemap, and
# per-entry routes pick it up automatically.

import json as _json
from pathlib import Path as _Path
ENTRIES = _json.loads((_Path(__file__).parent / "content_data" / "glossary.json").read_text(encoding="utf-8"))


# ── Lookups ──────────────────────────────────────────────────────────────────

_BY_SLUG: dict[str, dict] = {e["slug"]: e for e in ENTRIES}

def get(slug: str) -> dict | None:
    return _BY_SLUG.get(slug)

def all_entries() -> list[dict]:
    return list(ENTRIES)


# ── HTML rendering ───────────────────────────────────────────────────────────
# Self-contained pages — match the dark hero / orange-accent look of the main
# site, but with comfortable reading typography (Fraunces for headings, Inter
# for UI, larger body text).

_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --accent:  #c35500;
  --accent2: #ff7a18;
  --text:    #f5ede0;
  --text-mid:#cfc4b3;
  --muted:   #9b8f7d;
  --border:  rgba(255,255,255,0.08);
  --bg:      #0f0c08;
  --surface: #181310;
}
body {
  font-family: 'DM Sans', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.75;
  padding: 0 24px;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 720px; margin: 0 auto; padding: 56px 0 96px; }
.wrap-wide { max-width: 1080px; margin: 0 auto; padding: 56px 0 96px; }
.back {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 0.85rem; color: var(--muted);
  text-decoration: none; margin-bottom: 36px;
  transition: color 0.15s;
}
.back:hover { color: var(--accent2); }
.logo {
  font-family: 'Fraunces', serif;
  font-size: 1.4rem; font-weight: 400;
  color: var(--accent2);
  display: block; margin-bottom: 14px;
}
.logo em { font-style: italic; }
.breadcrumb { font-size: 0.78rem; color: var(--muted); margin-bottom: 18px; letter-spacing: 0.02em; }
.breadcrumb a { color: var(--muted); text-decoration: none; }
.breadcrumb a:hover { color: var(--accent2); }
h1 {
  font-family: 'Fraunces', serif;
  font-size: 2.1rem; font-weight: 400;
  margin-bottom: 10px;
  line-height: 1.25;
  color: var(--text);
}
.term-context {
  font-size: 0.95rem; color: var(--muted);
  margin-bottom: 36px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
  font-style: italic;
}
h2 {
  font-family: 'Fraunces', serif;
  font-size: 1.3rem; font-weight: 400;
  margin: 36px 0 12px;
  color: var(--text);
}
p, li {
  font-size: 1rem;
  color: var(--text-mid);
  margin-bottom: 14px;
}
ul, ol { padding-left: 22px; margin-bottom: 14px; }
li { margin-bottom: 8px; }
li::marker { color: var(--accent); }
strong { color: var(--text); font-weight: 600; }
em { font-style: italic; }
a { color: var(--accent2); text-decoration: none; border-bottom: 1px solid rgba(255,122,24,0.25); }
a:hover { border-bottom-color: var(--accent2); }
blockquote {
  border-left: 3px solid var(--accent);
  padding: 6px 16px; margin: 18px 0;
  color: var(--text); font-style: italic;
  background: rgba(195,85,0,0.05);
}

/* CTA card */
.cta {
  margin-top: 56px; padding: 26px 28px;
  background: linear-gradient(135deg, rgba(195,85,0,0.10), rgba(255,122,24,0.05));
  border: 1px solid rgba(255,122,24,0.25);
  border-radius: 14px;
}
.cta-eyebrow {
  font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--accent2); font-weight: 700; margin-bottom: 8px;
  display: block;
}
.cta h3 {
  font-family: 'Fraunces', serif; font-size: 1.25rem; font-weight: 400;
  color: var(--text); margin-bottom: 8px;
}
.cta p { color: var(--text-mid); font-size: 0.95rem; margin-bottom: 16px; }
.cta-btn {
  display: inline-block; padding: 11px 22px;
  background: var(--accent); color: #fff;
  font-family: inherit; font-weight: 500; font-size: 0.92rem;
  text-decoration: none; border-radius: 8px; border: none;
  transition: background 0.15s, transform 0.15s;
}
.cta-btn:hover { background: var(--accent2); transform: translateY(-1px); border-bottom: none; }

/* Related */
.related { margin-top: 56px; padding-top: 28px; border-top: 1px solid var(--border); }
.related-title {
  font-size: 0.74rem; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--muted); font-weight: 700; margin-bottom: 14px;
}
.related-list { display: grid; gap: 8px; }
.related-item {
  display: block; padding: 14px 16px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; text-decoration: none;
  transition: border-color 0.15s, transform 0.15s;
}
.related-item:hover { border-color: rgba(255,122,24,0.4); transform: translateY(-1px); }
.related-item-term {
  font-family: 'Fraunces', serif; font-size: 1rem; font-weight: 400;
  color: var(--text); margin-bottom: 2px;
}
.related-item-context { font-size: 0.82rem; color: var(--muted); font-style: italic; }

/* Index page extras */
.intro {
  font-size: 1.05rem; color: var(--text-mid);
  margin-bottom: 40px; padding-bottom: 28px;
  border-bottom: 1px solid var(--border);
}
.intro-link {
  display: inline-block; margin-top: 6px;
  color: var(--accent2); border-bottom: 1px solid transparent;
  text-decoration: none; font-size: 0.95rem;
  transition: border-color 0.15s;
}
.intro-link:hover { border-bottom-color: var(--accent2); }
.entry-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
}
.entry-card {
  display: flex; flex-direction: column;
  padding: 18px 20px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; text-decoration: none;
  transition: border-color 0.15s, transform 0.15s;
  height: 100%;
}
.entry-card:hover { border-color: rgba(255,122,24,0.4); transform: translateY(-1px); }
.entry-card-head {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 4px;
}
.entry-card-term {
  font-family: 'Fraunces', serif; font-size: 1.15rem; font-weight: 400;
  color: var(--text);
}
.entry-card-new {
  display: inline-flex; align-items: center;
  font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 2px 7px; border-radius: 999px;
  background: rgba(255,122,24,0.15); color: var(--accent2);
  border: 1px solid rgba(255,122,24,0.35);
}
.entry-card-context { font-size: 0.85rem; color: var(--muted); font-style: italic; margin-bottom: 10px; }
.entry-card-desc {
  font-size: 0.9rem; color: var(--text-mid); line-height: 1.55;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Search */
.entry-search-wrap {
  position: relative; margin-bottom: 28px;
}
.entry-search-icon {
  position: absolute; left: 14px; top: 50%;
  transform: translateY(-50%); color: var(--muted);
  pointer-events: none;
}
#entry-search {
  width: 100%; padding: 12px 16px 12px 40px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px;
  font-family: inherit; font-size: 0.95rem; color: var(--text);
  outline: none;
  transition: border-color 0.15s, background 0.15s;
}
#entry-search:focus {
  border-color: rgba(255,122,24,0.45);
  background: var(--surface);
}
#entry-search::placeholder { color: var(--muted); }
.entry-empty {
  text-align: center; padding: 40px 20px;
  color: var(--muted); font-size: 0.9rem;
}

.closing {
  margin-top: 56px; padding-top: 28px;
  border-top: 1px solid var(--border);
  font-size: 0.85rem; color: var(--muted);
  text-align: center;
}
.closing em { font-style: italic; color: var(--accent2); }
.closing a { color: var(--muted); border-bottom: none; }
.closing a:hover { color: var(--accent2); }

@media (max-width: 640px) {
  h1 { font-size: 1.7rem; }
  .wrap { padding: 40px 0 72px; }
}
"""


def _head(title: str, description: str, canonical: str,
         og_image: str = "https://lexio.site/og-image.png") -> str:
    """Shared <head> block — title/meta/OG/Twitter/Plausible."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{escape(title)} — Lexio</title>
  <meta name="description" content="{escape(description)}" />
  <meta name="author" content="Lexio" />
  <link rel="canonical" href="{escape(canonical)}" />
  <link rel="alternate" hreflang="en" href="{escape(canonical)}" />
  <link rel="alternate" hreflang="x-default" href="{escape(canonical)}" />
  <link rel="sitemap" type="application/xml" href="/sitemap.xml" />
  <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large" />
  <meta name="theme-color" content="#f3ead8" />
  <link rel="icon" type="image/x-icon" href="/favicon.ico" />

  <!-- Open Graph -->
  <meta property="og:type" content="article" />
  <meta property="og:title" content="{escape(title)} — Lexio" />
  <meta property="og:description" content="{escape(description)}" />
  <meta property="og:url" content="{escape(canonical)}" />
  <meta property="og:image" content="{escape(og_image)}" />
  <meta property="og:locale" content="en_US" />
  <meta property="og:site_name" content="Lexio" />

  <!-- Twitter -->
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{escape(title)} — Lexio" />
  <meta name="twitter:description" content="{escape(description)}" />
  <meta name="twitter:image" content="{escape(og_image)}" />

  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400..700;1,9..144,400..700&family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet" />
  <style>{_CSS}</style>

  <!-- Privacy-friendly analytics -->
  <script async src="https://plausible.io/js/pa-uClUulm_iku5Ah2kWnseu.js"></script>
  <script>
    window.plausible=window.plausible||function(){{(plausible.q=plausible.q||[]).push(arguments)}},plausible.init=plausible.init||function(i){{plausible.o=i||{{}}}};
    plausible.init()
  </script>
</head>
"""


def _related_block(slugs: Iterable[str]) -> str:
    items = []
    for s in slugs:
        e = _BY_SLUG.get(s)
        if not e: continue
        items.append(f"""
        <a class="related-item" href="/glossary/{escape(e['slug'])}">
          <div class="related-item-term">{escape(e['term'])}</div>
          <div class="related-item-context">in {escape(e['context'])}</div>
        </a>""")
    if not items: return ""
    return f"""
  <div class="related">
    <div class="related-title">Related entries</div>
    <div class="related-list">{''.join(items)}</div>
  </div>"""


def _cta_block() -> str:
    return """
  <div class="cta">
    <span class="cta-eyebrow">Try Lexio</span>
    <h3>Look up any word like this — in any book, in any browser.</h3>
    <p>Lexio is a free Chrome extension and web app that reads a word's actual context and tells you what it means <em>in this sentence</em>, not from a generic dictionary.</p>
    <a class="cta-btn" href="/">Try Lexio — free →</a>
  </div>"""


def _jsonld_entry(entry: dict, canonical: str) -> str:
    """Schema.org DefinedTerm + Article hybrid — best for glossary pages."""
    import json as _json
    import re as _re

    # Strip HTML tags from body for articleBody / wordCount — Google uses these
    # to assess content depth and freshness.
    _plain = _re.sub(r"<[^>]+>", " ", entry["body_html"])
    _plain = _re.sub(r"\s+", " ", _plain).strip()
    _word_count = len(_plain.split())

    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "DefinedTerm",
                "name": entry["term"],
                "description": entry["meta_description"],
                "inDefinedTermSet": {
                    "@type": "DefinedTermSet",
                    "name": "Lexio Glossary",
                    "url": "https://lexio.site/glossary",
                },
                "url": canonical,
                "inLanguage": "en",
            },
            {
                "@type": "Article",
                "headline": entry["title"],
                "description": entry["meta_description"],
                "url": canonical,
                "datePublished": entry["updated"],
                "dateModified": entry["updated"],
                "inLanguage": "en",
                "wordCount": _word_count,
                "image": "https://lexio.site/og-image.png",
                "about": {"@type": "Thing", "name": entry["term"]},
                "keywords": [entry["term"], entry["context"], "literary terms", "contextual definition"],
                "articleSection": "Glossary",
                "author": {
                    "@type": "Organization",
                    "name": "Lexio",
                    "url": "https://lexio.site/",
                },
                "publisher": {
                    "@type": "Organization",
                    "name": "Lexio",
                    "url": "https://lexio.site/",
                    "logo": {"@type": "ImageObject", "url": "https://lexio.site/favicon-512.png"},
                },
                "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Lexio", "item": "https://lexio.site/"},
                    {"@type": "ListItem", "position": 2, "name": "Glossary", "item": "https://lexio.site/glossary"},
                    {"@type": "ListItem", "position": 3, "name": entry["term"], "item": canonical},
                ],
            },
        ],
    }
    return f'<script type="application/ld+json">{_json.dumps(data, ensure_ascii=False)}</script>'


def render_entry(entry: dict) -> str:
    canonical = f"https://lexio.site/glossary/{entry['slug']}"
    head = _head(entry["title"], entry["meta_description"], canonical)
    jsonld = _jsonld_entry(entry, canonical)
    return f"""{head}
<body>
{jsonld}
<div class="wrap">
  <a class="back" href="/glossary">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    All glossary entries
  </a>

  <span class="logo">Le<em>x</em>io</span>
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">Home</a> &nbsp;›&nbsp; <a href="/glossary">Glossary</a> &nbsp;›&nbsp; {escape(entry['term'])}
  </nav>

  <h1>{escape(entry['h1'])}</h1>
  <p class="term-context">A term you'll meet in {escape(entry['context'])}.</p>

  {entry['body_html']}

  {_cta_block()}
  {_related_block(entry.get('related', []))}

  <p class="closing">
    <em>Read deeper. Understand everything.</em><br>
    © 2026 Lexio · <a href="/privacy.html">Privacy</a> · <a href="/credits.html">Credits</a>
  </p>
</div>
</body>
</html>
"""


def render_index() -> str:
    canonical = "https://lexio.site/glossary"
    head = _head(
        "Lexio Glossary — Literary terms explained in context",
        "Free explainers for literary terms students actually search: spleen in Baudelaire, sublime in Romanticism, melancholy in Hamlet, and more.",
        canonical,
    )

    import json as _json
    import re
    from datetime import date, timedelta

    # Sort entries alphabetically by term (case-insensitive, ignoring leading "the ")
    def sort_key(e: dict) -> str:
        t = e["term"].lower()
        if t.startswith("the "):
            t = t[4:]
        return t

    sorted_entries = sorted(ENTRIES, key=sort_key)
    total = len(sorted_entries)

    # "New" threshold — entries updated within the last 30 days
    today = date.today()
    new_cutoff = today - timedelta(days=30)

    jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Lexio Glossary",
        "description": "Free explainers for literary terms in context.",
        "url": canonical,
        "hasPart": [
            {
                "@type": "DefinedTerm",
                "name": e["term"],
                "description": e["meta_description"],
                "url": f"https://lexio.site/glossary/{e['slug']}",
            }
            for e in sorted_entries
        ],
    }
    jsonld_tag = f'<script type="application/ld+json">{_json.dumps(jsonld, ensure_ascii=False)}</script>'

    cards = []
    for e in sorted_entries:
        body = e["body_html"]
        start = body.find("<p>")
        end = body.find("</p>", start) if start != -1 else -1
        preview = ""
        if start != -1 and end != -1:
            raw = body[start + 3:end]
            preview = re.sub(r"<[^>]+>", "", raw)
            preview = preview.strip().replace("\n", " ")
            if len(preview) > 180:
                preview = preview[:180].rstrip() + "…"

        # Determine "new" badge
        is_new = False
        try:
            updated_str = e.get("updated", "")
            if updated_str:
                y, m, d = updated_str.split("-")
                entry_date = date(int(y), int(m), int(d))
                is_new = entry_date >= new_cutoff
        except Exception:
            pass

        new_badge = '<span class="entry-card-new">New</span>' if is_new else ''

        # data-search attribute for client-side filtering
        search_blob = f"{e['term']} {e['context']} {preview}".lower()

        cards.append(f"""
    <a class="entry-card" href="/glossary/{escape(e['slug'])}" data-search="{escape(search_blob)}">
      <div class="entry-card-head">
        <div class="entry-card-term">{escape(e['term'])}</div>
        {new_badge}
      </div>
      <div class="entry-card-context">in {escape(e['context'])}</div>
      <div class="entry-card-desc">{escape(preview)}</div>
    </a>""")

    search_js = """
<script>
(function() {
  var input = document.getElementById('entry-search');
  var grid = document.getElementById('entry-grid');
  var empty = document.getElementById('entry-empty');
  if (!input || !grid) return;
  var cards = grid.querySelectorAll('.entry-card');
  input.addEventListener('input', function() {
    var q = (input.value || '').trim().toLowerCase();
    var visible = 0;
    cards.forEach(function(c) {
      var blob = c.getAttribute('data-search') || '';
      var match = q === '' || blob.indexOf(q) !== -1;
      c.style.display = match ? '' : 'none';
      if (match) visible++;
    });
    if (empty) empty.style.display = visible === 0 ? 'block' : 'none';
  });
})();
</script>
"""

    return f"""{head}
<body>
{jsonld_tag}
<div class="wrap-wide">
  <a class="back" href="/">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    Back to Lexio
  </a>

  <span class="logo">Le<em>x</em>io</span>
  <h1>Glossary</h1>
  <p class="intro">Literary terms that don't survive a dictionary lookup — explained in the context where you actually meet them. Free to read, no signup. {total} entries and counting. <a href="/works" class="intro-link">Or browse reader's guides to whole works →</a></p>

  <div class="entry-search-wrap">
    <svg class="entry-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    <input id="entry-search" type="search" placeholder="Search {total} entries — try ‘hamartia’, ‘irony’, ‘Bakhtin’…" autocomplete="off" />
  </div>

  <div class="entry-grid" id="entry-grid">{''.join(cards)}</div>
  <p id="entry-empty" class="entry-empty" style="display:none">No entries match. Try a shorter query.</p>

  {_cta_block()}

  <p class="closing">
    <em>Read deeper. Understand everything.</em><br>
    © 2026 Lexio · <a href="/privacy.html">Privacy</a> · <a href="/credits.html">Credits</a>
  </p>
</div>
{search_js}
</body>
</html>
"""
