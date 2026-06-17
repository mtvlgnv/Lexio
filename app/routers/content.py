"""SEO/content + catalog page routes (Phase 2 extract)."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse, Response

router = APIRouter()


# ── Dynamic XML sitemap ───────────────────────────────────────────────────────
# Generated from live glossary/works content so it never drifts out of sync.
# Declared before the StaticFiles mount in main.py, so it shadows any static
# sitemap.xml. nginx proxies /sitemap.xml to the app (see route allowlist).
import sitemap as _sitemap

@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml():
    return Response(content=_sitemap.render(), media_type="application/xml")


# ── Named static page routes ─────────────────────────────────────────────────

@router.get("/pro", include_in_schema=False)
async def pro_page():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/#lp-pro", status_code=301)

@router.get("/recap", response_class=HTMLResponse, include_in_schema=False)
async def recap_page():
    """Spotify-Wrapped-style annual reading recap. Server returns a static
    HTML shell; the page calls /api/annual-recap on load and renders the
    user's stats. For unauthenticated visitors, the page acts as marketing
    for the annual plan (sign-in CTA + sample numbers)."""
    with open("static/recap.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@router.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def privacy_page():
    with open("static/privacy.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ── Glossary (SEO long-tail content) ────────────────────────────────────────
import glossary as _glossary

@router.get("/glossary", response_class=HTMLResponse, include_in_schema=False)
@router.get("/glossary/", response_class=HTMLResponse, include_in_schema=False)
async def glossary_index():
    return HTMLResponse(_glossary.render_index())

@router.get("/glossary/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def glossary_entry(slug: str):
    entry = _glossary.get(slug)
    if not entry:
        return RedirectResponse(url="/glossary", status_code=302)
    return HTMLResponse(_glossary.render_entry(entry))


# ── Reader's guides — work-specific landing pages ──────────────────────────────
import works as _works

@router.get("/works", response_class=HTMLResponse, include_in_schema=False)
@router.get("/works/", response_class=HTMLResponse, include_in_schema=False)
async def works_index():
    return HTMLResponse(_works.render_index())

@router.get("/works/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def work_page(slug: str):
    work = _works.get(slug)
    if not work:
        return RedirectResponse(url="/works", status_code=302)
    return HTMLResponse(_works.render_work(work))


# ── Book catalog (JSON) — powers the in-app library/Browse screen ──────────────
import catalog as _catalog

@router.get("/api/catalog", response_class=JSONResponse)
async def catalog_list(lang: Optional[str] = None):
    """Catalog metadata (no text). Optional `?lang=fr` filters by language.

    Returns the set of available languages (with counts) plus the matching
    books, so the client can build a language picker and list in one call.
    """
    return JSONResponse({
        "languages": _catalog.languages(),
        "books": _catalog.all_books(lang),
    })

@router.get("/api/catalog/{slug}", response_class=JSONResponse)
async def catalog_book(slug: str):
    """One book's metadata plus its full public-domain text."""
    meta = _catalog.get(slug)
    if not meta:
        raise HTTPException(status_code=404, detail="Book not found.")
    body = _catalog.text(slug)
    if body is None:
        raise HTTPException(status_code=404, detail="Book text unavailable.")
    return JSONResponse({**meta, "body": body})


# ── This Week on Lexio (top-words content/SEO page) ────────────────────────────
import thisweek as _thisweek

@router.get("/this-week", response_class=HTMLResponse, include_in_schema=False)
@router.get("/this-week/", response_class=HTMLResponse, include_in_schema=False)
async def this_week_page():
    return HTMLResponse(_thisweek.render())


# ── App (tool) page ────────────────────────────────────────────────────────────
# The tool lives on its own route; the same index.html renders the tool instead
# of the marketing landing based on the URL path (see the routing script in the
# page). Must be declared before the catch-all StaticFiles mount below.
from fastapi.responses import FileResponse

@router.get("/app", response_class=HTMLResponse, include_in_schema=False)
@router.get("/app/", response_class=HTMLResponse, include_in_schema=False)
async def app_page():
    return FileResponse("static/index.html")
