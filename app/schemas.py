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
    word:    str = Field(..., min_length=1, max_length=60)
    context: str = Field(..., min_length=1, max_length=8_000)
    lang:    str = Field(default="auto", max_length=40)
    model:   str = Field(default="sonnet", max_length=40)  # haiku, gemini, gpt-4-mini, sonnet


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
