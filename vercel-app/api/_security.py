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

from _store import (
    StoreError,
    bump as store_bump,
    configured as store_configured,
    read_counts as store_read_counts,
    seconds_to_utc_midnight,
)

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

    def retry_after(self, key: str, window_seconds: int) -> int:
        """Seconds until the oldest hit leaves the window (0 when empty)."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 0
            return max(1, int(hits[0] + window_seconds - now) + 1)

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
WINDOW_SECONDS = 10 * 60
DAY_SECONDS = 24 * 60 * 60


def _caps() -> tuple[int, int, int, int]:
    return (
        _int_env("DEMO_IP_REQUESTS_PER_10_MIN", 8, 1, 100),
        _int_env("DEMO_IP_REQUESTS_PER_DAY", 25, 1, 1000),
        _int_env("DEMO_CLIENT_REQUESTS_PER_DAY", 15, 1, 1000),
        _int_env("DEMO_DAILY_REQUEST_CAP", 100, 1, 5000),
    )


def _shared_keys(ip: str, client: str, now: float) -> dict[str, tuple[str, int]]:
    """Redis key plus TTL for each counter.

    Keys carry the UTC date or the 10-minute bucket, so a late TTL can never let
    yesterday's count leak into today. The TTL is only a cleanup hint.
    """
    day = time.strftime("%Y%m%d", time.gmtime(now))
    day_ttl = seconds_to_utc_midnight(now)
    bucket = int(now // WINDOW_SECONDS)
    return {
        "global": (f"pr:day:{day}:global", day_ttl),
        "client": (f"pr:day:{day}:client:{client or 'anon'}", day_ttl),
        "window": (f"pr:win:{bucket}:ip:{ip}", WINDOW_SECONDS + 120),
        "ipday": (f"pr:day:{day}:ip:{ip}", day_ttl),
    }


def _memory_used(ip: str, client: str) -> dict[str, int]:
    return {
        "global": _global_day.count("global", DAY_SECONDS),
        "client": _client_day.count(f"client:{client}", DAY_SECONDS) if client else 0,
        "window": _ip_window.count(f"ip:{ip}", WINDOW_SECONDS),
        "ipday": _ip_day.count(f"ip:{ip}", DAY_SECONDS),
    }


def _shared_used(ip: str, client: str, now: float) -> dict[str, int]:
    keys = _shared_keys(ip, client, now)
    names = ("global", "client", "window", "ipday")
    return dict(zip(names, store_read_counts([keys[name][0] for name in names])))


def _quota_payload(
    used: dict[str, int],
    per_window: int,
    per_day: int,
    per_client: int,
    daily_cap: int,
    mode: str,
) -> dict:
    def left(name: str, limit: int) -> int:
        return max(0, limit - used.get(name, 0))

    short_term = left("window", per_window)
    ip_day = left("ipday", per_day)
    client_day = left("client", per_client)
    global_day = left("global", daily_cap)
    return {
        "perSession": short_term,
        "perSessionLimit": per_window,
        "perDay": ip_day,
        "perDayLimit": per_day,
        "perClientDay": client_day,
        "perClientDayLimit": per_client,
        "globalDay": global_day,
        "globalDayLimit": daily_cap,
        # What one more click can actually use, and what is left today.
        "remaining": min(short_term, ip_day, client_day, global_day),
        "today": min(ip_day, client_day, global_day),
        # "shared" survives restarts and extra instances; "memory" does not.
        "budgetStore": mode,
    }


def remaining_quota(request: Request) -> dict:
    """Report what is left without consuming a call.

    Two numbers matter and they used to be conflated: the 10-minute window
    (how many calls are left right now) and the daily ceilings. The UI showed
    the smallest of them as "calls left today", so a 10-minute window looked
    like a daily limit and climbed back up after ten idle minutes.
    """
    per_window, per_day, per_client, daily_cap = _caps()
    ip = client_ip(request)
    client = (request.cookies.get(CLIENT_COOKIE) or "").strip()

    mode = "memory"
    if store_configured():
        try:
            used = _shared_used(ip, client, time.time())
            return _quota_payload(used, per_window, per_day, per_client, daily_cap, "shared")
        except StoreError:
            # The health check must still answer; say the numbers are local.
            mode = "degraded"

    return _quota_payload(
        _memory_used(ip, client), per_window, per_day, per_client, daily_cap, mode
    )


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

    # name, limit, window length, refusal text (in the order a caller meets them)
    specs = (
        (
            "global",
            daily_cap,
            DAY_SECONDS,
            "The research budget for today is used up. Try again tomorrow.",
        ),
        (
            "client",
            per_client,
            DAY_SECONDS,
            f"You have used today's {per_client} research calls. "
            "The limit resets tomorrow; ask for a higher limit if you need more.",
        ),
        (
            "window",
            per_window,
            WINDOW_SECONDS,
            "Too many research requests from this connection. "
            "Try again in {retry} seconds.",
        ),
        (
            "ipday",
            per_day,
            DAY_SECONDS,
            "This connection has reached its daily research limit. "
            "Please try again tomorrow.",
        ),
    )

    def retry_after(span: int, now: float) -> int:
        if span == WINDOW_SECONDS:
            return max(1, int(WINDOW_SECONDS - (now % WINDOW_SECONDS)))
        return seconds_to_utc_midnight(now)

    def refuse(detail: str, wait: int) -> None:
        raise HTTPException(
            status_code=429,
            detail=detail.format(retry=wait) if "{retry}" in detail else detail,
            headers={"Retry-After": str(wait)},
        )

    def store_unavailable(exc: StoreError, phase: str) -> None:
        # Fail closed: if the shared counter cannot be read or written we do not
        # know the spend, so the paid call must not run.
        print(f"budget_store_error phase={phase} error={str(exc)[:120]}", flush=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "The budget check is unavailable right now, so no paid research was run. "
                "Try again in a moment."
            ),
        )

    if store_configured():
        now = time.time()
        keys = _shared_keys(ip, client, now)
        names = [name for name, _, _, _ in specs]
        try:
            used = dict(zip(names, store_read_counts([keys[name][0] for name in names])))
        except StoreError as exc:
            store_unavailable(exc, "read")

        for name, limit, span, detail in specs:
            if used[name] >= limit:
                refuse(detail, retry_after(span, now))

        try:
            after = dict(
                zip(
                    names,
                    store_bump(
                        [keys[name][0] for name in names],
                        [keys[name][1] for name in names],
                    ),
                )
            )
        except StoreError as exc:
            store_unavailable(exc, "write")

        # Two clicks landing at once can both pass the read; refuse the one that
        # pushed a counter over. It stays counted, which only makes the cap tighter.
        for name, limit, span, detail in specs:
            if after[name] > limit:
                refuse(detail, retry_after(span, now))
        return

    # No shared store configured: per-instance counters, as a fallback brake.
    limits = (
        (_global_day, "global", daily_cap, DAY_SECONDS, specs[0][3]),
        (_client_day, f"client:{client}", per_client, DAY_SECONDS, specs[1][3]),
        (_ip_window, f"ip:{ip}", per_window, WINDOW_SECONDS, specs[2][3]),
        (_ip_day, f"ip:{ip}", per_day, DAY_SECONDS, specs[3][3]),
    )

    # Check every limit before charging any of them. Charging as we went meant a
    # request rejected for its IP was still counted against the global budget.
    for window, key, limit, span, detail in limits:
        if window.count(key, span) >= limit:
            refuse(detail, window.retry_after(key, span))

    for window, key, limit, span, detail in limits:
        allowed, retry = window.allow(key, limit, span)
        if not allowed:
            refuse(detail, retry)


def log_request(request: Request, action: str) -> None:
    """One compact line per paid call, with no raw IP or payload."""
    digest = hashlib.sha256(client_ip(request).encode("utf-8")).hexdigest()[:10]
    print(f"demo_request action={action} ip={digest}", flush=True)
