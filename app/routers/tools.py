"""/fetch-text (SSRF-guarded URL reader) + /stats/top-words (Phase 2 extract)."""
import asyncio
import datetime
import ipaddress
import logging
import socket as _socket

import trafilatura
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.db import get_db
from app.models import SearchLog
from app.ratelimit import limiter
from app.limits import _CACHE_TTL, _top_words_cache
from app.schemas import FetchRequest

logger = logging.getLogger("lexio")
router = APIRouter()


def _ip_is_safe(addr: str) -> bool:
    """Return True only if the IP address is globally routable."""
    try:
        ip = ipaddress.ip_address(addr)
        return (
            ip.is_global
            and not ip.is_private
            and not ip.is_loopback
            and not ip.is_link_local
            and not ip.is_reserved
            and not ip.is_multicast
            and not ip.is_unspecified
        )
    except ValueError:
        return False

def _is_safe_url(url: str) -> bool:
    """
    Return False if any resolved address (IPv4 or IPv6) for the URL's hostname
    is non-global (SSRF guard).  Uses getaddrinfo so all A/AAAA records are
    checked — gethostbyname() only returns a single IPv4 result and misses IPv6.
    """
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            return False
        # getaddrinfo returns all A + AAAA records
        results = _socket.getaddrinfo(hostname, None)
        if not results:
            return False
        for res in results:
            addr = res[4][0]
            if not _ip_is_safe(addr):
                return False
        return True
    except Exception:
        return False


def _safe_fetch(url: str, max_redirects: int = 3) -> str | None:
    """
    Fetch *url* with a redirect-following loop that re-checks SSRF safety on
    every hop.  Returns the raw HTML/text or None on failure.
    """
    import urllib.request as _ur
    import urllib.error as _ue

    current_url = url
    for _ in range(max_redirects + 1):
        if not _is_safe_url(current_url):
            return None
        req = _ur.Request(
            current_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Lexio/1.0; +https://lexio.site)"},
        )
        try:
            with _ur.urlopen(req, timeout=10) as resp:
                # Follow redirect manually so we can re-check the destination
                final_url = resp.geturl()
                if final_url != current_url:
                    current_url = final_url
                    continue
                content_type = resp.headers.get_content_type() or ""
                if not any(t in content_type for t in ("html", "text", "xml")):
                    return None
                return resp.read(2_000_000).decode("utf-8", errors="replace")
        except _ue.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                from urllib.parse import urljoin
                current_url = urljoin(current_url, exc.headers["Location"])
                continue
            return None
    return None   # too many redirects


# ── /fetch-text ───────────────────────────────────────────────────────────────

@router.post("/fetch-text")
@limiter.limit("5/minute")
async def fetch_article(request: Request, payload: FetchRequest):
    try:
        import trafilatura
        url = str(payload.url)

        if not _is_safe_url(url):
            raise HTTPException(status_code=422, detail="URL not allowed.")

        def _extract() -> str | None:
            html_content = _safe_fetch(url)
            if not html_content:
                return None
            return trafilatura.extract(
                html_content,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )

        text = await asyncio.to_thread(_extract)
        if not text or len(text.strip()) < 50:
            raise HTTPException(
                status_code=422,
                detail="Could not extract readable text — try copying and pasting the article manually.",
            )
        return {"text": text[:8_000].strip()}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("/fetch-text error: %s", exc)
        raise HTTPException(status_code=422, detail="Could not extract text from that URL.")


# ── /stats/top-words ─────────────────────────────────────────────────────────

@router.get("/stats/top-words")
async def top_words(db: DBSession = Depends(get_db)):
    """
    Return the top 5 most-looked-up words in the current calendar month.
    Result is cached in memory for 1 hour so the DB isn't queried on every
    page load.
    """
    now = datetime.datetime.utcnow()

    # Serve from cache if still fresh
    if (
        _top_words_cache["data"] is not None
        and _top_words_cache["fetched_at"] is not None
        and now - _top_words_cache["fetched_at"] < _CACHE_TTL
    ):
        return _top_words_cache["data"]

    # Start of current month
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    rows = (
        db.query(SearchLog.word, func.count(SearchLog.id).label("n"))
        .filter(SearchLog.searched_at >= month_start)
        .group_by(SearchLog.word)
        .order_by(func.count(SearchLog.id).desc())
        .limit(5)
        .all()
    )

    result = {
        "month": now.strftime("%B %Y"),
        "words": [{"word": r.word, "count": r.n} for r in rows],
    }

    _top_words_cache["data"]       = result
    _top_words_cache["fetched_at"] = now
    return result
