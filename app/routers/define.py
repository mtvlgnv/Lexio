"""/define endpoint + anonymous search logging (Phase 2 extract)."""
import asyncio
import base64
import binascii
import json
import datetime
import logging

import anthropic
from groq import BadRequestError
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
from app.json_utils import _safe_json_loads, _normalize_define_keys
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

def _profile_note(user: Optional[User]) -> str:
    """ROADMAP P1-5 Phase 1: fold the signed-in reader's profile into the
    prompt — domain sense + explanation complexity, never forced onto
    words where it doesn't fit (the over-personalization guard is the
    whole point of this feature; it's the #1 risk of getting it wrong).
    Anonymous users and users with no profile set get an empty string.
    """
    if not user or not getattr(user, "profile_json", None):
        return ""
    try:
        profile = json.loads(user.profile_json)
    except (TypeError, ValueError):
        return ""
    about = (profile.get("about") or "").strip()
    level = (profile.get("english_level") or "").strip()
    if not about and not level:
        return ""
    parts = []
    if about:
        parts.append(f"Reader profile: {about}.")
    if level:
        parts.append(f"English level: {level}.")
    parts.append(
        "If the word has a domain sense plausible in the on-screen context AND relevant to "
        "the reader's world, prefer/mention it; calibrate explanation complexity to their level. "
        "NEVER force the reader's domain onto words where it doesn't fit the context."
    )
    return " " + " ".join(parts)

VISION_MAX_IMAGE_BYTES = 6 * 1024 * 1024  # base64 inflates ~33%; keep the decoded image well under Gemini's limits

async def _define_from_image(req: DefineRequest, bg: BackgroundTasks,
                              user: Optional[User], db: DBSession, ip: str):
    """Lexio Glance's screen-point mode: no word/context up front — the model
    identifies the word itself from a screenshot centered on the cursor.
    Baseline is always routed through Gemini ("balanced" hourly weight),
    ungated, since this mode has no free-tier text alternative to fall
    back to. req.model == "deep" escalates to Claude Sonnet 4.5 ("Think
    deeper", P1-4/B2) — weight 3, Pro-gated with the same 403 pro_required
    flow text mode uses.

    Metered as a normal LOOKUP (kind="lookup": ANON_LOOKUP_LIMIT anon,
    FREE_LOOKUP_LIMIT free, unbounded Pro) — NOT the photo-scanner bucket
    (kind="ocr", 3/month): screen lookups are the desktop app's every-single
    -lookup path now, and the marketing promise is "20 free lookups/month".
    """
    try:
        image_bytes = base64.b64decode(req.image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="image_base64 is not valid base64.")
    if not image_bytes or len(image_bytes) > VISION_MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="Image is missing or too large.")
    mime = (req.image_mime or "image/png").lower().strip()
    if mime not in ("image/png", "image/jpeg"):
        raise HTTPException(status_code=422, detail="image_mime must be image/png or image/jpeg.")

    # Baseline is always Gemini/"balanced" (the only vision-capable model,
    # ungated — this mode has no free-tier text alternative to fall back
    # to). req.model == "deep" escalates to Claude Sonnet 4.5 for "Think
    # deeper" (P1-4/B2) — weight 3, Pro-gated like text mode's Deep.
    actual_model = "deep" if (req.model or "").lower().strip() == "deep" else "balanced"

    if actual_model == "deep" and not _has_pro_access(db, user):
        raise HTTPException(
            status_code=403,
            detail={
                "code":    "pro_required",
                "model":   actual_model,
                "message": "Think deeper requires a Pro plan. Upgrade to unlock it, or stick with the fast answer.",
            },
        )

    hourly = _check_hourly_limit(db, user, actual_model)
    if not hourly["allowed"]:
        if hourly.get("kind") == "monthly":
            raise HTTPException(
                status_code=402,
                detail={"code": "limit_exceeded", "kind": "monthly_credit",
                        "used": hourly["month_used"], "limit": hourly["month_limit"],
                        "weight": hourly["weight"], "model": actual_model},
            )
        raise HTTPException(
            status_code=429,
            detail={"code": "hourly_limit", "weight": hourly["weight"], "used": hourly["used"],
                    "limit": hourly["limit"], "reset_in": hourly["reset_in"], "model": actual_model},
            headers={"Retry-After": str(hourly["reset_in"])},
        )

    usage = _check_usage(db, user, ip, "lookup")
    if not usage["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={"code": "limit_exceeded", "kind": "lookup", "used": usage["used"], "limit": usage["limit"]},
        )

    lang_code = (req.lang or "auto").strip().lower()
    lang_name = LANG_NAMES.get(lang_code)
    if lang_name:
        lang_note = (
            f"The semantic fields (definition, contextual, why, etymology) MUST be written entirely in {lang_name}. "
            f"The structural/label fields (word, pos, ipa, simpler, register) MUST remain in English, except "
            f"'word' itself which must be transcribed exactly as it appears in the image."
        )
    else:
        lang_note = (
            "Write semantic fields (definition, contextual, why, etymology) in the same language the image's text "
            "is written in. Keep structural/label fields (pos, ipa, simpler, register) in English."
        )

    # Deep ("Think deeper") adds two extra keys on top of the same base
    # ask — nuance (connotation/register vs. near synonyms — why THIS word)
    # and examples (2 short sentences reusing the word in the same sense).
    deep_note = (
        " Also include nuance (why this exact word was chosen over close synonyms — "
        "connotation, register, precision) and examples (a JSON array of exactly 2 short "
        "original sentences reusing the word in this same sense)."
        if actual_model == "deep" else ""
    )
    prompt = (
        "This is a screenshot of whatever the user is currently reading on their screen. "
        "A magenta ring (a small circle with a white halo) has been drawn on the image at the exact point "
        "of the user's pointer. Identify the single word the ring is centered on — the word directly under "
        "or immediately touching the ring. If that word is part of a fixed multi-word unit (a phrasal verb, "
        "idiom, or proper name), you may return the whole unit. If text at the ring appears visibly "
        "selected/highlighted, that selection is the target. "
        "IMPORTANT: never pick a more prominent, interesting, or central-looking word from elsewhere in the "
        "screenshot — only the word at the ring matters; everything else is unrelated background. "
        "Then define that word as it is used in its surrounding sentence on screen. "
        f"{lang_note} "
        "Respond in JSON only, with these keys: word (the exact word/phrase at the ring), pos, ipa, "
        "definition, contextual (what it means in this specific sentence), why (why the author chose this word "
        "here), simpler, etymology, register. Use null for ipa, simpler, or etymology when uncertain. "
        f"Keep each field to 1-2 short sentences.{deep_note}{_profile_note(user)}"
    )

    def _call_and_parse():
        if actual_model == "deep":
            text = ai._call_anthropic_vision(prompt, image_bytes, mime_type=mime)
        else:
            text = ai._call_google_vision(prompt, image_bytes, mime_type=mime)
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(l for l in lines if not l.startswith("```")).strip()
        parsed = _normalize_define_keys(_safe_json_loads(text))
        if "word" not in parsed or not str(parsed["word"]).strip():
            raise ValueError(f"Missing key: word (got {list(parsed.keys())})")
        return parsed

    _DEFINE_ATTEMPTS = 3
    result = None
    last_exc: Exception | None = None
    try:
        for attempt in range(_DEFINE_ATTEMPTS):
            try:
                result = await asyncio.to_thread(_call_and_parse)
                break
            except (json.JSONDecodeError, ValueError) as exc:
                last_exc = exc
                if attempt < _DEFINE_ATTEMPTS - 1:
                    logger.warning("/define (image) attempt failed (%s) — retry %d/%d",
                                   exc, attempt + 1, _DEFINE_ATTEMPTS)
        if result is None:
            raise last_exc
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("/define (image) parse error: %s", exc)
        raise HTTPException(status_code=502, detail="The AI model returned an unexpected response. Please try again.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("/define (image) unexpected error: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="An unexpected error occurred. Please try again.")

    hourly_post = _consume_hourly_credits(db, user, actual_model)
    usage_post = _consume_usage(db, user, ip, "lookup")

    word = str(result.get("word", "")).strip()
    bg.add_task(_log_search, word)
    if user:
        bg.add_task(_log_user_search, user.id, word)

    return {
        **result,
        "_usage":  {"used": usage_post["used"], "limit": usage_post["limit"]},
        "_hourly": {
            "used": hourly_post["used"], "limit": hourly_post["limit"], "weight": hourly_post["weight"],
            "reset_in": hourly_post["reset_in"], "month_used": hourly_post["month_used"],
            "month_limit": hourly_post["month_limit"],
        },
    }


@router.post("/define")
@limiter.limit("20/minute")
async def define_word(request: Request, req: DefineRequest, bg: BackgroundTasks,
                      user: Optional[User] = Depends(optional_user),
                      db: DBSession = Depends(get_db)):
    ip = _get_client_ip(request)

    if req.image_base64:
        return await _define_from_image(req, bg, user, db, ip)

    if not req.word or not req.context:
        raise HTTPException(status_code=422, detail="word and context are required for a text-based lookup.")

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

    # json.dumps so quotes/newlines in AX-captured context can't break the prompt.
    # Cap context length — long documents shouldn't inflate the prompt or token budget.
    word_lit = json.dumps(req.word.strip()[:60])
    ctx_lit  = json.dumps(req.context.strip()[:3000])
    concise  = "Keep each field to 1-2 short sentences. Respond in JSON only."
    profile_note = _profile_note(user)

    if is_phrase:
        prompt = (
            f"The phrase or sentence {word_lit} appears in this text: {ctx_lit}\n"
            f"{lang_note} {concise}{profile_note}"
        )
        required_keys = ("definition", "contextual")
    else:
        prompt = (
            f"The word {word_lit} appears in this text: {ctx_lit}\n"
            f"{lang_note} {concise} Use null for ipa, simpler, or etymology when uncertain.{profile_note}"
        )
        required_keys = ("pos", "contextual")

    # ── AI call (no debit until we have a valid response) ──────────────────
    def _call_and_parse():
        if actual_model == "fast":
            text = ai._call_groq(prompt, phrase=is_phrase)  # GPT-OSS 20B, strict JSON
        elif actual_model == "balanced":
            text = ai._call_google(prompt)          # Gemini 2.5 Flash
        else:  # deep
            text = ai._call_anthropic(prompt, "claude-sonnet-4-5-20250929")

        # Clean up markdown code blocks if present
        if text.startswith("```"):
            lines = text.splitlines()
            text  = "\n".join(l for l in lines if not l.startswith("```")).strip()

        parsed = _normalize_define_keys(_safe_json_loads(text))
        for key in required_keys:
            if key not in parsed:
                raise ValueError(f"Missing key: {key} (got {list(parsed.keys())})")
        return parsed

    # Up to 3 attempts on parse/value errors — providers occasionally produce
    # malformed JSON or wrong keys on the first sample; a fresh draw usually
    # succeeds. Provider SDKs are synchronous: run them in a thread so the
    # multi-second AI call doesn't block the event loop for other requests.
    _DEFINE_ATTEMPTS = 3
    result = None
    last_exc: Exception | None = None
    try:
        for attempt in range(_DEFINE_ATTEMPTS):
            try:
                result = await asyncio.to_thread(_call_and_parse)
                break
            except (json.JSONDecodeError, ValueError, BadRequestError) as exc:
                last_exc = exc
                if attempt < _DEFINE_ATTEMPTS - 1:
                    logger.warning("/define %s attempt failed (%s) — retry %d/%d",
                                   actual_model, exc, attempt + 1, _DEFINE_ATTEMPTS)
        if result is None:
            raise last_exc
    except json.JSONDecodeError as exc:
        logger.error("/define JSON parse error: %s", exc)
        raise HTTPException(status_code=502, detail="The AI model returned an unexpected response. Please try again.")
    except ValueError as exc:
        logger.error("/define value error: %s", exc)
        raise HTTPException(status_code=502, detail="The AI model returned an unexpected response. Please try again.")
    except BadRequestError as exc:
        logger.error("/define Groq error: %s", exc)
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
