"""AI provider clients and thin call wrappers.

Extracted verbatim from main.py (Phase 2). Clients are instantiated at import
time, so this module must be imported only AFTER environment variables are
loaded (main.py imports it well below its load_dotenv() call, preserving the
original ordering).

The define endpoint resolves _call_openai/_call_google/_call_anthropic through
main's namespace (main re-imports them), so the existing tests that monkeypatch
`main._call_*` continue to work unchanged.
"""
import os

import anthropic
import openai
from google import genai as google_genai
from google.genai import types as genai_types

# ── API Clients ──────────────────────────────────────────────────────────────
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
google_client = google_genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))


# ── Model wrappers ───────────────────────────────────────────────────────────

def _call_anthropic(prompt: str, model: str = "claude-haiku-4-5-20251001") -> str:
    """Call Anthropic API and return the response text."""
    message = anthropic_client.messages.create(
        model=model,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def _call_openai(prompt: str) -> str:
    """Call OpenAI API (GPT-4 mini) and return the response text."""
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not configured")
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


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
