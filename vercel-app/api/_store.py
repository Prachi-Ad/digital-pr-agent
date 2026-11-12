"""Shared budget counters (Upstash Redis REST).

The counters in `_security.py` live in each Vercel instance's memory, so a cold
start resets them and every extra instance multiplies the cap. That makes them a
brake, not a ceiling. This module moves the paid-call counters into one store that
every instance reads.

Configuration (either pair works; the Upstash / Vercel KV integration sets them):

    UPSTASH_REDIS_REST_URL
    UPSTASH_REDIS_REST_TOKEN

or, for Vercel's older KV naming:

    KV_REST_API_URL
    KV_REST_API_TOKEN

Behaviour without configuration: `configured()` is False and `_security.py`
keeps using its in-memory counters. Behaviour when configured but unreachable:
`StoreError`, and the guard refuses paid calls (fail closed). Refusing research
is preferable to running it uncapped.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

TIMEOUT_SECONDS = 3.0


class StoreError(RuntimeError):
    """The shared counter store could not be read or written."""


def _url() -> str:
    for name in ("UPSTASH_REDIS_REST_URL", "KV_REST_API_URL"):
        value = (os.environ.get(name) or "").strip().rstrip("/")
        if value:
            return value
    return ""


def _token() -> str:
    for name in ("UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_TOKEN"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def configured() -> bool:
    return bool(_url() and _token())


def _post(path: str, payload: object) -> object:
    url = _url() + path
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise StoreError(str(exc)[:200]) from exc
    if isinstance(body, dict) and body.get("error"):
        raise StoreError(str(body["error"])[:200])
    return body


def pipeline(commands: list[list]) -> list:
    """Run several commands in one round trip and return their results in order."""
    if not commands:
        return []
    body = _post("/pipeline", commands)
    if not isinstance(body, list) or len(body) != len(commands):
        raise StoreError("Unexpected reply from the budget store.")
    out = []
    for entry in body:
        if isinstance(entry, dict):
            if entry.get("error"):
                raise StoreError(str(entry["error"])[:200])
            out.append(entry.get("result"))
        else:
            out.append(entry)
    return out


def read_counts(keys: list[str]) -> list[int]:
    """Current value of each counter, missing keys as 0."""
    values = pipeline([["GET", key] for key in keys])
    counts = []
    for value in values:
        try:
            counts.append(int(value or 0))
        except (TypeError, ValueError):
            counts.append(0)
    return counts


def bump(keys: list[str], ttls: list[int]) -> list[int]:
    """Increment each counter once, setting its TTL when the key is created.

    Returns the post-increment values so the caller can refuse a request that
    pushed a counter over its limit.
    """
    values = pipeline([["INCR", key] for key in keys])
    counts = []
    fresh = []
    for index, value in enumerate(values):
        try:
            count = int(value)
        except (TypeError, ValueError):
            raise StoreError("The budget store returned a non-numeric count.")
        counts.append(count)
        if count == 1:
            fresh.append(index)
    if fresh:
        # Only new keys need a TTL; re-setting it every call would slide the
        # daily window forward instead of ending it at midnight.
        pipeline([["EXPIRE", keys[index], ttls[index]] for index in fresh])
    return counts


def seconds_to_utc_midnight(now: float) -> int:
    return max(1, 86_400 - int(now % 86_400) + 120)
