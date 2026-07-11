"""AI provider clients and thin call wrappers.

Extracted verbatim from main.py (Phase 2). Clients are instantiated at import
time, so this module must be imported only AFTER environment variables are
loaded (main.py imports it well below its load_dotenv() call, preserving the
original ordering).

The define endpoint resolves _call_groq/_call_google/_call_anthropic through
main's namespace (main re-imports them), so the existing tests that monkeypatch
`main._call_*` continue to work unchanged.
"""
import base64
import os
import time

import anthropic
import openai
from groq import Groq, BadRequestError
from google import genai as google_genai
from google.genai import types as genai_types

# ── API Clients ──────────────────────────────────────────────────────────────
# openai_client is kept for the /ocr vision fallback in routers/account.py;
# OpenAI is no longer used for the /define fast tier (that's Groq below).
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
google_client = google_genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))


# ── /define response schemas (Groq strict JSON mode) ─────────────────────────
# strict: true requires every property listed + additionalProperties: false.
_REGISTER = {
    "type": "string",
    "enum": ["formal", "literary", "technical", "colloquial", "neutral", "archaic"],
}

DEFINE_WORD_SCHEMA = {
    "type": "object",
    "properties": {
        "pos":         {"type": "string"},
        "ipa":         {"type": ["string", "null"]},
        "definition":  {"type": "string"},
        "contextual":  {"type": "string"},
        "why":         {"type": "string"},
        "simpler":     {"type": ["string", "null"]},
        "etymology":   {"type": ["string", "null"]},
        "register":    _REGISTER,
    },
    "required": [
        "pos", "ipa", "definition", "contextual", "why", "simpler", "etymology", "register",
    ],
    "additionalProperties": False,
}

DEFINE_PHRASE_SCHEMA = {
    "type": "object",
    "properties": {
        "definition": {"type": "string"},
        "contextual": {"type": "string"},
        "why":        {"type": "string"},
        "register":   _REGISTER,
    },
    "required": ["definition", "contextual", "why", "register"],
    "additionalProperties": False,
}

GROQ_FAST_MODEL = os.getenv("GROQ_FAST_MODEL", "openai/gpt-oss-20b")
# Strict constrained decoding can burn tokens on retries; 600 was too low
# (Groq: "max completion tokens reached before generating a valid document").
GROQ_FAST_MAX_TOKENS = int(os.getenv("GROQ_FAST_MAX_TOKENS", "1200"))


# ── Model wrappers ───────────────────────────────────────────────────────────

def _call_anthropic(prompt: str, model: str = "claude-haiku-4-5-20251001") -> str:
    """Call Anthropic API and return the response text."""
    message = anthropic_client.messages.create(
        model=model,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def _call_anthropic_vision(prompt: str, image_bytes: bytes, mime_type: str = "image/png",
                            model: str = "claude-sonnet-4-5-20250929") -> str:
    """Call Anthropic with an image + text prompt — Lexio Glance's "Think
    deeper" escalation on a screen-point capture (P1-4). Claude Sonnet 4.5
    is multimodal; same base64-image-block shape Anthropic's SDK expects
    everywhere else, mirroring _call_google_vision's signature so the
    caller in define.py can pick either provider by model name alone.
    """
    message = anthropic_client.messages.create(
        model=model,
        max_tokens=900,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": base64.b64encode(image_bytes).decode("ascii"),
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return message.content[0].text.strip()


def _groq_schema_call(prompt: str, schema: dict, name: str, *, strict: bool) -> str:
    response = groq_client.chat.completions.create(
        model=GROQ_FAST_MODEL,
        max_tokens=GROQ_FAST_MAX_TOKENS,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": name, "strict": strict, "schema": schema},
        },
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Groq returned empty content")
    return content.strip()


def _call_groq(prompt: str, *, phrase: bool = False) -> str:
    """Call Groq Fast tier with constrained-decoding JSON schema.

    Defaults to GPT-OSS 20B (`openai/gpt-oss-20b`). Tries strict schema first,
    then best-effort schema — Groq occasionally returns 400 json_validate_failed
    under strict mode, especially with long or quote-heavy context text.
    """
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("GROQ_API_KEY not configured")
    schema = DEFINE_PHRASE_SCHEMA if phrase else DEFINE_WORD_SCHEMA
    name   = "lexio_define_phrase" if phrase else "lexio_define_word"
    last_err: Exception | None = None
    # (strict mode, attempt count)
    for strict, attempts in ((True, 4), (False, 3)):
        for attempt in range(attempts):
            try:
                return _groq_schema_call(prompt, schema, name, strict=strict)
            except BadRequestError as exc:
                last_err = exc
                time.sleep(0.2 * (attempt + 1))
    raise last_err or ValueError("Groq call failed")


def _call_google(prompt: str) -> str:
    """Call Google Gemini API and return the response text.

    Uses response_mime_type="application/json" so Gemini is forced into
    strict-JSON mode — without this the model occasionally emits literal
    newlines or unescaped quotes inside string values, producing
    JSONDecodeErrors that surface to the user as "unexpected response".
    """
    if not os.getenv("GOOGLE_API_KEY"):
        raise ValueError("GOOGLE_API_KEY not configured")
    response = google_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    return response.text.strip()


def _call_google_vision(prompt: str, image_bytes: bytes, mime_type: str = "image/png") -> str:
    """Call Gemini with an image + text prompt (Lexio Glance's screen-point
    mode) and return the response text. Same strict-JSON mode as
    _call_google; same fallback-to-parts read as the /ocr endpoint, since
    thinking mode can leave response.text empty even on success.
    """
    if not os.getenv("GOOGLE_API_KEY"):
        raise ValueError("GOOGLE_API_KEY not configured")
    response = google_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt,
        ],
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    text = (response.text or "").strip()
    if not text:
        try:
            parts = response.candidates[0].content.parts
            text = " ".join(
                p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False)
            ).strip()
        except Exception:
            pass
    return text
