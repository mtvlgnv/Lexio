"""
Lexio — "This Week on Lexio" content/SEO page  (/this-week)

A weekly post built from Lexio's own /stats/top-words data: the real words
readers tapped, paired with what each one means in its exact sentence. It reuses
the glossary page shell (shared <head>, CSS, and CTA) so styling stays identical
site-wide.

To publish next week's issue, update ISSUE below (date, intro, words) — the
route picks it up automatically.
"""
from __future__ import annotations
from html import escape
import json as _json

import glossary as _glossary  # reuse shared _head(), _cta_block(), _CSS


ISSUE = {
    "date": "2026-06-08",
    "title": "This Week on Lexio: the words readers couldn't skip past",
    "meta_description": (
        "The real words readers tapped on Lexio this week — from Moby-Dick's "
        "\"driving off the spleen\" to confabulating — and what each one means "
        "in its exact sentence, not from a generic dictionary."
    ),
    "intro": (
        "Every week, readers tap words inside Lexio to find out what they mean — "
        "not in general, but in the <em>exact sentence</em> they're stuck on. "
        "Here are five that stopped people mid-read this week."
    ),
    "words": [
        {
            "term": "spleen",
            "source": "Moby-Dick, opening chapter",
            "body_html": """
<p><strong>Not the organ.</strong> <em>Spleen</em> is the old word for gloom and
bad temper — once believed to live in the actual organ. When Ishmael takes to
the ship as a way of <em>"driving off the spleen,"</em> he means shaking off his
black mood. <strong>"Driving off the spleen" was our single most-tapped phrase
this week</strong> — proof a 170-year-old sentence still stops modern readers cold.</p>""",
        },
        {
            "term": "confabulating",
            "source": "a neuroscience read",
            "body_html": """
<p>The brain filling memory gaps with details that <em>feel</em> true but never
happened — with no intent to deceive. Not "making things up"; more like the mind
quietly editing its own footage.</p>""",
        },
        {
            "term": "epistemology",
            "source": "philosophy",
            "body_html": """
<p>The study of knowledge itself: how we know what we know, and where the limits
are. The word hiding behind every "&hellip;but how do you actually <em>know</em>
that?"</p>""",
        },
        {
            "term": "hippocampal",
            "source": "psychology",
            "body_html": """
<p>Of the hippocampus — the seahorse-shaped brain region that turns <em>today</em>
into long-term memory. Readers who tapped it were usually deep in how memories
get made.</p>""",
        },
        {
            "term": "shrewd",
            "source": "fiction",
            "body_html": """
<p>Sharp, practical judgment. Not book-smart — reads-the-room smart. The
character who sizes up a situation and bets right.</p>""",
        },
    ],
}


def _jsonld(canonical: str) -> str:
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": ISSUE["title"],
                "description": ISSUE["meta_description"],
                "url": canonical,
                "datePublished": ISSUE["date"],
                "dateModified": ISSUE["date"],
                "inLanguage": "en",
                "image": "https://lexio.site/og-image.png",
                "articleSection": "This Week on Lexio",
                "author": {"@type": "Organization", "name": "Lexio", "url": "https://lexio.site/"},
                "publisher": {
                    "@type": "Organization", "name": "Lexio", "url": "https://lexio.site/",
                    "logo": {"@type": "ImageObject", "url": "https://lexio.site/favicon-512.png"},
                },
                "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Lexio", "item": "https://lexio.site/"},
                    {"@type": "ListItem", "position": 2, "name": "This Week on Lexio", "item": canonical},
                ],
            },
        ],
    }
    return f'<script type="application/ld+json">{_json.dumps(data, ensure_ascii=False)}</script>'


def render() -> str:
    canonical = "https://lexio.site/this-week"
    head = _glossary._head(ISSUE["title"], ISSUE["meta_description"], canonical)

    cards = []
    for i, w in enumerate(ISSUE["words"], 1):
        cards.append(
            f"""
  <h2>{i}. {escape(w['term'])} <span class="tw-source">— {escape(w['source'])}</span></h2>
  {w['body_html']}"""
        )
    words_html = "\n".join(cards)

    return f"""{head}
<body>
{_jsonld(canonical)}
<div class="wrap">
  <a class="back" href="/">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    Back to Lexio
  </a>

  <span class="logo">Le<em>x</em>io</span>
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">Home</a> &nbsp;&rsaquo;&nbsp; This Week on Lexio
  </nav>

  <h1>{escape(ISSUE['title'])}</h1>
  <p class="term-context">Issue &middot; {escape(ISSUE['date'])} &middot; built from real lookup data</p>

  <p>{ISSUE['intro']}</p>
{words_html}

  {_glossary._cta_block()}

  <p class="closing">
    <em>Read deeper. Understand everything.</em><br>
    &copy; 2026 Lexio &middot; <a href="/privacy.html">Privacy</a> &middot; <a href="/credits.html">Credits</a>
  </p>
</div>
<style>.tw-source{{font-weight:400;opacity:.6;font-size:.72em;}}</style>
</body>
</html>
"""
