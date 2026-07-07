"""Dynamic XML sitemap.

Generated from the live glossary / works content plus the static marketing
pages, so it never drifts out of sync the way a hand-maintained static file
does (the old static/sitemap.xml had grown 3 stale glossary URLs and frozen
lastmod dates). Served at /sitemap.xml by app/routers/content.py, ahead of the
StaticFiles mount.
"""
from datetime import date
from xml.sax.saxutils import escape

import glossary as _glossary
import works as _works

BASE = "https://lexio.site"

# Static, crawlable pages: (path, changefreq, priority). The tool (/app) and
# personal pages (/recap) are intentionally excluded — /app is a thin app
# shell (canonical → /) and /recap is per-user and disallowed in robots.txt.
#
# URL form matters: in production nginx proxies /glossary, /works, /this-week
# (and /) to the app, but serves everything else as a static file via
# try_files with NO .html fallback — so /for-readers 404s while
# /for-readers.html resolves. Each path below is the form that returns 200 and
# matches the page's own canonical, so the sitemap never lists a 404.
_STATIC_PAGES = [
    ("/",                      "weekly",  "1.0"),
    ("/glossary",              "weekly",  "0.8"),
    ("/works",                 "weekly",  "0.8"),
    ("/this-week",             "daily",   "0.6"),
    ("/for-readers.html",      "monthly", "0.7"),
    ("/for-educators.html",    "monthly", "0.7"),
    ("/for-language-learners.html", "monthly", "0.7"),
    ("/for-students.html",     "monthly", "0.7"),
    ("/for-professionals.html", "monthly", "0.7"),
    ("/chrome-extension.html", "monthly", "0.7"),
    ("/changelog.html",        "monthly", "0.4"),
    ("/privacy.html",          "yearly",  "0.2"),
    ("/credits.html",          "yearly",  "0.2"),
]


def _url(loc: str, lastmod: str, changefreq: str, priority: str) -> str:
    return (
        "  <url>\n"
        f"    <loc>{escape(loc)}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        "  </url>"
    )


def _lastmod(value) -> str:
    """Validate a YYYY-MM-DD string; fall back to today if missing/odd."""
    today = date.today().isoformat()
    if not value:
        return today
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return today


def render() -> str:
    today = date.today().isoformat()
    rows: list[str] = []

    for path, changefreq, priority in _STATIC_PAGES:
        rows.append(_url(f"{BASE}{path}", today, changefreq, priority))

    for e in _glossary.all_entries():
        rows.append(_url(
            f"{BASE}/glossary/{e['slug']}",
            _lastmod(e.get("updated")),
            "monthly", "0.6",
        ))

    for w in _works.all_works():
        rows.append(_url(
            f"{BASE}/works/{w['slug']}",
            _lastmod(w.get("updated")),
            "monthly", "0.6",
        ))

    body = "\n".join(rows)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )
