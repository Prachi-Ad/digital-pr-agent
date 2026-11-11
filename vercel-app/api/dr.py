"""Ahrefs Domain Rating lookups via the free public endpoint.

Uses GET /v3/public/domain-rating-free, which is free and only needs an
APIv3 key (free Ahrefs account -> Account settings -> API keys).
Attribution required wherever DR is shown: "Domain Rating by Ahrefs".
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

API_BASE = "https://api.ahrefs.com/v3/public/domain-rating-free"
TIMEOUT_SECONDS = 15
MAX_DOMAINS = 10


def _api_key() -> str:
    return (os.environ.get("AHREFS_API_KEY") or "").strip()


def configured() -> bool:
    return bool(_api_key())


def get_domain_ratings(domains: list[str]) -> list[dict]:
    """Return [{domain, dr}] for up to MAX_DOMAINS domains. Raises on failure."""
    key = _api_key()
    if not key:
        raise RuntimeError(
            "Ahrefs is not connected. Add AHREFS_API_KEY in Vercel (free key from Ahrefs account settings)."
        )
    cleaned: list[str] = []
    for d in domains or []:
        d = (d or "").strip().lower()
        if d and d not in cleaned:
            cleaned.append(d)
    cleaned = cleaned[:MAX_DOMAINS]
    results: list[dict] = []
    for domain in cleaned:
        query = urllib.parse.urlencode({"target": domain, "output": "json"})
        req = urllib.request.Request(
            f"{API_BASE}?{query}",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as res:
                payload = json.loads(res.read().decode("utf-8"))
        except Exception as e:
            results.append({"domain": domain, "dr": None, "error": str(e)[:120]})
            continue
        dr = (payload.get("domain_rating") or {}).get("domain_rating")
        try:
            dr = int(round(float(dr))) if dr is not None else None
        except (TypeError, ValueError):
            dr = None
        results.append({"domain": domain, "dr": dr})
    return results
