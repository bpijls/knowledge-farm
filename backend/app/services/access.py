"""One shared access key for the whole site (ACCESS_KEY in .env; empty = open).

The browser trades the key for an HttpOnly cookie at POST /api/login. Because EventSource and
<img> cannot send headers, the cookie is what normally authorises a request; scripts may send
the key itself in an `X-Access-Key` header instead.
"""
import hashlib
import hmac

from fastapi import Request

from app.config import settings

COOKIE = "kf_access"
# Reachable without the key: the login itself, and what the login screen needs to decide.
OPEN_PATHS = {"/api/health", "/api/session", "/api/login", "/api/logout"}


def required() -> bool:
    return bool(settings.access_key)


def token() -> str:
    """What the cookie holds: derived from the key, so the key itself never sits in a cookie."""
    return hmac.new(settings.access_key.encode(), b"knowledge-farm session", hashlib.sha256).hexdigest()


def key_matches(candidate: str) -> bool:
    return hmac.compare_digest(candidate.encode(), settings.access_key.encode())


def authorised(request: Request) -> bool:
    if not required():
        return True
    header = request.headers.get("x-access-key")
    if header is not None and key_matches(header):
        return True
    return hmac.compare_digest(request.cookies.get(COOKIE, "").encode(), token().encode())
