import asyncio
import os
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, AnyHttpUrl
import anthropic
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

# ── Rate limiter ────────────────────────────────────────────────────────────
# key_func reads X-Forwarded-For (set by Nginx) so the limit is per real
# client IP, not per Nginx proxy address.
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Lexio")
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests — wait a moment before looking up another word."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# ── Request models ──────────────────────────────────────────────────────────

class DefineRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=60)
    context: str = Field(..., min_length=1, max_length=8_000)


class FetchRequest(BaseModel):
    url: AnyHttpUrl


# ── /define ─────────────────────────────────────────────────────────────────

@app.post("/define")
@limiter.limit("20/minute")
async def define_word(request: Request, req: DefineRequest):
    prompt = (
        f'The word "{req.word}" appears in this text: "{req.context}"\n'
        "Respond ONLY in JSON with no markdown:\n"
        '{"pos": "noun/verb/etc", '
        '"contextual": "definition as used in this passage, 1-2 sentences", '
        '"why": "why this word rather than a simpler synonym, 1 sentence", '
        '"simpler": "the simplest common one-word synonym, or null if none"}'
    )

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text.strip()

        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        result = json.loads(text)

        for key in ("pos", "contextual", "why"):
            if key not in result:
                raise ValueError(f"Missing key: {key}")

        return result

    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to parse model response: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except anthropic.APIError as exc:
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {exc}")


# ── /fetch-text ─────────────────────────────────────────────────────────────

@app.post("/fetch-text")
@limiter.limit("5/minute")
async def fetch_article(request: Request, payload: FetchRequest):
    """Fetch a URL and extract its main article text via trafilatura."""
    try:
        import trafilatura

        url = str(payload.url)

        def _extract() -> str | None:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return None
            return trafilatura.extract(
                downloaded,
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
        raise HTTPException(status_code=422, detail=str(exc))


# ── Static frontend — mount last so API routes take precedence ───────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")
