"""AI provider clients and thin call wrappers.

Extracted verbatim from main.py (Phase 2). Clients are instantiated at import
time, so this module must be imported only AFTER environment variables are
loaded (main.py imports it well below its load_dotenv() call, preserving the
original ordering).

The define endpoint resolves _call_groq/_call_google/_call_anthropic through
main's namespace (main re-imports them), so the existing tests that monkeypatch
`main._call_*` continue to work unchanged.
"""
import os

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


# ── Model wrappers ───────────────────────────────────────────────────────────

def _call_anthropic(prompt: str, model: str = "claude-haiku-4-5-20251001") -> str:
    """Call Anthropic API and return the response text."""
    message = anthropic_client.messages.create(
        model=model,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def _call_groq(prompt: str, *, phrase: bool = False) -> str:
    """Call Groq Fast tier with constrained-decoding JSON schema.

    Defaults to GPT-OSS 20B (`openai/gpt-oss-20b`), which supports Groq
    Structured Outputs with strict: true — the model cannot emit syntactically
    invalid JSON or omit required fields. Override via GROQ_FAST_MODEL.
    Retries Groq-side json_validate_failed 400s before surfacing an error.
    """
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("GROQ_API_KEY not configured")
    schema = DEFINE_PHRASE_SCHEMA if phrase else DEFINE_WORD_SCHEMA
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            response = groq_client.chat.completions.create(
                model=GROQ_FAST_MODEL,
                max_tokens=600,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "lexio_define_phrase" if phrase else "lexio_define_word",
                        "strict": True,
                        "schema": schema,
                    },
                },
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Groq returned empty content")
            return content.strip()
        except BadRequestError as exc:
            last_err = exc
            # Groq occasionally rejects a strict-json sample before returning it.
            if attempt < 2:
                continue
            raise
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
