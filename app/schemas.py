"""Pydantic request/response schemas (Phase 2 extract)."""
from typing import Optional
from pydantic import BaseModel, Field, AnyHttpUrl, EmailStr


class WBEntry(BaseModel):
    word:       str = Field(..., min_length=1, max_length=200)
    pos:        Optional[str] = Field(default=None, max_length=100)
    ipa:        Optional[str] = Field(default=None, max_length=200)
    definition: Optional[str] = Field(default=None, max_length=2000)
    contextual: Optional[str] = Field(default=None, max_length=2000)
    why:        Optional[str] = Field(default=None, max_length=1000)
    simpler:    Optional[str] = Field(default=None, max_length=200)
    etymology:  Optional[str] = Field(default=None, max_length=1000)
    register:   Optional[str] = Field(default=None, max_length=100)
    savedAt:    Optional[str] = Field(default=None, max_length=50)
    context:    Optional[str] = Field(default=None, max_length=1000)

    model_config = {"extra": "ignore"}   # silently drop unknown fields

class WBSyncRequest(BaseModel):
    entries: list[WBEntry] = Field(default_factory=list, max_length=500)


class DefineRequest(BaseModel):
    # Text-based lookup: word + surrounding context, both required.
    # Image-based lookup (Lexio Glance's screen-point mode): image_base64
    # instead, word/context are unknown up front (the model identifies the
    # word itself) so both become optional and are validated in the route.
    word:          Optional[str] = Field(default=None, max_length=60)
    context:       Optional[str] = Field(default=None, max_length=8_000)
    image_base64:  Optional[str] = Field(default=None, max_length=8_000_000)
    image_mime:    str = Field(default="image/png", max_length=40)
    lang:          str = Field(default="auto", max_length=40)
    model:         str = Field(default="sonnet", max_length=40)  # haiku, gemini, gpt-4-mini, sonnet


class ProfileRequest(BaseModel):
    # ROADMAP P1-5 Phase 1 — one free-text line plus two calibration fields.
    # All optional/nullable: a partial profile (or none) is the common case.
    about:         Optional[str] = Field(default=None, max_length=300)
    english_level: Optional[str] = Field(default=None, max_length=40)
    native_lang:   Optional[str] = Field(default=None, max_length=40)

    model_config = {"extra": "ignore"}


class FeedbackRequest(BaseModel):
    # B13: 👍/👎 on a definition. No context text accepted on purpose —
    # this is the prompt-quality dataset, not a support ticket.
    word:    str = Field(..., min_length=1, max_length=100)
    model:   str = Field(..., max_length=40)
    verdict: str = Field(..., pattern="^(up|down)$")
    lang:    str = Field(default="auto", max_length=40)
    mode:    str = Field(..., pattern="^(text|image)$")


class FetchRequest(BaseModel):
    url: AnyHttpUrl


class RegisterRequest(BaseModel):
    email:    EmailStr
    password: str = Field(..., min_length=8)
    name:     Optional[str] = Field(default=None, max_length=80)

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

from app.schemas import WBEntry, WBSyncRequest
