"""/define endpoint + anonymous search logging (Phase 2 extract)."""
import asyncio
import json
import datetime
import logging

import anthropic
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session as DBSession

from app import ai
from app.db import get_db, SessionLocal
from app.models import User, SearchLog, UserSearchLog
from app.security import optional_user
from app.limits import (
    _get_client_ip, _check_hourly_limit, _consume_hourly_credits,
    _check_usage, _consume_usage, _has_pro_access,
)
from app.json_utils import _safe_json_loads
from app.ratelimit import limiter
from app.schemas import DefineRequest

logger = logging.getLogger("lexio")
router = APIRouter()


# ── Search logging (fire-and-forget, completely anonymous) ────────────────────

def _log_search(word: str) -> None:
    """Write one anonymous row. Normalise to lowercase, skip very short words."""
    w = word.strip().lower()
    if len(w) < 2:
        return
    db = SessionLocal()
    try:
        db.add(SearchLog(word=w))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

def _log_user_search(user_id: int, word: str) -> None:
    """Write one per-user search row."""
    w = word.strip().lower()
    if len(w) < 2:
        return
    db = SessionLocal()
    try:
        db.add(UserSearchLog(user_id=user_id, word=w))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ── /define ──────────────────────────────────────────────────────────────────

LANG_NAMES = {
    'en':'English','es':'Spanish','fr':'French','de':'German','it':'Italian',
    'pt':'Portuguese','ru':'Russian','zh':'Chinese','ja':'Japanese','ko':'Korean',
    'ar':'Arabic','hi':'Hindi','nl':'Dutch','pl':'Polish','tr':'Turkish','sv':'Swedish',
}

@router.post("/define")
@limiter.limit("20/minute")
async def define_word(request: Request, req: DefineRequest, bg: BackgroundTasks,
                      user: Optional[User] = Depends(optional_user),
                      db: DBSession = Depends(get_db)):
    ip = _get_client_ip(request)

    # Resolve the requested mode up-front so we can weight the hourly check.
    _model_map = {
        "fast": "fast", "balanced": "balanced", "deep": "deep",
        "haiku": "fast", "gpt-4-mini": "fast", "gpt-4o-mini": "fast",
        "gemini": "balanced", "sonnet": "deep",
    }
    actual_model = _model_map.get((req.model or "fast").lower().strip(), "fast")

    # ── Server-side model gate ──────────────────────────────────────────────
    # Balanced and Deep are Pro/trial only. Anonymous and free users get Fast,
    # regardless of what the frontend sends.
    if actual_model in ("balanced", "deep") and not _has_pro_access(db, user):
        raise HTTPException(
            status_code=403,
            detail={
                "code":     "pro_required",
                "model":    actual_model,
                "message":  f"{actual_model.title()} mode requires a Pro plan. Upgrade to unlock all three models, or use Fast (free).",
            },
        )

    # ── Pre-flight checks (no debit yet) ────────────────────────────────────
    # Hourly + monthly weighted rate limit (per-user; anonymous skipped).
    hourly = _check_hourly_limit(db, user, actual_model)
    if not hourly["allowed"]:
        if hourly.get("kind") == "monthly":
            # Pro monthly credit ceiling — 402 so the existing limit modal
            # handles it; user has to wait for next billing cycle.
            raise HTTPException(
                status_code=402,
                detail={
                    "code":        "limit_exceeded",
                    "kind":        "monthly_credit",
                    "used":        hourly["month_used"],
                    "limit":       hourly["month_limit"],
                    "weight":      hourly["weight"],
                    "model":       actual_model,
                },
            )
        # Hourly: 429 with Retry-After so clients can back off
        raise HTTPException(
            status_code=429,
            detail={
                "code":     "hourly_limit",
                "weight":   hourly["weight"],
                "used":     hourly["used"],
                "limit":    hourly["limit"],
                "reset_in": hourly["reset_in"],
                "model":    actual_model,
            },
            headers={"Retry-After": str(hourly["reset_in"])},
        )

    usage = _check_usage(db, user, ip, "lookup")
    if not usage["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={"code": "limit_exceeded", "kind": "lookup",
                    "used": usage["used"], "limit": usage["limit"]},
        )

    lang_code    = (req.lang or 'auto').strip().lower()
    lang_name    = LANG_NAMES.get(lang_code)   # None if auto/unknown

    # Structural fields (pos, ipa, register, simpler) are always English because
    # they are used as machine-readable labels in the UI.  Semantic fields
    # (definition, contextual, why, etymology) are localised when a language is
    # explicitly chosen, or matched to the input language when lang is 'auto'.
    if lang_name:
        lang_note = (
            f"The semantic fields (definition, contextual, why, etymology) MUST be written entirely in {lang_name}. "
            f"The structural/label fields (pos, ipa, simpler, register) MUST remain in English."
        )
    else:
        lang_note = (
            "Write semantic fields (definition, contextual, why, etymology) in the same language as the input text. "
            "Keep structural/label fields (pos, ipa, simpler, register) in English."
        )

    word_count = len(req.word.strip().split())
    is_phrase   = word_count > 1

    if is_phrase:
        # Phrase / sentence: skip pos & ipa, focus on meaning and usage
        prompt = (
            f'The phrase or sentence "{req.word}" appears in this text: "{req.context}"\n'
            f"{lang_note} Respond ONLY in valid JSON with no markdown:\n"
            '{\"definition\": \"meaning of this phrase/sentence, 1-2 sentences\", '
            '\"contextual\": \"what it specifically means in this passage, 1-2 sentences\", '
            '\"why\": \"why the author chose this phrasing, 1 sentence\", '
            '\"register\": \"exactly one of these English labels: formal, literary, technical, colloquial, neutral, archaic\"}'
        )
        required_keys = ("definition", "contextual")
    else:
        # Single word: full analysis
        prompt = (
            f'The word "{req.word}" appears in this text: "{req.context}"\n'
            f"{lang_note} Respond ONLY in valid JSON with no markdown:\n"
            '{\"pos\": \"English label: noun, verb, adjective, adverb, etc.\", '
            '\"ipa\": \"IPA transcription e.g. /ɪˈfɛm.ər.əl/ — or null if uncertain\", '
            '\"definition\": \"general dictionary definition, 1 sentence\", '
            '\"contextual\": \"definition as used in this passage, 1-2 sentences\", '
            '\"why\": \"why this word rather than a simpler synonym, 1 sentence\", '
            '\"simpler\": \"simplest English one-word synonym, or null if none applies\", '
            '\"etymology\": \"brief word origin, e.g. from Latin ephemeron — or null if uncertain\", '
            '\"register\": \"exactly one of these English labels: formal, literary, technical, colloquial, neutral, archaic\"}'
        )
        required_keys = ("pos", "contextual")

    # ── AI call (no debit until we have a valid response) ──────────────────
    def _call_and_parse():
        if actual_model == "fast":
            text = ai._call_groq(prompt)            # Llama 3.1 8B Instant (Groq)
        elif actual_model == "balanced":
            text = ai._call_google(prompt)          # Gemini 2.5 Flash
        else:  # deep
            text = ai._call_anthropic(prompt, "claude-sonnet-4-5-20250929")

        # Clean up markdown code blocks if present
        if text.startswith("```"):
            lines = text.splitlines()
            text  = "\n".join(l for l in lines if not l.startswith("```")).strip()

        parsed = _safe_json_loads(text)
        for key in required_keys:
            if key not in parsed:
                raise ValueError(f"Missing key: {key}")
        return parsed

    # Single retry on parse/value errors — Gemini occasionally produces
    # malformed JSON on the first call; a fresh sample usually succeeds.
    # The provider SDKs are synchronous: run them in a thread so the
    # multi-second AI call doesn't block the event loop for every other
    # request on this worker.
    try:
        try:
            result = await asyncio.to_thread(_call_and_parse)
        except (json.JSONDecodeError, ValueError) as first_exc:
            logger.warning("/define %s parse failed (%s) — retrying once",
                           actual_model, first_exc)
            result = await asyncio.to_thread(_call_and_parse)
    except json.JSONDecodeError as exc:
        logger.error("/define JSON parse error: %s", exc)
        raise HTTPException(status_code=502, detail="The AI model returned an unexpected response. Please try again.")
    except ValueError as exc:
        logger.error("/define value error: %s", exc)
        raise HTTPException(status_code=502, detail="The AI model returned an unexpected response. Please try again.")
    except anthropic.APIError as exc:
        logger.error("/define Anthropic error: %s", exc)
        raise HTTPException(status_code=502, detail="AI provider error. Please try again.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("/define unexpected error: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="An unexpected error occurred. Please try again.")

    # ── Debit only after a valid response is in hand ────────────────────────
    hourly_post = _consume_hourly_credits(db, user, actual_model)
    usage_post  = _consume_usage(db, user, ip, "lookup")

    # Save user's model preference if authenticated
    if user:
        try:
            user_record = db.query(User).filter(User.id == user.id).first()
            if user_record and user_record.preferred_model != actual_model:
                user_record.preferred_model = actual_model
                db.commit()
        except Exception:
            db.rollback()

    # Log anonymously (always) and per-user (when authenticated)
    bg.add_task(_log_search, req.word)
    if user:
        bg.add_task(_log_user_search, user.id, req.word)
    return {
        **result,
        "_usage":  {"used": usage_post["used"], "limit": usage_post["limit"]},
        "_hourly": {
            "used":        hourly_post["used"],
            "limit":       hourly_post["limit"],
            "weight":      hourly_post["weight"],
            "reset_in":    hourly_post["reset_in"],
            "month_used":  hourly_post["month_used"],
            "month_limit": hourly_post["month_limit"],
        },
    }
