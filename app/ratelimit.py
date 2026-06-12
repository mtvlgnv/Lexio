"""Shared slowapi limiter (Phase 2 extract)."""
from slowapi import Limiter
from app.limits import _get_client_ip

limiter = Limiter(key_func=_get_client_ip)
