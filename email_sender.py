"""Local, human-approved email sending.

Supports Gmail / Google Workspace with an app password or OAuth 2.0, plus any
custom SMTP provider with a designated From address. The module only sends when
the Streamlit app explicitly calls send_email(). Credentials live in
data/email_config.json (gitignored) or environment variables. No credentials
are written to the database or the send log.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, replace
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(
    os.environ.get("PR_AGENT_DATA_DIR")
    or os.environ.get("VISTA_DATA_DIR")
    or ROOT / "data"
)
CONFIG_PATH = DATA_DIR / "email_config.json"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
DEFAULT_FROM_NAME = "Prachi, SEO Specialist"
DEFAULT_DELAY_SECONDS = 30
DEFAULT_DAILY_CAP = 20
MAX_DAILY_CAP = 200
MIN_DELAY_SECONDS = 5
MAX_DELAY_SECONDS = 300

AUTH_METHOD_APP_PASSWORD = "app_password"
AUTH_METHOD_OAUTH = "oauth"
AUTH_METHOD_SMTP = "smtp"
SMTP_SECURITY_STARTTLS = "starttls"
SMTP_SECURITY_SSL = "ssl"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_OAUTH_SCOPE = "openid email https://mail.google.com/"
DEFAULT_OAUTH_REDIRECT_URI = "http://localhost:8501/"
OAUTH_STATE_MAX_AGE_SECONDS = 15 * 60

_OAUTH_TOKEN_CACHE: dict[str, dict[str, object]] = {}

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


@dataclass
class EmailConfig:
    from_email: str = ""
    app_password: str = ""
    from_name: str = DEFAULT_FROM_NAME
    delay_seconds: int = DEFAULT_DELAY_SECONDS
    daily_cap: int = DEFAULT_DAILY_CAP
    postal_address: str = ""
    smtp_host: str = ""
    smtp_port: int = SMTP_PORT
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_security: str = SMTP_SECURITY_STARTTLS
    auth_method: str = AUTH_METHOD_APP_PASSWORD
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_refresh_token: str = ""
    oauth_email: str = ""
    oauth_redirect_uri: str = DEFAULT_OAUTH_REDIRECT_URI


@dataclass
class SendResult:
    success: bool
    message_id: str = ""
    error: str = ""
    fatal: bool = False


@dataclass
class OAuthResult:
    success: bool
    email: str = ""
    error: str = ""


class OAuthError(Exception):
    """A user-actionable Google OAuth failure."""


def _normalize_auth_method(value: object) -> str:
    method = str(value or "").strip().lower()
    if method in {"oauth", "google", "google_oauth", "workspace"}:
        return AUTH_METHOD_OAUTH
    if method in {"smtp", "custom_smtp", "other_smtp", "designated_email"}:
        return AUTH_METHOD_SMTP
    return AUTH_METHOD_APP_PASSWORD


def _normalize_smtp_security(value: object) -> str:
    security = str(value or "").strip().lower()
    if security in {"ssl", "ssl/tls", "implicit", "smtps"}:
        return SMTP_SECURITY_SSL
    return SMTP_SECURITY_STARTTLS


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def load_email_config() -> EmailConfig:
    """Load local settings, with optional environment-variable overrides."""
    raw: dict = {}
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except (OSError, json.JSONDecodeError):
            raw = {}

    auth_method = _normalize_auth_method(
        os.environ.get("EMAIL_AUTH_METHOD") or raw.get("auth_method")
    )
    oauth_email = (
        os.environ.get("GOOGLE_OAUTH_EMAIL")
        or str(raw.get("oauth_email", ""))
    ).strip()
    from_email = (
        os.environ.get("GMAIL_SMTP_USER")
        or os.environ.get("EMAIL_FROM_EMAIL")
        or str(raw.get("from_email", ""))
    ).strip()
    if auth_method == AUTH_METHOD_OAUTH and oauth_email:
        from_email = oauth_email
    app_password = (
        os.environ.get("GMAIL_SMTP_APP_PASSWORD")
        or os.environ.get("EMAIL_APP_PASSWORD")
        or str(raw.get("app_password", ""))
    ).strip()
    postal_address = (
        os.environ.get("EMAIL_POSTAL_ADDRESS")
        or str(raw.get("postal_address", ""))
    ).strip()
    oauth_redirect_uri = (
        os.environ.get("GOOGLE_OAUTH_REDIRECT_URI")
        or str(raw.get("oauth_redirect_uri", ""))
        or DEFAULT_OAUTH_REDIRECT_URI
    ).strip()
    smtp_host = (
        os.environ.get("SMTP_HOST")
        or str(raw.get("smtp_host", ""))
    ).strip()
    if not smtp_host and auth_method != AUTH_METHOD_SMTP:
        smtp_host = SMTP_HOST
    smtp_username = (
        os.environ.get("SMTP_USERNAME")
        or str(raw.get("smtp_username", ""))
        or from_email
    ).strip()
    smtp_password = (
        os.environ.get("SMTP_PASSWORD")
        or str(raw.get("smtp_password", ""))
    ).strip()
    smtp_security = _normalize_smtp_security(
        os.environ.get("SMTP_SECURITY") or raw.get("smtp_security")
    )

    return EmailConfig(
        from_email=from_email,
        app_password=app_password,
        from_name=DEFAULT_FROM_NAME,
        delay_seconds=_bounded_int(
            os.environ.get("EMAIL_DELAY_SECONDS", raw.get("delay_seconds")),
            DEFAULT_DELAY_SECONDS,
            MIN_DELAY_SECONDS,
            MAX_DELAY_SECONDS,
        ),
        daily_cap=_bounded_int(
            os.environ.get("EMAIL_DAILY_CAP", raw.get("daily_cap")),
            DEFAULT_DAILY_CAP,
            1,
            MAX_DAILY_CAP,
        ),
        postal_address=postal_address,
        smtp_host=smtp_host,
        smtp_port=_bounded_int(
            os.environ.get("SMTP_PORT", raw.get("smtp_port")),
            SMTP_PORT,
            1,
            65535,
        ),
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_security=smtp_security,
        auth_method=auth_method,
        oauth_client_id=(
            os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
            or str(raw.get("oauth_client_id", ""))
        ).strip(),
        oauth_client_secret=(
            os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
            or str(raw.get("oauth_client_secret", ""))
        ).strip(),
        oauth_refresh_token=(
            os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN")
            or str(raw.get("oauth_refresh_token", ""))
        ).strip(),
        oauth_email=oauth_email,
        oauth_redirect_uri=oauth_redirect_uri,
    )


def save_email_config(config: EmailConfig) -> Path:
    """Write local SMTP/OAuth settings. The data directory is gitignored."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = asdict(config)
    payload["from_name"] = DEFAULT_FROM_NAME
    payload["auth_method"] = _normalize_auth_method(config.auth_method)
    payload["app_password"] = (config.app_password or "").replace(" ", "").strip()
    payload["smtp_host"] = (config.smtp_host or "").strip()
    payload["smtp_port"] = _bounded_int(config.smtp_port, SMTP_PORT, 1, 65535)
    payload["smtp_username"] = (
        (config.smtp_username or "").strip() or (config.from_email or "").strip()
    )
    payload["smtp_password"] = (config.smtp_password or "").strip()
    payload["smtp_security"] = _normalize_smtp_security(config.smtp_security)
    payload["oauth_client_id"] = (config.oauth_client_id or "").strip()
    payload["oauth_client_secret"] = (config.oauth_client_secret or "").strip()
    payload["oauth_refresh_token"] = (config.oauth_refresh_token or "").strip()
    payload["oauth_email"] = (config.oauth_email or "").strip()
    payload["oauth_redirect_uri"] = (
        (config.oauth_redirect_uri or "").strip() or DEFAULT_OAUTH_REDIRECT_URI
    )
    payload["from_email"] = (config.from_email or "").strip()
    if payload["auth_method"] == AUTH_METHOD_OAUTH and payload["oauth_email"]:
        payload["from_email"] = payload["oauth_email"]
    CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
    return CONFIG_PATH


def is_valid_email(value: str) -> bool:
    email = (value or "").strip()
    return (
        bool(email)
        and len(email) <= 254
        and "\n" not in email
        and "\r" not in email
        and bool(_EMAIL_RE.match(email))
    )


def is_oauth_connected(config: EmailConfig) -> bool:
    return (
        _normalize_auth_method(config.auth_method) == AUTH_METHOD_OAUTH
        and is_valid_email(config.from_email)
        and bool((config.oauth_refresh_token or "").strip())
    )


def missing_config_fields(config: EmailConfig) -> list[str]:
    missing: list[str] = []
    method = _normalize_auth_method(config.auth_method)
    if method == AUTH_METHOD_SMTP:
        if not is_valid_email(config.from_email):
            missing.append("a valid From email address")
        if not (config.smtp_host or "").strip():
            missing.append("an SMTP host")
        if not (config.smtp_username or config.from_email or "").strip():
            missing.append("an SMTP username")
        if not (config.smtp_password or "").strip():
            missing.append("an SMTP password")
        return missing
    if method == AUTH_METHOD_OAUTH:
        if (
            not (config.oauth_refresh_token or "").strip()
            or not is_valid_email(config.from_email)
        ):
            missing.append("a connected Google Workspace account")
        if not (config.oauth_client_id or "").strip():
            missing.append("a Google OAuth client ID")
        if not (config.oauth_client_secret or "").strip():
            missing.append("a Google OAuth client secret")
        return missing
    if not is_valid_email(config.from_email):
        missing.append("a valid Gmail / Google Workspace address")
    if not (config.app_password or "").strip():
        missing.append("a Google app password")
    return missing


def _oauth_state_path() -> Path:
    return CONFIG_PATH.parent / "oauth_state.json"


def create_oauth_state() -> str:
    """Create a short-lived local state token for one OAuth redirect."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = secrets.token_urlsafe(32)
    state_path = _oauth_state_path()
    state_path.write_text(
        json.dumps({"state": state, "created_at": time.time()}),
        encoding="utf-8",
    )
    try:
        os.chmod(state_path, 0o600)
    except OSError:
        pass
    return state


def validate_oauth_state(state: str) -> bool:
    """Consume and validate the local OAuth state token."""
    path = _oauth_state_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    if not isinstance(raw, dict):
        return False
    try:
        created_at = float(raw.get("created_at", 0))
    except (TypeError, ValueError):
        return False
    if time.time() - created_at > OAUTH_STATE_MAX_AGE_SECONDS:
        return False
    return hmac.compare_digest(str(raw.get("state", "")), str(state or ""))


def build_oauth_url(config: EmailConfig, state: str) -> str:
    """Build the Google consent URL for a Web application OAuth client."""
    client_id = (config.oauth_client_id or "").strip()
    if not client_id:
        raise OAuthError("Add a Google OAuth client ID first.")
    redirect_uri = (
        (config.oauth_redirect_uri or "").strip() or DEFAULT_OAUTH_REDIRECT_URI
    )
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_OAUTH_SCOPE,
        "access_type": "offline",
        "prompt": "consent select_account",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


def _oauth_http_json(
    url: str,
    *,
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict:
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(
        url, data=body, headers=request_headers, method="POST" if body else "GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            error_body = json.loads(exc.read().decode("utf-8"))
            code = str(error_body.get("error", "")).strip()
            description = str(error_body.get("error_description", "")).strip()
            detail = f"{code}: {description}" if code and description else description or code
        except Exception:
            detail = ""
        raise OAuthError(detail or f"Google returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OAuthError(f"Could not reach Google sign-in: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OAuthError("Google returned an unreadable sign-in response.") from exc
    if not isinstance(parsed, dict):
        raise OAuthError("Google returned an unexpected sign-in response.")
    return parsed


def _oauth_cache_key(config: EmailConfig) -> str:
    material = (
        f"{config.oauth_client_id}|{config.oauth_refresh_token}|{config.from_email}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _cache_oauth_token(
    config: EmailConfig, access_token: str, expires_in: int
) -> None:
    _OAUTH_TOKEN_CACHE[_oauth_cache_key(config)] = {
        "access_token": access_token,
        "expires_at": time.time() + max(60, int(expires_in)),
    }


def get_oauth_access_token(config: EmailConfig, *, force: bool = False) -> str:
    """Return a cached access token, refreshing it when needed."""
    if not (config.oauth_client_id or "").strip():
        raise OAuthError("Add a Google OAuth client ID in Settings first.")
    if not (config.oauth_client_secret or "").strip():
        raise OAuthError("Add a Google OAuth client secret in Settings first.")
    if not (config.oauth_refresh_token or "").strip():
        raise OAuthError(
            "No Google Workspace account is connected. Use Connect Google Workspace "
            "account in Settings."
        )
    key = _oauth_cache_key(config)
    cached = _OAUTH_TOKEN_CACHE.get(key)
    if cached and not force and float(cached.get("expires_at", 0)) > time.time() + 60:
        return str(cached.get("access_token", ""))
    try:
        payload = _oauth_http_json(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": config.oauth_client_id.strip(),
                "client_secret": config.oauth_client_secret.strip(),
                "refresh_token": config.oauth_refresh_token.strip(),
                "grant_type": "refresh_token",
            },
        )
    except OAuthError as exc:
        if "invalid_grant" in str(exc).lower():
            raise OAuthError(
                "Google sign-in expired or was revoked. Reconnect the Google "
                "Workspace account in Settings."
            ) from exc
        raise
    access_token = str(payload.get("access_token", "")).strip()
    if not access_token:
        raise OAuthError("Google did not return an access token. Reconnect the account.")
    expires_in = _bounded_int(payload.get("expires_in"), 3600, 60, 86400)
    new_refresh = str(payload.get("refresh_token", "")).strip()
    if new_refresh and new_refresh != config.oauth_refresh_token:
        config.oauth_refresh_token = new_refresh
        save_email_config(config)
    _cache_oauth_token(config, access_token, expires_in)
    return access_token


def _get_google_userinfo(access_token: str) -> dict:
    payload = _oauth_http_json(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    email = str(payload.get("email", "")).strip()
    if not is_valid_email(email):
        raise OAuthError("Google did not return a valid account email.")
    if payload.get("verified_email") is False:
        raise OAuthError("Google says this account email is not verified.")
    return payload


def complete_oauth(config: EmailConfig, code: str) -> OAuthResult:
    """Exchange an authorization code, verify the account, and save the refresh token."""
    if not (code or "").strip():
        return OAuthResult(False, error="Google did not return an authorization code.")
    if not (config.oauth_client_id or "").strip():
        return OAuthResult(False, error="Add a Google OAuth client ID in Settings first.")
    if not (config.oauth_client_secret or "").strip():
        return OAuthResult(False, error="Add a Google OAuth client secret in Settings first.")
    redirect_uri = (
        (config.oauth_redirect_uri or "").strip() or DEFAULT_OAUTH_REDIRECT_URI
    )
    try:
        payload = _oauth_http_json(
            GOOGLE_TOKEN_URL,
            data={
                "code": code.strip(),
                "client_id": config.oauth_client_id.strip(),
                "client_secret": config.oauth_client_secret.strip(),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        access_token = str(payload.get("access_token", "")).strip()
        refresh_token = (
            str(payload.get("refresh_token", "")).strip()
            or config.oauth_refresh_token.strip()
        )
        if not access_token:
            raise OAuthError("Google did not return an access token.")
        if not refresh_token:
            raise OAuthError(
                "Google did not return a refresh token. Remove this app's access in "
                "your Google Account permissions and reconnect."
            )
        user = _get_google_userinfo(access_token)
        email = str(user.get("email", "")).strip()
        updated = replace(
            config,
            auth_method=AUTH_METHOD_OAUTH,
            from_email=email,
            oauth_email=email,
            oauth_refresh_token=refresh_token,
        )
        save_email_config(updated)
        expires_in = _bounded_int(payload.get("expires_in"), 3600, 60, 86400)
        _cache_oauth_token(updated, access_token, expires_in)
        return OAuthResult(True, email=email)
    except OAuthError as exc:
        return OAuthResult(False, error=str(exc))


def disconnect_oauth(config: EmailConfig) -> EmailConfig:
    """Forget the local refresh token while keeping OAuth client settings."""
    _OAUTH_TOKEN_CACHE.pop(_oauth_cache_key(config), None)
    updated = replace(
        config,
        oauth_refresh_token="",
        oauth_email="",
    )
    save_email_config(updated)
    return updated


def _footer(config: EmailConfig) -> str:
    lines = [
        'If you would prefer not to receive future outreach, reply "unsubscribe" '
        "and I will remove you."
    ]
    address = (config.postal_address or "").strip()
    if address:
        lines.append(address)
    return "\n".join(lines)


def build_message(
    config: EmailConfig,
    to_email: str,
    subject: str,
    body: str,
    to_name: str = "",
) -> EmailMessage:
    """Build a plain-text message and append the required opt-out footer."""
    if not is_valid_email(to_email):
        raise ValueError("The recipient email address is not valid.")
    if not is_valid_email(config.from_email):
        raise ValueError("The sender email address is not valid.")

    body_text = (body or "").strip()
    if not body_text:
        raise ValueError("The email body is empty.")
    body_text = f"{body_text}\n\n{_footer(config)}"

    message = EmailMessage()
    message["From"] = formataddr((config.from_name or DEFAULT_FROM_NAME, config.from_email))
    message["To"] = formataddr((to_name.strip(), to_email)) if to_name.strip() else to_email
    message["Subject"] = (subject or "").strip()
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=config.from_email.split("@", 1)[-1])
    message["Reply-To"] = config.from_email
    message["List-Unsubscribe"] = (
        f"<mailto:{config.from_email}?subject=unsubscribe>"
    )
    message.set_content(body_text)
    return message


def _friendly_error(exc: Exception, config: EmailConfig | None = None) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        if config is not None and _normalize_auth_method(config.auth_method) == AUTH_METHOD_OAUTH:
            return (
                "Google rejected the OAuth sign-in. Reconnect the Google Workspace "
                "account in Settings. If it still fails, ask your Workspace admin to "
                "allow this OAuth app and the Gmail scope."
            )
        if config is not None and _normalize_auth_method(config.auth_method) == AUTH_METHOD_SMTP:
            return (
                "The SMTP provider rejected the login. Check the SMTP host, port, "
                "username, and password. Some providers require an app-specific "
                "password or an API key instead of your normal password."
            )
        return (
            "Gmail rejected the login. Use the full Gmail address and a Google "
            "app password with 2-Step Verification enabled, not your normal password."
        )
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "The recipient address was refused by the mail server. No email was sent."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return (
            "The sender address was refused by the mail server. If you are using "
            "custom SMTP, verify that the From address or its domain is allowed by "
            "the provider. No email was sent."
        )
    if isinstance(exc, smtplib.SMTPDataError):
        return f"The mail server rejected the message. It was not sent: {exc}"
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return (
            "The SMTP server disconnected before the operation completed. If this "
            "happened during a send, the email may or may not have been delivered; "
            "check the recipient before retrying."
        )
    if isinstance(exc, smtplib.SMTPConnectError):
        if config is not None and _normalize_auth_method(config.auth_method) == AUTH_METHOD_SMTP:
            host = (config.smtp_host or "the SMTP host").strip()
            return (
                f"The app could not connect to {host}. Check the host, port, "
                "connection security, and internet connection."
            )
        return "The app could not connect to smtp.gmail.com. Check the internet connection."
    if isinstance(exc, (socket.gaierror, TimeoutError, OSError)):
        return (
            "Network or SMTP connection error. No message was confirmed as sent; "
            f"check before retrying: {exc}"
        )
    return (
        "Email sending failed. The message may or may not have been sent; check "
        f"before retrying: {exc}"
    )


def _smtp_oauth2_login(
    server: smtplib.SMTP, config: EmailConfig, access_token: str
) -> None:
    auth_string = (
        f"user={config.from_email}\x01auth=Bearer {access_token}\x01\x01"
    )
    server.auth(
        "XOAUTH2",
        lambda challenge=None: auth_string,
        initial_response_ok=True,
    )


def _connect_smtp(config: EmailConfig, timeout: int) -> smtplib.SMTP:
    """Open the correct SMTP connection and authenticate the sender."""
    method = _normalize_auth_method(config.auth_method)
    if method == AUTH_METHOD_SMTP:
        host = (config.smtp_host or "").strip()
        port = _bounded_int(config.smtp_port, SMTP_PORT, 1, 65535)
        security = _normalize_smtp_security(config.smtp_security)
    else:
        host = SMTP_HOST
        port = SMTP_PORT
        security = SMTP_SECURITY_STARTTLS

    context = ssl.create_default_context()
    server: smtplib.SMTP | None = None
    try:
        if security == SMTP_SECURITY_SSL:
            server = smtplib.SMTP_SSL(
                host, port, timeout=timeout, context=context
            )
            server.ehlo()
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
        if method == AUTH_METHOD_OAUTH:
            access_token = get_oauth_access_token(config)
            _smtp_oauth2_login(server, config, access_token)
        elif method == AUTH_METHOD_SMTP:
            server.login(
                (config.smtp_username or config.from_email).strip(),
                config.smtp_password or "",
            )
        else:
            server.login(
                config.from_email, (config.app_password or "").replace(" ", "")
            )
    except Exception:
        if server is not None:
            try:
                server.close()
            except Exception:
                pass
        raise
    return server


def send_email(
    config: EmailConfig,
    to_email: str,
    subject: str,
    body: str,
    to_name: str = "",
) -> SendResult:
    """Send one plain-text email. Never retries automatically."""
    missing = missing_config_fields(config)
    if missing:
        return SendResult(
            success=False,
            error="Email sending is not configured. Add " + " and ".join(missing) + " in Settings.",
            fatal=True,
        )

    try:
        message = build_message(config, to_email, subject, body, to_name=to_name)
    except ValueError as exc:
        return SendResult(success=False, error=str(exc), fatal=False)

    try:
        with _connect_smtp(config, timeout=30) as server:
            server.send_message(message)
        return SendResult(success=True, message_id=str(message["Message-ID"]))
    except OAuthError as exc:
        return SendResult(success=False, error=str(exc), fatal=True)
    except smtplib.SMTPAuthenticationError as exc:
        return SendResult(success=False, error=_friendly_error(exc, config), fatal=True)
    except smtplib.SMTPRecipientsRefused as exc:
        return SendResult(success=False, error=_friendly_error(exc, config), fatal=False)
    except smtplib.SMTPDataError as exc:
        return SendResult(success=False, error=_friendly_error(exc, config), fatal=False)
    except (
        smtplib.SMTPConnectError,
        smtplib.SMTPServerDisconnected,
        smtplib.SMTPHeloError,
        smtplib.SMTPSenderRefused,
    ) as exc:
        return SendResult(success=False, error=_friendly_error(exc, config), fatal=True)
    except (socket.gaierror, TimeoutError, OSError) as exc:
        return SendResult(success=False, error=_friendly_error(exc, config), fatal=True)
    except Exception as exc:  # pragma: no cover - defensive stop for unexpected failures
        return SendResult(
            success=False,
            error=_friendly_error(exc, config),
            fatal=True,
        )


def test_connection(config: EmailConfig) -> tuple[bool, str]:
    """Verify SMTP login without sending an email."""
    missing = missing_config_fields(config)
    if missing:
        return False, "Add " + " and ".join(missing) + " first."
    try:
        with _connect_smtp(config, timeout=20) as server:
            server.noop()
        method = _normalize_auth_method(config.auth_method)
        if method == AUTH_METHOD_OAUTH:
            return True, "Connected with Google Workspace sign-in. No email was sent."
        if method == AUTH_METHOD_SMTP:
            host = (config.smtp_host or "the SMTP provider").strip()
            return True, f"Connected to {host} and logged in. No email was sent."
        return True, "Connected and logged in. No email was sent."
    except OAuthError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, _friendly_error(exc, config)
