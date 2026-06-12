"""JSON parsing helpers for tolerant model-output handling.

Extracted verbatim from main.py (Phase 2). AI models occasionally wrap JSON
in prose/code fences or emit literal control characters inside string values;
these helpers recover a valid object where possible.
"""
import json
import re


def _extract_json_object(text: str) -> str | None:
    """
    Best-effort extraction of the first top-level JSON object from a string.
    Helps when models wrap JSON with prose or code fences.
    """
    if not text:
        return None
    s = text.strip()
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == "\"":
                in_str = False
        else:
            if ch == "\"":
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
    return None


_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def _repair_json_strings(text: str) -> str:
    """Escape literal control characters (newlines, tabs, etc.) that appear
    INSIDE JSON string values. Gemini occasionally emits raw newlines inside
    its definitions, which is invalid JSON. This walker tracks string state
    and rewrites the offending characters as their escaped equivalents.
    Outside of strings, whitespace is left untouched."""
    out = []
    in_str = False
    esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
                out.append(ch)
            elif ch == "\\":
                esc = True
                out.append(ch)
            elif ch == '"':
                in_str = False
                out.append(ch)
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            elif _CTRL_RE.match(ch):
                # Drop other control chars rather than try to escape them
                pass
            else:
                out.append(ch)
        else:
            if ch == '"':
                in_str = True
            out.append(ch)
    return "".join(out)


def _safe_json_loads(text: str) -> dict:
    """
    Parse model output as JSON. Try in order:
      1. Strict json.loads
      2. Extract the first {...} block, parse that
      3. Repair common Gemini issues (literal newlines inside strings),
         then re-parse the extracted block.
    """
    try:
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError("Model output JSON is not an object")
        return obj
    except Exception:
        extracted = _extract_json_object(text)
        if not extracted:
            raise
        try:
            obj = json.loads(extracted)
        except json.JSONDecodeError:
            # Last-resort: escape literal control characters inside strings,
            # which is the most common Gemini failure mode.
            repaired = _repair_json_strings(extracted)
            obj = json.loads(repaired)
        if not isinstance(obj, dict):
            raise ValueError("Extracted JSON is not an object")
        return obj
