"""Local SQLite persistence for the Vista Social PR Agent.

All data stays on this computer in the project's data directory.
No network/database service is required.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "vista_pr_agent.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _dump(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(_jsonable(value), ensure_ascii=False, separators=(",", ":"))


def _load(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _csv_safe(value: Any) -> Any:
    """Stop spreadsheet software from treating researched text as a formula."""
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if needed; never overwrites an existing database."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                state_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS listicle_prospects (
                prospect_key TEXT PRIMARY KEY,
                url TEXT,
                title TEXT NOT NULL,
                publication TEXT NOT NULL,
                search_theme TEXT NOT NULL DEFAULT '',
                placement_type TEXT NOT NULL DEFAULT 'Unclear',
                review_status TEXT NOT NULL DEFAULT 'Awaiting review',
                placement_progress TEXT NOT NULL DEFAULT 'Not contacted',
                payload_json TEXT NOT NULL,
                contact_json TEXT,
                policy_json TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pr_opportunities (
                record_key TEXT PRIMARY KEY,
                url TEXT,
                title TEXT NOT NULL,
                publication TEXT NOT NULL,
                selected_angle TEXT NOT NULL DEFAULT '',
                review_status TEXT NOT NULL DEFAULT 'Awaiting review',
                payload_json TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS journalist_records (
                record_key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                publication TEXT NOT NULL,
                relevant_article_url TEXT,
                related_opportunity_url TEXT,
                qualification_status TEXT NOT NULL DEFAULT 'Needs review',
                payload_json TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        _migrate_journalist_keys(conn)


def save_app_snapshot(snapshot: dict[str, Any]) -> None:
    """Save the latest active workspace so it can be restored after restart."""
    init_db()
    payload = _dump(snapshot) or "{}"
    with _connect() as conn:
        conn.execute(
            """INSERT INTO app_state(state_key, payload_json, updated_at)
               VALUES('active_workspace', ?, ?)
               ON CONFLICT(state_key) DO UPDATE SET
                   payload_json=excluded.payload_json,
                   updated_at=excluded.updated_at""",
            (payload, _now()),
        )


def load_app_snapshot() -> dict[str, Any]:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload_json FROM app_state WHERE state_key='active_workspace'"
        ).fetchone()
    return _load(row["payload_json"], {}) if row else {}


def canonical_url(url: str | None) -> str:
    """Normalize a URL for record matching without changing the displayed URL."""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        if not parts.scheme or not parts.netloc:
            return raw.rstrip("/").lower()
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))
    except Exception:
        return raw.rstrip("/").lower()


def _record_key(url: str | None, title: str, publication: str) -> str:
    normalized = canonical_url(url)
    if normalized:
        return normalized
    basis = f"{publication.strip().lower()}|{title.strip().lower()}"
    return "no-url:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _journalist_record_key(name: str, publication: str, article_url: str | None) -> str:
    """Identify a journalist by person, not just by the article they wrote.

    Co-authors frequently share one article URL, so a URL-only key would
    silently merge different people into a single record.
    """
    basis = "|".join(
        (
            (name or "Unknown").strip().lower(),
            (publication or "Unknown").strip().lower(),
            canonical_url(article_url),
        )
    )
    return "journalist:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _migrate_journalist_keys(conn: sqlite3.Connection) -> None:
    """Give legacy URL-keyed journalist rows a person-specific key."""
    rows = conn.execute(
        "SELECT * FROM journalist_records WHERE record_key NOT LIKE 'journalist:%'"
    ).fetchall()
    for row in rows:
        new_key = _journalist_record_key(
            row["name"], row["publication"], row["relevant_article_url"]
        )
        duplicate = conn.execute(
            "SELECT * FROM journalist_records WHERE record_key=?", (new_key,)
        ).fetchone()
        if duplicate is None:
            conn.execute(
                "UPDATE journalist_records SET record_key=? WHERE record_key=?",
                (new_key, row["record_key"]),
            )
            continue
        # The same person is already stored under the new key. Keep the newer copy.
        if (row["updated_at"] or "") > (duplicate["updated_at"] or ""):
            conn.execute(
                """UPDATE journalist_records SET
                       name=?, publication=?, relevant_article_url=?,
                       related_opportunity_url=?, qualification_status=?,
                       payload_json=?, first_seen=?, updated_at=?
                   WHERE record_key=?""",
                (
                    row["name"], row["publication"], row["relevant_article_url"],
                    row["related_opportunity_url"], row["qualification_status"],
                    row["payload_json"], row["first_seen"], row["updated_at"],
                    new_key,
                ),
            )
        conn.execute(
            "DELETE FROM journalist_records WHERE record_key=?", (row["record_key"],)
        )


def _row_to_listicle(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    result["payload"] = _load(result.pop("payload_json"), {})
    result["contact_data"] = _load(result.pop("contact_json"), None)
    result["policy_data"] = _load(result.pop("policy_json"), None)
    return result


def get_listicle_prospect(url: str, title: str = "", publication: str = "") -> dict[str, Any] | None:
    init_db()
    key = _record_key(url, title, publication)
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM listicle_prospects WHERE prospect_key=?", (key,)
        ).fetchone()
    return _row_to_listicle(row)


def upsert_listicle_prospect(
    item: Any,
    search_theme: str = "",
    review_status: str | None = None,
    contacts: Any = None,
    policy: Any = None,
    placement_progress: str | None = None,
) -> None:
    """Save listicle facts and enrichments, preserving existing decisions/data.

    Repeated saves with identical content only refresh ``last_seen`` so that
    ``updated_at`` continues to mean "the record actually changed".
    """
    init_db()
    payload = _jsonable(item)
    url = getattr(item, "listicle_url", "") or ""
    title = getattr(item, "listicle_title", "") or "Untitled prospect"
    publication = getattr(item, "publication", "") or "Unknown publication"
    key = _record_key(url, title, publication)
    stamp = _now()
    payload_json = _dump(payload) or "{}"
    contact_json = _dump(contacts)
    policy_json = _dump(policy)
    status = review_status
    progress = placement_progress
    placement_type = getattr(item, "placement_type", "Unclear") or "Unclear"

    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM listicle_prospects WHERE prospect_key=?", (key,)
        ).fetchone()

        if existing is not None:
            unchanged = (
                (url == "" or url == existing["url"])
                and title == existing["title"]
                and publication == existing["publication"]
                and (search_theme == "" or search_theme == existing["search_theme"])
                and placement_type == existing["placement_type"]
                and payload_json == existing["payload_json"]
                and (contact_json is None or contact_json == existing["contact_json"])
                and (policy_json is None or policy_json == existing["policy_json"])
                and (status is None or status == existing["review_status"])
                and (progress is None or progress == existing["placement_progress"])
            )
            if unchanged:
                conn.execute(
                    "UPDATE listicle_prospects SET last_seen=? WHERE prospect_key=?",
                    (stamp, key),
                )
                return

        conn.execute(
            """INSERT INTO listicle_prospects(
                   prospect_key, url, title, publication, search_theme, placement_type,
                   review_status, placement_progress, payload_json, contact_json,
                   policy_json, first_seen, last_seen, updated_at
               ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(prospect_key) DO UPDATE SET
                   url=CASE WHEN excluded.url <> '' THEN excluded.url ELSE listicle_prospects.url END,
                   title=excluded.title,
                   publication=excluded.publication,
                   search_theme=CASE WHEN excluded.search_theme <> '' THEN excluded.search_theme ELSE listicle_prospects.search_theme END,
                   placement_type=excluded.placement_type,
                   review_status=CASE WHEN ? IS NOT NULL THEN ? ELSE listicle_prospects.review_status END,
                   placement_progress=CASE WHEN ? IS NOT NULL THEN ? ELSE listicle_prospects.placement_progress END,
                   payload_json=excluded.payload_json,
                   contact_json=COALESCE(excluded.contact_json, listicle_prospects.contact_json),
                   policy_json=COALESCE(excluded.policy_json, listicle_prospects.policy_json),
                   last_seen=excluded.last_seen,
                   updated_at=excluded.updated_at""",
            (
                key, url, title, publication, search_theme, placement_type,
                status or "Awaiting review", progress or "Not contacted",
                payload_json, contact_json, policy_json,
                stamp, stamp, stamp,
                status, status, progress, progress,
            ),
        )


def list_listicle_prospects() -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM listicle_prospects ORDER BY updated_at DESC, rowid DESC"
        ).fetchall()
    return [_row_to_listicle(row) for row in rows if row is not None]


def _row_to_record(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    result["payload"] = _load(result.pop("payload_json"), {})
    return result


def get_pr_opportunity(url: str, title: str = "", publication: str = "") -> dict[str, Any] | None:
    init_db()
    key = _record_key(url, title, publication)
    with _connect() as conn:
        row = conn.execute("SELECT * FROM pr_opportunities WHERE record_key=?", (key,)).fetchone()
    return _row_to_record(row)


def upsert_pr_opportunity(
    item: Any,
    selected_angle: str = "",
    review_status: str | None = None,
) -> None:
    """Save a PR opportunity without rewriting unchanged rows."""
    init_db()
    url = getattr(item, "article_url", "") or ""
    title = getattr(item, "article_title", "") or "Untitled article"
    publication = getattr(item, "publication", "") or "Unknown publication"
    key = _record_key(url, title, publication)
    stamp = _now()
    status = review_status
    payload_json = _dump(item) or "{}"

    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM pr_opportunities WHERE record_key=?", (key,)
        ).fetchone()

        if existing is not None:
            unchanged = (
                (url == "" or url == existing["url"])
                and title == existing["title"]
                and publication == existing["publication"]
                and (selected_angle == "" or selected_angle == existing["selected_angle"])
                and (status is None or status == existing["review_status"])
                and payload_json == existing["payload_json"]
            )
            if unchanged:
                return

        conn.execute(
            """INSERT INTO pr_opportunities(
                   record_key, url, title, publication, selected_angle, review_status,
                   payload_json, first_seen, updated_at
               ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(record_key) DO UPDATE SET
                   url=CASE WHEN excluded.url <> '' THEN excluded.url ELSE pr_opportunities.url END,
                   title=excluded.title, publication=excluded.publication,
                   selected_angle=CASE WHEN excluded.selected_angle <> '' THEN excluded.selected_angle ELSE pr_opportunities.selected_angle END,
                   review_status=CASE WHEN ? IS NOT NULL THEN ? ELSE pr_opportunities.review_status END,
                   payload_json=excluded.payload_json, updated_at=excluded.updated_at""",
            (key, url, title, publication, selected_angle,
             status or "Awaiting review", payload_json, stamp, stamp,
             status, status),
        )


def list_pr_opportunities() -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM pr_opportunities ORDER BY updated_at DESC, rowid DESC").fetchall()
    return [_row_to_record(row) for row in rows if row is not None]


def get_journalist_record(person: Any, related_opportunity_url: str = "") -> dict[str, Any] | None:
    init_db()
    name = getattr(person, "name", "") or "Unknown"
    publication = getattr(person, "publication", "") or "Unknown"
    article_url = getattr(person, "relevant_article_url", "") or ""
    key = _journalist_record_key(name, publication, article_url)
    with _connect() as conn:
        row = conn.execute("SELECT * FROM journalist_records WHERE record_key=?", (key,)).fetchone()
    return _row_to_record(row)


def upsert_journalist(
    person: Any,
    related_opportunity_url: str = "",
    qualification_status: str | None = None,
) -> None:
    """Save a journalist record without rewriting unchanged rows."""
    init_db()
    name = getattr(person, "name", "") or "Unknown"
    publication = getattr(person, "publication", "") or "Unknown"
    article_url = getattr(person, "relevant_article_url", "") or ""
    key = _journalist_record_key(name, publication, article_url)
    stamp = _now()
    status = qualification_status
    payload_json = _dump(person) or "{}"

    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM journalist_records WHERE record_key=?", (key,)
        ).fetchone()

        if existing is not None:
            unchanged = (
                name == existing["name"]
                and publication == existing["publication"]
                and article_url == existing["relevant_article_url"]
                and (related_opportunity_url == "" or related_opportunity_url == existing["related_opportunity_url"])
                and (status is None or status == existing["qualification_status"])
                and payload_json == existing["payload_json"]
            )
            if unchanged:
                return

        conn.execute(
            """INSERT INTO journalist_records(
                   record_key, name, publication, relevant_article_url,
                   related_opportunity_url, qualification_status, payload_json,
                   first_seen, updated_at
               ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(record_key) DO UPDATE SET
                   name=excluded.name, publication=excluded.publication,
                   relevant_article_url=excluded.relevant_article_url,
                   related_opportunity_url=CASE WHEN excluded.related_opportunity_url <> '' THEN excluded.related_opportunity_url ELSE journalist_records.related_opportunity_url END,
                   qualification_status=CASE WHEN ? IS NOT NULL THEN ? ELSE journalist_records.qualification_status END,
                   payload_json=excluded.payload_json, updated_at=excluded.updated_at""",
            (key, name, publication, article_url, related_opportunity_url,
             status or "Needs review", payload_json, stamp, stamp,
             status, status),
        )


def list_journalists() -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM journalist_records ORDER BY updated_at DESC, rowid DESC").fetchall()
    return [_row_to_record(row) for row in rows if row is not None]


def listicle_csv_bytes() -> bytes:
    rows = list_listicle_prospects()
    out = io.StringIO(newline="")
    columns = [
        "publication", "title", "url", "search_theme", "placement_type",
        "review_status", "placement_progress", "contact_found", "contact_names",
        "public_professional_emails", "contact_methods", "policy_checked",
        "policy_recommendation", "policy_status", "policy_source_url",
        "first_seen", "last_seen", "updated_at",
    ]
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        contact_data = row.get("contact_data") or {}
        contacts = contact_data.get("contacts", []) if isinstance(contact_data, dict) else []
        policy_data = row.get("policy_data") or {}
        writer.writerow({
            "publication": _csv_safe(row.get("publication")),
            "title": _csv_safe(row.get("title")),
            "url": _csv_safe(row.get("url")),
            "search_theme": _csv_safe(row.get("search_theme")),
            "placement_type": _csv_safe(row.get("placement_type")),
            "review_status": _csv_safe(row.get("review_status")),
            "placement_progress": _csv_safe(row.get("placement_progress")),
            "contact_found": "Yes" if contacts else "No",
            "contact_names": _csv_safe("; ".join(str(c.get("contact_name", "")) for c in contacts if isinstance(c, dict))),
            "public_professional_emails": _csv_safe("; ".join(str(c.get("professional_email", "")) for c in contacts if isinstance(c, dict))),
            "contact_methods": _csv_safe("; ".join(str(c.get("contact_method", "")) for c in contacts if isinstance(c, dict))),
            "policy_checked": "Yes" if policy_data else "No",
            "policy_recommendation": _csv_safe(policy_data.get("recommended_disposition", "") if isinstance(policy_data, dict) else ""),
            "policy_status": _csv_safe(policy_data.get("policy_status", "") if isinstance(policy_data, dict) else ""),
            "policy_source_url": _csv_safe(policy_data.get("policy_source_url", "") if isinstance(policy_data, dict) else ""),
            "first_seen": row.get("first_seen"),
            "last_seen": row.get("last_seen"),
            "updated_at": row.get("updated_at"),
        })
    return out.getvalue().encode("utf-8-sig")


def opportunity_csv_bytes() -> bytes:
    rows = list_pr_opportunities()
    out = io.StringIO(newline="")
    columns = ["publication", "title", "url", "selected_angle", "review_status", "first_seen", "updated_at"]
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_safe(value) for key, value in row.items() if key in columns})
    return out.getvalue().encode("utf-8-sig")


def journalist_csv_bytes() -> bytes:
    rows = list_journalists()
    out = io.StringIO(newline="")
    columns = ["name", "publication", "relevant_article_url", "related_opportunity_url", "qualification_status", "first_seen", "updated_at"]
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_safe(value) for key, value in row.items() if key in columns})
    return out.getvalue().encode("utf-8-sig")


def create_database_backup() -> str:
    """Create a consistent, verified, dated SQLite backup under backups."""
    init_db()
    backup_dir = ROOT / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"vista_pr_agent_database_{stamp}.sqlite3"
    with sqlite3.connect(DB_PATH, timeout=15) as source:
        with sqlite3.connect(backup_path) as destination:
            source.backup(destination)
    with sqlite3.connect(backup_path, timeout=15) as check:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(
            f"The database backup did not pass its integrity check ({integrity})."
        )
    return str(backup_path)
