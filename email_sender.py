"""Local, human-approved Gmail / Google Workspace SMTP sending.

The module only sends when the Streamlit app explicitly calls send_email().
Credentials live in data/email_config.json (gitignored) or environment
variables. No credentials are written to the database or the send log.
"""
from __future__ import annotations

import json
import os
import re
import smtplib
import socket
import ssl
from dataclasses import asdict, dataclass
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
    smtp_host: str = SMTP_HOST
    smtp_port: int = SMTP_PORT


@dataclass
class SendResult:
    success: bool
    message_id: str = ""
    error: str = ""
    fatal: bool = False


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

    from_email = (
        os.environ.get("GMAIL_SMTP_USER")
        or os.environ.get("EMAIL_FROM_EMAIL")
        or str(raw.get("from_email", ""))
    ).strip()
    app_password = (
        os.environ.get("GMAIL_SMTP_APP_PASSWORD")
        or os.environ.get("EMAIL_APP_PASSWORD")
        or str(raw.get("app_password", ""))
    ).strip()
    postal_address = (
        os.environ.get("EMAIL_POSTAL_ADDRESS")
        or str(raw.get("postal_address", ""))
    ).strip()

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
        smtp_host=str(raw.get("smtp_host", SMTP_HOST)).strip() or SMTP_HOST,
        smtp_port=_bounded_int(raw.get("smtp_port"), SMTP_PORT, 1, 65535),
    )


def save_email_config(config: EmailConfig) -> Path:
    """Write local SMTP settings. The data directory is gitignored."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = asdict(config)
    payload["from_name"] = DEFAULT_FROM_NAME
    payload["app_password"] = (config.app_password or "").replace(" ", "").strip()
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


def missing_config_fields(config: EmailConfig) -> list[str]:
    missing: list[str] = []
    if not is_valid_email(config.from_email):
        missing.append("a valid Gmail / Google Workspace address")
    if not (config.app_password or "").strip():
        missing.append("a Google app password")
    return missing


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


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return (
            "Gmail rejected the login. Use the full Gmail address and a Google "
            "app password with 2-Step Verification enabled, not your normal password."
        )
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "The recipient address was refused by the mail server. No email was sent."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "The sender address was refused by the mail server. No email was sent."
    if isinstance(exc, smtplib.SMTPDataError):
        return f"The mail server rejected the message. It was not sent: {exc}"
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return (
            "The SMTP server disconnected before the operation completed. If this "
            "happened during a send, the email may or may not have been delivered; "
            "check the recipient before retrying."
        )
    if isinstance(exc, smtplib.SMTPConnectError):
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
        context = ssl.create_default_context()
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(config.from_email, config.app_password.replace(" ", ""))
            server.send_message(message)
        return SendResult(success=True, message_id=str(message["Message-ID"]))
    except smtplib.SMTPAuthenticationError as exc:
        return SendResult(success=False, error=_friendly_error(exc), fatal=True)
    except smtplib.SMTPRecipientsRefused as exc:
        return SendResult(success=False, error=_friendly_error(exc), fatal=False)
    except smtplib.SMTPDataError as exc:
        return SendResult(success=False, error=_friendly_error(exc), fatal=False)
    except (
        smtplib.SMTPConnectError,
        smtplib.SMTPServerDisconnected,
        smtplib.SMTPHeloError,
        smtplib.SMTPSenderRefused,
    ) as exc:
        return SendResult(success=False, error=_friendly_error(exc), fatal=True)
    except (socket.gaierror, TimeoutError, OSError) as exc:
        return SendResult(success=False, error=_friendly_error(exc), fatal=True)
    except Exception as exc:  # pragma: no cover - defensive stop for unexpected failures
        return SendResult(
            success=False,
            error=_friendly_error(exc),
            fatal=True,
        )


def test_connection(config: EmailConfig) -> tuple[bool, str]:
    """Verify SMTP login without sending an email."""
    missing = missing_config_fields(config)
    if missing:
        return False, "Add " + " and ".join(missing) + " first."
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(config.from_email, config.app_password.replace(" ", ""))
            server.noop()
        return True, "Connected and logged in. No email was sent."
    except Exception as exc:
        return False, _friendly_error(exc)
