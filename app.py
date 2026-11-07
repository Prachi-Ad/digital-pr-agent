import hashlib
import hmac
import html
import csv
import io
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import streamlit as st
import streamlit.components.v1 as components

import email_sender
import contact_providers

# Hosting platforms inject configuration through secrets. Mirror the values into
# the environment before importing agent.py, which reads them at import time.
try:
    for _key in (
        "OPENAI_API_KEY",
        "BRAND_NAME",
        "PRODUCT_DESCRIPTION",
        "BRAND_DOMAIN",
        "OPENAI_MODEL",
        "SEARCH_CONTEXT_SIZE",
    ):
        if _key not in os.environ and _key in st.secrets:
            os.environ[_key] = str(st.secrets[_key])
except Exception:
    pass

from agent import (
    BRAND_NAME,
    BRAND_DOMAIN,
    PRODUCT_DESCRIPTION,
    MODEL,
    SEARCH_CONTEXT_SIZE,
    HARDCODED_SENDER_NAME,
    HARDCODED_SENDER_ROLE,
    AssetAnalysis,
    JournalistProfile,
    JournalistResearchResults,
    ListicleContactResearchResults,
    ListicleOpportunity,
    ListicleResearchResults,
    PROpportunity,
    PRResearchResults,
    PublisherPolicyAssessment,
    analyze_article,
    assess_pr_fit,
    draft_journalist_pitch,
    draft_listicle_inclusion_request,
    find_opportunity_contact,
    research_journalists,
    research_journalist_email,
    research_listicle_contact,
    research_listicles,
    research_opportunities,
    research_publisher_policy,
)
from database import (
    DB_PATH,
    add_email_suppression,
    count_emails_sent_today,
    create_database_backup,
    email_sends_csv_bytes,
    get_journalist_record,
    get_journalist_contact_data,
    get_listicle_prospect,
    get_outreach_draft,
    get_pr_opportunity,
    init_db,
    is_email_suppressed,
    journalist_csv_bytes,
    list_email_sends,
    list_email_suppressions,
    list_journalists,
    list_listicle_prospects,
    list_outreach_drafts,
    list_pr_opportunities,
    listicle_csv_bytes,
    load_app_snapshot,
    log_email_send,
    mark_outreach_draft_send_failed,
    mark_outreach_draft_sent,
    opportunity_csv_bytes,
    outreach_csv_bytes,
    remove_email_suppression,
    save_app_snapshot,
    save_journalist_contact_data,
    sites_contacts_csv_bytes,
    update_outreach_draft,
    upsert_contact_book,
    upsert_journalist,
    upsert_listicle_prospect,
    upsert_outreach_draft,
    upsert_pr_opportunity,
    count_contact_book,
    find_contact_book,
    list_contact_book,
)

# Keep the SMTP config in the same local data directory as the database.
email_sender.DATA_DIR = Path(DB_PATH).parent
email_sender.CONFIG_PATH = email_sender.DATA_DIR / "email_config.json"
contact_providers.DATA_DIR = Path(DB_PATH).parent
contact_providers.CONFIG_PATH = contact_providers.DATA_DIR / "contactout_config.json"
contact_providers.HUNTER_CONFIG_PATH = contact_providers.DATA_DIR / "hunter_config.json"


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="PR Research Agent",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# The Google OAuth redirect returns to this page with ?code=...&state=...
# Handle it before the normal page is rendered. The state file and refresh
# token stay in the local, gitignored data folder.
def _handle_google_oauth_callback() -> None:
    params = st.query_params
    code = params.get("code")
    state = params.get("state")
    error = params.get("error")
    if not code and not error:
        return
    callback_id = hashlib.sha256(
        f"{code or ''}|{state or ''}|{error or ''}".encode("utf-8")
    ).hexdigest()[:16]
    if st.session_state.get("_oauth_callback_handled") == callback_id:
        return
    st.session_state["_oauth_callback_handled"] = callback_id
    st.session_state["main_nav"] = "Settings"

    if error:
        if state:
            email_sender.validate_oauth_state(state)
        detail = params.get("error_description") or error
        st.session_state["_email_settings_notice"] = (
            "warning",
            f"Google sign-in did not complete: {detail}",
        )
        st.query_params.clear()
        st.rerun()
        return

    if not email_sender.validate_oauth_state(state or ""):
        st.session_state["_email_settings_notice"] = (
            "error",
            "Google sign-in state did not match or expired. Start the connection "
            "again from Settings.",
        )
        st.query_params.clear()
        st.rerun()
        return

    config = email_sender.load_email_config()
    try:
        with st.spinner("Connecting Google Workspace account..."):
            result = email_sender.complete_oauth(config, code or "")
    except Exception as exc:
        result = email_sender.OAuthResult(
            False, error=f"Could not complete Google sign-in: {exc}"
        )
    if result.success:
        email_sender.add_oauth_account(result.email, result.refresh_token)
        st.session_state["_email_settings_notice"] = (
            "success",
            f"Connected {result.email}. Google sign-in is ready for sending.",
        )
    else:
        st.session_state["_email_settings_notice"] = ("error", result.error)
    st.query_params.clear()
    st.rerun()


_handle_google_oauth_callback()


# =========================================================
# OPTIONAL LOGIN GATE FOR A HOSTED DEPLOYMENT
# =========================================================

def _login_password() -> str:
    """Password from data/app_password.txt, falling back to APP_PASSWORD."""
    password_file = Path(DB_PATH).parent / "app_password.txt"
    try:
        if password_file.exists():
            value = password_file.read_text(encoding="utf-8-sig").strip()
            if value:
                return value
    except OSError:
        pass
    return (os.environ.get("APP_PASSWORD") or "").strip()


def _auth_secret() -> str:
    path = Path(DB_PATH).parent / "auth_secret.txt"
    try:
        if path.exists():
            value = path.read_text(encoding="utf-8-sig").strip()
            if value:
                return value
    except OSError:
        pass
    value = os.urandom(32).hex()
    try:
        path.write_text(value, encoding="utf-8")
    except OSError:
        pass
    return value


def _remember_token() -> str:
    return hmac.new(
        _auth_secret().encode("utf-8"),
        b"pr-agent-remember",
        hashlib.sha256,
    ).hexdigest()


def _cookie_authenticated() -> bool:
    try:
        value = (st.context.cookies.get("pr_auth") or "").strip()
    except Exception:
        return False
    return bool(value) and hmac.compare_digest(
        value.encode("utf-8"), _remember_token().encode("utf-8")
    )


def _set_remember_cookie() -> None:
    token = _remember_token()
    components.html(
        f"""<script>
        var secure = location.protocol === 'https:' ? '; Secure' : '';
        document.cookie = "pr_auth={token}; path=/; max-age=2592000; SameSite=Lax" + secure;
        </script>""",
        height=0,
    )


def _clear_remember_cookie() -> None:
    components.html(
        """<script>
        document.cookie = "pr_auth=; path=/; max-age=0; SameSite=Lax";
        </script>""",
        height=0,
    )


def _require_login() -> None:
    password = _login_password()
    if not password:
        return
    clearing = st.session_state.pop("_clear_auth_cookie", False)
    if clearing:
        _clear_remember_cookie()
    elif st.session_state.get("_authenticated") or _cookie_authenticated():
        st.session_state["_authenticated"] = True
        if st.session_state.pop("_set_auth_cookie", False):
            _set_remember_cookie()
        return
    st.markdown("## PR Research Agent")
    st.caption("Enter the workspace password to continue.")
    entered = st.text_input("Password", type="password", key="_login_password")
    if st.button("Sign in", type="primary", width="stretch"):
        if hmac.compare_digest(
            (entered or "").encode("utf-8"), password.encode("utf-8")
        ):
            st.session_state["_authenticated"] = True
            st.session_state["_set_auth_cookie"] = True
            st.session_state.pop("_login_password", None)
            st.rerun()
        else:
            st.error("That password is not correct.")
    st.stop()


_require_login()


# =========================================================
# SESSION STATE
# =========================================================

REVIEW_OPTIONS = [
    "Awaiting review",
    "Approve for journalist research",
    "Reject",
    "Needs more research",
]

LISTICLE_STATUS_OPTIONS = [
    "Awaiting review",
    "Approve to pursue",
    "Needs more research",
    "Already listed",
    "Reject",
]

PLACEMENT_OPTIONS = [
    "Not contacted",
    "Contacted",
    "Publisher replied",
    "Awaiting placement",
    "Placement confirmed",
    "Live placement verified",
    "Declined",
    "Already listed",
    "Closed",
]

JOURNALIST_STATUS_OPTIONS = [
    "Needs review",
    "Relevant writer",
    "Qualified pitch target",
    "Do not pursue",
]

DRAFT_STATUS_OPTIONS = [
    "Draft",
    "Ready to use",
    "Sent manually",
    "Replied",
    "Placement confirmed",
    "Declined",
    "Do not send",
]

# Older drafts may carry sending-oriented statuses. Show the closest
# research-only status without changing the stored record until saved.
LEGACY_DRAFT_STATUS = {
    "Approved for automated send": "Ready to use",
    "Approved for manual send": "Ready to use",
    "Sent": "Sent manually",
    "Send failed": "Ready to use",
}

PR_STEPS = ["Article", "PR angles", "Opportunities", "Journalists", "Outreach"]
LISTICLE_STEPS = ["Search", "Prospects", "Outreach"]

# The workflow shows three simple phases, while the saved step keeps the
# detailed screen the user is on. This keeps old saved work navigable.
PR_PHASES = {
    "Research": ["Article", "PR angles"],
    "Contacts": ["Opportunities", "Journalists"],
    "Outreach": ["Outreach"],
}
PR_STEP_PHASE = {
    step: phase for phase, steps in PR_PHASES.items() for step in steps
}
LISTICLE_PHASES = {
    "Find & review": ["Search", "Prospects"],
    "Outreach": ["Outreach"],
}
LISTICLE_STEP_PHASE = {
    step: phase for phase, steps in LISTICLE_PHASES.items() for step in steps
}
PR_PHASE_COPY = {
    "Research": (
        "Analyze the article and pick the angle.",
        "Paste a published article. The tool extracts credible angles and the evidence behind them.",
    ),
    "Contacts": (
        "Find the content and SEO contact.",
        "Approve the real openings, then the tool finds the writer, content manager, SEO lead, or link-building contact.",
    ),
    "Outreach": (
        "Write and copy.",
        "Draft the pitch, add a verified email, then copy it into your own email to send.",
    ),
}
LISTICLE_PHASE_COPY = {
    "Find & review": (
        "Find pages worth pursuing.",
        "Search for roundups and directories, then review fit, contact route, and policy.",
    ),
    "Outreach": (
        "Request inclusion.",
        "Draft the request, add a verified email, then copy it into your own email to send.",
    ),
}



DEFAULTS = {
    "analysis": None,
    "asset_analyses": {},
    "article_url": "",
    "selected_angle_index": None,
    "opportunity_results": None,
    "opportunity_reviews": {},
    "research_run_id": 0,
    "journalist_results": {},
    "journalist_reviews": {},
    "listicle_results": None,
    "listicle_reviews": {},
    "listicle_contact_results": {},
    "listicle_policy_results": {},
    "listicle_run_id": 0,
    "listicle_placement_progress": {},
    "workflow_mode": None,
    "pr_step": "Article",
    "listicle_step": "Search",
    "sender_name": HARDCODED_SENDER_NAME,
    "sender_role": HARDCODED_SENDER_ROLE,
    "main_nav": "Workspace",
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# PERMANENT LOCAL STORAGE
# =========================================================

init_db()


def _restore_model(value, model_class):
    if value is None:
        return None
    try:
        return model_class.model_validate(value)
    except Exception:
        return None


def _restore_map(key, model_class):
    restored = {}
    raw = _saved_snapshot.get(key, {}) if isinstance(_saved_snapshot, dict) else {}
    if isinstance(raw, dict):
        for item_key, item_value in raw.items():
            model = _restore_model(item_value, model_class)
            if model is not None:
                restored[str(item_key)] = model
    return restored


if not st.session_state.get("_persistent_state_loaded", False):
    _saved_snapshot = load_app_snapshot()
    model_fields = {
        "analysis": AssetAnalysis,
        "opportunity_results": PRResearchResults,
        "listicle_results": ListicleResearchResults,
    }
    simple_fields = [
        "article_url",
        "selected_angle_index",
        "opportunity_reviews",
        "research_run_id",
        "journalist_reviews",
        "listicle_reviews",
        "listicle_run_id",
        "listicle_placement_progress",
        "pr_step",
        "listicle_step",
        "sender_name",
        "sender_role",
    ]
    for state_key, model_class in model_fields.items():
        restored_value = _restore_model(_saved_snapshot.get(state_key), model_class)
        if restored_value is not None:
            st.session_state[state_key] = restored_value
    for state_key in simple_fields:
        if state_key in _saved_snapshot:
            st.session_state[state_key] = _saved_snapshot[state_key]
    st.session_state["journalist_results"] = _restore_map(
        "journalist_results", JournalistResearchResults
    )
    st.session_state["listicle_contact_results"] = _restore_map(
        "listicle_contact_results", ListicleContactResearchResults
    )
    st.session_state["listicle_policy_results"] = _restore_map(
        "listicle_policy_results", PublisherPolicyAssessment
    )
    st.session_state["asset_analyses"] = _restore_map(
        "asset_analyses", AssetAnalysis
    )
    # Older snapshots stored one active analysis. Seed the batch map from it,
    # but never resurrect an analysis the user explicitly cleared with
    # "Start new" (the snapshot then contains an explicit null).
    if "analysis" not in _saved_snapshot and st.session_state.asset_analyses:
        first_key = next(iter(st.session_state.asset_analyses))
        st.session_state.article_url = first_key
        st.session_state.analysis = st.session_state.asset_analyses[first_key]
    if st.session_state.analysis is not None:
        active_key = (st.session_state.article_url or "").strip()
        if active_key:
            st.session_state.asset_analyses[active_key] = st.session_state.analysis
    # Every new browser session starts on the launcher. Saved work remains
    # available through "Continue saved...", and "Back to start" always wins.
    st.session_state.workflow_mode = None
    st.session_state["_persistent_state_loaded"] = True

if st.session_state.pr_step not in PR_STEPS:
    st.session_state.pr_step = PR_STEPS[0]
if st.session_state.listicle_step not in LISTICLE_STEPS:
    st.session_state.listicle_step = LISTICLE_STEPS[0]

# Sender identity is fixed for this workspace. Override any older saved values.
st.session_state.sender_name = HARDCODED_SENDER_NAME
st.session_state.sender_role = HARDCODED_SENDER_ROLE


# =========================================================
# CUSTOM STYLING
# =========================================================

st.markdown(
    """
    <style>
    :root {
        --ink: #17182b;
        --muted: #6b6e85;
        --line: #e4e6f0;
        --surface: #ffffff;
        --accent: #5b5bd6;
        --accent-dark: #4646c6;
        --accent-soft: #eeefff;
        --teal: #0f9d8a;
        --amber: #b45309;
        --shadow: 0 10px 30px rgba(24, 28, 60, 0.06);
    }

    html, body, [class*="css"] {
        font-family: "Inter", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .stApp {
        background:
            radial-gradient(1100px 520px at 8% -12%, #eeefff 0%, rgba(238, 239, 255, 0) 62%),
            #f7f8fd;
    }

    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stAppDeployButton"] { display: none; }

    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid var(--line);
        width: 260px !important;
        min-width: 260px !important;
        flex-basis: 260px !important;
    }

    /* Let rows of cards and metric tiles wrap on smaller screens. */
    div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(88px, 1fr));
        gap: 0.5rem;
    }
    div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="stColumn"] {
        width: auto !important;
        min-width: 0;
    }
    div[data-testid="stHorizontalBlock"]:has(> div [data-testid="stVerticalBlockBorderWrapper"]) {
        flex-wrap: wrap;
    }
    div[data-testid="stHorizontalBlock"]:has(> div [data-testid="stVerticalBlockBorderWrapper"]) > div[data-testid="stColumn"] {
        flex: 1 1 280px;
        width: auto !important;
        min-width: 280px;
    }

    [data-testid="stSidebarContent"] { padding-top: 0.75rem; }
    [data-testid="stSidebarUserContent"] { padding: 0.4rem 1rem 1.4rem; }

    .block-container {
        max-width: 1200px;
        padding-top: 1.1rem;
        padding-bottom: 4rem;
    }
    [data-testid="stMain"] [data-testid="stVerticalBlock"] { gap: 0.75rem; }
    [data-testid="stMain"] .block-container > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has(style) { display: none; }

    h1, h2, h3, h4 { color: var(--ink); letter-spacing: -0.02em; padding: 0 !important; }
    h1 { font-size: 2rem; font-weight: 800; }
    h2 { font-size: 1.35rem; font-weight: 700; }
    h3 { font-size: 1.12rem; font-weight: 700; }
    h4 { font-size: 1.05rem !important; line-height: 1.35 !important; font-weight: 700; }

    [data-testid="stMarkdownContainer"]:has(h1),
    [data-testid="stMarkdownContainer"]:has(h2),
    [data-testid="stMarkdownContainer"]:has(h3),
    [data-testid="stMarkdownContainer"]:has(h4),
    [data-testid="stMarkdownContainer"]:has(.context-note),
    [data-testid="stMarkdownContainer"]:has(.queue-strip) { margin: 0 !important; }

    p, li, label, .stMarkdown { font-size: 15px; line-height: 1.6; }
    [data-testid="stCaptionContainer"] { margin: 0 !important; }
    [data-testid="stCaptionContainer"] p { margin: 0 !important; color: var(--muted); font-size: 13px; line-height: 1.45; }
    a { color: var(--accent); }

    /* ---------- page header ---------- */
    .page-header { margin: 0 0 0.9rem; }
    .page-eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        background: var(--accent-soft);
        color: #4338ca;
        border: 1px solid #d9dbff;
        border-radius: 999px;
        padding: 4px 10px;
        font-size: 10.5px;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .page-header h1 {
        margin: 0.42rem 0 0.22rem;
        font-size: 1.9rem;
        line-height: 1.16;
    }
    .page-header p { margin: 0; color: var(--muted); font-size: 14px; max-width: 780px; }

    /* ---------- sidebar brand ---------- */
    .app-brand {
        display: flex;
        align-items: center;
        gap: 11px;
        padding: 4px 0 14px;
    }
    .app-brand-mark {
        width: 40px;
        height: 40px;
        border-radius: 12px;
        background: linear-gradient(135deg, #7c7cf0, #4646c6);
        color: #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 13px;
        font-weight: 800;
        letter-spacing: -0.03em;
        box-shadow: 0 7px 16px rgba(91, 91, 214, 0.25);
    }
    .app-brand-name { font-size: 16px; font-weight: 800; color: var(--ink); line-height: 1.2; }
    .app-brand-tagline { font-size: 11px; color: var(--muted); margin-top: 2px; }

    .brand-chip {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        background: #f7f8fd;
        border: 1px solid var(--line);
        color: #4a4d68;
        border-radius: 999px;
        padding: 6px 11px;
        font-size: 12px;
        margin: 0 0 14px;
        max-width: 100%;
    }
    .brand-chip strong { color: var(--ink); font-weight: 700; }
    .brand-chip .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }

    /* ---------- sidebar navigation ---------- */
    [data-testid="stSidebar"] [data-testid="stRadioGroup"] { gap: 2px; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] {
        padding: 9px 12px;
        border-radius: 10px;
        cursor: pointer;
        transition: background 0.15s ease;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"]:hover { background: #f7f8fd; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] {
        background: var(--accent-soft);
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child {
        display: none;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] p {
        display: flex;
        align-items: center;
        gap: 9px;
        margin: 0;
        font-size: 14px;
        font-weight: 600;
        color: #4a4d68;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] [data-testid="stMarkdownContainer"] p {
        color: var(--accent);
        font-weight: 700;
    }

    /* Minimal monochrome nav icons (no emoji). */
    [data-testid="stSidebar"] [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] p::before {
        content: "";
        width: 17px;
        height: 17px;
        flex: 0 0 17px;
        background-color: #8a8da6;
        -webkit-mask-position: center;
        -webkit-mask-size: contain;
        -webkit-mask-repeat: no-repeat;
        mask-position: center;
        mask-size: contain;
        mask-repeat: no-repeat;
    }
    [data-testid="stSidebar"] [data-testid="stRadioGroup"] > div:nth-child(1) [data-testid="stMarkdownContainer"] p::before {
        -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='3' width='7' height='7' rx='1.5'/%3E%3Crect x='14' y='3' width='7' height='7' rx='1.5'/%3E%3Crect x='3' y='14' width='7' height='7' rx='1.5'/%3E%3Crect x='14' y='14' width='7' height='7' rx='1.5'/%3E%3C/svg%3E");
        mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='3' width='7' height='7' rx='1.5'/%3E%3Crect x='14' y='3' width='7' height='7' rx='1.5'/%3E%3Crect x='3' y='14' width='7' height='7' rx='1.5'/%3E%3Crect x='14' y='14' width='7' height='7' rx='1.5'/%3E%3C/svg%3E");
    }
    [data-testid="stSidebar"] [data-testid="stRadioGroup"] > div:nth-child(2) [data-testid="stMarkdownContainer"] p::before {
        -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 19.5A2.5 2.5 0 0 1 6.5 17H20'/%3E%3Cpath d='M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z'/%3E%3C/svg%3E");
        mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 19.5A2.5 2.5 0 0 1 6.5 17H20'/%3E%3Cpath d='M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z'/%3E%3C/svg%3E");
    }
    [data-testid="stSidebar"] [data-testid="stRadioGroup"] > div:nth-child(3) [data-testid="stMarkdownContainer"] p::before {
        -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='4' y1='21' x2='4' y2='14'/%3E%3Cline x1='4' y1='10' x2='4' y2='3'/%3E%3Cline x1='12' y1='21' x2='12' y2='12'/%3E%3Cline x1='12' y1='8' x2='12' y2='3'/%3E%3Cline x1='20' y1='21' x2='20' y2='16'/%3E%3Cline x1='20' y1='12' x2='20' y2='3'/%3E%3Cline x1='1' y1='14' x2='7' y2='14'/%3E%3Cline x1='9' y1='8' x2='15' y2='8'/%3E%3Cline x1='17' y1='16' x2='23' y2='16'/%3E%3C/svg%3E");
        mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='4' y1='21' x2='4' y2='14'/%3E%3Cline x1='4' y1='10' x2='4' y2='3'/%3E%3Cline x1='12' y1='21' x2='12' y2='12'/%3E%3Cline x1='12' y1='8' x2='12' y2='3'/%3E%3Cline x1='20' y1='21' x2='20' y2='16'/%3E%3Cline x1='20' y1='12' x2='20' y2='3'/%3E%3Cline x1='1' y1='14' x2='7' y2='14'/%3E%3Cline x1='9' y1='8' x2='15' y2='8'/%3E%3Cline x1='17' y1='16' x2='23' y2='16'/%3E%3C/svg%3E");
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] [data-testid="stMarkdownContainer"] p::before {
        background-color: var(--accent);
    }
    /* ---------- PR fit verdict ---------- */
    .fit-banner {
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        gap: 7px;
        padding: 8px 11px;
        border-radius: 9px;
        font-size: 13px;
        line-height: 1.45;
    }
    .fit-banner strong {
        font-size: 10.5px;
        font-weight: 800;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        white-space: nowrap;
    }
    .fit-banner span { color: #4a4d68; }
    .fit-banner.good { background: #ecfdf5; border: 1px solid #bbf7d0; }
    .fit-banner.good strong { color: #047857; }
    .fit-banner.possible { background: #eef2ff; border: 1px solid #c7d2fe; }
    .fit-banner.possible strong { color: #4338ca; }
    .fit-banner.warn { background: #fffbeb; border: 1px solid #fde68a; }
    .fit-banner.warn strong { color: #b45309; }
    .fit-banner.bad { background: #fef2f2; border: 1px solid #fecaca; }
    .fit-banner.bad strong { color: #b91c1c; }

    /* ---------- workflow header ---------- */
    .workflow-head { margin: 0 0 0.55rem; }
    .workflow-eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 10.5px;
        font-weight: 800;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        color: var(--accent);
    }
    .workflow-eyebrow .phase-count { color: var(--muted); font-weight: 700; letter-spacing: 0.05em; }
    .workflow-title { font-size: 1.55rem; font-weight: 800; letter-spacing: -0.02em; color: var(--ink); margin-top: 3px; }
    .workflow-sub { font-size: 13.5px; line-height: 1.5; color: var(--muted); margin-top: 2px; max-width: 720px; }
    .workflow-dots { display: flex; gap: 5px; margin-top: 10px; }
    .workflow-dots span {
        width: 42px;
        height: 4px;
        border-radius: 999px;
        background: #dfe2f2;
    }
    .workflow-dots span.done { background: var(--accent); }

    /* ---------- stepper pills ---------- */
    [data-testid="stMain"] [data-testid="stRadioGroup"][aria-orientation="horizontal"] {
        display: flex;
        flex-wrap: wrap;
        gap: 5px;
        width: fit-content;
        max-width: 100%;
        padding: 5px;
        background: #eef0f8;
        border-radius: 12px;
    }
    [data-testid="stMain"] [data-testid="stRadioGroup"][aria-orientation="horizontal"] [data-testid="stRadioOption"] {
        padding: 7px 13px;
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.15s ease;
    }
    [data-testid="stMain"] [data-testid="stRadioGroup"][aria-orientation="horizontal"] [data-testid="stRadioOption"]:hover {
        background: rgba(255, 255, 255, 0.7);
    }
    [data-testid="stMain"] [data-testid="stRadioGroup"][aria-orientation="horizontal"] [data-testid="stRadioOption"] > div > div:first-child {
        display: none;
    }
    [data-testid="stMain"] [data-testid="stRadioGroup"][aria-orientation="horizontal"] [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] p {
        font-size: 13px;
        font-weight: 600;
        color: #6b6e85;
        white-space: nowrap;
    }
    [data-testid="stMain"] [data-testid="stRadioGroup"][aria-orientation="horizontal"] [data-testid="stRadioOption"][data-selected="true"] {
        background: #ffffff;
        box-shadow: 0 2px 7px rgba(24, 28, 50, 0.14);
    }
    [data-testid="stMain"] [data-testid="stRadioGroup"][aria-orientation="horizontal"] [data-testid="stRadioOption"][data-selected="true"] [data-testid="stMarkdownContainer"] p {
        color: var(--ink);
        font-weight: 700;
    }
    /* ---------- metrics ---------- */
    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 9px 10px;
        box-shadow: 0 1px 2px rgba(24, 28, 50, 0.04);
        height: 100%;
    }
    [data-testid="stMetricLabel"] p {
        font-size: 10px !important;
        line-height: 1.3 !important;
        font-weight: 700 !important;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: var(--muted) !important;
    }
    [data-testid="stMetricValue"] { color: var(--ink); }
    [data-testid="stMetricValue"] p { font-size: 1.3rem; line-height: 1.2; font-weight: 800; }

    .context-note {
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        gap: 7px;
        padding: 0 0 0 10px;
        border-left: 2px solid #c7d2fe;
        font-size: 13px;
        line-height: 1.45;
        color: var(--muted);
    }
    .context-note span {
        font-size: 10px;
        font-weight: 800;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--muted);
    }

    .queue-strip {
        display: flex;
        gap: 1px;
        background: var(--line);
        border: 1px solid var(--line);
        border-radius: 12px;
        overflow: hidden;
    }
    .queue-strip > div {
        flex: 1;
        min-width: 0;
        background: var(--surface);
        padding: 9px 12px;
    }
    .queue-strip span {
        display: block;
        font-size: 9.5px;
        font-weight: 700;
        letter-spacing: 0.05em;
        line-height: 1.3;
        text-transform: uppercase;
        color: var(--muted);
    }
    .queue-strip strong {
        display: block;
        margin-top: 2px;
        font-size: 1.15rem;
        font-weight: 800;
        line-height: 1.2;
        color: var(--ink);
    }

    /* ---------- cards / containers ---------- */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--surface);
        border: 1px solid var(--line) !important;
        border-radius: 16px;
        box-shadow: var(--shadow);
    }

    /* Workflow picker cards */
    .st-key-workflow-pr,
    .st-key-workflow-listicles {
        background: var(--surface);
        border: 1px solid var(--line) !important;
        border-radius: 16px !important;
        box-shadow: var(--shadow);
        gap: 0.5rem !important;
        padding: 14px !important;
    }
    .st-key-workflow-pr [data-testid="stVerticalBlock"],
    .st-key-workflow-listicles [data-testid="stVerticalBlock"] {
        gap: 0.45rem;
    }
    .st-key-workflow-pr [data-testid="stVerticalBlock"]:has([data-testid="stButton"]),
    .st-key-workflow-listicles [data-testid="stVerticalBlock"]:has([data-testid="stButton"]) {
        border-radius: 14px;
    }

    [class*="st-key-opp-card"],
    [class*="st-key-listicle-card"] {
        padding: 12px 14px !important;
        gap: 0.5rem !important;
        border-radius: 14px !important;
    }

    [data-testid="stExpander"] {
        background: var(--surface);
        border: 1px solid var(--line) !important;
        border-radius: 12px;
        overflow: hidden;
    }
    [data-testid="stExpander"] summary {
        display: flex;
        align-items: center;
        padding: 0.7rem 0.95rem;
        font-weight: 600;
    }
    [data-testid="stExpander"] summary > span { flex: 1; }
    [data-testid="stExpander"] summary > span > span:first-child { display: none; }
    [data-testid="stExpander"] summary::after {
        content: "";
        width: 7px;
        height: 7px;
        flex: 0 0 7px;
        margin-left: auto;
        border-right: 1.6px solid #8a8da6;
        border-bottom: 1.6px solid #8a8da6;
        transform: rotate(45deg);
        transition: transform 0.15s ease;
    }
    [data-testid="stExpander"] details[open] summary::after { transform: rotate(-135deg); }
    [data-testid="stExpanderDetails"] { padding: 0 0.95rem 0.85rem; }

    /* ---------- buttons ---------- */
    .st-key-switch-workflow { display: flex; justify-content: flex-end; }
    .stButton > button,
    .stDownloadButton > button,
    .stLinkButton > a {
        border-radius: 10px;
        font-weight: 600;
        min-height: 2.5rem;
        transition: all 0.15s ease;
    }
    [data-testid="stBaseButton-secondary"] {
        background: #ffffff;
        border: 1px solid #dfe2f0;
        color: #2f3150;
    }
    [data-testid="stBaseButton-secondary"]:hover {
        border-color: var(--accent);
        color: var(--accent);
        background: #ffffff;
    }
    [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-primaryFormSubmit"] {
        background: linear-gradient(135deg, #6366f1, #4f46e5) !important;
        border: 1px solid transparent !important;
        color: #ffffff !important;
        box-shadow: 0 6px 14px rgba(79, 70, 229, 0.22);
    }
    [data-testid="stBaseButton-primary"]:hover,
    [data-testid="stBaseButton-primaryFormSubmit"]:hover {
        background: linear-gradient(135deg, #5b5bd6, #4646c6) !important;
        color: #ffffff !important;
    }

    /* ---------- inputs ---------- */
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea {
        border-radius: 10px;
        border-color: #dfe2f0;
        background: #ffffff;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {
        border-color: var(--accent);
        box-shadow: 0 0 0 3px rgba(91, 91, 214, 0.14);
    }

    /* ---------- tabs ---------- */
    [data-testid="stTabs"] [role="tablist"] {
        gap: 5px;
        background: #eef0f8;
        padding: 5px;
        border-radius: 12px;
        width: fit-content;
        max-width: 100%;
        overflow-x: auto;
        flex-wrap: nowrap;
    }
    [data-testid="stTabs"] button[role="tab"] {
        border-radius: 8px;
        padding: 7px 13px;
        font-size: 13px;
        font-weight: 600;
        color: #6b6e85;
    }
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        background: #ffffff;
        color: var(--ink);
        box-shadow: 0 2px 7px rgba(24, 28, 50, 0.14);
    }

    /* ---------- progress ---------- */
    [data-testid="stProgress"] { margin: 0.35rem 0 1rem; }
    [data-testid="stProgressBarTrack"] {
        height: 4px;
        background: #e8eaf5;
        border-radius: 999px;
        overflow: hidden;
    }
    [data-testid="stProgressBarTrack"] > div {
        background: linear-gradient(90deg, #7c7cf0, #4f46e5);
    }

    [data-testid="stAlert"] { border-radius: 12px; border: 1px solid var(--line); }
    hr { border-color: var(--line); margin: 0.9rem 0 !important; }

    .small-note { color: var(--muted); font-size: 13px; }

    .step-hint {
        background: #fffbeb;
        border: 1px solid #fde68a;
        border-radius: 12px;
        padding: 12px 14px;
        margin: 8px 0 16px 0;
    }

    @media (max-width: 900px) {
        .block-container { padding-left: 1rem; padding-right: 1rem; }
        [data-testid="stSidebar"] {
            width: 230px !important;
            min-width: 230px !important;
            flex-basis: 230px !important;
        }
        [data-testid="stMetric"] { padding: 8px 9px; }
        .page-header h1 { font-size: 1.7rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# NAVIGATION AND STEP HELPERS
# =========================================================

def go(page=None, mode=None, pr_step=None, listicle_step=None):
    """Navigate without touching a widget key after it has been rendered."""
    if page is not None:
        st.session_state["_goto_page"] = page
    if mode is not None:
        st.session_state["_goto_mode"] = mode
    if pr_step is not None:
        st.session_state["_goto_pr_step"] = pr_step
    if listicle_step is not None:
        st.session_state["_goto_listicle_step"] = listicle_step
    st.rerun()


def _go_home():
    """Leave the active workflow. Used as a widget callback so it always runs
    before the page is rendered."""
    st.session_state.workflow_mode = None
    for pending in (
        "_goto_mode",
        "_goto_page",
        "_goto_pr_step",
        "_goto_listicle_step",
    ):
        st.session_state.pop(pending, None)


def _apply_pending_navigation():
    if "_goto_page" in st.session_state:
        st.session_state.main_nav = st.session_state.pop("_goto_page")
    if "_goto_mode" in st.session_state:
        st.session_state.workflow_mode = st.session_state.pop("_goto_mode")
    if "_goto_pr_step" in st.session_state:
        candidate = st.session_state.pop("_goto_pr_step")
        if candidate in PR_STEPS:
            st.session_state.pr_step = candidate
    if "_goto_listicle_step" in st.session_state:
        candidate = st.session_state.pop("_goto_listicle_step")
        if candidate in LISTICLE_STEPS:
            st.session_state.listicle_step = candidate


def _step_control(steps, key):
    if st.session_state.get(key) not in steps:
        st.session_state[key] = steps[0]
    choice = st.radio(
        "Step",
        steps,
        horizontal=True,
        key=key,
        label_visibility="collapsed",
    )
    return choice


def _phase_control(phases, key, current, on_change):
    """Show the three workflow phases; the detailed step stays internal."""
    st.session_state[key] = current
    st.radio(
        "Phase",
        list(phases),
        horizontal=True,
        key=key,
        label_visibility="collapsed",
        on_change=on_change,
    )


def _pr_phase_changed():
    phase = st.session_state.pr_phase_widget
    st.session_state.pr_step = PR_PHASES[phase][0]


def _listicle_phase_changed():
    phase = st.session_state.listicle_phase_widget
    st.session_state.listicle_step = LISTICLE_PHASES[phase][0]


def _render_workflow_header(label, phase, phases, title, subtitle):
    """One compact header per phase: where you are, what to do, how far along."""
    index = list(phases).index(phase) + 1
    total = len(phases)
    dots = "".join(
        f'<span class="{"done" if position <= index else ""}"></span>'
        for position in range(1, total + 1)
    )
    st.markdown(
        f"""
        <div class="workflow-head">
            <div class="workflow-eyebrow">
                {html.escape(label)}
                <span class="phase-count">· Phase {index} of {total}</span>
            </div>
            <div class="workflow-title">{html.escape(title)}</div>
            <div class="workflow-sub">{html.escape(subtitle)}</div>
            <div class="workflow-dots">{dots}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _safe_choice(options, value):
    return value if value in options else options[0]


def _widget_suffix(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def _short_text(value, limit: int = 240) -> str:
    """One scannable line instead of a paragraph."""
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip(" ,.;:") + "…"


PR_FIT_STYLES = {
    "Strong fit": ("good", "Good for PR"),
    "Possible fit": ("possible", "Possible"),
    "Weak fit": ("warn", "Weak PR fit"),
    "Not suitable": ("bad", "Not good for PR"),
}


def _render_pr_fit(opportunity, key_prefix: str) -> None:
    """Show the publication verdict, and let the human check or re-check it."""
    fit = (getattr(opportunity, "pr_fit", "") or "").strip()
    reason = (getattr(opportunity, "pr_fit_reason", "") or "").strip()
    flags = [
        str(flag).strip()
        for flag in (getattr(opportunity, "pr_red_flags", []) or [])
        if str(flag).strip()
        and not str(flag).strip().lower().startswith("none")
        and "no red flags" not in str(flag).strip().lower()
    ]
    style, label = PR_FIT_STYLES.get(fit, ("", "PR fit not checked"))
    if style:
        st.markdown(
            f'<div class="fit-banner {style}"><strong>{label}</strong>'
            f"<span>{html.escape(reason or 'No reason recorded.')}</span></div>",
            unsafe_allow_html=True,
        )
        if flags:
            st.caption("Signals: " + " · ".join(flags))
    else:
        st.caption("This blog has not been checked for PR suitability yet.")

    if st.button(
        "Re-check PR fit" if style else "Check PR fit",
        key=f"{key_prefix}_fit_{_widget_suffix(opportunity.article_url)}",
        width="stretch",
    ):
        with st.spinner("Checking the blog, its authors, and its editorial route..."):
            try:
                assessment = assess_pr_fit(opportunity)
                opportunity.pr_fit = assessment.pr_fit
                opportunity.pr_fit_reason = assessment.reason
                opportunity.pr_red_flags = list(assessment.red_flags)
                opportunity.recommended_action = assessment.recommended_action
                upsert_pr_opportunity(opportunity, review_status=None)
                st.rerun()
            except Exception as exc:
                st.error(f"PR fit check failed: {exc}")


def _status_counts(statuses, options):
    counts = Counter(statuses)
    return {option: counts.get(option, 0) for option in options}


def _queue_strip(items):
    cells = "".join(
        f"<div><span>{html.escape(label)}</span><strong>{value}</strong></div>"
        for label, value in items
    )
    st.markdown(f'<div class="queue-strip">{cells}</div>', unsafe_allow_html=True)


def _load_saved_listicle_results():
    """Rebuild the listicle workflow from saved records after a restart."""
    rows = list_listicle_prospects()
    items = []
    themes = []
    for row in rows:
        try:
            items.append(ListicleOpportunity.model_validate(row.get("payload") or {}))
        except Exception:
            continue
        theme = row.get("search_theme")
        if theme and theme not in themes:
            themes.append(theme)
    if not items:
        return None
    return ListicleResearchResults(
        search_theme=", ".join(themes) or "Saved prospects",
        research_summary=(
            f"Showing {len(items)} listicle prospect(s) loaded from the local library. "
            "Saved review decisions, contacts, and policy findings are restored automatically."
        ),
        opportunities=items,
    )


def _load_saved_pr_results():
    """Rebuild the PR review queue from saved records after a restart."""
    rows = list_pr_opportunities()
    items = []
    angle = ""
    for row in rows:
        try:
            items.append(PROpportunity.model_validate(row.get("payload") or {}))
        except Exception:
            continue
        if not angle and row.get("selected_angle"):
            angle = row.get("selected_angle")
    if not items:
        return None
    return PRResearchResults(
        selected_angle=angle or "Saved PR research",
        research_summary=(
            f"Showing {len(items)} PR opportunity record(s) loaded from the local library. "
            "Saved review decisions are restored automatically."
        ),
        opportunities=items,
    )


# =========================================================
# SHARED RENDERING
# =========================================================

def _page_header(eyebrow: str, title: str, subtitle: str):
    """A compact, consistent page header used by all three pages."""
    st.markdown(
        f"""
        <div class="page-header">
            <div class="page-eyebrow">{html.escape(eyebrow)}</div>
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_workspace_metrics():
    listicles = list_listicle_prospects()
    opportunities = list_pr_opportunities()
    journalists = list_journalists()
    drafts = list_outreach_drafts()
    pending = (
        sum(1 for row in listicles if row.get("review_status") == "Awaiting review")
        + sum(1 for row in opportunities if row.get("review_status") == "Awaiting review")
        + sum(1 for row in journalists if row.get("qualification_status") == "Needs review")
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Listicle prospects", len(listicles))
    c2.metric("PR opportunities", len(opportunities))
    c3.metric("Journalists", len(journalists))
    c4.metric("Outreach drafts", len(drafts))
    c5.metric("Needs review", pending)


def _render_analysis_details(analysis):
    st.markdown(f"**Main topic:** {analysis.main_topic}")
    st.markdown("**Target audience**")
    for audience in analysis.target_audience:
        st.write(f"- {audience}")
    st.markdown("**Key claims**")
    for claim in analysis.key_claims:
        st.write(f"- {claim}")
    st.markdown("**Statistics and sources**")
    for stat in analysis.statistics:
        with st.expander(stat.statistic):
            st.write(f"**Source:** {stat.source}")
            st.write(f"**Data provenance:** {stat.data_provenance}")
            st.write(f"**PR relevance:** {stat.pr_relevance}")
    st.markdown("**Useful assets**")
    for asset in analysis.useful_assets:
        st.write(f"- {asset}")
    st.info(analysis.assessment)


def _find_saved_analysis(url: str):
    """Return the saved analysis matching a URL, if one exists."""
    target = (url or "").strip()
    item = (st.session_state.get("asset_analyses") or {}).get(target)
    if item is not None:
        return target, item
    return None, None


def _reset_pr_downstream():
    st.session_state.selected_angle_index = None
    st.session_state.opportunity_results = None
    st.session_state.opportunity_reviews = {}
    st.session_state.research_run_id = 0
    st.session_state.journalist_results = {}
    st.session_state.journalist_reviews = {}


def _start_new_pr():
    """Begin a fresh campaign without deleting saved analyses or records."""
    _reset_pr_downstream()
    st.session_state.analysis = None
    st.session_state.article_url = ""
    st.session_state.article_url_slot_count = 1
    for index in range(5):
        st.session_state.pop(f"article_url_{index}", None)
    go(mode="digital_pr", pr_step="Article")


def _start_new_listicle():
    """Begin a fresh listicle search without deleting saved prospects."""
    st.session_state.listicle_results = None
    st.session_state.listicle_reviews = {}
    st.session_state.listicle_run_id += 1
    go(mode="listicles", listicle_step="Search")


def _activate_asset(key: str, force_reset: bool = False):
    analyses = st.session_state.get("asset_analyses") or {}
    item = analyses.get(key)
    if item is None:
        return
    if force_reset or st.session_state.get("article_url") != key:
        _reset_pr_downstream()
    st.session_state.article_url = key
    st.session_state.analysis = item


def _parse_article_urls(raw: str):
    """Parse one URL per line, deduplicate, and return valid and invalid URLs."""
    valid = []
    invalid = []
    seen = set()
    for line in (raw or "").splitlines():
        url = line.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        if not url.startswith("https://"):
            invalid.append(url)
            continue
        valid.append(url)
    return valid, invalid


def _render_draft_editor(record, key_prefix):
    payload = record.get("payload") or {}
    st.divider()
    st.markdown("**Draft for review**")
    meta = (
        f"Channel: {payload.get('channel', 'Unknown')}  ·  "
        f"Confidence: {payload.get('confidence', 'Unknown')}"
    )
    st.caption(meta)

    target_url = (record.get("target_url") or "").strip()
    if target_url.startswith("https://"):
        st.link_button("Open target page", target_url, key=f"{key_prefix}_target_{_widget_suffix(record['draft_key'])}")

    suffix = _widget_suffix(f"{record['draft_key']}|{record['updated_at']}")
    form_key = f"{key_prefix}_form_{suffix}"
    current_status = LEGACY_DRAFT_STATUS.get(
        record.get("draft_status", "Draft"), record.get("draft_status", "Draft")
    )
    status_index = DRAFT_STATUS_OPTIONS.index(
        _safe_choice(DRAFT_STATUS_OPTIONS, current_status)
    )

    if st.session_state.pop(f"{key_prefix}_saved", False):
        st.success(
            "Draft saved locally. Copy it below and send it from your email."
        )
    if record.get("sent_at"):
        st.caption(
            f"Sent: {record['sent_at']} · Message ID: "
            f"{record.get('message_id') or 'Not recorded'}"
        )
        if record.get("draft_status") != "Sent":
            st.warning(
                "This draft has a sent record. Do not approve it for sending again "
                "unless you intend to email the recipient twice."
            )
    elif record.get("send_error"):
        st.warning(f"Last send failed: {record['send_error']}")
    if record.get("send_attempts"):
        st.caption(f"Send attempts recorded: {record['send_attempts']}")

    with st.form(form_key):
        subject = st.text_input(
            "Subject line",
            value=record.get("subject", ""),
            key=f"{key_prefix}_subject_{suffix}",
        )
        recipient_email = st.text_input(
            "Recipient email",
            value=record.get("recipient_email", ""),
            placeholder="name@publication.com",
            help=(
                "Use a verified public editorial or author email. Leave blank until you "
                "have checked the address. It is stored with the draft for your records."
            ),
            key=f"{key_prefix}_email_{suffix}",
        )
        body = st.text_area(
            "Message",
            value=record.get("body", ""),
            height=300,
            key=f"{key_prefix}_body_{suffix}",
        )
        status = st.selectbox(
            "Draft status",
            DRAFT_STATUS_OPTIONS,
            index=status_index,
            help=(
                "Track your own outreach: Draft, Ready to use, Sent manually, "
                "Replied, Placement confirmed."
            ),
            key=f"{key_prefix}_status_{suffix}",
        )
        if st.form_submit_button("Save draft", type="primary", width="stretch"):
            email_value = (recipient_email or "").strip()
            if email_value and not email_sender.is_valid_email(email_value):
                st.error("Enter a valid recipient email address, or leave it blank.")
            else:
                try:
                    update_outreach_draft(
                        record["draft_key"],
                        subject,
                        body,
                        status,
                        recipient_email=email_value,
                    )
                    st.session_state[f"{key_prefix}_saved"] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"Draft could not be saved: {exc}")

    with st.expander("Why this draft is personalized"):
        st.write(f"**Personalization evidence:** {payload.get('personalization_evidence', 'Not saved')}")
        st.write(f"**Asset used:** {payload.get('asset_used', 'Not saved')}")
        st.write(f"**Call to action:** {payload.get('call_to_action', 'Not saved')}")
        st.write("**Facts to verify before sending:**")
        facts = payload.get("facts_to_verify") or []
        if facts:
            for fact in facts:
                st.write(f"- {fact}")
        else:
            st.write("- None listed. Still verify names, links, and claims.")
        st.write(f"**Compliance notes:** {payload.get('compliance_notes', 'None')}")

    with st.expander("Copy this email"):
        st.caption(
            "Use the copy icon, then paste into Gmail. Subject and message are "
            "included."
        )
        st.code(
            f"To: {record.get('recipient_email', '')}\n"
            f"Subject: {record.get('subject', '')}\n\n"
            f"{record.get('body', '')}",
            language=None,
        )

    download_text = (
        f"To: {record.get('recipient_email', '')}\n"
        f"Subject: {record.get('subject', '')}\n\n{record.get('body', '')}\n"
    )
    st.download_button(
        "Download draft as text",
        data=download_text.encode("utf-8"),
        file_name=f"outreach_draft_{suffix}.txt",
        mime="text/plain",
        key=f"{key_prefix}_download_{suffix}",
    )
    st.caption(
        "Copy or download this draft and send it from your email. The app does "
        "not send in research-only mode."
    )


def _render_no_draft(record_label, button_label, button_key, on_prepare, disabled_reason=None):
    if disabled_reason:
        st.warning(disabled_reason)
        return
    if st.button(button_label, key=button_key, type="primary"):
        with st.spinner("Writing the draft locally. No web search is used for this step..."):
            try:
                on_prepare()
                st.rerun()
            except Exception as exc:
                st.error(f"{record_label} draft could not be prepared.")
                st.exception(exc)


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, remainder = divmod(seconds, 60)
    if minutes and remainder:
        return f"{minutes}m {remainder}s"
    if minutes:
        return f"{minutes}m"
    return f"{remainder}s"


def _approved_drafts_for_types(draft_types: set[str]) -> list[dict]:
    return [
        row
        for row in list_outreach_drafts()
        if row.get("draft_type") in draft_types
        and row.get("draft_status") == "Approved for automated send"
    ]


def _draft_ready_for_bulk_approval(record: dict) -> bool:
    """A draft can be bulk-approved only when it is complete and addressable."""
    if record.get("draft_status") != "Draft" or record.get("sent_at"):
        return False
    email_value = (record.get("recipient_email") or "").strip()
    return bool(
        email_sender.is_valid_email(email_value)
        and not is_email_suppressed(email_value)
        and (record.get("subject") or "").strip()
        and (record.get("body") or "").strip()
    )


def _bulk_approve_ready_drafts(draft_types: set[str]) -> tuple[int, int]:
    """Approve every complete draft for these types. Approval is not sending."""
    approved = 0
    skipped = 0
    for record in list_outreach_drafts():
        if record.get("draft_type") not in draft_types:
            continue
        if record.get("draft_status") != "Draft" or record.get("sent_at"):
            continue
        if not _draft_ready_for_bulk_approval(record):
            skipped += 1
            continue
        update_outreach_draft(
            record["draft_key"],
            record.get("subject", ""),
            record.get("body", ""),
            "Approved for automated send",
            recipient_email=(record.get("recipient_email") or "").strip(),
        )
        approved += 1
    return approved, skipped


def _drafts_needing_email(draft_types: set[str]) -> int:
    return sum(
        1
        for record in list_outreach_drafts()
        if record.get("draft_type") in draft_types
        and record.get("draft_status") == "Draft"
        and not email_sender.is_valid_email(
            (record.get("recipient_email") or "").strip()
        )
    )


def _render_bulk_outreach_actions(
    scope_key: str,
    draft_types: set[str],
    missing_count: int,
    prepare_missing,
) -> None:
    """Bulk draft creation and bulk approval for one outreach workflow."""
    notice_key = f"{scope_key}_notice"
    notice = st.session_state.pop(notice_key, None)
    if notice:
        tone, message = notice
        if tone == "success":
            st.success(message)
        else:
            st.warning(message)

    records = [
        record
        for record in list_outreach_drafts()
        if record.get("draft_type") in draft_types
    ]
    waiting = _drafts_needing_email(draft_types)
    st.caption(
        f"{len(records)} draft{'s' if len(records) != 1 else ''} saved · "
        f"{waiting} waiting for a recipient email."
    )
    if st.button(
        f"Prepare all missing drafts ({missing_count})",
        key=f"{scope_key}_prepare",
        type="primary",
        width="stretch",
        disabled=missing_count == 0,
    ):
        try:
            with st.spinner(
                "Preparing drafts locally. No web search is used for this step..."
            ):
                created = prepare_missing()
            st.session_state[notice_key] = (
                "success",
                f"Prepared {created} draft{'s' if created != 1 else ''}. "
                "Copy or download them below.",
            )
            st.rerun()
        except Exception as exc:
            st.error(f"Drafts could not be prepared: {exc}")

    st.caption(
        "Drafts are never sent by the app in this mode. Copy or download them "
        "and send from your email."
    )



def _run_email_batch(scope_key: str, approved: list[dict], config) -> None:
    """Send the approved queue sequentially, with a delay and a hard daily cap."""
    result_key = f"{scope_key}_email_result"
    fresh = {row["draft_key"]: row for row in list_outreach_drafts()}
    queue = []
    for row in approved:
        current = fresh.get(row["draft_key"])
        if (
            current is None
            or current.get("draft_status") != "Approved for automated send"
            or current.get("sent_at")
        ):
            st.session_state[result_key] = {
                "sent": [],
                "failed": [],
                "stopped": "The approved queue changed before sending. Review the drafts again.",
            }
            st.rerun()
        queue.append(current)

    total = len(queue)
    sent: list[dict] = []
    failed: list[dict] = []
    uncertain: list[dict] = []
    stopped = ""
    progress = st.progress(0.0, text="Preparing the approved queue...")
    status_area = st.empty()

    for index, row in enumerate(queue, start=1):
        if count_emails_sent_today() >= config.daily_cap:
            stopped = (
                f"Daily cap reached ({config.daily_cap}). "
                "The remaining approved drafts were not sent."
            )
            break

        recipient = (row.get("recipient_name") or "recipient").strip()
        email = (row.get("recipient_email") or "").strip()
        subject = row.get("subject") or ""
        body = row.get("body") or ""
        progress.progress(
            (index - 1) / total,
            text=f"Sending {index} of {total}: {recipient}",
        )

        send_result = email_sender.send_email(
            config,
            to_email=email,
            subject=subject,
            body=body,
            to_name=recipient,
        )

        if send_result.success:
            try:
                mark_outreach_draft_sent(
                    row["draft_key"], email, send_result.message_id
                )
                log_email_send(
                    draft_key=row["draft_key"],
                    draft_type=row.get("draft_type", ""),
                    recipient_name=recipient,
                    recipient_email=email,
                    publication=row.get("publication", ""),
                    subject=subject,
                    body=body,
                    status="sent",
                    message_id=send_result.message_id,
                )
            except Exception as exc:
                uncertain.append(
                    {
                        "recipient": recipient,
                        "email": email,
                        "error": (
                            "The email was sent, but the local record could not be "
                            f"saved: {exc}"
                        ),
                    }
                )
                st.session_state.setdefault("uncertain_sent_draft_keys", set()).add(
                    row["draft_key"]
                )
                stopped = (
                    "An email was sent but the local record could not be updated. "
                    "Do not resend it. Check the database and mark it manually."
                )
                status_area.error(stopped)
                break
            sent.append({"recipient": recipient, "email": email})
            status_area.success(f"Sent to {recipient} <{email}>.")
        else:
            try:
                mark_outreach_draft_send_failed(row["draft_key"], send_result.error)
                log_email_send(
                    draft_key=row["draft_key"],
                    draft_type=row.get("draft_type", ""),
                    recipient_name=recipient,
                    recipient_email=email,
                    publication=row.get("publication", ""),
                    subject=subject,
                    body=body,
                    status="failed",
                    error=send_result.error,
                )
            except Exception as exc:
                failed.append(
                    {
                        "recipient": recipient,
                        "email": email,
                        "error": (
                            f"{send_result.error} (The local log also failed: {exc})"
                        ),
                    }
                )
                stopped = (
                    "A send failed and the local record could not be updated. "
                    "Check the database and the recipient before retrying."
                )
                status_area.error(stopped)
                break
            failed.append(
                {
                    "recipient": recipient,
                    "email": email,
                    "error": send_result.error,
                }
            )
            status_area.error(f"Could not send to {recipient}: {send_result.error}")
            if send_result.fatal:
                stopped = (
                    "Sending stopped after a connection or authentication error. "
                    "Fix the email settings and review the remaining drafts. If the "
                    "connection dropped during a send, check that recipient before "
                    "retrying; delivery may be uncertain."
                )
                break

        progress.progress(index / total, text=f"Processed {index} of {total}")
        if index < total:
            for remaining in range(config.delay_seconds, 0, -1):
                status_area.caption(
                    f"Waiting {remaining}s before the next send. Keep this tab open."
                )
                time.sleep(1)

    if not stopped:
        progress.progress(1.0, text="Batch complete.")
    st.session_state[result_key] = {
        "sent": sent,
        "failed": failed,
        "uncertain": uncertain,
        "stopped": stopped,
    }
    st.rerun()


def _render_email_batch_panel(scope_key: str, draft_types: set[str]) -> None:
    st.subheader("Batch send approved drafts")
    st.caption(
        "Only drafts with status 'Approved for automated send' are included. "
        "The app sends one recipient at a time, with a delay, a daily cap, a "
        "do-not-send list, and a permanent send log. Every email gets an opt-out line."
    )

    result_key = f"{scope_key}_email_result"
    result = st.session_state.get(result_key)
    if result:
        with st.container(border=True):
            if result.get("sent"):
                st.success(
                    f"Sent {len(result['sent'])} email"
                    f"{'s' if len(result['sent']) != 1 else ''}."
                )
                for item in result["sent"]:
                    st.write(f"- {item['recipient']} · {item['email']}")
            if result.get("failed"):
                st.error(
                    f"{len(result['failed'])} email"
                    f"{'s' if len(result['failed']) != 1 else ''} failed."
                )
                for item in result["failed"]:
                    st.write(f"- {item['recipient']} · {item['email']}: {item['error']}")
            if result.get("uncertain"):
                st.warning(
                    f"{len(result['uncertain'])} send"
                    f"{'s' if len(result['uncertain']) != 1 else ''} have an "
                    "uncertain local record. Do not resend without checking."
                )
                for item in result["uncertain"]:
                    st.write(f"- {item['recipient']} · {item['email']}: {item['error']}")
                if st.button(
                    "I checked the uncertain sends; clear the session warning",
                    key=f"{scope_key}_clear_uncertain",
                ):
                    st.session_state.pop("uncertain_sent_draft_keys", None)
                    st.rerun()
            if result.get("stopped"):
                st.warning(result["stopped"])
            if st.button("Dismiss send summary", key=f"{scope_key}_dismiss_result"):
                st.session_state.pop(result_key, None)
                st.rerun()
        st.divider()

    config = email_sender.load_email_config()
    missing = email_sender.missing_config_fields(config)
    if missing:
        st.warning(
            "Email sending is not configured yet. Add "
            + " and ".join(missing)
            + " in Settings."
        )
        if st.button("Open email settings", key=f"{scope_key}_open_settings"):
            go(page="Settings")
        return

    approved = _approved_drafts_for_types(draft_types)
    if not approved:
        st.info(
            "No drafts are approved for automated send. Open a draft below, add the "
            "recipient's verified email, and set its status to "
            "'Approved for automated send'."
        )
        return

    table_rows = []
    blockers: list[str] = []
    for row in approved:
        recipient = (row.get("recipient_name") or "Unknown recipient").strip()
        email = (row.get("recipient_email") or "").strip()
        payload = row.get("payload") or {}
        channel = payload.get("channel", "Unknown")
        if row.get("sent_at"):
            blockers.append(f"{recipient} already has a sent record. Do not resend it.")
        if row["draft_key"] in st.session_state.get("uncertain_sent_draft_keys", set()):
            blockers.append(
                f"{recipient} may already have been sent in this session. "
                "Check the database before resending."
            )
        if not email_sender.is_valid_email(email):
            blockers.append(f"{recipient} needs a valid recipient email.")
        elif is_email_suppressed(email):
            blockers.append(f"{recipient} is on the do-not-send list.")
        if not (row.get("subject") or "").strip():
            blockers.append(f"{recipient} needs a subject line.")
        if not (row.get("body") or "").strip():
            blockers.append(f"{recipient} needs a message body.")
        table_rows.append(
            {
                "Recipient": recipient,
                "Email": email or "Missing",
                "Publication": row.get("publication", ""),
                "Channel": channel,
                "Subject": row.get("subject", ""),
            }
        )

    st.dataframe(table_rows, width="stretch", hide_index=True)

    channels = {
        str((row.get("payload") or {}).get("channel", "")).lower()
        for row in approved
    }
    if any("form" in channel for channel in channels):
        st.warning(
            "At least one draft was written for a contact form. Confirm that email "
            "is an appropriate route for that publisher before sending."
        )

    with st.expander("Preview the exact messages that will be sent"):
        for row in approved:
            recipient = (row.get("recipient_name") or "Unknown recipient").strip()
            st.markdown(f"**{recipient} · {row.get('recipient_email', '')}**")
            st.caption(row.get("subject", ""))
            body = row.get("body", "")
            st.text(body[:1600] + ("\n\n[Preview truncated]" if len(body) > 1600 else ""))
            st.caption("The opt-out footer is appended automatically at send time.")
            st.divider()

    if blockers:
        st.error("Fix these drafts before sending:\n\n- " + "\n- ".join(blockers))
        return

    sent_today = count_emails_sent_today()
    remaining = max(0, config.daily_cap - sent_today)
    st.caption(
        f"Daily cap: {sent_today}/{config.daily_cap} sent today · "
        f"{remaining} remaining · Delay: {config.delay_seconds}s between sends · "
        f"Estimated time: {_format_duration(max(0, len(approved) - 1) * config.delay_seconds)}."
    )
    if remaining == 0:
        st.error("The daily send cap has been reached. No more emails can be sent today.")
        return
    if len(approved) > remaining:
        st.error(
            f"{len(approved)} drafts are approved, but the daily cap allows only "
            f"{remaining} more send{'s' if remaining != 1 else ''} today. "
            "Reduce approvals or raise the cap in Settings."
        )
        return
    if not config.postal_address.strip():
        st.warning(
            "No mailing address is configured. Add one in Settings for commercial-email "
            "compliance. The opt-out line is still included."
        )

    signature = hashlib.sha256(
        "|".join(
            f"{row['draft_key']}:{row.get('updated_at', '')}:{row.get('recipient_email', '')}"
            for row in approved
        ).encode("utf-8")
    ).hexdigest()[:12]
    confirmed = st.checkbox(
        f"I verified the {len(approved)} recipient address"
        f"{'es' if len(approved) != 1 else ''}, the draft text, the publisher policy, "
        "and that email is an appropriate contact route.",
        key=f"{scope_key}_confirm_{signature}",
    )
    if st.button(
        f"Send {len(approved)} approved email"
        f"{'s' if len(approved) != 1 else ''}",
        type="primary",
        width="stretch",
        disabled=not confirmed,
        key=f"{scope_key}_send_{signature}",
    ):
        _run_email_batch(scope_key, approved, config)


# =========================================================
# DIGITAL PR WORKFLOW
# =========================================================

def _render_pr_article():
    st.caption(
        "Add up to 5 published article URLs. The agent extracts useful angles "
        "and evidence for each."
    )

    if "article_url_slot_count" not in st.session_state:
        st.session_state.article_url_slot_count = 1
    if st.session_state.pop("_remove_last_article_url", False):
        last_index = max(0, st.session_state.article_url_slot_count - 1)
        st.session_state.pop(f"article_url_{last_index}", None)
        st.session_state.article_url_slot_count = max(1, last_index)
    if "article_url_0" not in st.session_state:
        st.session_state.article_url_0 = (st.session_state.article_url or "").strip()

    slot_count = max(1, min(5, int(st.session_state.article_url_slot_count)))
    st.session_state.article_url_slot_count = slot_count
    url_values = []
    for index in range(slot_count):
        url_values.append(
            st.text_input(
                f"Article URL {index + 1}",
                key=f"article_url_{index}",
                placeholder="https://example.com/article",
            )
        )

    add_col, remove_col, _ = st.columns([1.2, 1.2, 3.6])
    with add_col:
        if slot_count < 5 and st.button(
            "+ Add URL", key="add_article_url", width="content"
        ):
            st.session_state.article_url_slot_count = slot_count + 1
            st.rerun()
    with remove_col:
        if slot_count > 1 and st.button(
            "− Remove last", key="remove_article_url", width="content"
        ):
            st.session_state["_remove_last_article_url"] = True
            st.rerun()

    reanalyze = st.checkbox(
        "Re-analyze URLs already saved",
        value=False,
        help="Off by default to avoid extra API calls. Saved analyses are reused.",
    )
    st.caption("Each new URL runs one analysis call. Up to 5 calls per batch.")

    if st.button("Analyze articles", type="primary", width="stretch"):
        urls, invalid = _parse_article_urls("\n".join(url_values))
        if invalid:
            st.error("Use full HTTPS URLs. Fix: " + ", ".join(invalid[:5]))
        elif not urls:
            st.warning("Add at least one article URL.")
        elif len(urls) > 5:
            st.warning(f"Analyze up to 5 articles at a time. You entered {len(urls)}.")
        else:
            existing = {}
            for url in urls:
                key, item = _find_saved_analysis(url)
                if item is not None:
                    existing[url] = (key, item)

            loaded = 0
            analyzed = 0
            reanalyzed_keys = set()
            errors = []
            batch_keys = []
            progress = st.progress(0.0, text="Preparing article analysis...")

            for index, url in enumerate(urls, start=1):
                progress.progress(
                    (index - 1) / len(urls),
                    text=f"Processing {index} of {len(urls)}...",
                )
                if not reanalyze and url in existing:
                    key, _ = existing[url]
                    if key not in batch_keys:
                        batch_keys.append(key)
                    loaded += 1
                    continue
                try:
                    item = analyze_article(url)
                    key = url.strip()
                    old_key = existing.get(url, (None, None))[0]
                    if old_key and old_key != key:
                        st.session_state.asset_analyses.pop(old_key, None)
                    st.session_state.asset_analyses[key] = item
                    if key not in batch_keys:
                        batch_keys.append(key)
                    reanalyzed_keys.add(key)
                    analyzed += 1
                except Exception as exc:
                    errors.append((url, str(exc)))

            progress.progress(1.0, text="Batch analysis complete.")
            progress.empty()

            active_key = (st.session_state.article_url or "").strip()
            if active_key not in st.session_state.asset_analyses:
                if batch_keys:
                    _activate_asset(batch_keys[0], force_reset=True)
            elif active_key in reanalyzed_keys:
                _activate_asset(active_key, force_reset=True)

            if analyzed or loaded:
                st.success(
                    f"Batch complete: {analyzed} analyzed, "
                    f"{loaded} loaded from saved."
                )
            if errors:
                st.error(f"{len(errors)} article(s) could not be analyzed.")
                with st.expander("Show failed URLs"):
                    for url, message in errors:
                        st.write(f"**{url}** — {message}")
            if not analyzed and not loaded:
                st.warning("No articles were analyzed. Check the URLs and try again.")

    analyses = st.session_state.get("asset_analyses") or {}
    if analyses and (len(analyses) > 1 or not st.session_state.analysis):
        st.divider()
        st.markdown(f"**Analyzed articles ({len(analyses)})**")
        for key, item in analyses.items():
            with st.container(border=True):
                c1, c2 = st.columns([5, 1.4], vertical_alignment="center")
                with c1:
                    st.markdown(f"**{item.article_title}**")
                    st.caption(key)
                with c2:
                    if key == st.session_state.get("article_url"):
                        st.caption("Active")
                    elif st.button(
                        "Use this article",
                        key=f"use_asset_{_widget_suffix(key)}",
                        width="stretch",
                    ):
                        _activate_asset(key, force_reset=True)
                        st.rerun()

    analysis = st.session_state.analysis
    if analysis:
        st.success(f"Active asset: {analysis.article_title}")
        st.caption(st.session_state.article_url)
        with st.expander("View the saved asset analysis"):
            _render_analysis_details(analysis)


def _render_pr_angles():
    st.caption("Choose the angle with the clearest editorial value. Research is only run for the angle you pick.")

    analysis = st.session_state.analysis
    if not analysis:
        st.info("Analyze an article first.")
        if st.button("Go to article step"):
            go(pr_step="Article")
        return

    for index, angle in enumerate(analysis.pr_angles):
        with st.container(border=True):
            st.markdown(f"#### {index + 1}. {angle.angle}")
            st.caption(f"{angle.story_type} · {angle.recommended_tactic} · Confidence: {angle.confidence}")
            st.write(angle.story_hypothesis)
            st.markdown(f"**Why a publication might care:** {angle.why_useful}")
            with st.expander("Full action plan"):
                st.markdown(f"**{BRAND_NAME}'s contribution:** {angle.brand_contribution}")
                st.markdown("**Target publication types**")
                for item in angle.target_publication_types:
                    st.write(f"- {item}")
                st.markdown("**Journalist beats to research**")
                for item in angle.target_journalist_beats:
                    st.write(f"- {item}")
                st.markdown(f"**Relevant asset:** {angle.relevant_asset}")
                st.markdown(f"**Supporting evidence:** {angle.evidence}")
                st.markdown(f"**Next action:** {angle.next_action}")

            if st.button(
                "Research this angle →",
                key=f"research_angle_{index}",
                type="primary",
                width="stretch",
            ):
                with st.spinner("Searching the web and evaluating editorial candidates..."):
                    try:
                        results = research_opportunities(angle)
                        st.session_state.selected_angle_index = index
                        st.session_state.opportunity_results = results
                        st.session_state.opportunity_reviews = {}
                        st.session_state.journalist_results = {}
                        st.session_state.journalist_reviews = {}
                        st.session_state.research_run_id += 1
                        for opportunity in results.opportunities:
                            upsert_pr_opportunity(
                                opportunity,
                                selected_angle=results.selected_angle,
                                review_status=None,
                            )
                        if results.opportunities:
                            go(pr_step="Opportunities")
                        else:
                            st.warning("No candidates were returned. Try a different angle or add more research context.")
                    except Exception as exc:
                        st.error("PR opportunity research failed.")
                        st.exception(exc)


def _render_pr_opportunities():
    st.caption("Approve only real, relevant articles with a credible editorial opening.")

    results = st.session_state.opportunity_results
    if not results:
        results = _load_saved_pr_results()
        if results is not None:
            st.session_state.opportunity_results = results
            st.session_state.research_run_id = 0
            st.session_state.opportunity_reviews = {}
            st.info("No active research run. Showing saved PR opportunities from the local library.")
        else:
            st.info("Research a PR angle first.")
            if st.button("Go to PR angles"):
                go(pr_step="PR angles")
            return

    st.markdown(
        f'<div class="context-note"><span>Selected angle</span>{html.escape(results.selected_angle)}</div>',
        unsafe_allow_html=True,
    )

    run_id = st.session_state.research_run_id
    reviews = st.session_state.opportunity_reviews
    for index, opportunity in enumerate(results.opportunities):
        review_key = f"{run_id}:{index}"
        if review_key not in reviews:
            saved = get_pr_opportunity(
                opportunity.article_url, opportunity.article_title, opportunity.publication
            )
            if saved and saved.get("review_status") in REVIEW_OPTIONS:
                reviews[review_key] = saved["review_status"]
    statuses = [
        reviews.get(f"{run_id}:{i}", "Awaiting review")
        for i in range(len(results.opportunities))
    ]
    counts = _status_counts(statuses, REVIEW_OPTIONS)
    needs_review = counts["Awaiting review"] + counts.get("Needs more research", 0)
    _queue_strip(
        [
            ("Candidates", len(results.opportunities)),
            ("Needs review", needs_review),
            ("Approved", counts["Approve for journalist research"]),
            ("Rejected", counts["Reject"]),
        ]
    )

    focus = st.radio(
        "Show",
        ["Needs review", "Approved", "All"],
        horizontal=True,
        key=f"opp_focus_{run_id}",
        label_visibility="collapsed",
    )
    if focus == "Needs review":
        visible_indices = [
            index
            for index, status in enumerate(statuses)
            if status in {"Awaiting review", "Needs more research"}
        ]
    elif focus == "Approved":
        visible_indices = [
            index
            for index, status in enumerate(statuses)
            if status == "Approve for journalist research"
        ]
    else:
        visible_indices = list(range(len(results.opportunities)))

    if not visible_indices:
        st.success("Nothing in this view. Switch the filter to review other opportunities.")

    for index in visible_indices:
        opportunity = results.opportunities[index]
        review_key = f"{run_id}:{index}"
        current = reviews.get(review_key, "Awaiting review")

        with st.container(border=True, key=f"opp-card-{run_id}-{index}"):
            title_col, link_col = st.columns(
                [4, 1.1], gap="small", vertical_alignment="center"
            )
            with title_col:
                st.markdown(f"#### {index + 1}. {opportunity.article_title}")
                fit_summary = opportunity.editorial_fit.split("—")[0].strip()
                st.caption(
                    f"{opportunity.publication} · {opportunity.published_date} · "
                    f"Fit: {fit_summary} · Confidence: {opportunity.confidence}"
                )
            with link_col:
                url = opportunity.article_url.strip()
                if url.startswith("https://"):
                    st.link_button(
                        "Open article",
                        url,
                        key=f"open_opp_{run_id}_{index}",
                        width="stretch",
                    )
                else:
                    st.caption("No verified link")

            st.write(
                f"**Why it matters:** {_short_text(opportunity.why_relevant, 260)}"
            )
            st.caption(
                f"{opportunity.topic} · {opportunity.opportunity_type} · "
                f"Fit: {fit_summary}"
            )
            _render_pr_fit(opportunity, f"opp_{run_id}_{index}")

            approve_col, skip_col = st.columns(2)
            is_approved = current == "Approve for journalist research"
            is_skipped = current == "Reject"
            if approve_col.button(
                "Approved ✓" if is_approved else "Approve",
                key=f"opp_approve_{run_id}_{index}",
                type="primary",
                width="stretch",
                disabled=is_approved,
            ):
                reviews[review_key] = "Approve for journalist research"
                upsert_pr_opportunity(
                    opportunity,
                    selected_angle=results.selected_angle,
                    review_status="Approve for journalist research",
                )
                st.rerun()
            if skip_col.button(
                "Skipped" if is_skipped else "Skip",
                key=f"opp_skip_{run_id}_{index}",
                width="stretch",
                disabled=is_skipped,
            ):
                reviews[review_key] = "Reject"
                upsert_pr_opportunity(
                    opportunity,
                    selected_angle=results.selected_angle,
                    review_status="Reject",
                )
                st.rerun()

            with st.expander("Full evidence and notes"):
                st.markdown(f"**Why relevant:** {opportunity.why_relevant}")
                st.markdown(f"**Topic:** {opportunity.topic}")
                st.markdown(f"**Opportunity type:** {opportunity.opportunity_type}")
                st.markdown(f"**Brand contribution:** {opportunity.brand_contribution}")
                st.markdown(f"**Competitor presence:** {opportunity.competitor_mention}")
                st.markdown(f"**Topical relevance:** {opportunity.topical_relevance}")
                st.markdown(f"**Editorial fit:** {opportunity.editorial_fit}")
                st.markdown(f"**Recommended action:** {opportunity.recommended_action}")
                st.markdown(f"**Evidence:** {opportunity.evidence}")
                status_index = (
                    REVIEW_OPTIONS.index(current)
                    if current in REVIEW_OPTIONS
                    else 0
                )
                chosen = st.selectbox(
                    "Status",
                    REVIEW_OPTIONS,
                    index=status_index,
                    key=(
                        f"opp_status_{run_id}_{index}_"
                        f"{_widget_suffix(current)}"
                    ),
                )
                if chosen != current:
                    reviews[review_key] = chosen
                    upsert_pr_opportunity(
                        opportunity,
                        selected_angle=results.selected_angle,
                        review_status=chosen,
                    )
                    st.rerun()

    approved = sum(
        1
        for index in range(len(results.opportunities))
        if reviews.get(f"{run_id}:{index}") == "Approve for journalist research"
    )
    st.divider()
    if approved == 0:
        st.caption(
            "Approve at least one candidate above. Writers appear here as soon "
            "as one is approved."
        )


def _render_pr_journalists():
    st.caption("Research writers with verified published work. A qualified target is ready for pitch preparation, not for sending.")
    fallback_notice = st.session_state.pop("journalist_fallback_notice", None)
    if fallback_notice:
        st.success(fallback_notice)

    results = st.session_state.opportunity_results
    analysis = st.session_state.analysis
    if not results or not analysis:
        st.info("Review some approved opportunities first.")
        if st.button("Go to opportunities"):
            go(pr_step="Opportunities")
        return

    run_id = st.session_state.research_run_id
    reviews = st.session_state.opportunity_reviews
    angle_index = st.session_state.selected_angle_index
    if angle_index is None:
        for candidate_index, candidate_angle in enumerate(analysis.pr_angles):
            if candidate_angle.angle == results.selected_angle:
                angle_index = candidate_index
                st.session_state.selected_angle_index = candidate_index
                break
    if angle_index is None or not (0 <= angle_index < len(analysis.pr_angles)):
        st.error("The original PR angle could not be matched. Research the angle again.")
        if st.button("Go to PR angles"):
            go(pr_step="PR angles")
        return
    angle = analysis.pr_angles[angle_index]

    approved_items = [
        (index, f"{run_id}:{index}", opportunity)
        for index, opportunity in enumerate(results.opportunities)
        if reviews.get(f"{run_id}:{index}") == "Approve for journalist research"
    ]
    if not approved_items:
        st.info("No approved candidates yet. Approve at least one opportunity first.")
        if st.button("Go to opportunities"):
            go(pr_step="Opportunities")
        return

    for index, review_key, opportunity in approved_items:
        with st.container(border=True):
            st.markdown(f"#### {opportunity.article_title}")
            st.caption(f"{opportunity.publication} · {opportunity.published_date}")
            if opportunity.article_url.strip().startswith("https://"):
                st.link_button("Open approved article", opportunity.article_url.strip(), key=f"approved_article_{run_id}_{index}")

            existing = st.session_state.journalist_results.get(review_key)
            if existing is None:
                st.write("Find writers who have covered this topic and could use the brand's contribution.")
                if st.button(
                    "Research journalists →",
                    key=f"research_journalists_{run_id}_{index}",
                    type="primary",
                ):
                    with st.spinner(
                        "Verifying writers, then checking content and SEO "
                        "contacts if none are found..."
                    ):
                        try:
                            result = research_journalists(angle, opportunity)
                            st.session_state.journalist_results[review_key] = result
                            for person in result.journalists:
                                upsert_journalist(
                                    person,
                                    related_opportunity_url=opportunity.article_url,
                                    qualification_status=None,
                                )
                            if not result.journalists:
                                fallback_person, _contact, _email = _auto_prepare_pitch(
                                    opportunity
                                )
                                st.session_state["journalist_fallback_notice"] = (
                                    f"No journalist was verified for "
                                    f"{opportunity.publication}. Prepared a pitch for "
                                    f"{fallback_person.name} "
                                    f"({fallback_person.current_role}) instead."
                                )
                            st.rerun()
                        except Exception as exc:
                            st.error("Journalist research failed.")
                            st.exception(exc)
            else:
                st.write(f"**Research summary:** {existing.research_summary}")
                # Ensure every researched person has a saved record, even before
                # a decision is made. This also restores records after a restart.
                for person_index, person in enumerate(existing.journalists):
                    qualification_key = f"{review_key}:{person_index}"
                    saved_person = get_journalist_record(person, opportunity.article_url)
                    current = st.session_state.journalist_reviews.get(
                        qualification_key, "Needs review"
                    )
                    if (
                        saved_person
                        and saved_person.get("qualification_status") in JOURNALIST_STATUS_OPTIONS
                        and qualification_key not in st.session_state.journalist_reviews
                    ):
                        current = saved_person["qualification_status"]
                    st.session_state.journalist_reviews[qualification_key] = current
                    upsert_journalist(
                        person,
                        related_opportunity_url=opportunity.article_url,
                        qualification_status=current,
                    )

                if not existing.journalists:
                    fallback_person = _linked_contact(opportunity)
                    fallback_draft = (
                        get_outreach_draft(
                            "journalist_pitch",
                            opportunity.article_url,
                            fallback_person.name,
                        )
                        if fallback_person
                        else None
                    )
                    if fallback_draft:
                        st.success(
                            "No journalist was verified. A content/SEO contact "
                            "pitch is ready below."
                        )
                    else:
                        st.warning(
                            "No suitable journalist was verified. Use the "
                            "content/SEO contact option below."
                        )
                else:
                    for person_index, person in enumerate(existing.journalists):
                        qualification_key = f"{review_key}:{person_index}"
                        saved_person = get_journalist_record(person, opportunity.article_url)
                        if (
                            qualification_key not in st.session_state.journalist_reviews
                            and saved_person
                            and saved_person.get("qualification_status") in JOURNALIST_STATUS_OPTIONS
                        ):
                            st.session_state.journalist_reviews[qualification_key] = saved_person["qualification_status"]
                        current = st.session_state.journalist_reviews.get(qualification_key, "Needs review")

                        with st.container(border=True):
                            st.markdown(f"**{person_index + 1}. {person.name}**")
                            st.caption(
                                f"{person.publication} · {person.current_role} · "
                                f"Coverage date: {person.article_date} · Confidence: {person.confidence}"
                            )
                            st.write(f"**Why relevant:** {person.why_relevant}")
                            with st.expander("Coverage and pitch angle"):
                                st.markdown(f"**Topic covered:** {person.topic_covered}")
                                st.markdown(f"**Relevant article:** {person.relevant_article_title}")
                                st.markdown(f"**Suggested pitch angle:** {person.suggested_pitch_angle}")
                                st.markdown(f"**Evidence:** {person.evidence}")
                            if person.relevant_article_url.strip().startswith("https://"):
                                st.link_button(
                                    "Open relevant article",
                                    person.relevant_article_url.strip(),
                                    key=f"j_article_{run_id}_{index}_{person_index}",
                                )
                            if person.author_profile_or_contact_page.strip().startswith("https://"):
                                st.link_button(
                                    "Open author profile / contact page",
                                    person.author_profile_or_contact_page.strip(),
                                    key=f"j_profile_{run_id}_{index}_{person_index}",
                                )

                            status_key = f"journalist_status_{run_id}_{index}_{person_index}"
                            if status_key not in st.session_state:
                                st.session_state[status_key] = current
                            chosen = st.selectbox(
                                "Qualification",
                                JOURNALIST_STATUS_OPTIONS,
                                key=status_key,
                                label_visibility="collapsed",
                            )
                            if chosen != current:
                                st.session_state.journalist_reviews[qualification_key] = chosen
                                upsert_journalist(
                                    person,
                                    related_opportunity_url=opportunity.article_url,
                                    qualification_status=chosen,
                                )
                                st.rerun()

                if st.button("Research again", key=f"research_again_{run_id}_{index}"):
                    st.session_state.journalist_results.pop(review_key, None)
                    for person_index in range(len(existing.journalists)):
                        st.session_state.journalist_reviews.pop(f"{review_key}:{person_index}", None)
                        st.session_state.pop(f"journalist_status_{run_id}_{index}_{person_index}", None)
                    st.rerun()

    qualified = sum(
        1
        for row in list_journalists()
        if row.get("qualification_status") == "Qualified pitch target"
        and (row.get("related_opportunity_url") or "").strip()
    )
    st.divider()
    if st.button(
        f"Continue to outreach ({qualified} qualified) →",
        type="primary",
        width="stretch",
        disabled=qualified == 0,
    ):
        go(pr_step="Outreach")
    if qualified == 0:
        st.caption("Mark at least one writer as a qualified pitch target to continue.")


def _qualified_journalist_targets():
    targets = []
    seen = set()
    for row in list_journalists():
        if row.get("qualification_status") != "Qualified pitch target":
            continue
        try:
            person = JournalistProfile.model_validate(row.get("payload") or {})
        except Exception:
            continue
        opportunity_row = get_pr_opportunity(row.get("related_opportunity_url") or "")
        if not opportunity_row:
            continue
        try:
            opportunity = PROpportunity.model_validate(opportunity_row.get("payload") or {})
        except Exception:
            continue
        key = (opportunity.article_url, person.name)
        if key in seen:
            continue
        seen.add(key)
        targets.append((opportunity, person, opportunity_row))
    return targets


def _selected_journalist_email(person) -> str:
    """Return the address the human chose for this journalist, if any."""
    data = get_journalist_contact_data(person) or {}
    value = (data.get("selected_email") or "").strip()
    return value if email_sender.is_valid_email(value) else ""


def _trusted_email_domains(person) -> set[str]:
    domains = set()
    for url in (
        getattr(person, "relevant_article_url", ""),
        getattr(person, "author_profile_or_contact_page", ""),
    ):
        host = urlsplit(url or "").netloc.lower()
        if host:
            domains.add(host[4:] if host.startswith("www.") else host)
    return domains


def _best_published_email(candidates, person) -> str:
    """Auto-pick only a high-confidence address on the publication's own domain."""
    trusted = _trusted_email_domains(person)
    if not trusted:
        return ""
    for candidate in candidates:
        email_value = (getattr(candidate, "email", "") or "").strip()
        if not email_sender.is_valid_email(email_value):
            continue
        if (getattr(candidate, "confidence", "") or "").strip().lower() != "high":
            continue
        domain = email_value.split("@")[-1].lower()
        domain = domain[4:] if domain.startswith("www.") else domain
        if domain in trusted:
            return email_value
    return ""


def _find_contacts_for_all(targets) -> dict[str, int]:
    """Check every writer who still needs an address; select only safe matches."""
    counts = {"selected": 0, "review": 0, "none": 0, "skipped": 0}
    for opportunity, person, _row in targets:
        saved = get_journalist_contact_data(person) or {}
        if saved.get("candidates") or _selected_journalist_email(person):
            counts["skipped"] += 1
            continue
        result = research_journalist_email(person, opportunity)
        payload = result.model_dump(mode="json")
        payload["checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        best = _best_published_email(result.candidates, person)
        payload["selected_email"] = best
        save_journalist_contact_data(person, payload)
        valid = [
            candidate
            for candidate in result.candidates
            if email_sender.is_valid_email(
                (getattr(candidate, "email", "") or "").strip()
            )
        ]
        if best:
            counts["selected"] += 1
        elif valid:
            counts["review"] += 1
        else:
            counts["none"] += 1
    return counts


def _use_journalist_email(person, draft_key: str | None, email_value: str) -> None:
    """Remember the chosen address and fill the matching draft's recipient."""
    data = dict(get_journalist_contact_data(person) or {})
    data["selected_email"] = email_value
    save_journalist_contact_data(person, data)
    if not draft_key:
        return
    fresh = next(
        (row for row in list_outreach_drafts() if row["draft_key"] == draft_key), None
    )
    if fresh is None:
        return
    update_outreach_draft(
        fresh["draft_key"],
        fresh.get("subject", ""),
        fresh.get("body", ""),
        fresh.get("draft_status", "Draft"),
        recipient_email=email_value,
    )


def _render_journalist_email_finder(person, opportunity, record, key_prefix: str) -> None:
    """Search public pages for a published address and let the human choose."""
    saved = get_journalist_contact_data(person) or {}
    selected = _selected_journalist_email(person)
    candidates = [
        candidate
        for candidate in (saved.get("candidates") or [])
        if email_sender.is_valid_email((candidate.get("email") or "").strip())
    ]
    suffix = _widget_suffix(f"{person.name}|{person.publication}")
    title = (
        f"Find public email ({len(candidates)} found)"
        if candidates
        else "Find public email"
    )
    with st.expander(title):
        st.caption(
            "Searches public pages only: author profiles, staff and contact pages, "
            "personal sites, and public bios. It never guesses an address pattern."
        )
        if saved.get("checked_at"):
            st.caption(f"Last searched {saved['checked_at']}")
        if saved.get("research_summary"):
            st.write(saved["research_summary"])
        if saved.get("recommended_contact_route"):
            st.caption(f"Best route: {saved['recommended_contact_route']}")

        for candidate_index, candidate in enumerate(candidates):
            email_value = (candidate.get("email") or "").strip()
            is_selected = email_value.lower() == selected.lower()
            with st.container(border=True):
                badge = " · **selected**" if is_selected else ""
                st.markdown(f"`{email_value}`{badge}")
                st.caption(
                    f"{candidate.get('source_name') or 'Public source'} · "
                    f"Confidence: {candidate.get('confidence') or 'Unknown'}"
                )
                if candidate.get("evidence"):
                    st.write(candidate["evidence"])
                source_url = (candidate.get("source_url") or "").strip()
                link_col, use_col = st.columns(2)
                if source_url.startswith("https://"):
                    link_col.link_button(
                        "Open source",
                        source_url,
                        key=f"{key_prefix}_email_source_{suffix}_{candidate_index}",
                    )
                if use_col.button(
                    "Use for this pitch",
                    key=f"{key_prefix}_email_use_{suffix}_{candidate_index}",
                    disabled=is_selected,
                    width="stretch",
                ):
                    _use_journalist_email(
                        person,
                        record["draft_key"] if record else None,
                        email_value,
                    )
                    st.rerun()

        book_domain = urlsplit(person.relevant_article_url or "").netloc
        shown_emails = {candidate["email"].lower() for candidate in candidates}
        book_matches = [
            match
            for match in find_contact_book(book_domain, person.name)
            if (match.get("email") or "").lower() not in shown_emails
        ]
        if book_matches:
            st.markdown("**From your contact book**")
            for match_index, match in enumerate(book_matches[:5]):
                match_email = (match.get("email") or "").strip()
                if not email_sender.is_valid_email(match_email):
                    continue
                with st.container(border=True):
                    st.markdown(f"`{match_email}`")
                    st.caption(
                        f"{match.get('name') or 'Unknown'} · "
                        f"{match.get('role') or 'Unknown'} · "
                        f"{match.get('source') or 'Imported'}"
                    )
                    if st.button(
                        "Use this address",
                        key=f"{key_prefix}_book_use_{suffix}_{match_index}",
                        width="stretch",
                    ):
                        _use_journalist_email(
                            person,
                            record["draft_key"] if record else None,
                            match_email,
                        )
                        st.rerun()

        hunter_config = contact_providers.load_hunter_config()
        if hunter_config.api_key:
            st.divider()
            st.markdown("**Hunter (paid lookup)**")
            st.caption(
                "Uses Hunter credits. It searches this person and the "
                "publication's content/SEO contacts."
            )
            hunter_results_key = f"{key_prefix}_hunter_{suffix}"
            if st.button(
                "Search Hunter",
                key=f"{hunter_results_key}_search",
                width="stretch",
            ):
                domain = urlsplit(person.relevant_article_url or "").netloc
                try:
                    with st.spinner("Searching Hunter..."):
                        hunter_results = contact_providers.search_hunter(
                            domain, name=person.name, limit=5
                        )
                    st.session_state[hunter_results_key] = hunter_results
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
            hunter_results = st.session_state.get(hunter_results_key) or []
            for result_index, result in enumerate(hunter_results):
                email_value = (result.get("email") or "").strip()
                if not email_sender.is_valid_email(email_value):
                    continue
                with st.container(border=True):
                    st.markdown(f"`{email_value}`")
                    st.caption(
                        f"{result.get('name') or 'Unknown'} · "
                        f"{result.get('title') or 'Unknown'} · Hunter"
                    )
                    if st.button(
                        "Use this address",
                        key=f"{hunter_results_key}_use_{result_index}",
                        width="stretch",
                    ):
                        _use_journalist_email(
                            person,
                            record["draft_key"] if record else None,
                            email_value,
                        )
                        st.rerun()
            if not hunter_results:
                st.caption("No Hunter results yet.")

        if saved and not candidates:
            st.info(
                "No published address was found. Use the publication's official "
                "contact page instead of guessing one."
            )
            contact_page = (
                getattr(person, "author_profile_or_contact_page", "") or ""
            ).strip()
            if contact_page.startswith("https://"):
                st.link_button(
                    "Open the official contact page",
                    contact_page,
                    key=f"{key_prefix}_contact_page_{suffix}",
                    width="stretch",
                )
            st.caption(
                "For form-based outreach, paste the draft below into the page, "
                "then set the draft status to 'Sent manually'."
            )

        contactout_config = contact_providers.load_config()
        if contactout_config.api_token:
            st.divider()
            st.markdown("**ContactOut (paid lookup)**")
            st.caption(
                "Looks up work emails for this person and the publication's "
                "content/SEO contacts. Each search uses ContactOut credits."
            )
            results_key = f"{key_prefix}_contactout_{suffix}"
            if st.button(
                "Search ContactOut",
                key=f"{results_key}_search",
                width="stretch",
            ):
                domain = urlsplit(person.relevant_article_url or "").netloc
                try:
                    with st.spinner("Searching ContactOut..."):
                        results = contact_providers.search_people(
                            domain,
                            None
                            if (person.name or "").strip()
                            else contact_providers.CONTENT_TITLES,
                            name=person.name if (person.name or "").strip() else "",
                            limit=5,
                        )
                    st.session_state[results_key] = results
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
            contactout_results = st.session_state.get(results_key) or []
            for result_index, result in enumerate(contactout_results):
                email_value = (result.get("email") or "").strip()
                if not email_sender.is_valid_email(email_value):
                    continue
                with st.container(border=True):
                    st.markdown(f"`{email_value}`")
                    st.caption(
                        f"{result.get('name') or 'Unknown'} · "
                        f"{result.get('title') or 'Unknown'} · ContactOut"
                    )
                    linkedin_url = (result.get("linkedin_url") or "").strip()
                    if linkedin_url.startswith("https://"):
                        st.link_button(
                            "Open LinkedIn profile",
                            linkedin_url,
                            key=f"{results_key}_li_{result_index}",
                        )
                    if st.button(
                        "Use this address",
                        key=f"{results_key}_use_{result_index}",
                        width="stretch",
                    ):
                        _use_journalist_email(
                            person,
                            record["draft_key"] if record else None,
                            email_value,
                        )
                        data = dict(get_journalist_contact_data(person) or {})
                        contact_candidates = list(data.get("candidates") or [])
                        contact_candidates.append(
                            {
                                "email": email_value,
                                "source_url": linkedin_url,
                                "source_name": "ContactOut",
                                "evidence": (
                                    f"{result.get('name') or ''} · "
                                    f"{result.get('title') or ''}"
                                ).strip(" ·"),
                                "confidence": "Medium",
                            }
                        )
                        data["candidates"] = contact_candidates
                        data["selected_email"] = email_value
                        data["recommended_contact_route"] = "ContactOut work email"
                        save_journalist_contact_data(person, data)
                        st.rerun()
            if not contactout_results:
                st.caption(
                    "No ContactOut results yet. Search to look up a work email."
                )

        if st.button(
            "Search again" if saved else "Find public email",
            key=f"{key_prefix}_email_search_{suffix}",
            width="stretch",
        ):
            try:
                with st.spinner(
                    "Checking public pages for a published address. This can take a minute..."
                ):
                    result = research_journalist_email(person, opportunity)
                payload = result.model_dump(mode="json")
                payload["checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                payload["selected_email"] = selected
                save_journalist_contact_data(person, payload)
                st.rerun()
            except Exception as exc:
                st.error(f"Email research failed: {exc}")


def _create_journalist_draft(opportunity, person, opportunity_row):
    """Create one pitch draft and prefill any address the human already chose."""
    draft_key = upsert_outreach_draft(
        draft_journalist_pitch(
            opportunity,
            person,
            angle_context=opportunity_row.get("selected_angle", ""),
            sender_name=st.session_state.sender_name,
            sender_role=st.session_state.sender_role,
        ),
        "journalist_pitch",
        target_url=opportunity.article_url,
        related_url=person.relevant_article_url,
        draft_status="Draft",
    )
    chosen_email = _selected_journalist_email(person)
    if chosen_email:
        fresh = get_outreach_draft(
            "journalist_pitch", opportunity.article_url, person.name
        )
        if fresh and not (fresh.get("recipient_email") or "").strip():
            update_outreach_draft(
                fresh["draft_key"],
                fresh.get("subject", ""),
                fresh.get("body", ""),
                fresh.get("draft_status", "Draft"),
                recipient_email=chosen_email,
            )
    return draft_key


def _linked_contact(opportunity):
    """Return the saved contact for this opportunity, preferring one with a draft."""
    matches = []
    for row in list_journalists():
        if (row.get("related_opportunity_url") or "").strip() != (
            opportunity.article_url or ""
        ).strip():
            continue
        try:
            person = JournalistProfile.model_validate(row.get("payload") or {})
        except Exception:
            continue
        matches.append(person)
    for person in matches:
        if get_outreach_draft(
            "journalist_pitch", opportunity.article_url, person.name
        ):
            return person
    return matches[0] if matches else None


def _auto_prepare_pitch(opportunity):
    """Find a content/SEO contact and write the pitch in one step."""
    contact = find_opportunity_contact(opportunity)
    name = (contact.contact_name or "").strip()
    if not name or name.lower() in {"not found", "unknown", "n/a"}:
        name = f"{opportunity.publication} content team"

    person = JournalistProfile(
        name=name,
        publication=opportunity.publication,
        current_role=(contact.role or "").strip() or "Content contact",
        relevant_article_title=opportunity.article_title,
        relevant_article_url=opportunity.article_url,
        article_date=opportunity.published_date,
        topic_covered=opportunity.topic,
        why_relevant=opportunity.why_relevant,
        suggested_pitch_angle=contact.route or "Relevant content contribution",
        author_profile_or_contact_page=(
            contact.contact_page_url or contact.source_url or ""
        ),
        evidence=contact.evidence or "",
        confidence=contact.confidence or "Medium",
    )
    upsert_journalist(
        person,
        related_opportunity_url=opportunity.article_url,
        qualification_status="Qualified pitch target",
    )

    email_value = (contact.email or "").strip()
    email_source = contact.route or "Published page"
    email_source_url = contact.source_url or ""
    email_evidence = contact.evidence or ""
    email_confidence = contact.confidence or "Medium"
    if not email_sender.is_valid_email(email_value):
        contactout_config = contact_providers.load_config()
        if contactout_config.api_token:
            try:
                domain = urlsplit(opportunity.article_url or "").netloc
                people = contact_providers.search_people(
                    domain,
                    None,
                    name=name,
                    limit=3,
                )
                normalized = name.strip().lower()
                match = next(
                    (
                        person_result
                        for person_result in people
                        if email_sender.is_valid_email(
                            (person_result.get("email") or "").strip()
                        )
                        and (person_result.get("name") or "").strip().lower()
                        == normalized
                    ),
                    None,
                )
                if match:
                    email_value = (match.get("email") or "").strip()
                    email_source = "ContactOut"
                    email_source_url = (
                        match.get("linkedin_url") or ""
                    ).strip()
                    email_evidence = (
                        f"ContactOut work email for "
                        f"{match.get('name') or name}."
                    )
                    email_confidence = "Medium"
            except Exception:
                email_value = ""
    if not email_sender.is_valid_email(email_value):
        domain = urlsplit(opportunity.article_url or "").netloc
        normalized = name.strip().lower()
        book_match = next(
            (
                match
                for match in find_contact_book(domain, name)
                if email_sender.is_valid_email(
                    (match.get("email") or "").strip()
                )
                and (match.get("name") or "").strip().lower() == normalized
            ),
            None,
        )
        if book_match:
            email_value = (book_match.get("email") or "").strip()
            email_source = "Contact book"
            email_source_url = ""
            email_evidence = (
                f"Imported contact book match for "
                f"{book_match.get('name') or name}."
            )
            email_confidence = "Medium"
    if not email_sender.is_valid_email(email_value):
        hunter_config = contact_providers.load_hunter_config()
        if hunter_config.api_key:
            try:
                domain = urlsplit(opportunity.article_url or "").netloc
                people = contact_providers.search_hunter(
                    domain, name=name, limit=3
                )
                normalized = name.strip().lower()
                match = next(
                    (
                        person_result
                        for person_result in people
                        if email_sender.is_valid_email(
                            (person_result.get("email") or "").strip()
                        )
                        and (person_result.get("name") or "").strip().lower()
                        == normalized
                    ),
                    None,
                )
                if match:
                    email_value = (match.get("email") or "").strip()
                    email_source = "Hunter"
                    email_source_url = (
                        match.get("linkedin_url") or ""
                    ).strip()
                    email_evidence = (
                        f"Hunter work email for "
                        f"{match.get('name') or name}."
                    )
                    email_confidence = "Medium"
            except Exception:
                email_value = ""
    if email_sender.is_valid_email(email_value):
        save_journalist_contact_data(
            person,
            {
                "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "research_summary": (
                    email_evidence
                    or f"Contact found via {email_source}."
                ),
                "recommended_contact_route": email_source,
                "candidates": [
                    {
                        "email": email_value,
                        "source_url": email_source_url,
                        "source_name": email_source,
                        "evidence": email_evidence,
                        "confidence": email_confidence,
                    }
                ],
                "selected_email": email_value,
            },
        )

    opportunity_row = get_pr_opportunity(opportunity.article_url) or {}
    _create_journalist_draft(opportunity, person, opportunity_row)
    return person, contact, email_value


def _render_pr_auto_outreach(approved):
    """One-click contact finding and pitch writing for approved articles."""
    st.markdown("### Other contacts (content, SEO, link building)")
    st.caption(
        "One click finds the bylined writer, content manager, SEO lead, or "
        "link-building contact, then writes the pitch. Only published emails "
        "are used; nothing is guessed."
    )

    def has_draft(opportunity) -> bool:
        person = _linked_contact(opportunity)
        return bool(
            person
            and get_outreach_draft(
                "journalist_pitch", opportunity.article_url, person.name
            )
        )

    pending = [opportunity for opportunity in approved if not has_draft(opportunity)]
    auto_notice = st.session_state.pop("pr_auto_notice", None)
    if auto_notice:
        st.success(auto_notice)
    if st.button(
        f"Find contacts and prepare all ({len(pending)})",
        key="auto_outreach_all",
        type="primary",
        width="stretch",
        disabled=not pending,
    ):
        prepared = 0
        failures = []
        with st.spinner(
            "Finding contacts and writing pitches. This can take a minute per "
            "article..."
        ):
            for opportunity in pending:
                try:
                    _auto_prepare_pitch(opportunity)
                    prepared += 1
                except Exception as exc:
                    failures.append(f"{opportunity.publication}: {exc}")
        message = (
            f"Prepared {prepared} pitch{'es' if prepared != 1 else ''}. "
            "Review them in Outreach."
        )
        if failures:
            message += (
                f" {len(failures)} could not be prepared: "
                + "; ".join(failures[:2])
            )
        st.session_state["pr_auto_notice"] = message
        st.rerun()

    for index, opportunity in enumerate(approved):
        person = _linked_contact(opportunity)
        record = (
            get_outreach_draft(
                "journalist_pitch", opportunity.article_url, person.name
            )
            if person
            else None
        )
        with st.container(border=True):
            st.markdown(f"#### {opportunity.publication}")
            st.caption(opportunity.article_title)
            if person:
                st.write(f"**Contact:** {person.name} · {person.current_role}")
                email_value = _selected_journalist_email(person)
                if email_value:
                    st.caption(f"Email: {email_value}")
                else:
                    st.caption("No published email yet. Open the contact page or check it in Outreach.")
                contact_page = (
                    person.author_profile_or_contact_page or ""
                ).strip()
                if contact_page.startswith("https://"):
                    st.link_button(
                        "Open contact page",
                        contact_page,
                        key=f"auto_contact_{index}",
                    )
            if record:
                st.success("Pitch ready. Review it in Outreach.")
                if st.button(
                    "Open in Outreach",
                    key=f"auto_open_{index}",
                    type="primary",
                    width="stretch",
                ):
                    go(pr_step="Outreach")
            else:
                if st.button(
                    "Find content/SEO contact & write pitch",
                    key=f"auto_prepare_{index}",
                    type="primary",
                    width="stretch",
                ):
                    try:
                        with st.spinner(
                            "Finding the contact and writing the pitch..."
                        ):
                            _auto_prepare_pitch(opportunity)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Contact lookup failed: {exc}")


FOLLOW_UP_DAYS = 4


def _followups_due() -> list[dict]:
    """Sent pitches old enough for one follow-up, with no reply or follow-up."""
    drafts = list_outreach_drafts()
    done = {
        ((row.get("target_url") or ""), (row.get("recipient_name") or "").lower())
        for row in drafts
        if row.get("draft_type") == "journalist_followup"
    }
    closed = {
        "Replied",
        "Declined",
        "Placement confirmed",
        "Do not send",
        "Sent manually",
    }
    due = []
    for row in drafts:
        if row.get("draft_type") != "journalist_pitch" or not row.get("sent_at"):
            continue
        if row.get("draft_status") in closed:
            continue
        key = ((row.get("target_url") or ""), (row.get("recipient_name") or "").lower())
        if key in done:
            continue
        try:
            sent = datetime.fromisoformat(row["sent_at"])
            if sent.tzinfo is None:
                sent = sent.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if (datetime.now(timezone.utc) - sent).days >= FOLLOW_UP_DAYS:
            due.append(row)
    return due


def _create_followups(due: list[dict]) -> int:
    """Create one short follow-up draft for each due pitch."""
    created = 0
    for row in due:
        recipient = (row.get("recipient_name") or "there").strip()
        first_name = recipient.split()[0] if recipient else "there"
        subject = (row.get("subject") or "Quick follow-up").strip()
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        body = (
            f"Hi {first_name},\n\n"
            "Just following up on my note below. I can share the data and "
            "commentary if it is useful for your coverage.\n\n"
            "If this is not the right person, could you point me to whoever "
            "handles content or SEO?\n\n"
            "Best,\n"
            f"{row.get('sender_name') or HARDCODED_SENDER_NAME}\n"
            f"{row.get('sender_role') or HARDCODED_SENDER_ROLE}"
        )
        upsert_outreach_draft(
            SimpleNamespace(
                recipient_name=row.get("recipient_name") or "",
                publication=row.get("publication") or "",
                subject_line=subject,
                message_body=body,
                target_url=row.get("target_url") or "",
                channel="email",
                confidence="High",
                personalization_evidence="Follow-up to an earlier sent pitch.",
                asset_used="",
                call_to_action="One low-pressure follow-up.",
                facts_to_verify=[],
                compliance_notes="Follow-up only; no new claims.",
            ),
            "journalist_followup",
            target_url=row.get("target_url") or "",
            related_url=row.get("related_url") or "",
            draft_status="Draft",
            recipient_email=row.get("recipient_email") or "",
        )
        created += 1
    return created


def _render_pr_outreach():
    st.caption(
        "Review or write a draft, add a verified public email, then copy it and "
        "send it from your email."
    )

    with st.expander("Sender identity (used in drafts)"):
        st.markdown(f"**{HARDCODED_SENDER_NAME}** · {HARDCODED_SENDER_ROLE}")
        st.caption("Hardcoded for this workspace.")

    targets = _qualified_journalist_targets()
    if not targets:
        st.warning("No qualified contacts yet. Find a writer or contact in the Contacts step first.")
        if st.button("Go to contacts"):
            go(pr_step="Opportunities")
        return

    def prepare_missing() -> int:
        created = 0
        for opportunity, person, opportunity_row in targets:
            if get_outreach_draft(
                "journalist_pitch", opportunity.article_url, person.name
            ):
                continue
            _create_journalist_draft(opportunity, person, opportunity_row)
            created += 1
        return created

    missing_count = sum(
        1
        for opportunity, person, _ in targets
        if get_outreach_draft("journalist_pitch", opportunity.article_url, person.name)
        is None
    )

    unchecked = [
        (opportunity, person, row)
        for opportunity, person, row in targets
        if not (get_journalist_contact_data(person) or {}).get("candidates")
        and not _selected_journalist_email(person)
    ]
    st.markdown("### Contacts")
    st.caption(
        "Find a published email for every writer who still needs one. Only "
        "public pages are used; addresses are never guessed."
    )
    contacts_notice = st.session_state.pop("pr_contacts_notice", None)
    if contacts_notice:
        st.success(contacts_notice)
    if st.button(
        f"Find contacts for all ({len(unchecked)})",
        key="pr_find_contacts_all",
        width="stretch",
        disabled=not unchecked,
    ):
        try:
            with st.spinner(
                "Checking public pages for each writer. This can take a minute "
                "per person..."
            ):
                counts = _find_contacts_for_all(unchecked)
            message = (
                f"Selected {counts['selected']} verified email"
                f"{'s' if counts['selected'] != 1 else ''}. "
                f"{counts['review']} need your choice. "
                f"{counts['none']} had no published email."
            )
            if counts["skipped"]:
                message += f" {counts['skipped']} already checked."
            st.session_state["pr_contacts_notice"] = message
            st.rerun()
        except Exception as exc:
            st.error(f"Contact lookup failed: {exc}")

    _render_bulk_outreach_actions(
        "pr_outreach_bulk",
        {"journalist_pitch", "journalist_followup"},
        missing_count,
        prepare_missing,
    )

    for index, (opportunity, person, opportunity_row) in enumerate(targets):
        with st.container(border=True):
            st.markdown(f"#### {person.name}")
            st.caption(f"{person.publication} · {person.current_role}")
            st.markdown(f"**Opportunity:** {opportunity.article_title}")
            st.markdown(f"**Why this writer:** {person.why_relevant}")

            record = get_outreach_draft("journalist_pitch", opportunity.article_url, person.name)
            _render_journalist_email_finder(
                person, opportunity, record, f"journalist_email_{index}"
            )

            if record is None:
                _render_no_draft(
                    "Pitch",
                    "Prepare personalized pitch",
                    f"prepare_pitch_{index}",
                    lambda o=opportunity, p=person, r=opportunity_row: _create_journalist_draft(
                        o, p, r
                    ),
                )
            else:
                _render_draft_editor(record, f"journalist_draft_{index}")

    st.divider()
    st.caption(
        "Review every link, name, and claim. Copy or download the draft and send "
        "it from your email. Use 'Sent manually' to track it."
    )


def _render_digital_pr():
    step = st.session_state.pr_step
    phase = PR_STEP_PHASE.get(step, "Research")
    _phase_control(PR_PHASES, "pr_phase_widget", phase, _pr_phase_changed)

    if phase == "Research":
        if st.session_state.analysis:
            _render_pr_angles()
            with st.expander("Analyze another article"):
                _render_pr_article()
        else:
            _render_pr_article()
        return

    if phase == "Contacts":
        _render_pr_opportunities()
        results = st.session_state.opportunity_results
        reviews = st.session_state.opportunity_reviews
        run_id = st.session_state.research_run_id
        approved_opportunities = []
        if results:
            approved_opportunities = [
                opportunity
                for index, opportunity in enumerate(results.opportunities)
                if reviews.get(f"{run_id}:{index}")
                == "Approve for journalist research"
            ]
        if approved_opportunities:
            st.markdown("### Find writers (journalists)")
            _render_pr_journalists()
            _render_pr_auto_outreach(approved_opportunities)

        st.download_button(
            "Download sites + contacts (CSV)",
            data=sites_contacts_csv_bytes(),
            file_name="pr_sites_contacts.csv",
            mime="text/csv",
            key="download_sites_contacts",
            width="stretch",
        )
        return

    _render_pr_outreach()


# =========================================================
# LISTICLE WORKFLOW
# =========================================================

def _render_listicle_search():
    st.caption("Find roundups, best-tool lists, alternatives pages, comparisons, and directories where the brand may fit.")

    with st.form("listicle_search_form"):
        search_theme = st.text_input(
            "What should we find?",
            placeholder="best social media management tools for agencies",
            help="Describe the category, use case, or audience.",
        )
        with st.expander("Advanced search options"):
            related_queries = st.text_area(
                "Related categories or query variations",
                placeholder="best social media scheduling tools; Hootsuite alternatives; social media analytics tools",
                help="Separate queries with semicolons. Leave blank to let the agent generate variations.",
            )
            c1, c2 = st.columns(2)
            target_audience = c1.selectbox(
                "Target audience",
                [
                    "All relevant audiences",
                    "Agencies",
                    "Social media managers",
                    "Marketing teams",
                    "Small and medium businesses",
                    "Enterprise teams",
                    "Creators and influencers",
                ],
            )
            target_market = c2.selectbox(
                "Target market",
                [
                    "Global English-language",
                    "United States",
                    "United Kingdom",
                    "Canada",
                    "Australia",
                ],
            )
            competitor_text = st.text_input(
                "Competitors to check",
                placeholder="Hootsuite, Sprout Social, Buffer, Later",
                help="Comma-separated. The agent only reports competitors it verifies on a page.",
            )
            max_results = st.select_slider(
                "Maximum candidate pages",
                options=[5, 10, 15, 20],
                value=15,
                help="Choose 5 for a smaller, faster search.",
            )
        submitted = st.form_submit_button(
            "Find listicle opportunities",
            type="primary",
            width="stretch",
        )

    if submitted:
        if not search_theme.strip():
            st.warning("Enter a category or search theme first.")
        else:
            competitors = [item.strip() for item in competitor_text.split(",") if item.strip()]
            st.session_state.listicle_results = None
            st.session_state.listicle_reviews = {}
            st.session_state.listicle_contact_results = {}
            st.session_state.listicle_policy_results = {}
            st.session_state.listicle_placement_progress = {}
            st.session_state.listicle_run_id += 1

            with st.spinner("Searching the web and checking inclusion fit..."):
                try:
                    results = research_listicles(
                        search_theme=search_theme.strip(),
                        related_queries=related_queries,
                        target_audience=target_audience,
                        target_market=target_market,
                        competitors=competitors,
                        max_results=max_results,
                    )
                    st.session_state.listicle_results = results
                    for item in results.opportunities:
                        upsert_listicle_prospect(item, search_theme=results.search_theme)
                    if results.opportunities:
                        go(listicle_step="Prospects")
                    else:
                        st.warning("No suitable pages were returned. Try a broader category or different variations.")
                except Exception as exc:
                    st.error("Listicle research failed.")
                    st.exception(exc)

    results = st.session_state.listicle_results
    if results is not None:
        st.divider()
        st.success(f"Last search: {len(results.opportunities)} candidate pages")
        st.write(results.research_summary)
        if st.button("View prospects →", width="stretch"):
            go(listicle_step="Prospects")
    else:
        saved = _load_saved_listicle_results()
        if saved is not None:
            st.divider()
            st.info(f"{len(saved.opportunities)} saved prospect(s) are available in the local library.")
            if st.button("Review saved prospects →", width="stretch"):
                st.session_state.listicle_results = saved
                st.session_state.listicle_run_id = 0
                go(listicle_step="Prospects")


def _render_listicle_prospects():
    st.caption(
        "Review prospects — check the page, the fit, the publisher route, "
        "and the policy before approving."
    )

    results = st.session_state.listicle_results
    if results is None:
        results = _load_saved_listicle_results()
        if results is not None:
            st.session_state.listicle_results = results
            st.session_state.listicle_run_id = 0
            st.session_state.listicle_reviews = {}
            st.session_state.listicle_contact_results = {}
            st.session_state.listicle_policy_results = {}
            st.session_state.listicle_placement_progress = {}
            st.info("No active search. Showing saved listicle prospects from the local library.")
        else:
            st.info("Run a listicle search first.")
            if st.button("Go to search"):
                go(listicle_step="Search")
            return

    st.markdown(
        f'<div class="context-note"><span>Search</span>{html.escape(results.search_theme)}</div>',
        unsafe_allow_html=True,
    )
    run_id = st.session_state.listicle_run_id
    reviews = st.session_state.listicle_reviews

    # Restore saved decisions before counting or filtering so the metrics and
    # filters reflect the database, not just the current browser session.
    for index, item in enumerate(results.opportunities):
        review_key = f"{run_id}:{index}"
        saved_record = get_listicle_prospect(item.listicle_url, item.listicle_title, item.publication)
        if not saved_record:
            continue
        if review_key not in reviews and saved_record.get("review_status") in LISTICLE_STATUS_OPTIONS:
            reviews[review_key] = saved_record["review_status"]
        if (
            review_key not in st.session_state.listicle_placement_progress
            and saved_record.get("placement_progress") in PLACEMENT_OPTIONS
        ):
            st.session_state.listicle_placement_progress[review_key] = saved_record["placement_progress"]
        if review_key not in st.session_state.listicle_contact_results and saved_record.get("contact_data"):
            try:
                st.session_state.listicle_contact_results[review_key] = (
                    ListicleContactResearchResults.model_validate(saved_record["contact_data"])
                )
            except Exception:
                pass
        if review_key not in st.session_state.listicle_policy_results and saved_record.get("policy_data"):
            try:
                st.session_state.listicle_policy_results[review_key] = (
                    PublisherPolicyAssessment.model_validate(saved_record["policy_data"])
                )
            except Exception:
                pass

    statuses = [
        reviews.get(f"{run_id}:{i}", "Awaiting review")
        for i in range(len(results.opportunities))
    ]
    counts = _status_counts(statuses, LISTICLE_STATUS_OPTIONS)
    needs_review = counts["Awaiting review"] + counts.get("Needs more research", 0)
    _queue_strip(
        [
            ("Candidates", len(results.opportunities)),
            ("Needs review", needs_review),
            ("Approved", counts["Approve to pursue"]),
            ("Already listed", counts["Already listed"]),
        ]
    )

    focus = st.radio(
        "Show",
        ["Needs review", "Approved", "All"],
        horizontal=True,
        key=f"listicle_focus_{run_id}",
        label_visibility="collapsed",
    )
    if focus == "Needs review":
        visible_indices = [
            index
            for index, status in enumerate(statuses)
            if status in {"Awaiting review", "Needs more research"}
        ]
    elif focus == "Approved":
        visible_indices = [
            index for index, status in enumerate(statuses) if status == "Approve to pursue"
        ]
    else:
        visible_indices = list(range(len(results.opportunities)))

    if not visible_indices:
        st.success("Nothing in this view. Switch the filter to review other prospects.")

    for index in visible_indices:
        item = results.opportunities[index]
        review_key = f"{run_id}:{index}"
        current = reviews.get(review_key, "Awaiting review")
        current_progress = st.session_state.listicle_placement_progress.get(
            review_key, "Not contacted"
        )
        contact_results = st.session_state.listicle_contact_results.get(review_key)
        policy_result = st.session_state.listicle_policy_results.get(review_key)

        # Keep the record present even if the page is opened before a decision.
        upsert_listicle_prospect(
            item,
            search_theme=results.search_theme,
            review_status=current,
            contacts=contact_results,
            policy=policy_result,
            placement_progress=current_progress,
        )

        with st.container(border=True, key=f"listicle-card-{run_id}-{index}"):
            title_col, link_col = st.columns(
                [4, 1.1], gap="small", vertical_alignment="center"
            )
            with title_col:
                st.markdown(f"#### {index + 1}. {item.listicle_title}")
                st.caption(
                    f"{item.publication} · {item.placement_type} · "
                    f"{BRAND_NAME} listed: {item.brand_currently_listed}"
                )
            with link_col:
                page_url = item.listicle_url.strip()
                if page_url.startswith("https://"):
                    st.link_button(
                        "Open page",
                        page_url,
                        key=f"open_listicle_{run_id}_{index}",
                        width="stretch",
                    )
                else:
                    st.caption("No verified link")

            if item.brand_fit and not item.brand_fit.startswith("Not recorded"):
                fit_note = " ".join(item.brand_fit.split())
                if len(fit_note) > 140:
                    fit_note = fit_note[:137].rsplit(" ", 1)[0] + "…"
                st.caption(f"Why it may fit: {fit_note}")

            c1, c2 = st.columns(2, gap="small")
            status_key = f"listicle_review_decision_{run_id}_{index}"
            if status_key not in st.session_state:
                st.session_state[status_key] = current
            chosen = c1.selectbox(
                "Review decision",
                LISTICLE_STATUS_OPTIONS,
                key=status_key,
            )
            progress_key = f"listicle_placement_progress_{run_id}_{index}"
            if progress_key not in st.session_state:
                st.session_state[progress_key] = current_progress
            chosen_progress = c2.selectbox(
                "Placement progress",
                PLACEMENT_OPTIONS,
                key=progress_key,
            )

            if chosen != current:
                reviews[review_key] = chosen
                upsert_listicle_prospect(
                    item,
                    search_theme=results.search_theme,
                    review_status=chosen,
                    contacts=contact_results,
                    policy=policy_result,
                    placement_progress=chosen_progress,
                )
                st.rerun()

            if chosen_progress != current_progress:
                st.session_state.listicle_placement_progress[review_key] = chosen_progress
                upsert_listicle_prospect(
                    item,
                    search_theme=results.search_theme,
                    review_status=chosen,
                    contacts=contact_results,
                    policy=policy_result,
                    placement_progress=chosen_progress,
                )
                st.rerun()

            with st.expander("Details, contact & policy"):
                st.markdown(f"**Published / updated:** {item.published_or_updated}")
                st.markdown(f"**Category:** {item.listicle_category}")
                st.markdown(f"**Target audience:** {item.target_audience}")
                st.markdown(f"**Inclusion gap:** {item.inclusion_gap}")
                competitors = ", ".join(item.competitors_listed) if item.competitors_listed else "None verified"
                st.markdown(f"**Competitors verified on the page:** {competitors}")
                st.markdown(f"**Contact route:** {item.contact_route}")
                st.markdown(f"**Recommended action:** {item.recommended_action}")
                st.markdown(f"**Evidence:** {item.evidence}")
                st.markdown(f"**Confidence:** {item.confidence}")
                st.divider()
                st.caption("Run these only for prospects worth pursuing. Each check uses web search.")
                b1, b2 = st.columns(2)
                if b1.button(
                    "Find publisher contact",
                    key=f"find_listicle_contact_{run_id}_{index}",
                    width="stretch",
                ):
                    with st.spinner("Checking the author, editorial team, and official contact routes..."):
                        try:
                            found_contacts = research_listicle_contact(item)
                            st.session_state.listicle_contact_results[review_key] = found_contacts
                            upsert_listicle_prospect(
                                item,
                                search_theme=results.search_theme,
                                review_status=chosen,
                                contacts=found_contacts,
                                policy=policy_result,
                                placement_progress=chosen_progress,
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error("Publisher contact research failed.")
                            st.exception(exc)

                if b2.button(
                    "Check publisher policy",
                    key=f"check_publisher_policy_{run_id}_{index}",
                    width="stretch",
                ):
                    with st.spinner("Checking official publisher rules and submission routes..."):
                        try:
                            policy_result = research_publisher_policy(item)
                            st.session_state.listicle_policy_results[review_key] = policy_result
                            upsert_listicle_prospect(
                                item,
                                search_theme=results.search_theme,
                                review_status=chosen,
                                contacts=contact_results,
                                policy=policy_result,
                                placement_progress=chosen_progress,
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error("Publisher policy research failed.")
                            st.exception(exc)

                if contact_results is not None:
                    st.divider()
                    st.markdown("**Publisher contact research**")
                    st.write(contact_results.research_summary)
                    for contact_index, contact in enumerate(contact_results.contacts, start=1):
                        with st.container(border=True):
                            st.markdown(f"**Contact option {contact_index}: {contact.contact_name}**")
                            st.write(f"**Role:** {contact.current_role}")
                            st.write(f"**Professional email:** {contact.professional_email}")
                            st.write(f"**Best contact method:** {contact.contact_method}")
                            st.write(f"**Why this route fits:** {contact.why_this_contact}")
                            st.write(f"**Evidence:** {contact.evidence}")
                            st.caption(f"Confidence: {contact.confidence}")
                            if contact.author_profile_url.strip().startswith("https://"):
                                st.link_button(
                                    "Open author profile",
                                    contact.author_profile_url.strip(),
                                    key=f"l_author_{run_id}_{index}_{contact_index}",
                                )
                            if contact.contact_page_url.strip().startswith("https://"):
                                st.link_button(
                                    "Open contact page",
                                    contact.contact_page_url.strip(),
                                    key=f"l_contact_{run_id}_{index}_{contact_index}",
                                )
                            if contact.source_url.strip().startswith("https://"):
                                st.link_button(
                                    "Open verification source",
                                    contact.source_url.strip(),
                                    key=f"l_source_{run_id}_{index}_{contact_index}",
                                )
                    st.caption(
                        "Contact details are research candidates. Verify the route before use. "
                        "No emails or forms are sent by this app."
                    )

                if policy_result is not None:
                    st.divider()
                    st.markdown("**Publisher policy assessment**")
                    disposition = policy_result.recommended_disposition
                    if disposition == "Do not pursue":
                        st.error(f"Recommendation: {disposition}")
                    elif disposition in {"Needs verification", "Paid option to review"}:
                        st.warning(f"Recommendation: {disposition}")
                    elif disposition == "Already listed":
                        st.info(f"Recommendation: {disposition}")
                    else:
                        st.success(f"Recommendation: {disposition}")
                    st.write(f"**Policy status:** {policy_result.policy_status}")
                    st.write(policy_result.policy_summary)
                    st.write(f"**Recommended route:** {policy_result.recommended_route}")
                    st.write(f"**Why:** {policy_result.disposition_reason}")
                    st.caption(f"Confidence: {policy_result.confidence}")
                    if policy_result.policy_source_url.strip().startswith("https://"):
                        st.link_button(
                            "Open publisher policy source",
                            policy_result.policy_source_url.strip(),
                            key=f"l_policy_{run_id}_{index}",
                        )
                    st.caption(
                        "This is a recommendation based on accessible policy evidence, not permission or a guarantee. "
                        "The app does not submit publisher forms automatically."
                    )

    approved_with_contact = sum(
        1
        for index, item in enumerate(results.opportunities)
        if reviews.get(f"{run_id}:{index}") == "Approve to pursue"
        and st.session_state.listicle_contact_results.get(f"{run_id}:{index}") is not None
    )
    st.divider()
    if st.button(
        f"Continue to outreach ({approved_with_contact} approved with contacts) →",
        type="primary",
        width="stretch",
        disabled=approved_with_contact == 0,
    ):
        go(listicle_step="Outreach")
    if approved_with_contact == 0:
        st.caption("Approve a prospect and run contact research to continue.")


def _listicle_outreach_targets():
    targets = []
    for row in list_listicle_prospects():
        if row.get("review_status") != "Approve to pursue":
            continue
        contact_data = row.get("contact_data")
        if not contact_data:
            continue
        try:
            item = ListicleOpportunity.model_validate(row.get("payload") or {})
            contacts = ListicleContactResearchResults.model_validate(contact_data)
        except Exception:
            continue
        policy = None
        if row.get("policy_data"):
            try:
                policy = PublisherPolicyAssessment.model_validate(row["policy_data"])
            except Exception:
                policy = None
        targets.append((item, contacts, policy, row))
    return targets


def _render_listicle_outreach():
    st.caption(
        "Review or write a request, add a verified public email, then copy it and "
        "send it from your email."
    )

    with st.expander("Sender identity (used in drafts)"):
        st.markdown(f"**{HARDCODED_SENDER_NAME}** · {HARDCODED_SENDER_ROLE}")
        st.caption("Hardcoded for this workspace.")

    targets = _listicle_outreach_targets()
    if not targets:
        st.warning("No approved prospects with contact research yet.")
        if st.button("Go to prospects"):
            go(listicle_step="Prospects")
        return

    actionable = []
    for item, contacts, policy, _row in targets:
        blocked = bool(
            policy
            and policy.recommended_disposition in {"Do not pursue", "Already listed"}
        )
        if blocked:
            continue
        for contact in contacts.contacts:
            actionable.append((item, contact, policy))

    def prepare_missing() -> int:
        created = 0
        for item, contact, policy in actionable:
            if get_outreach_draft(
                "listicle_request", item.listicle_url, contact.contact_name
            ):
                continue
            upsert_outreach_draft(
                draft_listicle_inclusion_request(
                    item,
                    contact,
                    policy,
                    sender_name=st.session_state.sender_name,
                    sender_role=st.session_state.sender_role,
                ),
                "listicle_request",
                target_url=item.listicle_url,
                related_url=(policy.policy_source_url if policy else ""),
                draft_status="Draft",
                recipient_email=(
                    contact.professional_email
                    if email_sender.is_valid_email(contact.professional_email)
                    else ""
                ),
            )
            created += 1
        return created

    missing_count = sum(
        1
        for item, contact, _policy in actionable
        if get_outreach_draft(
            "listicle_request", item.listicle_url, contact.contact_name
        )
        is None
    )
    _render_bulk_outreach_actions(
        "listicle_outreach_bulk",
        {"listicle_request"},
        missing_count,
        prepare_missing,
    )

    for target_index, (item, contacts, policy, row) in enumerate(targets):
        with st.container(border=True):
            st.markdown(f"#### {item.listicle_title}")
            st.caption(f"{item.publication} · {item.placement_type}")
            st.link_button("Open listicle", item.listicle_url, key=f"outreach_listicle_{target_index}")

            blocked = policy and policy.recommended_disposition in {"Do not pursue", "Already listed"}
            if blocked:
                st.error(
                    f"Policy recommendation: {policy.recommended_disposition}. "
                    "No outreach draft should be prepared for this page."
                )
                st.write(policy.disposition_reason)

            for contact_index, contact in enumerate(contacts.contacts):
                with st.container(border=True):
                    st.markdown(f"**Contact: {contact.contact_name}**")
                    st.caption(
                        f"{contact.current_role} · {contact.contact_method} · "
                        f"Email: {contact.professional_email}"
                    )
                    st.write(contact.why_this_contact)

                    record = get_outreach_draft(
                        "listicle_request", item.listicle_url, contact.contact_name
                    )
                    if record is None:
                        _render_no_draft(
                            "Inclusion request",
                            "Prepare inclusion request",
                            f"prepare_listicle_{target_index}_{contact_index}",
                            lambda i=item, c=contact, p=policy: upsert_outreach_draft(
                                draft_listicle_inclusion_request(
                                    i,
                                    c,
                                    p,
                                    sender_name=st.session_state.sender_name,
                                    sender_role=st.session_state.sender_role,
                                ),
                                "listicle_request",
                                target_url=i.listicle_url,
                                related_url=(p.policy_source_url if p else ""),
                                draft_status="Draft",
                                recipient_email=(
                                    contact.professional_email
                                    if email_sender.is_valid_email(contact.professional_email)
                                    else ""
                                ),
                            ),
                            disabled_reason=(
                                f"Policy recommendation: {policy.recommended_disposition}. "
                                "Do not prepare outreach."
                                if blocked
                                else None
                            ),
                        )
                    else:
                        _render_draft_editor(
                            record,
                            f"listicle_draft_{target_index}_{contact_index}",
                        )

    st.divider()
    st.caption(
        "Review the page, the policy, and every claim. Copy or download the draft "
        "and send it from your email. Use 'Sent manually' to track it."
    )


def _render_listicles():
    phase = LISTICLE_STEP_PHASE.get(
        st.session_state.listicle_step, "Find & review"
    )
    _phase_control(
        LISTICLE_PHASES, "listicle_phase_widget", phase, _listicle_phase_changed
    )

    if phase == "Find & review":
        if st.session_state.listicle_results is None:
            _render_listicle_search()
        else:
            _render_listicle_prospects()
            with st.expander("Start a new search"):
                _render_listicle_search()
        return

    _render_listicle_outreach()


# =========================================================
# WORKSPACE
# =========================================================

def _render_workspace():
    mode = st.session_state.workflow_mode
    if mode is None:
        _page_header(
            "Workspace",
            "Start a campaign.",
            f"One clear path from research to send. {BRAND_NAME} research stays local, and you approve every decision and every send.",
        )
        _render_workspace_metrics()
        st.subheader("What are you working on?")
        listicle_count = len(list_listicle_prospects())
        opportunity_count = len(list_pr_opportunities())
        draft_count = len(list_outreach_drafts())

        with st.container(border=True, key="workflow-pr"):
            st.markdown("### Digital PR")
            st.caption("Article → contacts → drafts")
            st.write("Turn a published article into a verified angle, editorial openings, and writer research.")
            st.caption("Best for: expert commentary, data stories, and media coverage.")
            if opportunity_count:
                st.caption(
                    f"{opportunity_count} saved opportunit{'y' if opportunity_count == 1 else 'ies'} "
                    f"· {draft_count} draft{'s' if draft_count != 1 else ''}"
                )
                action1, action2 = st.columns([1.35, 1], gap="small")
                with action1:
                    if st.button("Continue saved Digital PR →", type="primary", width="stretch"):
                        go(mode="digital_pr", pr_step="Opportunities")
                with action2:
                    if st.button("Start new Digital PR", width="stretch"):
                        _start_new_pr()
            else:
                if st.button("Start Digital PR →", type="primary", width="stretch"):
                    _start_new_pr()

        with st.container(border=True, key="workflow-listicles"):
            st.markdown("### Listicle inclusion")
            st.caption("Search → prospects → outreach")
            st.write("Find roundups, alternatives pages, comparisons, and directories where the product may fit.")
            st.caption("Best for: software listings, roundups, and directory inclusion.")
            if listicle_count:
                st.caption(f"{listicle_count} saved prospect{'s' if listicle_count != 1 else ''}")
                action1, action2 = st.columns([1.35, 1], gap="small")
                with action1:
                    if st.button("Continue saved listicles →", type="primary", width="stretch"):
                        go(mode="listicles", listicle_step="Prospects")
                with action2:
                    if st.button("Start new listicle search", width="stretch"):
                        _start_new_listicle()
            else:
                if st.button("Start listicle research →", type="primary", width="stretch"):
                    _start_new_listicle()
        return

    if mode == "digital_pr":
        phases = PR_PHASES
        phase = PR_STEP_PHASE.get(st.session_state.pr_step, "Research")
        label = "Digital PR"
        copy = PR_PHASE_COPY
    else:
        phases = LISTICLE_PHASES
        phase = LISTICLE_STEP_PHASE.get(
            st.session_state.listicle_step, "Find & review"
        )
        label = "Listicle inclusion"
        copy = LISTICLE_PHASE_COPY

    header_col, action_col = st.columns(
        [6, 1.7], gap="small", vertical_alignment="top"
    )
    with header_col:
        title, subtitle = copy[phase]
        _render_workflow_header(label, phase, phases, title, subtitle)
    with action_col:
        st.button(
            "← Back to start",
            key="switch-workflow",
            width="stretch",
            on_click=_go_home,
        )

    if mode == "digital_pr":
        _render_digital_pr()
    else:
        _render_listicles()


# =========================================================
# RESEARCH LIBRARY
# =========================================================

def _render_library():
    _page_header(
        "Research Library",
        "Everything you've saved.",
        "Prospects, PR opportunities, journalists, drafts, send history, and "
        "placements — all stored locally.",
    )

    saved_listicles = list_listicle_prospects()
    saved_opportunities = list_pr_opportunities()
    saved_journalists = list_journalists()
    saved_drafts = list_outreach_drafts()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Listicle prospects", len(saved_listicles))
    c2.metric("PR opportunities", len(saved_opportunities))
    c3.metric("Journalists", len(saved_journalists))
    c4.metric("Outreach drafts", len(saved_drafts))
    c5.metric(
        "Live placements",
        sum(1 for row in saved_listicles if row.get("placement_progress") == "Live placement verified"),
    )

    tab_listicles, tab_pr, tab_journalists, tab_drafts, tab_sends = st.tabs(
        [
            "Listicle prospects",
            "PR opportunities",
            "Journalists",
            "Outreach drafts",
            "Email send log",
        ]
    )

    with tab_listicles:
        if not saved_listicles:
            st.info("No listicle prospects saved yet. Run a search in the Workspace.")
        else:
            rows = [
                {
                    "Publication": row.get("publication", ""),
                    "Listicle": row.get("title", ""),
                    "URL": row.get("url", ""),
                    "Placement type": row.get("placement_type", "Unclear"),
                    "Review": row.get("review_status", "Awaiting review"),
                    "Progress": row.get("placement_progress", "Not contacted"),
                    "Contact": "Yes" if row.get("contact_data") else "No",
                    "Policy": "Yes" if row.get("policy_data") else "No",
                    "Updated": row.get("updated_at", ""),
                }
                for row in saved_listicles
            ]
            st.dataframe(
                rows,
                width="stretch",
                hide_index=True,
                column_config={"URL": st.column_config.LinkColumn("URL", display_text="Open page")},
            )
            st.download_button(
                "Export listicle prospects as CSV",
                data=listicle_csv_bytes(),
                file_name="listicle_prospects.csv",
                mime="text/csv",
            )
            with st.expander("View saved contact and policy details"):
                for row in saved_listicles:
                    st.markdown(f"**{row.get('publication', 'Unknown')} · {row.get('title', 'Untitled')}**")
                    st.caption(
                        f"Review: {row.get('review_status')} · Progress: {row.get('placement_progress')}"
                    )
                    contacts = row.get("contact_data")
                    if contacts:
                        st.write(contacts.get("research_summary", ""))
                        for contact in contacts.get("contacts", []):
                            st.write(
                                f"- {contact.get('contact_name', 'Contact')} · "
                                f"{contact.get('current_role', 'Unknown')} · "
                                f"Email: {contact.get('professional_email', 'Not publicly found')}"
                            )
                    policy = row.get("policy_data")
                    if policy:
                        st.write(
                            f"- Policy: {policy.get('recommended_disposition', 'Unknown')} · "
                            f"{policy.get('policy_summary', '')}"
                        )
                    st.divider()

    with tab_pr:
        if not saved_opportunities:
            st.info("No PR opportunities saved yet. Research an angle in the Workspace.")
        else:
            rows = [
                {
                    "Publication": row.get("publication", ""),
                    "Article": row.get("title", ""),
                    "URL": row.get("url", ""),
                    "PR angle": row.get("selected_angle", ""),
                    "Review": row.get("review_status", "Awaiting review"),
                    "Updated": row.get("updated_at", ""),
                }
                for row in saved_opportunities
            ]
            st.dataframe(
                rows,
                width="stretch",
                hide_index=True,
                column_config={"URL": st.column_config.LinkColumn("URL", display_text="Open article")},
            )
            st.download_button(
                "Export PR opportunities as CSV",
                data=opportunity_csv_bytes(),
                file_name="pr_opportunities.csv",
                mime="text/csv",
            )
            st.download_button(
                "Export sites + contacts as CSV",
                data=sites_contacts_csv_bytes(),
                file_name="pr_sites_contacts.csv",
                mime="text/csv",
                key="library_sites_contacts",
            )

    with tab_journalists:
        if not saved_journalists:
            st.info("No journalist records saved yet. Research journalists for an approved opportunity.")
        else:
            rows = [
                {
                    "Name": row.get("name", ""),
                    "Publication": row.get("publication", ""),
                    "Relevant article": row.get("relevant_article_url", ""),
                    "Qualification": row.get("qualification_status", "Needs review"),
                    "Updated": row.get("updated_at", ""),
                }
                for row in saved_journalists
            ]
            st.dataframe(
                rows,
                width="stretch",
                hide_index=True,
                column_config={
                    "Relevant article": st.column_config.LinkColumn(
                        "Relevant article", display_text="Open article"
                    )
                },
            )
            st.download_button(
                "Export journalists as CSV",
                data=journalist_csv_bytes(),
                file_name="journalists.csv",
                mime="text/csv",
            )

    with tab_drafts:
        if not saved_drafts:
            st.info("No outreach drafts yet. Qualify a target and prepare a draft in the Workspace.")
        else:
            rows = [
                {
                    "Type": row.get("draft_type", ""),
                    "Recipient": row.get("recipient_name", ""),
                    "Email": row.get("recipient_email", ""),
                    "Publication": row.get("publication", ""),
                    "Subject": row.get("subject", ""),
                    "Status": row.get("draft_status", "Draft"),
                    "Sent": row.get("sent_at", ""),
                    "Updated": row.get("updated_at", ""),
                }
                for row in saved_drafts
            ]
            st.dataframe(rows, width="stretch", hide_index=True)
            st.download_button(
                "Export outreach drafts as CSV",
                data=outreach_csv_bytes(),
                file_name="outreach_drafts.csv",
                mime="text/csv",
            )
            with st.expander("View draft text"):
                for row in saved_drafts:
                    st.markdown(f"**{row.get('recipient_name', 'Unknown')} · {row.get('publication', '')}**")
                    st.caption(
                        f"{row.get('draft_type')} · {row.get('draft_status')} · "
                        f"Email: {row.get('recipient_email') or 'Not set'}"
                    )
                    if row.get("sent_at"):
                        st.caption(
                            f"Sent: {row['sent_at']} · Message ID: "
                            f"{row.get('message_id') or 'Not recorded'}"
                        )
                    if row.get("send_error"):
                        st.caption(f"Last send error: {row['send_error']}")
                    st.markdown(f"**Subject:** {row.get('subject', '')}")
                    st.text(row.get("body", ""))
                    st.divider()

    with tab_sends:
        send_rows = list_email_sends()
        if not send_rows:
            st.info(
                "No emails have been sent yet. Approved batch sends will appear here "
                "with their status, recipient, and message ID."
            )
        else:
            sent_today = count_emails_sent_today()
            st.caption(
                f"{sent_today} successful send"
                f"{'s' if sent_today != 1 else ''} today · "
                f"{len(send_rows)} logged send attempt"
                f"{'s' if len(send_rows) != 1 else ''} shown."
            )
            rows = [
                {
                    "Time": row.get("created_at", ""),
                    "Status": row.get("status", ""),
                    "Recipient": row.get("recipient_name", ""),
                    "Email": row.get("recipient_email", ""),
                    "Publication": row.get("publication", ""),
                    "Subject": row.get("subject", ""),
                    "Message ID": row.get("message_id", ""),
                    "Error": row.get("error", ""),
                }
                for row in send_rows
            ]
            st.dataframe(rows, width="stretch", hide_index=True)
            st.download_button(
                "Export email send log as CSV",
                data=email_sends_csv_bytes(),
                file_name="email_send_log.csv",
                mime="text/csv",
            )

    st.divider()
    st.subheader("Backup")
    st.caption("Create a dated, verified SQLite backup before updating the app or moving computers.")
    if st.button("Create database backup", type="primary"):
        try:
            backup_file = create_database_backup()
            st.success(f"Backup created: {backup_file}")
        except Exception as exc:
            st.error(f"Backup failed: {exc}")
    st.caption(f"Database: {DB_PATH}")


# =========================================================
# SETTINGS
# =========================================================

def _brand_config_path() -> Path:
    data_dir = Path(
        os.environ.get("PR_AGENT_DATA_DIR")
        or Path(__file__).resolve().parent / "data"
    )
    return data_dir / "brand_config.json"


def _render_settings():
    _page_header(
        "Settings",
        "Make it yours.",
        f"Brand profile for {BRAND_NAME}, email sending, model cost, sender details, "
        "and local storage.",
    )

    st.subheader("Cost controls")
    st.write(f"**Active model:** `{MODEL}`")
    st.write(f"**Web search context:** `{SEARCH_CONTEXT_SIZE}`")
    st.write("**Draft writing:** no web search, short prompt, one model call.")
    st.caption(
        "The default is a nano model. To lower cost further, set OPENAI_MODEL to "
        "gpt-5-nano-flex before launching. Web search is the largest cost, so contact, "
        "policy, and journalist research run only when you click their buttons."
    )
    st.markdown("**Model options (USD per 1M tokens)**")
    st.table(
        [
            {"Model": "gpt-5-nano (default)", "Input": "$0.05", "Output": "$0.40", "Notes": "Best balance"},
            {"Model": "gpt-5-nano-flex", "Input": "$0.025", "Output": "$0.20", "Notes": "Lowest cost, slower queue"},
            {"Model": "gpt-5.4-nano", "Input": "$0.20", "Output": "$1.25", "Notes": "Higher cost"},
        ]
    )
    st.caption(
        "Web search is billed separately by OpenAI and is usually the largest cost. "
        "Draft writing uses no web search."
    )

    st.divider()
    st.subheader("Brand profile")
    st.caption(
        "Use this tool for any company, client, or product. The brand profile below is used "
        "in research prompts, draft writing, and labels throughout the workspace."
    )
    st.write(f"**Active brand:** {BRAND_NAME}")
    st.write(f"**Product or service:** {PRODUCT_DESCRIPTION}")
    if BRAND_DOMAIN:
        st.write(f"**Website:** {BRAND_DOMAIN}")
    st.caption(
        "Changing the brand affects new research and drafts. Saved records keep the text "
        "they were created with. Stored in data/brand_config.json. Environment variables "
        "BRAND_NAME, PRODUCT_DESCRIPTION, and BRAND_DOMAIN override the file. "
        "Restart the app after saving."
    )
    with st.form("brand_settings_form"):
        brand_name = st.text_input("Brand name", value=BRAND_NAME)
        brand_domain = st.text_input(
            "Website (optional)",
            value=BRAND_DOMAIN,
            placeholder="https://example.com",
        )
        product_description = st.text_area(
            "One-line product or service description",
            value=PRODUCT_DESCRIPTION,
            height=80,
        )
        if st.form_submit_button("Save brand profile"):
            config_path = _brand_config_path()
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps(
                    {
                        "brand_name": brand_name.strip(),
                        "brand_domain": brand_domain.strip(),
                        "product_description": product_description.strip(),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            st.success("Brand profile saved. Restart the app to apply it.")

    st.divider()
    st.subheader("Your sender details")
    st.markdown(f"**{HARDCODED_SENDER_NAME}** · {HARDCODED_SENDER_ROLE}")
    st.caption("This sender identity is hardcoded and used in every outreach draft.")

    st.divider()
    st.subheader("Email sending (optional, not used in research-only mode)")
    st.caption(
        "You do not need this section. Drafts are copied or downloaded and sent "
        "from your own email. The setup below is only for optional in-app sending."
    )
    st.caption(
        "Sending is local only. Use Google Workspace sign-in (OAuth) or a Google "
        "app password for Gmail/Workspace. Use Custom SMTP to send from another "
        "designated mailbox with the host, username, and password from that "
        "provider. Credentials and tokens are stored in data/email_config.json, "
        "which is gitignored."
    )
    email_notice = st.session_state.pop("_email_settings_notice", None)
    if email_notice:
        notice_kind, notice_text = email_notice
        if notice_kind == "success":
            st.success(notice_text)
        elif notice_kind == "error":
            st.error(notice_text)
        else:
            st.warning(notice_text)

    email_config = email_sender.load_email_config()
    AUTH_APP_PASSWORD_LABEL = "Google app password"
    AUTH_OAUTH_LABEL = "Sign in with Google (OAuth)"
    if (
        st.session_state.get("email_auth_mode_label")
        == "Google Workspace sign-in (OAuth)"
    ):
        st.session_state["email_auth_mode_label"] = AUTH_OAUTH_LABEL
    AUTH_SMTP_LABEL = "Custom SMTP / designated email"

    def _save_email_auth_method() -> None:
        current = email_sender.load_email_config()
        selected = st.session_state.get(
            "email_auth_mode_label", AUTH_APP_PASSWORD_LABEL
        )
        if selected == AUTH_OAUTH_LABEL:
            current.auth_method = "oauth"
        elif selected == AUTH_SMTP_LABEL:
            current.auth_method = "smtp"
        else:
            current.auth_method = "app_password"
        email_sender.save_email_config(current)

    auth_index = 0
    if email_config.auth_method == "oauth":
        auth_index = 1
    elif email_config.auth_method == "smtp":
        auth_index = 2
    selected_label = st.radio(
        "Sending method",
        [AUTH_APP_PASSWORD_LABEL, AUTH_OAUTH_LABEL, AUTH_SMTP_LABEL],
        index=auth_index,
        horizontal=True,
        key="email_auth_mode_label",
        on_change=_save_email_auth_method,
        help=(
            "Changing this saves the method immediately. OAuth is the option for "
            "Google Workspace accounts where app passwords are blocked. Custom "
            "SMTP works with any provider that gives you SMTP login details."
        ),
    )
    email_config = email_sender.load_email_config()
    if selected_label == AUTH_OAUTH_LABEL:
        selected_mode = "oauth"
    elif selected_label == AUTH_SMTP_LABEL:
        selected_mode = "smtp"
    else:
        selected_mode = "app_password"
    st.caption(f"Local config file: {email_sender.CONFIG_PATH}")

    if selected_mode == "oauth":
        oauth_accounts = email_sender.ensure_oauth_accounts(email_config)
        if email_sender.is_oauth_connected(email_config):
            st.success(
                f"Connected as {email_config.from_email}. Batch sending will use "
                "the active Google account."
            )
            st.caption(
                "Run Test active account once to confirm that Google accepts the "
                "SMTP connection for this account."
            )
        elif email_config.oauth_refresh_token:
            st.warning(
                "A Google account is connected, but the sender address is missing. "
                "Reconnect the account below."
            )
        else:
            st.warning(
                "No Google Workspace account is connected yet. Add the OAuth client "
                "details below, then connect."
            )

        with st.expander(
            "How to create the Google OAuth client",
            expanded=not bool(email_config.oauth_client_id),
        ):
            st.markdown(
                """
1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or select a project.
2. Open **APIs & Services → OAuth consent screen**. Choose **External** and add each Google account you want to send from as a **test user** (up to 100).
3. Add these scopes: `openid`, `email`, `https://mail.google.com/`.
4. Open **Credentials → Create credentials → OAuth client ID → Web application**.
5. Add the redirect URI shown below (local: `http://localhost:8501/`, hosted: `https://pr.prachiadmane.com/`).
6. Copy the client ID and client secret below, save, then use **Connect another Google account** once per account.
7. Pick the **Active sending account** above. Batch sending uses that account.

Testing mode works for a few personal accounts, but Google expires refresh tokens every 7 days. To avoid reconnecting weekly, publish the OAuth consent screen (unverified apps show a warning but keep tokens). A Workspace admin may also need to allow the app and the Gmail scope.
"""
            )

        with st.form("email_oauth_form"):
            oauth_client_id = st.text_input(
                "Google OAuth client ID",
                value=email_config.oauth_client_id,
                placeholder="....apps.googleusercontent.com",
                help="The client ID from your Google Cloud OAuth Web application.",
            )
            oauth_client_secret = st.text_input(
                "Google OAuth client secret",
                value="",
                type="password",
                help="Leave blank to keep the saved secret.",
            )
            clear_oauth_secret = st.checkbox(
                "Delete the saved OAuth client secret",
                value=False,
                help="Check this only when you want to remove the saved client secret.",
            )
            delay_col, cap_col = st.columns(2)
            delay_seconds = delay_col.number_input(
                "Delay between sends (seconds)",
                min_value=email_sender.MIN_DELAY_SECONDS,
                max_value=email_sender.MAX_DELAY_SECONDS,
                value=email_config.delay_seconds,
                step=5,
            )
            daily_cap = cap_col.number_input(
                "Daily send cap",
                min_value=1,
                max_value=email_sender.MAX_DAILY_CAP,
                value=email_config.daily_cap,
                step=1,
                help="Successful sends per local day. Keep this well below your Gmail limit.",
            )
            postal_address = st.text_area(
                "Mailing address (optional, recommended)",
                value=email_config.postal_address,
                height=70,
                placeholder="Company name, street address, city, country",
                help=(
                    "Appended to every outgoing email. Commercial email rules often "
                    "require a physical postal address."
                ),
            )
            save_oauth = st.form_submit_button(
                "Save OAuth settings", type="primary", width="stretch"
            )
            if save_oauth:
                client_id = (oauth_client_id or "").strip()
                secret = (oauth_client_secret or "").strip()
                if not secret and not clear_oauth_secret:
                    secret = email_config.oauth_client_secret
                if clear_oauth_secret:
                    secret = ""
                refresh_token = email_config.oauth_refresh_token
                oauth_email = email_config.oauth_email
                if client_id != email_config.oauth_client_id.strip():
                    refresh_token = ""
                    oauth_email = ""
                candidate = email_sender.EmailConfig(
                    from_email=email_config.from_email,
                    app_password=email_config.app_password,
                    auth_method="oauth",
                    smtp_host=email_config.smtp_host,
                    smtp_port=email_config.smtp_port,
                    smtp_username=email_config.smtp_username,
                    smtp_password=email_config.smtp_password,
                    smtp_security=email_config.smtp_security,
                    oauth_client_id=client_id,
                    oauth_client_secret=secret,
                    oauth_refresh_token=refresh_token,
                    oauth_email=oauth_email,
                    oauth_redirect_uri=email_config.oauth_redirect_uri,
                    delay_seconds=int(delay_seconds),
                    daily_cap=int(daily_cap),
                    postal_address=(postal_address or "").strip(),
                )
                email_sender.save_email_config(candidate)
                if not client_id or not secret:
                    notice = (
                        "OAuth settings saved. Add both the client ID and client "
                        "secret, then connect the account."
                    )
                elif not refresh_token:
                    notice = (
                        "OAuth client settings saved. Now connect your Google "
                        "accounts below."
                    )
                else:
                    notice = "OAuth settings saved. Google sign-in is ready."
                st.session_state["_email_settings_notice"] = ("success", notice)
                st.rerun()

        if not email_config.oauth_client_id or not email_config.oauth_client_secret:
            st.info(
                "Save the OAuth client ID and client secret first. The Connect "
                "button appears after they are stored."
            )
        else:
            st.caption(
                "Authorized redirect URI — add this exact value to the Google OAuth "
                "client:"
            )
            st.code(email_config.oauth_redirect_uri, language="text")
            connected = email_sender.is_oauth_connected(email_config)
            oauth_accounts = email_sender.ensure_oauth_accounts(email_config)
            if oauth_accounts["accounts"]:
                names = [
                    account["email"] for account in oauth_accounts["accounts"]
                ]
                active = oauth_accounts.get("active") or names[0]
                st.markdown("**Connected Google accounts**")
                chosen = st.radio(
                    "Active sending account",
                    names,
                    index=names.index(active) if active in names else 0,
                    key="active_oauth_account",
                    help="Batch sending uses this account. Add more below.",
                )
                if chosen != active:
                    email_sender.set_active_oauth_account(chosen)
                    st.rerun()
                test_col, remove_col = st.columns(2)
                if test_col.button(
                    "Test active account",
                    key="oauth_test_connection",
                    width="stretch",
                ):
                    connected_ok, message = email_sender.test_connection(
                        email_sender.load_email_config()
                    )
                    if connected_ok:
                        st.success(message)
                    else:
                        st.error(message)
                if remove_col.button(
                    f"Remove {active}",
                    key="oauth_disconnect",
                    width="stretch",
                ):
                    email_sender.remove_oauth_account(
                        active, email_sender.load_email_config()
                    )
                    st.session_state["_email_settings_notice"] = (
                        "warning",
                        "Removed this Google account locally. To revoke the app at "
                        "Google, remove it from your Google Account permissions.",
                    )
                    st.rerun()
            else:
                st.caption("No Google accounts connected yet.")
            try:
                oauth_state = email_sender.create_oauth_state()
                oauth_url = email_sender.build_oauth_url(email_config, oauth_state)
            except email_sender.OAuthError as exc:
                st.error(str(exc))
            else:
                oauth_label = (
                    "Connect another Google account"
                    if oauth_accounts["accounts"]
                    else "Connect Google account"
                )
                st.markdown(
                    f'<a href="{html.escape(oauth_url, quote=True)}" target="_self" '
                    'style="display:inline-flex;align-items:center;justify-content:center;'
                    'padding:0.55rem 1rem;border-radius:0.5rem;background:#ff4b4b;'
                    'color:#ffffff;text-decoration:none;font-weight:600;">'
                    f"{oauth_label}</a>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Google opens its consent screen. After approving, you return "
                    "here automatically."
                )

    elif selected_mode == "smtp":
        st.info(
            "Use this when you have a designated sending mailbox from your email "
            "host or an SMTP service. Enter the From address and the SMTP login "
            "that provider gives you. The provider must allow that From address."
        )
        if email_config.smtp_password:
            st.caption(
                "A custom SMTP password is saved locally. Leave the password field "
                "blank to keep it."
            )
        else:
            st.warning(
                "No custom SMTP password is saved yet. Batch sending is disabled "
                "until you add one."
            )
        st.caption(
            "Google Workspace usually requires the OAuth option above or an "
            "admin-approved SMTP relay. A normal Google password will not work."
        )
        with st.form("email_custom_smtp_form"):
            smtp_from_email = st.text_input(
                "Designated From email address",
                value=email_config.from_email,
                placeholder="prachi@yourdomain.com",
                help="The address that will appear in the From header.",
            )
            host_col, port_col = st.columns([3, 1])
            default_host = email_config.smtp_host or ""
            if (
                default_host == email_sender.SMTP_HOST
                and not email_config.smtp_password
            ):
                default_host = ""
            smtp_host = host_col.text_input(
                "SMTP host",
                value=default_host,
                placeholder="smtp.yourprovider.com",
            )
            smtp_port = port_col.number_input(
                "SMTP port",
                min_value=1,
                max_value=65535,
                value=int(email_config.smtp_port or 587),
                step=1,
            )
            security_labels = [
                "STARTTLS (usually port 587)",
                "SSL/TLS (usually port 465)",
            ]
            security_label = st.selectbox(
                "Connection security",
                security_labels,
                index=1 if email_config.smtp_security == "ssl" else 0,
            )
            smtp_username = st.text_input(
                "SMTP username",
                value=email_config.smtp_username or email_config.from_email,
                placeholder="Usually the full email address",
            )
            smtp_password = st.text_input(
                "SMTP password",
                value="",
                type="password",
                help=(
                    "The SMTP password or API key from your provider. Leave blank "
                    "to keep the saved password."
                ),
            )
            clear_smtp_password = st.checkbox(
                "Delete the saved SMTP password",
                value=False,
                help="Check this only when you want to remove the saved credential.",
            )
            delay_col, cap_col = st.columns(2)
            delay_seconds = delay_col.number_input(
                "Delay between sends (seconds)",
                min_value=email_sender.MIN_DELAY_SECONDS,
                max_value=email_sender.MAX_DELAY_SECONDS,
                value=email_config.delay_seconds,
                step=5,
            )
            daily_cap = cap_col.number_input(
                "Daily send cap",
                min_value=1,
                max_value=email_sender.MAX_DAILY_CAP,
                value=email_config.daily_cap,
                step=1,
                help="Successful sends per local day. Keep this below your provider's limit.",
            )
            postal_address = st.text_area(
                "Mailing address (optional, recommended)",
                value=email_config.postal_address,
                height=70,
                placeholder="Company name, street address, city, country",
                help=(
                    "Appended to every outgoing email. Commercial email rules often "
                    "require a physical postal address."
                ),
            )
            save_smtp = st.form_submit_button(
                "Save custom SMTP settings", type="primary", width="stretch"
            )
            test_smtp = st.form_submit_button(
                "Test custom SMTP connection", width="stretch"
            )

            if save_smtp or test_smtp:
                password = (smtp_password or "").strip()
                if not password and not clear_smtp_password:
                    password = email_config.smtp_password
                if clear_smtp_password:
                    password = ""
                security = "ssl" if security_label.startswith("SSL") else "starttls"
                candidate = email_sender.EmailConfig(
                    from_email=(smtp_from_email or "").strip(),
                    app_password=email_config.app_password,
                    auth_method="smtp",
                    smtp_host=(smtp_host or "").strip(),
                    smtp_port=int(smtp_port),
                    smtp_username=(smtp_username or "").strip()
                    or (smtp_from_email or "").strip(),
                    smtp_password=password,
                    smtp_security=security,
                    oauth_client_id=email_config.oauth_client_id,
                    oauth_client_secret=email_config.oauth_client_secret,
                    oauth_refresh_token=email_config.oauth_refresh_token,
                    oauth_email=email_config.oauth_email,
                    oauth_redirect_uri=email_config.oauth_redirect_uri,
                    delay_seconds=int(delay_seconds),
                    daily_cap=int(daily_cap),
                    postal_address=(postal_address or "").strip(),
                )
                if save_smtp:
                    email_sender.save_email_config(candidate)
                    missing = email_sender.missing_config_fields(candidate)
                    if missing:
                        st.session_state["_email_settings_notice"] = (
                            "warning",
                            "Settings saved, but sending is not ready. Add "
                            + " and ".join(missing)
                            + ".",
                        )
                    else:
                        st.session_state["_email_settings_notice"] = (
                            "success",
                            "Custom SMTP settings saved locally. Batch sending is ready.",
                        )
                    st.rerun()
                if test_smtp:
                    connected, message = email_sender.test_connection(candidate)
                    if connected:
                        st.success(message)
                    else:
                        st.error(message)

    else:
        if email_config.app_password:
            st.caption(
                "A Google app password is saved locally. Leave the password field "
                "blank to keep it."
            )
        else:
            st.warning(
                "No Google app password is saved yet. Batch sending is disabled "
                "until you add one."
            )
        st.markdown(
            "Create an app password at "
            "[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). "
            "Use `smtp.gmail.com` on port `587` with STARTTLS."
        )
        with st.form("email_settings_form"):
            from_email = st.text_input(
                "Gmail / Google Workspace address",
                value=email_config.from_email,
                placeholder="you@yourdomain.com",
                help="The full address that will appear in the From header.",
            )
            app_password = st.text_input(
                "Google app password",
                value="",
                type="password",
                help=(
                    "The 16-character app password. Spaces are ignored. Leave blank "
                    "to keep the saved password."
                ),
            )
            clear_password = st.checkbox(
                "Delete the saved app password",
                value=False,
                help="Check this only when you want to remove the saved credential.",
            )
            delay_col, cap_col = st.columns(2)
            delay_seconds = delay_col.number_input(
                "Delay between sends (seconds)",
                min_value=email_sender.MIN_DELAY_SECONDS,
                max_value=email_sender.MAX_DELAY_SECONDS,
                value=email_config.delay_seconds,
                step=5,
            )
            daily_cap = cap_col.number_input(
                "Daily send cap",
                min_value=1,
                max_value=email_sender.MAX_DAILY_CAP,
                value=email_config.daily_cap,
                step=1,
                help="Successful sends per local day. Keep this well below your Gmail limit.",
            )
            postal_address = st.text_area(
                "Mailing address (optional, recommended)",
                value=email_config.postal_address,
                height=70,
                placeholder="Company name, street address, city, country",
                help=(
                    "Appended to every outgoing email. Commercial email rules often "
                    "require a physical postal address."
                ),
            )
            save_email = st.form_submit_button(
                "Save email settings", type="primary", width="stretch"
            )
            test_email = st.form_submit_button(
                "Test SMTP connection", width="stretch"
            )
            test_send = st.form_submit_button(
                "Send a test email to myself", width="stretch"
            )

            if save_email or test_email:
                password = (app_password or "").strip().replace(" ", "")
                if not password and not clear_password:
                    password = email_config.app_password
                if clear_password:
                    password = ""
                candidate = email_sender.EmailConfig(
                    from_email=(from_email or "").strip(),
                    app_password=password,
                    auth_method="app_password",
                    smtp_host=email_config.smtp_host,
                    smtp_port=email_config.smtp_port,
                    smtp_username=email_config.smtp_username,
                    smtp_password=email_config.smtp_password,
                    smtp_security=email_config.smtp_security,
                    oauth_client_id=email_config.oauth_client_id,
                    oauth_client_secret=email_config.oauth_client_secret,
                    oauth_refresh_token=email_config.oauth_refresh_token,
                    oauth_email=email_config.oauth_email,
                    oauth_redirect_uri=email_config.oauth_redirect_uri,
                    delay_seconds=int(delay_seconds),
                    daily_cap=int(daily_cap),
                    postal_address=(postal_address or "").strip(),
                )
                if save_email:
                    email_sender.save_email_config(candidate)
                    missing = email_sender.missing_config_fields(candidate)
                    if missing:
                        st.session_state["_email_settings_notice"] = (
                            "warning",
                            "Settings saved, but sending is not ready. Add "
                            + " and ".join(missing)
                            + ".",
                        )
                    else:
                        st.session_state["_email_settings_notice"] = (
                            "success",
                            "Email settings saved locally. Batch sending is ready.",
                        )
                    st.rerun()
                if test_email:
                    connected, message = email_sender.test_connection(candidate)
                    if connected:
                        st.success(message)
                    else:
                        st.error(message)
                if test_send:
                    connected, message = email_sender.test_connection(candidate)
                    if not connected:
                        st.error(message)
                    else:
                        test_result = email_sender.send_email(
                            candidate,
                            candidate.from_email,
                            "Test from your Digital PR Agent",
                            (
                                "This is a test from your Digital PR Agent.\n\n"
                                "If you received it, the SMTP connection, sender "
                                "identity, and opt-out footer all work.\n\n"
                                f"Sent at {datetime.now():%Y-%m-%d %H:%M}."
                            ),
                        )
                        if test_result.success:
                            st.success(
                                f"Test email sent to {candidate.from_email}. "
                                "Check that inbox."
                            )
                        else:
                            st.error(f"Test email failed: {test_result.error}")

    st.caption(
        f"From name: {email_sender.DEFAULT_FROM_NAME} (fixed). Every email also gets "
        "an automatic opt-out line."
    )
    st.caption(
        "The app sends only approved drafts, one recipient at a time, with the configured "
        "delay and daily cap. It never sends on a schedule or without a confirmation."
    )

    st.divider()
    st.subheader("Do-not-send list (opt-outs)")
    st.caption(
        "If someone asks not to be contacted, add their email here. Matching drafts are "
        "blocked from batch sending. The opt-out footer asks recipients to reply "
        "\"unsubscribe\"."
    )
    with st.form("suppression_form"):
        suppress_email = st.text_input(
            "Email to suppress",
            placeholder="name@publication.com",
            help="Case is ignored. This blocks every future batch send to the address.",
        )
        suppress_reason = st.text_input(
            "Reason (optional)",
            placeholder="Replied unsubscribe",
        )
        add_suppression = st.form_submit_button(
            "Add to do-not-send list", width="stretch"
        )
        if add_suppression:
            value = (suppress_email or "").strip().lower()
            if not email_sender.is_valid_email(value):
                st.error("Enter a valid email address.")
            else:
                add_email_suppression(value, suppress_reason)
                st.success(f"{value} is blocked from batch sending.")

    suppressions = list_email_suppressions()
    if suppressions:
        st.dataframe(
            [
                {
                    "Email": row.get("email", ""),
                    "Reason": row.get("reason", ""),
                    "Added": row.get("created_at", ""),
                }
                for row in suppressions
            ],
            width="stretch",
            hide_index=True,
        )
        with st.expander("Remove an address from the do-not-send list"):
            for row in suppressions:
                address_col, action_col = st.columns([5, 1])
                address_col.write(row.get("email", ""))
                if action_col.button(
                    "Remove", key=f"remove_suppression_{row.get('email', '')}"
                ):
                    remove_email_suppression(row.get("email", ""))
                    st.rerun()
    else:
        st.caption("No addresses are on the do-not-send list.")

    st.divider()
    st.subheader("ContactOut (optional paid lookup)")
    contactout_config = contact_providers.load_config()
    st.caption(
        "Add a ContactOut API token to look up work emails for content, SEO, and "
        "link-building contacts. The token stays in your local data folder. Each "
        "search consumes ContactOut credits. Sample keys return demo data only; "
        "use a production key for live results."
    )
    if contactout_config.api_token:
        st.success("ContactOut is configured. Lookups will use your credits.")
    else:
        st.caption("Not configured. The app still uses published public emails.")
    with st.form("contactout_token_form", clear_on_submit=True):
        contactout_token = st.text_input(
            "ContactOut API token",
            type="password",
            placeholder="Paste a token to add or replace the saved one",
        )
        save_contactout = st.form_submit_button(
            "Save ContactOut token", width="stretch"
        )
        if save_contactout:
            value = (contactout_token or "").strip()
            if not value:
                st.error("Paste a ContactOut API token first.")
            else:
                contact_providers.save_config(
                    contact_providers.ContactOutConfig(api_token=value)
                )
                st.success("ContactOut token saved locally.")
                st.rerun()
    if contactout_config.api_token and st.button(
        "Remove ContactOut token", key="remove_contactout_token", width="stretch"
    ):
        contact_providers.save_config(contact_providers.ContactOutConfig())
        st.success("ContactOut token removed.")
        st.rerun()

    if contactout_config.api_token:
        st.markdown("**Test the connection**")
        st.caption(
            "Runs the same People Search the app uses. This consumes ContactOut credits."
        )
        test_domain = st.text_input(
            "Publication domain",
            placeholder="digiday.com",
            key="contactout_test_domain",
        )
        if st.button(
            "Test ContactOut lookup",
            key="contactout_test_lookup",
            width="stretch",
        ):
            value = (test_domain or "").strip()
            if not value:
                st.error("Enter a publication domain first.")
            else:
                try:
                    with st.spinner("Searching ContactOut..."):
                        test_results = contact_providers.search_people(
                            value,
                            contact_providers.CONTENT_TITLES,
                            limit=5,
                        )
                    if not test_results:
                        st.warning(
                            "ContactOut returned no profiles for that domain and "
                            "those titles. Try the bare domain or fewer titles."
                        )
                    else:
                        st.success(
                            f"ContactOut returned {len(test_results)} profile"
                            f"{'s' if len(test_results) != 1 else ''}."
                        )
                        for result in test_results:
                            st.write(
                                f"**{result.get('name') or 'Unknown'}** · "
                                f"{result.get('title') or 'Unknown'} · "
                                f"{result.get('email') or 'No email returned'}"
                            )
                except Exception as exc:
                    st.error(str(exc))

    st.divider()
    st.subheader("Hunter (optional)")
    hunter_config = contact_providers.load_hunter_config()
    st.caption(
        "Hunter has a self-serve API with a free tier, useful as a cheaper "
        "work-email fallback. The key stays in your local data folder."
    )
    if hunter_config.api_key:
        st.success("Hunter is configured.")
    else:
        st.caption("Not configured. The app still uses published public emails.")
    with st.form("hunter_key_form", clear_on_submit=True):
        hunter_key = st.text_input(
            "Hunter API key",
            type="password",
            placeholder="Paste a Hunter API key to add or replace the saved one",
        )
        save_hunter = st.form_submit_button("Save Hunter key", width="stretch")
        if save_hunter:
            value = (hunter_key or "").strip()
            if not value:
                st.error("Paste a Hunter API key first.")
            else:
                contact_providers.save_hunter_config(
                    contact_providers.HunterConfig(api_key=value)
                )
                st.success("Hunter key saved locally.")
                st.rerun()
    if hunter_config.api_key and st.button(
        "Remove Hunter key", key="remove_hunter_key", width="stretch"
    ):
        contact_providers.save_hunter_config(contact_providers.HunterConfig())
        st.success("Hunter key removed.")
        st.rerun()
    if hunter_config.api_key:
        hunter_test_domain = st.text_input(
            "Hunter test domain",
            placeholder="digiday.com",
            key="hunter_test_domain",
        )
        if st.button(
            "Test Hunter lookup",
            key="hunter_test_lookup",
            width="stretch",
        ):
            value = (hunter_test_domain or "").strip()
            if not value:
                st.error("Enter a publication domain first.")
            else:
                try:
                    with st.spinner("Searching Hunter..."):
                        hunter_results = contact_providers.search_hunter(
                            value, limit=5
                        )
                    if not hunter_results:
                        st.warning("Hunter returned no profiles for that domain.")
                    else:
                        st.success(
                            f"Hunter returned {len(hunter_results)} profile"
                            f"{'s' if len(hunter_results) != 1 else ''}."
                        )
                        for result in hunter_results:
                            st.write(
                                f"**{result.get('name') or 'Unknown'}** · "
                                f"{result.get('title') or 'Unknown'} · "
                                f"{result.get('email') or 'No email returned'}"
                            )
                except Exception as exc:
                    st.error(str(exc))

    st.divider()
    st.subheader("Contact book (CSV import)")
    st.caption(
        "Import an export from ContactOut, Apollo, Hunter, or a spreadsheet. "
        f"{count_contact_book()} contact(s) are saved locally. The app matches "
        "them by publication domain or name."
    )
    uploaded_contacts = st.file_uploader(
        "Contact CSV",
        type=["csv"],
        key="contact_book_csv",
        help=(
            "Columns: email (required), name, role, publication, domain, linkedin. "
            "Header names are matched loosely."
        ),
    )
    if uploaded_contacts is not None:
        raw_bytes = uploaded_contacts.getvalue()
        try:
            csv_text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            csv_text = raw_bytes.decode("latin-1", errors="replace")
        try:
            reader = csv.DictReader(io.StringIO(csv_text))
            headers = {
                (name or "").strip().lower(): name
                for name in (reader.fieldnames or [])
            }

            def pick(row, *aliases):
                for alias in aliases:
                    key = headers.get(alias)
                    if key and (row.get(key) or "").strip():
                        return (row.get(key) or "").strip()
                return ""

            imported_rows = []
            for row in reader:
                email_value = pick(
                    row, "email", "e-mail", "mail", "work email", "work_email"
                ).lower()
                if not email_sender.is_valid_email(email_value):
                    continue
                domain_value = pick(row, "domain", "website", "company domain")
                if not domain_value:
                    domain_value = pick(row, "publication", "company", "site")
                imported_rows.append(
                    {
                        "email": email_value,
                        "name": pick(row, "name", "full name", "full_name", "contact"),
                        "role": pick(row, "role", "title", "position", "job title"),
                        "publication": pick(row, "publication", "company", "site"),
                        "domain": domain_value,
                        "linkedin": pick(
                            row, "linkedin", "linkedin url", "linkedin_url"
                        ),
                        "source": "CSV import",
                    }
                )
        except Exception as exc:
            imported_rows = []
            st.error(f"That CSV could not be read: {exc}")

        if not imported_rows:
            st.warning("No rows with a valid email column were found.")
        else:
            st.caption(f"{len(imported_rows)} valid contact row(s). Preview:")
            st.dataframe(imported_rows[:5], width="stretch", hide_index=True)
            if st.button(
                "Import these contacts",
                key="import_contact_book",
                type="primary",
                width="stretch",
            ):
                saved = upsert_contact_book(imported_rows)
                st.success(f"Imported {saved} contact(s) into the local contact book.")
                st.rerun()

    st.divider()
    st.subheader("Storage and safety")
    st.write(f"**Database:** `{DB_PATH}`")
    st.write("**Backups:** `backups/` in the project folder")
    st.caption(
        "Data stays on this computer. It is not synced. Create a backup before updating "
        "the app or moving to another computer."
    )
    if st.button("Create database backup now"):
        try:
            backup_file = create_database_backup()
            st.success(f"Backup created: {backup_file}")
        except Exception as exc:
            st.error(f"Backup failed: {exc}")

    st.divider()
    st.subheader("Safety rules")
    st.markdown(
        """
        - Research-only mode is the default: drafts are copied or downloaded and
          sent from your own email. The app does not send anything.
        - Optional in-app sending is local only and requires a draft status of
          'Approved for automated send' plus a separate batch confirmation.
        - The app sends one recipient at a time, with a delay, a daily cap, and a
          permanent send log. It never sends on a schedule.
        - Every outgoing email gets an automatic opt-out line. Add a mailing
          address for commercial-email compliance. If someone opts out, add their
          address to the do-not-send list before any further batch send.
        - Research, contacts, and policy findings must be checked by a human.
          Use only publicly listed, relevant editorial contacts.
        - Publisher policy findings are recommendations, not permission or a guarantee.
        - The app never submits publisher forms automatically.
        """
    )


# =========================================================
# SIDEBAR AND ROUTING
# =========================================================

_apply_pending_navigation()

with st.sidebar:
    st.markdown(
        f"""
        <div class="app-brand">
            <div class="app-brand-mark">PR</div>
            <div>
                <div class="app-brand-name">PR Research Agent</div>
                <div class="app-brand-tagline">Digital PR · Listicles · Drafts</div>
            </div>
        </div>
        <div class="brand-chip">
            <span class="dot"></span>
            Working for <strong>{html.escape(BRAND_NAME)}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )

    page = st.radio(
        "Navigation",
        ["Workspace", "Research Library", "Settings"],
        key="main_nav",
        label_visibility="collapsed",
    )
    if st.session_state.get("workflow_mode"):
        st.button(
            "← Back to start",
            key="sidebar_home",
            width="stretch",
            on_click=_go_home,
        )
    if _login_password():
        if st.button("Log out", key="logout", width="stretch"):
            st.session_state["_clear_auth_cookie"] = True
            st.session_state["_authenticated"] = False
            st.rerun()

    st.divider()
    st.caption(f"Model: {MODEL}")
    st.caption(f"Search context: {SEARCH_CONTEXT_SIZE}")
    st.caption("Local only · human-approved email")


if page == "Workspace":
    _render_workspace()
elif page == "Research Library":
    _render_library()
else:
    _render_settings()


# =========================================================
# SAVE ACTIVE WORKSPACE AFTER EACH STREAMLIT RUN
# =========================================================

_PERSISTED_STATE_KEYS = [
    "analysis",
    "asset_analyses",
    "article_url",
    "selected_angle_index",
    "opportunity_results",
    "opportunity_reviews",
    "research_run_id",
    "journalist_results",
    "journalist_reviews",
    "listicle_results",
    "listicle_reviews",
    "listicle_contact_results",
    "listicle_policy_results",
    "listicle_run_id",
    "listicle_placement_progress",
    "workflow_mode",
    "pr_step",
    "listicle_step",
    "sender_name",
    "sender_role",
]


def _snapshot_value(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _snapshot_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_snapshot_value(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


_snapshot = {
    key: _snapshot_value(st.session_state.get(key))
    for key in _PERSISTED_STATE_KEYS
}
# Only write when something changed. This keeps ordinary reruns from doing a
# full JSON write to SQLite on every click.
if _snapshot != st.session_state.get("_last_saved_snapshot"):
    save_app_snapshot(_snapshot)
    st.session_state["_last_saved_snapshot"] = _snapshot
