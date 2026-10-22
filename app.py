import hashlib
import html
import json
import os
from collections import Counter
from pathlib import Path

import streamlit as st

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
    draft_journalist_pitch,
    draft_listicle_inclusion_request,
    research_journalists,
    research_listicle_contact,
    research_listicles,
    research_opportunities,
    research_publisher_policy,
)
from database import (
    DB_PATH,
    create_database_backup,
    get_journalist_record,
    get_listicle_prospect,
    get_outreach_draft,
    get_pr_opportunity,
    init_db,
    journalist_csv_bytes,
    list_journalists,
    list_listicle_prospects,
    list_outreach_drafts,
    list_pr_opportunities,
    listicle_csv_bytes,
    load_app_snapshot,
    opportunity_csv_bytes,
    outreach_csv_bytes,
    save_app_snapshot,
    update_outreach_draft,
    upsert_journalist,
    upsert_listicle_prospect,
    upsert_outreach_draft,
    upsert_pr_opportunity,
)


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="PR Research Agent",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)


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
    "Approved for manual send",
    "Sent manually",
    "Replied",
    "Placement confirmed",
    "Declined",
    "Do not send",
]

PR_STEPS = ["Article", "PR angles", "Opportunities", "Journalists", "Outreach"]
LISTICLE_STEPS = ["Search", "Prospects", "Outreach"]



DEFAULTS = {
    "analysis": None,
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
        "workflow_mode",
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
    # Infer a sensible starting workflow only on the first load. This must not
    # run on every rerun, or "Switch workflow" would immediately undo itself.
    if st.session_state.workflow_mode is None:
        if st.session_state.analysis is not None:
            st.session_state.workflow_mode = "digital_pr"
        elif st.session_state.listicle_results is not None:
            st.session_state.workflow_mode = "listicles"
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


def _safe_choice(options, value):
    return value if value in options else options[0]


def _widget_suffix(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


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
    status_index = DRAFT_STATUS_OPTIONS.index(
        _safe_choice(DRAFT_STATUS_OPTIONS, record.get("draft_status", "Draft"))
    )

    with st.form(form_key):
        subject = st.text_input(
            "Subject line",
            value=record.get("subject", ""),
            key=f"{key_prefix}_subject_{suffix}",
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
            key=f"{key_prefix}_status_{suffix}",
        )
        if st.form_submit_button("Save draft", type="primary", width="stretch"):
            update_outreach_draft(record["draft_key"], subject, body, status)
            st.success("Draft saved locally. Nothing was sent.")

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

    download_text = f"Subject: {record.get('subject', '')}\n\n{record.get('body', '')}\n"
    st.download_button(
        "Download draft as text",
        data=download_text.encode("utf-8"),
        file_name=f"outreach_draft_{suffix}.txt",
        mime="text/plain",
        key=f"{key_prefix}_download_{suffix}",
    )
    st.caption(
        "This app never sends email or submits forms. Copy the approved draft into your "
        "email client or the publisher's official form yourself."
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


# =========================================================
# DIGITAL PR WORKFLOW
# =========================================================

def _render_pr_article():
    st.caption("Paste a published article from your brand, a client, or an industry source. The agent extracts useful angles and evidence.")

    if "article_url_input" not in st.session_state:
        st.session_state.article_url_input = st.session_state.article_url
    article_url = st.text_input(
        "Article URL",
        key="article_url_input",
        placeholder="https://example.com/article",
    )

    if st.button("Analyze article", type="primary", width="stretch"):
        if not article_url.strip():
            st.warning("Paste an article URL first.")
        elif not article_url.startswith("https://"):
            st.error("Please enter a valid HTTPS URL.")
        else:
            with st.spinner("Reading the article and building PR angles..."):
                try:
                    analysis = analyze_article(article_url.strip())
                    st.session_state.article_url = article_url.strip()
                    st.session_state.analysis = analysis
                    st.session_state.selected_angle_index = None
                    st.session_state.opportunity_results = None
                    st.session_state.opportunity_reviews = {}
                    st.session_state.journalist_results = {}
                    st.session_state.journalist_reviews = {}
                    go(pr_step="PR angles")
                except Exception as exc:
                    st.error("Article analysis failed.")
                    st.exception(exc)

    analysis = st.session_state.analysis
    if analysis:
        st.success(f"Current asset: {analysis.article_title}")
        with st.expander("View the saved asset analysis"):
            _render_analysis_details(analysis)
        if st.button("Continue to PR angles →", width="stretch"):
            go(pr_step="PR angles")


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

            with st.expander("Details and evidence"):
                st.markdown(f"**Why relevant:** {opportunity.why_relevant}")
                st.markdown(f"**Topic:** {opportunity.topic}")
                st.markdown(f"**Opportunity type:** {opportunity.opportunity_type}")
                st.markdown(f"**Brand contribution:** {opportunity.brand_contribution}")
                st.markdown(f"**Competitor presence:** {opportunity.competitor_mention}")
                st.markdown(f"**Topical relevance:** {opportunity.topical_relevance}")
                st.markdown(f"**Editorial fit:** {opportunity.editorial_fit}")
                st.markdown(f"**Recommended action:** {opportunity.recommended_action}")
                st.markdown(f"**Evidence:** {opportunity.evidence}")

            review_col, hint_col = st.columns(
                [1.6, 1], gap="small", vertical_alignment="center"
            )
            with review_col:
                widget_key = f"opp_status_{run_id}_{index}"
                if widget_key not in st.session_state:
                    st.session_state[widget_key] = current
                chosen = st.selectbox(
                    "Review decision",
                    REVIEW_OPTIONS,
                    key=widget_key,
                )
            with hint_col:
                st.caption("Changes save automatically.")
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
    if st.button(
        f"Continue to journalists ({approved} approved) →",
        type="primary",
        width="stretch",
        disabled=approved == 0,
    ):
        go(pr_step="Journalists")
    if approved == 0:
        st.caption("Approve at least one candidate to continue.")


def _render_pr_journalists():
    st.caption("Research writers with verified published work. A qualified target is ready for pitch preparation, not for sending.")

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
                    with st.spinner("Verifying writers and their published work..."):
                        try:
                            result = research_journalists(angle, opportunity)
                            st.session_state.journalist_results[review_key] = result
                            for person in result.journalists:
                                upsert_journalist(
                                    person,
                                    related_opportunity_url=opportunity.article_url,
                                    qualification_status=None,
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
                    st.warning("No suitable journalist could be verified. Do not guess a contact.")
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
        for value in st.session_state.journalist_reviews.values()
        if value == "Qualified pitch target"
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


def _render_pr_outreach():
    st.caption("Write and review a personalized pitch. The app never sends it.")

    st.info(
        "Choose a qualified writer below, prepare a draft, edit it, and mark your own status. "
        "Nothing leaves this computer."
    )

    with st.expander("Your sender details (used in drafts)"):
        st.markdown(f"**{HARDCODED_SENDER_NAME}** · {HARDCODED_SENDER_ROLE}")
        st.caption("Hardcoded for this workspace.")

    targets = _qualified_journalist_targets()
    if not targets:
        st.warning("No qualified pitch targets yet. Qualify a writer in the Journalists step first.")
        if st.button("Go to journalists"):
            go(pr_step="Journalists")
        return

    for index, (opportunity, person, opportunity_row) in enumerate(targets):
        with st.container(border=True):
            st.markdown(f"#### {person.name}")
            st.caption(f"{person.publication} · {person.current_role}")
            st.markdown(f"**Opportunity:** {opportunity.article_title}")
            st.markdown(f"**Why this writer:** {person.why_relevant}")

            record = get_outreach_draft("journalist_pitch", opportunity.article_url, person.name)
            if record is None:
                _render_no_draft(
                    "Pitch",
                    "Prepare personalized pitch",
                    f"prepare_pitch_{index}",
                    lambda o=opportunity, p=person, r=opportunity_row: upsert_outreach_draft(
                        draft_journalist_pitch(
                            o,
                            p,
                            angle_context=r.get("selected_angle", ""),
                            sender_name=st.session_state.sender_name,
                            sender_role=st.session_state.sender_role,
                        ),
                        "journalist_pitch",
                        target_url=o.article_url,
                        related_url=p.relevant_article_url,
                        draft_status="Draft",
                    ),
                )
            else:
                _render_draft_editor(record, f"journalist_draft_{index}")

    st.divider()
    st.caption(
        "Tip: change the draft status to 'Approved for manual send' only after checking every link, "
        "name, and claim. Use 'Sent manually' after you send it yourself."
    )


def _render_digital_pr():
    step = _step_control(PR_STEPS, "pr_step")
    if step == "Article":
        _render_pr_article()
    elif step == "PR angles":
        _render_pr_angles()
    elif step == "Opportunities":
        _render_pr_opportunities()
    elif step == "Journalists":
        _render_pr_journalists()
    else:
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
                        "The app does not contact publishers or submit forms."
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
    st.caption("Write and review a request for an approved prospect. The app never sends or submits it.")

    st.info(
        "Only approved prospects with saved contact research appear here. Nothing leaves this computer."
    )

    with st.expander("Your sender details (used in drafts)"):
        st.markdown(f"**{HARDCODED_SENDER_NAME}** · {HARDCODED_SENDER_ROLE}")
        st.caption("Hardcoded for this workspace.")

    targets = _listicle_outreach_targets()
    if not targets:
        st.warning("No approved prospects with contact research yet.")
        if st.button("Go to prospects"):
            go(listicle_step="Prospects")
        return

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
        "Tip: change the draft status to 'Approved for manual send' only after checking the page, "
        "the policy, and every claim. Use 'Sent manually' after you send or submit it yourself."
    )


def _render_listicles():
    step = _step_control(LISTICLE_STEPS, "listicle_step")
    if step == "Search":
        _render_listicle_search()
    elif step == "Prospects":
        _render_listicle_prospects()
    else:
        _render_listicle_outreach()


# =========================================================
# WORKSPACE
# =========================================================

def _render_workspace():
    mode = st.session_state.workflow_mode
    if mode is None:
        _page_header(
            "Workspace",
            "Research, review, prepare.",
            f"Digital PR and listicle prospecting for {BRAND_NAME}. You approve every decision and every send.",
        )
        _render_workspace_metrics()
        st.subheader("What are you working on?")
        listicle_count = len(list_listicle_prospects())
        opportunity_count = len(list_pr_opportunities())
        draft_count = len(list_outreach_drafts())

        with st.container(border=True, key="workflow-pr"):
            st.markdown("### Digital PR")
            st.caption("Article → PR angles → Opportunities → Journalists → Outreach")
            st.write("Turn a published article into PR angles, editorial opportunities, and journalist research.")
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
                        go(mode="digital_pr", pr_step="Article")
            else:
                if st.button("Start Digital PR →", type="primary", width="stretch"):
                    go(mode="digital_pr", pr_step="Article")

        with st.container(border=True, key="workflow-listicles"):
            st.markdown("### Listicle inclusion")
            st.caption("Search → Prospects → Outreach")
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
                        go(mode="listicles", listicle_step="Search")
            else:
                if st.button("Start listicle research →", type="primary", width="stretch"):
                    go(mode="listicles", listicle_step="Search")
        return

    header_col, action_col = st.columns(
        [5, 1.8], gap="small", vertical_alignment="center"
    )
    with header_col:
        label = "Digital PR" if mode == "digital_pr" else "Listicle inclusion"
        _page_header("Workspace", label, "You approve every decision and every send.")
    with action_col:
        if st.button("Switch workflow", key="switch-workflow", width="content"):
            st.session_state.workflow_mode = None
            st.rerun()

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
        "Prospects, PR opportunities, journalists, drafts, and placements — all stored locally.",
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

    tab_listicles, tab_pr, tab_journalists, tab_drafts = st.tabs(
        ["Listicle prospects", "PR opportunities", "Journalists", "Outreach drafts"]
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
                    "Publication": row.get("publication", ""),
                    "Subject": row.get("subject", ""),
                    "Status": row.get("draft_status", "Draft"),
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
                    st.caption(f"{row.get('draft_type')} · {row.get('draft_status')}")
                    st.markdown(f"**Subject:** {row.get('subject', '')}")
                    st.text(row.get("body", ""))
                    st.divider()

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
    return Path(__file__).resolve().parent / "data" / "brand_config.json"


def _render_settings():
    _page_header(
        "Settings",
        "Make it yours.",
        f"Brand profile for {BRAND_NAME}, plus model cost, sender details, and local storage.",
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
        - The app never sends email, submits publisher forms, or contacts anyone.
        - Research, contacts, and policy findings must be checked by a human.
        - Approval only prepares the next step; it does not send outreach.
        - Publisher policy findings are recommendations, not permission or a guarantee.
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

    st.divider()
    st.caption(f"Model: {MODEL}")
    st.caption(f"Search context: {SEARCH_CONTEXT_SIZE}")
    st.caption("Local only · no automatic outreach")


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


save_app_snapshot({
    key: _snapshot_value(st.session_state.get(key))
    for key in _PERSISTED_STATE_KEYS
})
