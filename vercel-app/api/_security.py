"""Request guards for the public Vercel demo.

The public demo must stay usable by a human visitor while remaining expensive
to abuse. This module adds, in order:

1. a configured signing secret (fail closed if missing),
2. an origin/referer allowlist,
3. a short-lived HMAC bearer token minted by /api/token,
4. a per-IP sliding-window rate limit,
5. a per-instance daily request budget as a best-effort spend cap.

The daily budget is intentionally labelled best effort: Vercel may run several
function instances, so each instance keeps its own counter. Move the counters
to a shared store (Upstash/Redis or Vercel KV) if a hard global cap is needed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import threading
import time
from collections import deque
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

TOKEN_PREFIX = "v1"
TOKEN_CLOCK_SKEW_SECONDS = 30
TOKEN_MAX_LIFETIME_SECONDS = 600
MAX_BODY_BYTES = 256_000
AUTH_COOKIE = "pr_auth"
AUTH_MESSAGE = "vista-pr-auth-v1"

# Exact hosts that serve the demo UI.
EXACT_HOSTS = {
    "pr.prachiadmane.com",
    "vercel-app-gules-three.vercel.app",
    "vercel-app-prachi-8a13.vercel.app",
    "vercel-app-git-main-prachi-8a13.vercel.app",
    "localhost:3000",
    "127.0.0.1:3000",
}


def _secret() -> str:
    return (os.environ.get("DEMO_SIGNING_SECRET") or "").strip()


def _site_password() -> str:
    return (os.environ.get("SITE_PASSWORD") or "").strip()


def _expected_auth_value() -> str:
    password = _site_password()
    if not password:
        return ""
    digest = hmac.new(
        password.encode("utf-8"),
        AUTH_MESSAGE.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _is_authenticated(request: Request) -> bool:
    expected = _expected_auth_value()
    if not expected:
        return False
    provided = (request.cookies.get(AUTH_COOKIE) or "").strip()
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int((os.environ.get(name) or "").strip() or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _base64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def client_ip(request: Request) -> str:
    # Vercel sets x-real-ip; the leftmost x-forwarded-for entry can be supplied
    # by the caller, so prefer the platform header and the rightmost fallback.
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    forwarded = [
        part.strip()
        for part in (request.headers.get("x-forwarded-for") or "").split(",")
        if part.strip()
    ]
    if forwarded:
        return forwarded[-1]
    return "unknown"


def _host_from(value: str) -> str:
    if not value:
        return ""
    try:
        return urlsplit(value).netloc.lower()
    except ValueError:
        return ""


def _host_allowed(host: str) -> bool:
    if not host:
        return False
    if host in EXACT_HOSTS:
        return True
    return host.endswith(".vercel.app") and "prachi-8a13" in host


def verify_access_token(token: str) -> bool:
    parts = (token or "").split(".")
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        return False
    try:
        expires_at = int(parts[1])
    except ValueError:
        return False

    now = int(time.time())
    if expires_at < now - TOKEN_CLOCK_SKEW_SECONDS:
        return False
    if expires_at > now + TOKEN_MAX_LIFETIME_SECONDS:
        return False

    expected = hmac.new(
        _secret().encode("utf-8"),
        f"{TOKEN_PREFIX}.{expires_at}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    try:
        provided = _base64url_decode(parts[2])
    except (ValueError, UnicodeEncodeError):
        return False
    return hmac.compare_digest(expected, provided)


class _SlidingWindow:
    """Thread-safe sliding-window counter (the API runs sync handlers in a pool)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def count(self, key: str, window_seconds: int) -> int:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 0
            while hits and hits[0] <= cutoff:
                hits.popleft()
            return len(hits)

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            if len(self._hits) > 5000:
                self._hits = {
                    name: hits
                    for name, hits in self._hits.items()
                    if hits and hits[-1] > cutoff
                }
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(1, int(hits[0] + window_seconds - now) + 1)
                return False, retry_after
            hits.append(now)
            return True, 0


_ip_window = _SlidingWindow()
_ip_day = _SlidingWindow()
_global_day = _SlidingWindow()
_client_day = _SlidingWindow()

CLIENT_COOKIE = "pr_client"


def _caps() -> tuple[int, int, int, int]:
    return (
        _int_env("DEMO_IP_REQUESTS_PER_10_MIN", 8, 1, 100),
        _int_env("DEMO_IP_REQUESTS_PER_DAY", 25, 1, 1000),
        _int_env("DEMO_CLIENT_REQUESTS_PER_DAY", 15, 1, 1000),
        _int_env("DEMO_DAILY_REQUEST_CAP", 100, 1, 5000),
    )


def remaining_quota(request: Request) -> dict:
    """Report what is left without consuming a call."""
    per_window, per_day, per_client, daily_cap = _caps()
    ip = client_ip(request)
    client = (request.cookies.get(CLIENT_COOKIE) or "").strip()

    def left(window: _SlidingWindow, key: str, limit: int) -> int:
        used = window.count(key, 24 * 60 * 60) if window is not _ip_window else window.count(key, 10 * 60)
        return max(0, limit - used)

    return {
        "perSession": left(_ip_window, f"ip:{ip}", per_window),
        "perSessionLimit": per_window,
        "perDay": left(_ip_day, f"ip:{ip}", per_day),
        "perDayLimit": per_day,
        "remaining": min(
            left(_ip_window, f"ip:{ip}", per_window),
            left(_ip_day, f"ip:{ip}", per_day),
            left(_client_day, f"client:{client}", per_client) if client else per_client,
            left(_global_day, "global", daily_cap),
        ),
    }


def guard(request: Request) -> None:
    """Raise an HTTPException unless the request may run a paid research call."""
    if not _is_authenticated(request):
        raise HTTPException(
            status_code=401,
            detail="Sign in required.",
        )
    if len(_secret()) < 32:
        raise HTTPException(
            status_code=503,
            detail="The demo is not configured for requests yet.",
        )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Request body is too large.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length.")

    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if not _host_allowed(_host_from(origin)):
        raise HTTPException(
            status_code=403,
            detail="Requests must come from the demo site.",
        )

    authorization = request.headers.get("authorization") or ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not verify_access_token(token.strip()):
        raise HTTPException(
            status_code=401,
            detail="Missing or expired demo token. Reload the page and try again.",
        )

    ip = client_ip(request)
    per_window, per_day, per_client, daily_cap = _caps()
    client = (request.cookies.get(CLIENT_COOKIE) or "").strip() or f"ip:{ip}"

    allowed, retry_after = _global_day.allow("global", daily_cap, 24 * 60 * 60)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="The research budget for today is used up. Try again tomorrow.",
            headers={"Retry-After": str(retry_after)},
        )

    allowed, retry_after = _client_day.allow(f"client:{client}", per_client, 24 * 60 * 60)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You have used today's {per_client} research calls. "
                "The limit resets tomorrow; ask for a higher limit if you need more."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    allowed, retry_after = _ip_window.allow(f"ip:{ip}", per_window, 10 * 60)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many research requests from this connection. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    allowed, retry_after = _ip_day.allow(f"ip:{ip}", per_day, 24 * 60 * 60)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="This connection has reached its daily research limit. Please try again tomorrow.",
            headers={"Retry-After": str(retry_after)},
        )


def log_request(request: Request, action: str) -> None:
    """One compact line per paid call, with no raw IP or payload."""
    digest = hashlib.sha256(client_ip(request).encode("utf-8")).hexdigest()[:10]
    print(f"demo_request action={action} ip={digest}", flush=True)
