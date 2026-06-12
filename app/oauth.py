"""Google ID-token (OIDC) verification with cached JWKS (Phase 2 extract)."""
import datetime
from typing import Optional


_google_jwks_cache: dict = {"keys": None, "fetched_at": None}
_GOOGLE_JWKS_TTL = datetime.timedelta(hours=6)

def _get_google_jwks() -> list:
    now = datetime.datetime.utcnow()
    if (
        _google_jwks_cache["keys"] is not None
        and _google_jwks_cache["fetched_at"] is not None
        and now - _google_jwks_cache["fetched_at"] < _GOOGLE_JWKS_TTL
    ):
        return _google_jwks_cache["keys"]
    import urllib.request as _ur2
    import json as _json
    with _ur2.urlopen("https://www.googleapis.com/oauth2/v3/certs", timeout=8) as r:
        data = _json.loads(r.read())
    _google_jwks_cache["keys"] = data.get("keys", [])
    _google_jwks_cache["fetched_at"] = now
    return _google_jwks_cache["keys"]

def _verify_google_jwt(token: str, client_id: str, expected_nonce: Optional[str] = None) -> dict:
    """
    Verify Google ID token locally using cached JWKS.
    If *expected_nonce* is provided it must match the nonce claim in the token.
    """
    from jose import jwt as jose_jwt, JWTError as _JWTErr
    from jose.exceptions import ExpiredSignatureError, JWTClaimsError

    try:
        header = jose_jwt.get_unverified_header(token)
    except Exception:
        raise ValueError("Malformed token header")

    kid = header.get("kid")
    keys = _get_google_jwks()
    key  = next((k for k in keys if k.get("kid") == kid), None)

    # If kid not found, refresh cache once and retry
    if key is None:
        _google_jwks_cache["fetched_at"] = None
        keys = _get_google_jwks()
        key  = next((k for k in keys if k.get("kid") == kid), None)

    if key is None:
        raise ValueError("Google public key not found")

    claims = jose_jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=client_id,
    )

    issuer = claims.get("iss", "")
    if issuer not in ("https://accounts.google.com", "accounts.google.com"):
        raise ValueError("Invalid token issuer")

    # Nonce binding: reject the token if the caller supplied a nonce and it doesn't match
    if expected_nonce is not None:
        token_nonce = claims.get("nonce", "")
        if not token_nonce or token_nonce != expected_nonce:
            raise ValueError("Nonce mismatch — possible replay attack")

    return claims
