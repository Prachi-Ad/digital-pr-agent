"""Optional paid contact lookup through ContactOut.

The token is stored locally next to the other app data and is never sent to the
browser or the public demo. The app uses the REST API directly; it does not need
the ContactOut MCP server.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("PR_AGENT_DATA_DIR") or ROOT / "data")
CONFIG_PATH = DATA_DIR / "contactout_config.json"
HUNTER_CONFIG_PATH = DATA_DIR / "hunter_config.json"
SEARCH_URL = "https://api.contactout.com/v1/people/search"
HUNTER_DOMAIN_URL = "https://api.hunter.io/v2/domain-search"
HUNTER_FINDER_URL = "https://api.hunter.io/v2/email-finder"

# Titles that own content, SEO, or link placement at a publication.
CONTENT_TITLES = [
    "SEO",
    "SEO Manager",
    "SEO Specialist",
    "Content Manager",
    "Content Writer",
    "Content Editor",
    "Managing Editor",
    "Link Building",
    "Outreach Manager",
    "Partnerships Manager",
    "Editor",
]


@dataclass
class ContactOutConfig:
    api_token: str = ""


def load_config() -> ContactOutConfig:
    if not CONFIG_PATH.exists():
        return ContactOutConfig()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ContactOutConfig()
    return ContactOutConfig(api_token=str(raw.get("api_token") or ""))


def save_config(config: ContactOutConfig) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
    return CONFIG_PATH


def is_configured(config: ContactOutConfig | None = None) -> bool:
    return bool((config or load_config()).api_token.strip())


def _error_message(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    if exc.code in (401, 403):
        return "ContactOut rejected the API token. Check the token in Settings."
    detail = ""
    try:
        detail = str(json.loads(body).get("message") or "")
    except Exception:
        detail = body[:200]
    return f"ContactOut returned HTTP {exc.code}. {detail}".strip()


def search_people(
    domain: str,
    titles: list[str] | None = None,
    name: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search ContactOut for content/SEO contacts at one publication domain."""
    config = load_config()
    if not is_configured(config):
        raise RuntimeError(
            "Add a ContactOut API token in Settings before using this lookup."
        )
    domain = (domain or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    payload: dict[str, Any] = {
        "page": 1,
        "page_size": max(1, min(25, int(limit))),
        "reveal_info": True,
        "data_types": ["work_email"],
        "include_related_job_titles": True,
    }
    if domain:
        payload["domain"] = [domain]
    if titles:
        payload["job_title"] = titles[:50]
    if name.strip():
        payload["name"] = name.strip()

    request = urllib.request.Request(
        SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "token": config.api_token.strip(),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_error_message(exc)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"ContactOut could not be reached: {exc.reason}") from exc

    profiles = data.get("profiles") or {}
    results = []
    for linkedin_url, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        info = profile.get("contact_info") or {}
        emails = (
            info.get("work_emails")
            or info.get("emails")
            or info.get("personal_emails")
            or []
        )
        email = next((item for item in emails if item), "")
        company = profile.get("company")
        if isinstance(company, dict):
            company_name = company.get("name") or ""
        else:
            company_name = str(company or "")
        results.append(
            {
                "name": profile.get("full_name") or profile.get("name") or "",
                "title": profile.get("title") or profile.get("headline") or "",
                "email": email,
                "linkedin_url": profile.get("linkedin_url") or linkedin_url,
                "company": company_name,
                "source": "ContactOut",
            }
        )
    return results


@dataclass
class HunterConfig:
    api_key: str = ""


def load_hunter_config() -> HunterConfig:
    if not HUNTER_CONFIG_PATH.exists():
        return HunterConfig()
    try:
        raw = json.loads(HUNTER_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return HunterConfig()
    return HunterConfig(api_key=str(raw.get("api_key") or ""))


def save_hunter_config(config: HunterConfig) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HUNTER_CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    try:
        os.chmod(HUNTER_CONFIG_PATH, 0o600)
    except OSError:
        pass
    return HUNTER_CONFIG_PATH


def is_hunter_configured(config: HunterConfig | None = None) -> bool:
    return bool((config or load_hunter_config()).api_key.strip())


def _hunter_get(url: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {key: value for key, value in params.items() if value not in ("", None)}
    )
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"Accept": "application/json", "api_key": api_key},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError(
                "Hunter rejected the API key. Check the key in Settings."
            ) from exc
        if exc.code == 429:
            raise RuntimeError(
                "Hunter rate limit reached. Wait, or upgrade the Hunter plan."
            ) from exc
        raise RuntimeError(f"Hunter returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Hunter could not be reached: {exc.reason}") from exc


def _split_name(name: str) -> tuple[str, str]:
    parts = (name or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def search_hunter(
    domain: str,
    name: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Find published/verified work emails via Hunter's domain search or finder."""
    config = load_hunter_config()
    if not is_hunter_configured(config):
        raise RuntimeError("Add a Hunter API key in Settings before using this lookup.")
    domain = (domain or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    key = config.api_key.strip()
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    first_name, last_name = _split_name(name)
    if first_name and last_name:
        data = _hunter_get(
            HUNTER_FINDER_URL,
            {
                "domain": domain,
                "first_name": first_name,
                "last_name": last_name,
                "api_key": key,
            },
            key,
        ).get("data") or {}
        email_value = str(data.get("email") or "").strip()
        if email_value:
            results.append(
                {
                    "name": name.strip(),
                    "title": data.get("position") or "",
                    "email": email_value,
                    "linkedin_url": data.get("linkedin_url") or "",
                    "company": domain,
                    "source": "Hunter",
                }
            )
            seen.add(email_value.lower())

    if len(results) < max(1, limit):
        data = _hunter_get(
            HUNTER_DOMAIN_URL,
            {"domain": domain, "limit": max(1, min(100, limit)), "api_key": key},
            key,
        ).get("data") or {}
        for item in data.get("emails") or []:
            email_value = str(item.get("value") or "").strip()
            if not email_value or email_value.lower() in seen:
                continue
            person_name = " ".join(
                part
                for part in (item.get("first_name"), item.get("last_name"))
                if part
            ).strip()
            results.append(
                {
                    "name": person_name,
                    "title": item.get("position") or "",
                    "email": email_value,
                    "linkedin_url": item.get("linkedin") or "",
                    "company": domain,
                    "source": "Hunter",
                }
            )
            seen.add(email_value.lower())
            if len(results) >= max(1, limit):
                break

    normalized = (name or "").strip().lower()
    priorities = (
        "seo",
        "content",
        "editor",
        "link",
        "outreach",
        "partnership",
        "writer",
        "marketing",
    )

    def rank(row: dict[str, Any]) -> tuple[int, int]:
        title = str(row.get("title") or "").lower()
        name_hit = (
            0
            if normalized and str(row.get("name") or "").strip().lower() == normalized
            else 1
        )
        role_hit = 0 if any(word in title for word in priorities) else 1
        return (name_hit, role_hit)

    results.sort(key=rank)
    return results
