import hashlib
import os

import streamlit as st

# Hosting platforms (e.g. Streamlit Community Cloud) inject configuration via
# secrets rather than environment variables. Mirror them into os.environ before
# importing agent.py, which reads them at import time.
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
    MODEL,
    AssetAnalysis,
    PRResearchResults,
    JournalistResearchResults,
    ListicleResearchResults,
    ListicleContactResearchResults,
    PublisherPolicyAssessment,
    analyze_article,
    research_opportunities,
    research_journalists,
    research_listicles,
    research_listicle_contact,
    research_publisher_policy,
)
from database import (
    init_db,
    load_app_snapshot,
    save_app_snapshot,
    get_listicle_prospect,
    upsert_listicle_prospect,
    list_listicle_prospects,
    get_pr_opportunity,
    upsert_pr_opportunity,
    list_pr_opportunities,
    get_journalist_record,
    upsert_journalist,
    list_journalists,
    listicle_csv_bytes,
    opportunity_csv_bytes,
    journalist_csv_bytes,
    create_database_backup,
)


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title=f"{BRAND_NAME} PR Agent",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# SESSION STATE
# =========================================================

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
    st.session_state["_persistent_state_loaded"] = True


# =========================================================
# REVIEW STATUS HELPERS
# =========================================================

REVIEW_OPTIONS = [
    "Awaiting review",
    "Approve for journalist research",
    "Reject",
    "Needs more research",
]


def get_review_counts():
    """Count saved review decisions for the current research run."""
    results = st.session_state.opportunity_results
    if results is None:
        return {
            "total": 0,
            "awaiting": 0,
            "approved": 0,
            "rejected": 0,
            "more_research": 0,
        }

    run_id = st.session_state.research_run_id
    reviews = st.session_state.opportunity_reviews
    statuses = [
        reviews.get(f"{run_id}:{i}", "Awaiting review")
        for i, _ in enumerate(results.opportunities)
    ]

    return {
        "total": len(statuses),
        "awaiting": statuses.count("Awaiting review"),
        "approved": statuses.count("Approve for journalist research"),
        "rejected": statuses.count("Reject"),
        "more_research": statuses.count("Needs more research"),
    }


# =========================================================
# CUSTOM STYLING
# =========================================================

st.markdown(
    """
    <style>
    .stApp {
        background-color: #f7f7fb;
    }

    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e8e8ef;
    }

    h1, h2, h3 {
        color: #27243a;
    }

    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
    }

    .stButton > button[kind="primary"] {
        background-color: #ff4f5e;
        color: white;
        border: none;
    }

    .stButton > button[kind="primary"]:hover {
        background-color: #ed3f4e;
        color: white;
    }

    .block-container {
        padding-top: 2.2rem;
        padding-bottom: 3rem;
    }

    .sidebar-brand {
        font-size: 21px;
        font-weight: 700;
        color: #27243a;
    }

    .sidebar-subtitle {
        color: #777487;
        font-size: 13px;
        margin-bottom: 25px;
    }

    .field-label {
        font-size: 11px;
        font-weight: 700;
        color: #777487;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.markdown(
        '<div class="sidebar-brand">Digital PR Agent</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sidebar-subtitle">Digital PR</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Cost-optimized model: {MODEL}")

    page = st.radio(
        "Navigation",
        [
            "PR Home",
            "Asset Analysis",
            "PR Action Plans",
            "PR Opportunities",
            "Listicle Opportunities",
            "Journalists",
            "Outreach",
            "Research Library",
        ],
        label_visibility="collapsed",
    )


# =========================================================
# PR HOME
# =========================================================

if page == "PR Home":
    st.title("Digital PR")
    st.caption("Turn existing content into actionable PR research.")
    st.divider()

    st.subheader("Analyze an article")
    st.write("Enter the URL of a published article.")

    article_url = st.text_input(
        "Article URL",
        value=st.session_state.article_url,
        placeholder="https://example.com/article",
    )

    if st.button("Analyze article", type="primary"):
        if not article_url:
            st.warning("Please enter an article URL.")
        elif not article_url.startswith("https://"):
            st.error("Please enter a valid HTTPS URL.")
        else:
            st.session_state.article_url = article_url
            with st.spinner("Analyzing the article..."):
                try:
                    analysis = analyze_article(article_url)
                    st.session_state.analysis = analysis
                    st.session_state.selected_angle_index = None
                    st.session_state.opportunity_results = None
                    st.session_state.opportunity_reviews = {}
                    st.session_state.journalist_results = {}
                    st.session_state.journalist_reviews = {}
                    st.success("Analysis complete. Open PR Action Plans to continue.")
                except Exception as e:
                    st.error("Article analysis failed.")
                    st.exception(e)

    st.divider()
    st.subheader("PR Agent Overview")
    st.caption("A quick view of your current PR research and review queue.")

    counts = get_review_counts()
    analysis = st.session_state.analysis

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Current asset", "1" if analysis else "0")
    c2.metric("PR action plans", len(analysis.pr_angles) if analysis else 0)
    c3.metric("Awaiting review", counts["awaiting"])
    c4.metric("Approved for journalist research", counts["approved"])
    listicle_results = st.session_state.listicle_results
    c5.metric("Listicle candidates", len(listicle_results.opportunities) if listicle_results else 0)

    if counts["total"]:
        st.caption(
            f"Candidates: {counts['total']}  |  "
            f"Needs more research: {counts['more_research']}  |  "
            f"Rejected: {counts['rejected']}"
        )

    if analysis:
        st.divider()
        st.subheader("Current asset")
        st.write(analysis.article_title)


# =========================================================
# ASSET ANALYSIS
# =========================================================

elif page == "Asset Analysis":
    st.title("Asset Analysis")
    st.caption("Review the article's content, evidence, and PR value.")

    analysis = st.session_state.analysis
    if not analysis:
        st.info("Analyze an article from PR Home first.")
    else:
        st.subheader(analysis.article_title)
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Main topic**")
            st.write(analysis.main_topic)

        with col2:
            st.markdown("**Target audience**")
            for audience in analysis.target_audience:
                st.write(f"• {audience}")

        st.divider()
        st.subheader("Key claims")
        for claim in analysis.key_claims:
            st.write(f"• {claim}")

        st.divider()
        st.subheader("Statistics and sources")
        for stat in analysis.statistics:
            with st.expander(stat.statistic):
                st.markdown("**Source**")
                st.write(stat.source)
                st.markdown("**Data provenance**")
                st.write(stat.data_provenance)
                st.markdown("**PR relevance**")
                st.write(stat.pr_relevance)

        st.divider()
        st.subheader("Useful assets")
        for asset in analysis.useful_assets:
            st.write(f"• {asset}")

        st.divider()
        st.subheader("Overall PR assessment")
        st.info(analysis.assessment)


# =========================================================
# PR ACTION PLANS
# =========================================================

elif page == "PR Action Plans":
    st.title("PR Action Plans")
    st.caption("Choose a story angle and research real editorial opportunities.")

    analysis = st.session_state.analysis
    if not analysis:
        st.info("Analyze an article from PR Home first.")
    else:
        st.write(f"**Source asset:** {analysis.article_title}")
        st.divider()

        for i, angle in enumerate(analysis.pr_angles):
            with st.container(border=True):
                st.subheader(f"{i + 1}. {angle.angle}")

                col1, col2 = st.columns(2)
                with col1:
                    st.caption("STORY TYPE")
                    st.write(angle.story_type)
                with col2:
                    st.caption("RECOMMENDED TACTIC")
                    st.write(angle.recommended_tactic)

                st.divider()
                st.caption("STORY HYPOTHESIS")
                st.write(angle.story_hypothesis)
                st.caption("WHY A PUBLICATION MIGHT CARE")
                st.write(angle.why_useful)
                st.caption(f"{BRAND_NAME.upper()}'S CONTRIBUTION")
                st.write(angle.brand_contribution)

                col1, col2 = st.columns(2)
                with col1:
                    st.caption("TARGET PUBLICATION TYPES")
                    for item in angle.target_publication_types:
                        st.write(f"• {item}")
                with col2:
                    st.caption("JOURNALIST BEATS TO RESEARCH")
                    for item in angle.target_journalist_beats:
                        st.write(f"• {item}")

                st.caption("RELEVANT ASSET")
                st.write(angle.relevant_asset)
                st.caption("SUPPORTING EVIDENCE")
                st.write(angle.evidence)
                st.warning(f"NEXT ACTION: {angle.next_action}")
                st.caption(f"Confidence: {angle.confidence}")

                if st.button(
                    "Research this angle →",
                    key=f"research_angle_{i}",
                    type="primary",
                ):
                    st.session_state.selected_angle_index = i
                    st.session_state.opportunity_results = None
                    st.session_state.opportunity_reviews = {}

                    with st.spinner("Searching the web and evaluating candidate articles..."):
                        try:
                            results = research_opportunities(angle)
                            st.session_state.opportunity_results = results
                            st.session_state.research_run_id += 1
                            st.session_state.opportunity_reviews = {}
                            for researched_opportunity in results.opportunities:
                                upsert_pr_opportunity(
                                    researched_opportunity,
                                    selected_angle=results.selected_angle,
                                    review_status=None,
                                )
                            st.success(
                                "Research finished. Open PR Opportunities to review the candidates."
                            )
                        except Exception as e:
                            st.error("PR opportunity research failed.")
                            st.exception(e)


# =========================================================
# PR OPPORTUNITIES WITH HUMAN REVIEW
# =========================================================

elif page == "PR Opportunities":
    st.title("PR Opportunities")
    st.caption("Review candidate articles before passing any to journalist research.")

    results = st.session_state.opportunity_results
    if not results:
        st.info(
            "No research results yet. Open PR Action Plans and click "
            "'Research this angle' on a story you want to investigate."
        )
    else:
        st.subheader("Research summary")
        st.write(results.research_summary)
        st.markdown("**Selected PR angle**")
        st.write(results.selected_angle)
        st.info(
            "Approval here only moves a candidate to the journalist-research queue. "
            "It does not approve or send outreach."
        )

        counts = get_review_counts()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total candidates", counts["total"])
        c2.metric("Awaiting review", counts["awaiting"])
        c3.metric("Approved", counts["approved"])
        c4.metric("Rejected", counts["rejected"])
        st.caption(f"Needs more research: {counts['more_research']}")
        st.divider()

        run_id = st.session_state.research_run_id
        reviews = st.session_state.opportunity_reviews

        for i, opportunity in enumerate(results.opportunities):
            review_key = f"{run_id}:{i}"
            widget_key = f"review_decision_{run_id}_{i}"
            saved_opportunity = get_pr_opportunity(
                opportunity.article_url, opportunity.article_title, opportunity.publication
            )
            if review_key not in reviews and saved_opportunity:
                stored_status = saved_opportunity.get("review_status")
                if stored_status in REVIEW_OPTIONS:
                    reviews[review_key] = stored_status
            current_status = reviews.get(review_key, "Awaiting review")

            with st.container(border=True):
                st.subheader(f"{i + 1}. {opportunity.article_title}")
                st.markdown(f"**Publication:** {opportunity.publication}")

                col1, col2 = st.columns(2)
                with col1:
                    st.caption("PUBLISHED DATE")
                    st.write(opportunity.published_date)
                with col2:
                    st.caption("OPPORTUNITY TYPE")
                    st.write(opportunity.opportunity_type)

                st.divider()
                st.caption("TOPIC")
                st.write(opportunity.topic)
                st.caption("WHY IT MATCHES THE PR ANGLE")
                st.write(opportunity.why_relevant)
                st.caption(f"WHAT {BRAND_NAME.upper()} COULD CONTRIBUTE")
                st.write(opportunity.brand_contribution)
                st.caption("COMPETITOR PRESENCE")
                st.write(opportunity.competitor_mention)

                col1, col2 = st.columns(2)
                with col1:
                    st.caption("TOPICAL RELEVANCE")
                    st.write(opportunity.topical_relevance)
                with col2:
                    st.caption("EDITORIAL FIT")
                    st.write(opportunity.editorial_fit)

                st.caption("RECOMMENDED ACTION")
                st.write(opportunity.recommended_action)
                st.caption("EVIDENCE")
                st.write(opportunity.evidence)
                st.caption("CONFIDENCE")
                st.write(opportunity.confidence)

                url = opportunity.article_url.strip()
                if url.startswith("https://"):
                    st.link_button("Open candidate article", url)
                else:
                    st.warning(
                        "The agent did not return a usable HTTPS article URL. "
                        "Verify the source before using this candidate."
                    )

                st.divider()
                st.markdown("**Your review decision**")
                st.caption(
                    "Approve only if the article is real, relevant, and offers "
                    "a credible editorial opening."
                )

                st.selectbox(
                    "Status",
                    options=REVIEW_OPTIONS,
                    index=REVIEW_OPTIONS.index(current_status),
                    key=widget_key,
                    label_visibility="collapsed",
                )

                if st.button("Save review decision", key=f"save_review_{run_id}_{i}"):
                    chosen_status = st.session_state[widget_key]
                    st.session_state.opportunity_reviews[review_key] = chosen_status
                    upsert_pr_opportunity(
                        opportunity,
                        selected_angle=results.selected_angle,
                        review_status=chosen_status,
                    )
                    st.success(f"Saved: {chosen_status}")

                upsert_pr_opportunity(
                    opportunity,
                    selected_angle=results.selected_angle,
                    review_status=st.session_state.opportunity_reviews.get(review_key, current_status),
                )

        st.divider()
        st.subheader("Review summary")
        updated_counts = get_review_counts()
        st.write(
            f"Approved for journalist research: {updated_counts['approved']}  |  "
            f"Needs more research: {updated_counts['more_research']}  |  "
            f"Rejected: {updated_counts['rejected']}  |  "
            f"Awaiting review: {updated_counts['awaiting']}"
        )
        st.caption(
            "Research results and saved review decisions are stored in the local database on this computer. "
            "No outreach is sent automatically."
        )




# =========================================================
# LISTICLE OPPORTUNITIES
# =========================================================

elif page == "Listicle Opportunities":
    st.title("Listicle Opportunities")
    st.caption(
        "Find existing software roundups, best-tool lists, alternatives pages, comparisons, and directories where your brand may fit."
    )

    st.info(
        "This is a separate acquisition workflow from journalist-led Digital PR. "
        "Editorial, affiliate, sponsored, and directory opportunities are labelled separately. "
        "The agent researches and prepares recommendations; it does not contact publishers."
    )

    with st.form("listicle_research_form"):
        st.subheader("Search for listicle prospects")

        search_theme = st.text_input(
            "Primary category or search theme",
            value="social media management tools",
            help="Example: best social media management tools for agencies",
        )

        related_queries = st.text_area(
            "Related categories or query variations (optional)",
            value=(
                "best social media scheduling tools; social media tools for agencies; "
                "Hootsuite alternatives; Sprout Social alternatives; social media analytics tools"
            ),
            help="Separate queries with semicolons. Add categories you want the agent to cover.",
        )

        form_col1, form_col2 = st.columns(2)
        with form_col1:
            target_audience = st.selectbox(
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
                index=0,
            )

        with form_col2:
            target_market = st.selectbox(
                "Target market",
                [
                    "Global English-language",
                    "United States",
                    "United Kingdom",
                    "Canada",
                    "Australia",
                    "Other / specify in related queries",
                ],
                index=0,
            )

        competitor_text = st.text_input(
            "Competitors to check",
            value="Hootsuite, Sprout Social, Buffer, Later, SocialBee",
            help="Comma-separated names. The agent only reports competitors it verifies on a page.",
        )

        max_results = st.select_slider(
            "Maximum candidate pages to request",
            options=[10, 15, 20],
            value=15,
            help="The agent may return fewer if it cannot verify enough relevant pages.",
        )

        submitted = st.form_submit_button(
            "Find listicle opportunities",
            type="primary",
        )

    if submitted:
        if not search_theme.strip():
            st.warning("Enter a category or search theme first.")
        else:
            competitors = [
                item.strip()
                for item in competitor_text.split(",")
                if item.strip()
            ]
            st.session_state.listicle_results = None
            st.session_state.listicle_reviews = {}
            st.session_state.listicle_contact_results = {}
            st.session_state.listicle_policy_results = {}
            st.session_state.listicle_placement_progress = {}
            st.session_state.listicle_run_id += 1

            with st.spinner(
                "Searching the web for listicles and checking inclusion fit..."
            ):
                try:
                    listicle_results = research_listicles(
                        search_theme=search_theme,
                        related_queries=related_queries,
                        target_audience=target_audience,
                        target_market=target_market,
                        competitors=competitors,
                        max_results=max_results,
                    )
                    st.session_state.listicle_results = listicle_results
                    st.success(
                        f"Listicle research finished. Candidate pages returned: {len(listicle_results.opportunities)}."
                    )
                except Exception as e:
                    st.error("Listicle research failed.")
                    st.exception(e)

    results = st.session_state.listicle_results
    if results is not None:
        st.divider()
        st.subheader("Research summary")
        st.write(results.research_summary)
        st.caption(f"Search theme: {results.search_theme}")

        statuses = [
            st.session_state.listicle_reviews.get(
                f"{st.session_state.listicle_run_id}:{i}",
                "Awaiting review",
            )
            for i, _ in enumerate(results.opportunities)
        ]
        total = len(statuses)
        awaiting = statuses.count("Awaiting review")
        approved = statuses.count("Approve to pursue")
        rejected = statuses.count("Reject")
        more_research = statuses.count("Needs more research")
        already_listed = statuses.count("Already listed")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Candidates", total)
        c2.metric("Awaiting review", awaiting)
        c3.metric("Approved to pursue", approved)
        c4.metric("Needs research", more_research)
        c5.metric("Already listed", already_listed)
        st.caption(f"Rejected: {rejected}")

        if not results.opportunities:
            st.warning(
                "No suitable listicle pages were returned. Try a different category or add more query variations."
            )

        listicle_status_options = [
            "Awaiting review",
            "Approve to pursue",
            "Needs more research",
            "Already listed",
            "Reject",
        ]
        run_id = st.session_state.listicle_run_id

        placement_progress_options = [
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

        for i, item in enumerate(results.opportunities):
            review_key = f"{run_id}:{i}"
            widget_key = f"listicle_review_decision_{run_id}_{i}"
            contact_key = f"{run_id}:{i}"
            policy_key = f"{run_id}:{i}"
            placement_widget_key = f"listicle_placement_progress_{run_id}_{i}"
            saved_record = get_listicle_prospect(
                item.listicle_url, item.listicle_title, item.publication
            )

            # Recover prior decisions and research for this URL from the local database.
            if saved_record:
                stored_review = saved_record.get("review_status")
                if review_key not in st.session_state.listicle_reviews and stored_review in listicle_status_options:
                    st.session_state.listicle_reviews[review_key] = stored_review
                if review_key not in st.session_state.listicle_placement_progress:
                    progress = saved_record.get("placement_progress") or "Not contacted"
                    if progress in placement_progress_options:
                        st.session_state.listicle_placement_progress[review_key] = progress
                contact_data = saved_record.get("contact_data")
                if contact_key not in st.session_state.listicle_contact_results and contact_data:
                    try:
                        st.session_state.listicle_contact_results[contact_key] = ListicleContactResearchResults.model_validate(contact_data)
                    except Exception:
                        pass
                policy_data = saved_record.get("policy_data")
                if policy_key not in st.session_state.listicle_policy_results and policy_data:
                    try:
                        st.session_state.listicle_policy_results[policy_key] = PublisherPolicyAssessment.model_validate(policy_data)
                    except Exception:
                        pass

            saved_status = st.session_state.listicle_reviews.get(
                review_key, "Awaiting review"
            )

            with st.container(border=True):
                st.subheader(f"{i + 1}. {item.listicle_title}")
                st.write(f"**Publication:** {item.publication}")

                c1, c2, c3 = st.columns(3)
                c1.caption("PUBLISHED / UPDATED")
                c1.write(item.published_or_updated)
                c2.caption("PLACEMENT TYPE")
                c2.write(item.placement_type)
                c3.caption(f"CURRENTLY LISTS {BRAND_NAME.upper()}?")
                c3.write(item.brand_currently_listed)

                st.divider()
                st.caption("CATEGORY")
                st.write(item.listicle_category)
                st.caption("TARGET AUDIENCE")
                st.write(item.target_audience)
                st.caption(f"WHY {BRAND_NAME.upper()} MAY FIT")
                st.write(item.brand_fit)
                st.caption("INCLUSION GAP")
                st.write(item.inclusion_gap)

                st.caption("COMPETITORS VERIFIED ON THE PAGE")
                st.write(", ".join(item.competitors_listed) if item.competitors_listed else "None verified")

                st.caption("CONTACT ROUTE")
                st.write(item.contact_route)
                st.caption("RECOMMENDED ACTION")
                st.write(item.recommended_action)
                st.caption("EVIDENCE")
                st.write(item.evidence)
                st.caption("CONFIDENCE")
                st.write(item.confidence)

                page_url = item.listicle_url.strip()
                if page_url.startswith("https://"):
                    st.link_button(
                        "Open listicle",
                        page_url,
                        key=f"open_listicle_{run_id}_{i}",
                    )
                else:
                    st.warning(
                        "No verifiable HTTPS URL was returned. Check the page manually before pursuing it."
                    )

                # Deep contact discovery is run only for prospects the user chooses.
                # This avoids spending extra search calls on every low-priority candidate.
                if st.button(
                    "Find publisher contact",
                    key=f"find_listicle_contact_{run_id}_{i}",
                ):
                    with st.spinner(
                        "Checking the author, editorial team, and official contact routes..."
                    ):
                        try:
                            found_contacts = research_listicle_contact(item)
                            st.session_state.listicle_contact_results[contact_key] = found_contacts
                            upsert_listicle_prospect(
                                item,
                                search_theme=results.search_theme,
                                review_status=st.session_state.listicle_reviews.get(review_key, saved_status),
                                contacts=found_contacts,
                                policy=st.session_state.listicle_policy_results.get(policy_key),
                                placement_progress=st.session_state.listicle_placement_progress.get(review_key),
                            )
                            st.success("Contact research finished. Review the verified routes below.")
                        except Exception as e:
                            st.error("Publisher contact research failed.")
                            st.exception(e)

                contact_results = st.session_state.listicle_contact_results.get(contact_key)
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
                            st.write(f"**Confidence:** {contact.confidence}")

                            profile_url = contact.author_profile_url.strip()
                            if profile_url.startswith("https://"):
                                st.link_button(
                                    "Open author profile",
                                    profile_url,
                                    key=f"listicle_author_profile_{run_id}_{i}_{contact_index}",
                                )

                            contact_url = contact.contact_page_url.strip()
                            if contact_url.startswith("https://"):
                                st.link_button(
                                    "Open contact page",
                                    contact_url,
                                    key=f"listicle_contact_page_{run_id}_{i}_{contact_index}",
                                )

                            source_url = contact.source_url.strip()
                            if source_url.startswith("https://"):
                                st.link_button(
                                    "Open verification source",
                                    source_url,
                                    key=f"listicle_contact_source_{run_id}_{i}_{contact_index}",
                                )

                    st.caption(
                        "Contact details are research candidates. Verify the route before use. "
                        "No emails or forms are sent by this app."
                    )

                # Publisher-policy research is on demand to control API/search costs.
                if st.button(
                    "Check publisher policy",
                    key=f"check_publisher_policy_{run_id}_{i}",
                ):
                    with st.spinner(
                        "Checking official publisher rules, submission routes, and placement policies..."
                    ):
                        try:
                            policy_result = research_publisher_policy(item)
                            st.session_state.listicle_policy_results[policy_key] = policy_result
                            upsert_listicle_prospect(
                                item,
                                search_theme=results.search_theme,
                                review_status=st.session_state.listicle_reviews.get(review_key, saved_status),
                                contacts=st.session_state.listicle_contact_results.get(contact_key),
                                policy=policy_result,
                                placement_progress=st.session_state.listicle_placement_progress.get(review_key),
                            )
                            st.success("Publisher policy check finished. Review the evidence below.")
                        except Exception as e:
                            st.error("Publisher policy research failed.")
                            st.exception(e)

                policy_result = st.session_state.listicle_policy_results.get(policy_key)
                if policy_result is not None:
                    st.divider()
                    st.markdown("**Publisher policy assessment**")

                    policy_status = policy_result.recommended_disposition
                    if policy_status == "Do not pursue":
                        st.error(f"RECOMMENDATION: {policy_status}")
                    elif policy_status == "Needs verification":
                        st.warning(f"RECOMMENDATION: {policy_status}")
                    elif policy_status == "Paid option to review":
                        st.warning(f"RECOMMENDATION: {policy_status}")
                    elif policy_status == "Already listed":
                        st.info(f"RECOMMENDATION: {policy_status}")
                    else:
                        st.success(f"RECOMMENDATION: {policy_status}")

                    st.caption("POLICY STATUS")
                    st.write(policy_result.policy_status)
                    st.caption("POLICY SUMMARY")
                    st.write(policy_result.policy_summary)
                    st.caption("EVIDENCE")
                    st.write(policy_result.policy_evidence)
                    st.caption("RECOMMENDED ROUTE")
                    st.write(policy_result.recommended_route)
                    st.caption("WHY THIS DISPOSITION")
                    st.write(policy_result.disposition_reason)
                    st.caption("CONFIDENCE")
                    st.write(policy_result.confidence)

                    policy_source = policy_result.policy_source_url.strip()
                    if policy_source.startswith("https://"):
                        st.link_button(
                            "Open publisher policy source",
                            policy_source,
                            key=f"policy_source_{run_id}_{i}",
                        )
                    else:
                        st.caption("No directly verifiable policy source URL was returned.")

                    st.caption(
                        "This is a recommendation based on accessible policy evidence, not a permission or placement guarantee. "
                        "Verify the source before acting. The app does not contact publishers or submit forms."
                    )

                if widget_key not in st.session_state:
                    st.session_state[widget_key] = saved_status

                st.divider()
                st.markdown("**Your review decision**")
                st.caption(
                    "Approve only after checking the page, product fit, placement model, and contact route. "
                    "Approval queues the prospect for follow-up preparation; it does not contact the publisher."
                )
                st.selectbox(
                    "Listicle status",
                    options=listicle_status_options,
                    key=widget_key,
                    label_visibility="collapsed",
                )

                if st.button(
                    "Save listicle decision",
                    key=f"save_listicle_review_{run_id}_{i}",
                ):
                    chosen_status = st.session_state[widget_key]
                    st.session_state.listicle_reviews[review_key] = chosen_status
                    upsert_listicle_prospect(
                        item,
                        search_theme=results.search_theme,
                        review_status=chosen_status,
                        contacts=contact_results,
                        policy=policy_result,
                        placement_progress=st.session_state.listicle_placement_progress.get(review_key),
                    )
                    st.success(f"Saved: {chosen_status}")

                st.divider()
                st.markdown("**Placement progress**")
                saved_progress = st.session_state.listicle_placement_progress.get(
                    review_key,
                    (saved_record or {}).get("placement_progress", "Not contacted"),
                )
                if placement_widget_key not in st.session_state:
                    st.session_state[placement_widget_key] = (
                        saved_progress if saved_progress in placement_progress_options else "Not contacted"
                    )
                st.selectbox(
                    "Placement progress",
                    options=placement_progress_options,
                    key=placement_widget_key,
                    label_visibility="collapsed",
                )
                if st.button(
                    "Save placement progress",
                    key=f"save_listicle_progress_{run_id}_{i}",
                ):
                    st.session_state.listicle_placement_progress[review_key] = st.session_state[placement_widget_key]
                    upsert_listicle_prospect(
                        item,
                        search_theme=results.search_theme,
                        review_status=st.session_state.listicle_reviews.get(review_key, saved_status),
                        contacts=contact_results,
                        policy=policy_result,
                        placement_progress=st.session_state[placement_widget_key],
                    )
                    st.success(f"Saved placement progress: {st.session_state[placement_widget_key]}")

                # Persist the prospect, enrichment, and any saved decisions on every app run.
                # A user's unsaved widget changes are not written as decisions.
                upsert_listicle_prospect(
                    item,
                    search_theme=results.search_theme,
                    review_status=st.session_state.listicle_reviews.get(review_key, saved_status),
                    contacts=contact_results,
                    policy=policy_result,
                    placement_progress=st.session_state.listicle_placement_progress.get(
                        review_key,
                        (saved_record or {}).get("placement_progress", "Not contacted"),
                    ),
                )

        st.caption(
            "Research, contact and policy findings, saved decisions, and placement progress are stored in a local database on this computer. "
            "Use Research Library to review or export saved records. The app never contacts publishers automatically."
        )


# =========================================================
# JOURNALISTS
# =========================================================

elif page == "Journalists":
    st.title("Journalists")
    st.caption(
        "Research writers with verified published work related to approved PR opportunities."
    )

    results = st.session_state.opportunity_results
    analysis = st.session_state.analysis
    reviews = st.session_state.opportunity_reviews
    run_id = st.session_state.research_run_id
    saved_journalist_results = st.session_state.journalist_results

    if not results or not analysis:
        st.info(
            "First analyze an article, research a PR angle, "
            "and review its candidate articles."
        )
    else:
        approved_items = []
        for i, opportunity in enumerate(results.opportunities):
            review_key = f"{run_id}:{i}"
            status = reviews.get(review_key, "Awaiting review")
            if status == "Approve for journalist research":
                approved_items.append((i, review_key, opportunity))

        if not approved_items:
            st.info(
                "No candidates are approved yet. Open PR Opportunities and "
                "save at least one candidate as 'Approve for journalist research'."
            )
        else:
            st.success(
                f"{len(approved_items)} approved candidate(s) are ready for journalist research."
            )
            st.caption(
                "Research identifies relevant writers and evidence of their coverage. "
                "It does not guess email addresses and never sends outreach."
            )

            angle_index = st.session_state.selected_angle_index
            if angle_index is None or not (0 <= angle_index < len(analysis.pr_angles)):
                st.error(
                    "The original PR angle could not be matched to this research run. "
                    "Return to PR Action Plans and research the angle again."
                )
            else:
                angle = analysis.pr_angles[angle_index]

                for i, review_key, opportunity in approved_items:
                    with st.container(border=True):
                        st.subheader(opportunity.article_title)
                        st.write(f"**Publication:** {opportunity.publication}")
                        st.caption(
                            f"Approved candidate · Published: {opportunity.published_date}"
                        )

                        if opportunity.article_url.strip().startswith("https://"):
                            st.link_button(
                                "Open approved article",
                                opportunity.article_url.strip(),
                            )

                        existing_result = saved_journalist_results.get(review_key)

                        if existing_result is None:
                            st.write(
                                "Find writers who have covered this topic and could reasonably use "
                                "the brand's contribution."
                            )
                            if st.button(
                                "Research journalists →",
                                key=f"research_journalists_{run_id}_{i}",
                                type="primary",
                            ):
                                with st.spinner(
                                    "Researching writers and verifying their published work..."
                                ):
                                    try:
                                        journalist_result = research_journalists(angle, opportunity)
                                        st.session_state.journalist_results[review_key] = journalist_result
                                        for researched_person in journalist_result.journalists:
                                            upsert_journalist(
                                                researched_person,
                                                related_opportunity_url=opportunity.article_url,
                                                qualification_status=None,
                                            )
                                        st.rerun()
                                    except Exception as e:
                                        st.error("Journalist research failed.")
                                        st.exception(e)
                        else:
                            st.markdown("**Research summary**")
                            st.write(existing_result.research_summary)

                            journalists = existing_result.journalists
                            if not journalists:
                                st.warning(
                                    "No suitable journalist could be verified for this opportunity. "
                                    "Do not guess a contact. Try another approved opportunity or review the evidence."
                                )
                            else:
                                st.write(
                                    f"**Journalist candidates found: {len(journalists)}**"
                                )
                                journalist_status_options = [
                                    "Needs review",
                                    "Relevant writer",
                                    "Qualified pitch target",
                                    "Do not pursue",
                                ]

                                for j, person in enumerate(journalists, start=1):
                                    person_index = j - 1
                                    qualification_key = f"{review_key}:{person_index}"
                                    status_widget_key = f"journalist_status_{run_id}_{i}_{person_index}"
                                    saved_journalist_record = get_journalist_record(
                                        person, opportunity.article_url
                                    )
                                    if qualification_key not in st.session_state.journalist_reviews and saved_journalist_record:
                                        stored_qualification = saved_journalist_record.get("qualification_status")
                                        if stored_qualification in [
                                            "Needs review", "Relevant writer", "Qualified pitch target", "Do not pursue"
                                        ]:
                                            st.session_state.journalist_reviews[qualification_key] = stored_qualification
                                    saved_review = st.session_state.journalist_reviews.get(
                                        qualification_key, "Needs review"
                                    )

                                    with st.container(border=True):
                                        st.markdown(f"### {j}. {person.name}")
                                        st.write(f"**Publication:** {person.publication}")
                                        st.write(f"**Current role:** {person.current_role}")
                                        st.write(f"**Topic covered:** {person.topic_covered}")
                                        st.write(f"**Relevant article:** {person.relevant_article_title}")
                                        st.write(f"**Article date:** {person.article_date}")
                                        st.write(f"**Why relevant:** {person.why_relevant}")
                                        st.write(f"**Suggested pitch angle:** {person.suggested_pitch_angle}")
                                        st.write(f"**Evidence:** {person.evidence}")
                                        st.caption(f"Research confidence: {person.confidence}")

                                        byline_url = person.relevant_article_url.strip()
                                        profile_url = person.author_profile_or_contact_page.strip()
                                        if byline_url.startswith("https://"):
                                            st.link_button(
                                                "Open relevant article",
                                                byline_url,
                                                key=f"journalist_article_{run_id}_{i}_{j}",
                                            )
                                        if profile_url.startswith("https://"):
                                            st.link_button(
                                                "Open author profile / contact page",
                                                profile_url,
                                                key=f"journalist_profile_{run_id}_{i}_{j}",
                                            )

                                        st.divider()
                                        st.markdown("**Your journalist qualification**")
                                        st.caption(
                                            "A relevant writer has covered the topic. A qualified pitch target also has "
                                            "a credible reason to receive this specific story. Qualification only permits "
                                            "pitch preparation; it does not approve sending an email."
                                        )

                                        if status_widget_key not in st.session_state:
                                            st.session_state[status_widget_key] = saved_review

                                        st.selectbox(
                                            "Journalist status",
                                            options=journalist_status_options,
                                            key=status_widget_key,
                                            label_visibility="collapsed",
                                        )

                                        if st.button(
                                            "Save qualification",
                                            key=f"save_journalist_status_{run_id}_{i}_{person_index}",
                                        ):
                                            chosen_status = st.session_state[status_widget_key]
                                            st.session_state.journalist_reviews[qualification_key] = chosen_status
                                            upsert_journalist(
                                                person,
                                                related_opportunity_url=opportunity.article_url,
                                                qualification_status=chosen_status,
                                            )
                                            st.success(f"Saved status: {chosen_status}")

                                        upsert_journalist(
                                            person,
                                            related_opportunity_url=opportunity.article_url,
                                            qualification_status=st.session_state.journalist_reviews.get(qualification_key, saved_review),
                                        )

                            if st.button(
                                "Research again",
                                key=f"research_journalists_again_{run_id}_{i}",
                            ):
                                st.session_state.journalist_results.pop(review_key, None)
                                for person_index in range(len(existing_result.journalists)):
                                    qualification_key = f"{review_key}:{person_index}"
                                    status_widget_key = f"journalist_status_{run_id}_{i}_{person_index}"
                                    st.session_state.journalist_reviews.pop(qualification_key, None)
                                    st.session_state.pop(status_widget_key, None)
                                st.rerun()

                        st.divider()

            st.caption(
                "Journalist research and qualification decisions are saved to the local database. "
                "This page never sends outreach."
            )


# =========================================================
# RESEARCH LIBRARY: PERMANENT LOCAL STORAGE
# =========================================================

elif page == "Research Library":
    st.title("Research Library")
    st.caption("Your saved PR research, listicle prospects, contacts, policy checks, and placement progress.")
    st.info(
        "Records are saved locally on this computer in a SQLite database. They remain available after closing and reopening the app. "
        "They are not automatically synced to other devices."
    )

    saved_listicles = list_listicle_prospects()
    saved_opportunities = list_pr_opportunities()
    saved_journalists = list_journalists()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Saved listicle prospects", len(saved_listicles))
    c2.metric("Saved PR opportunities", len(saved_opportunities))
    c3.metric("Saved journalist records", len(saved_journalists))
    c4.metric(
        "Live placements",
        sum(1 for record in saved_listicles if record.get("placement_progress") == "Live placement verified"),
    )

    tab_listicles, tab_pr, tab_journalists = st.tabs(
        ["Listicle prospects", "PR opportunities", "Journalists"]
    )

    with tab_listicles:
        st.subheader("Saved listicle prospects")
        if not saved_listicles:
            st.info("No listicle prospects saved yet. Run a search in Listicle Opportunities.")
        else:
            table_rows = []
            for record in saved_listicles:
                table_rows.append({
                    "Publication": record.get("publication", ""),
                    "Listicle": record.get("title", ""),
                    "URL": record.get("url", ""),
                    "Category searched": record.get("search_theme", ""),
                    "Placement type": record.get("placement_type", "Unclear"),
                    "Review decision": record.get("review_status", "Awaiting review"),
                    "Placement progress": record.get("placement_progress", "Not contacted"),
                    "Contact researched": "Yes" if record.get("contact_data") else "No",
                    "Policy checked": "Yes" if record.get("policy_data") else "No",
                    "Last updated": record.get("updated_at", ""),
                })
            st.dataframe(table_rows, use_container_width=True, hide_index=True, column_config={
                "URL": st.column_config.LinkColumn("URL", display_text="Open page")
            })
            st.download_button(
                "Export listicle prospects as CSV",
                data=listicle_csv_bytes(),
                file_name="listicle_prospects.csv",
                mime="text/csv",
            )

            st.markdown("**Saved contact and policy details**")
            for record in saved_listicles:
                with st.expander(f"{record.get('publication', 'Unknown')} · {record.get('title', 'Untitled')}"):
                    st.write(f"**URL:** {record.get('url') or 'Unknown'}")
                    st.write(f"**Review decision:** {record.get('review_status')}")
                    st.write(f"**Placement progress:** {record.get('placement_progress')}")
                    contacts = record.get("contact_data")
                    if contacts:
                        st.markdown("**Publisher contact research**")
                        st.write(contacts.get("research_summary", ""))
                        for contact in contacts.get("contacts", []):
                            st.write(f"**{contact.get('contact_name', 'Contact')}** · {contact.get('current_role', 'Unknown')}")
                            st.write(f"Email: {contact.get('professional_email', 'Not publicly found')}")
                            st.write(f"Method: {contact.get('contact_method', 'Unknown')}")
                            st.write(f"Evidence: {contact.get('evidence', 'No evidence saved')}")
                            contact_url = contact.get("contact_page_url", "")
                            if isinstance(contact_url, str) and contact_url.startswith("https://"):
                                st.link_button("Open saved contact page", contact_url, key="library_contact_" + hashlib.sha256((str(record.get('prospect_key')) + contact_url).encode()).hexdigest()[:12])
                    policy = record.get("policy_data")
                    if policy:
                        st.markdown("**Publisher policy assessment**")
                        st.write(f"Recommendation: {policy.get('recommended_disposition', 'Unknown')}")
                        st.write(policy.get("policy_summary", ""))
                        st.write(f"Evidence: {policy.get('policy_evidence', '')}")
                        policy_url = policy.get("policy_source_url", "")
                        if isinstance(policy_url, str) and policy_url.startswith("https://"):
                            st.link_button("Open saved policy source", policy_url, key="library_policy_" + hashlib.sha256((str(record.get('prospect_key')) + policy_url).encode()).hexdigest()[:12])

    with tab_pr:
        st.subheader("Saved PR opportunities")
        if not saved_opportunities:
            st.info("No PR opportunities saved yet. Research an angle from PR Action Plans.")
        else:
            table_rows = [{
                "Publication": r.get("publication", ""),
                "Article": r.get("title", ""),
                "URL": r.get("url", ""),
                "PR angle": r.get("selected_angle", ""),
                "Review decision": r.get("review_status", "Awaiting review"),
                "Updated": r.get("updated_at", ""),
            } for r in saved_opportunities]
            st.dataframe(table_rows, use_container_width=True, hide_index=True, column_config={
                "URL": st.column_config.LinkColumn("URL", display_text="Open article")
            })
            st.download_button(
                "Export PR opportunities as CSV",
                data=opportunity_csv_bytes(),
                file_name="pr_opportunities.csv",
                mime="text/csv",
            )

    with tab_journalists:
        st.subheader("Saved journalist records")
        if not saved_journalists:
            st.info("No journalist records saved yet. Research journalists for an approved PR opportunity.")
        else:
            table_rows = [{
                "Name": r.get("name", ""),
                "Publication": r.get("publication", ""),
                "Relevant article": r.get("relevant_article_url", ""),
                "Related opportunity": r.get("related_opportunity_url", ""),
                "Qualification": r.get("qualification_status", "Needs review"),
                "Updated": r.get("updated_at", ""),
            } for r in saved_journalists]
            st.dataframe(table_rows, use_container_width=True, hide_index=True, column_config={
                "Relevant article": st.column_config.LinkColumn("Relevant article", display_text="Open article"),
                "Related opportunity": st.column_config.LinkColumn("Related opportunity", display_text="Open opportunity"),
            })
            st.download_button(
                "Export journalists as CSV",
                data=journalist_csv_bytes(),
                file_name="journalists.csv",
                mime="text/csv",
            )

    st.divider()
    st.subheader("Back up your local database")
    st.caption("Create a dated SQLite backup inside your project's backups folder before updating the app or moving computers.")
    if st.button("Create database backup", type="primary"):
        backup_file = create_database_backup()
        st.success(f"Database backup created: {backup_file}")


# =========================================================
# OUTREACH
# =========================================================

elif page == "Outreach":
    st.title("Outreach")
    st.caption(
        "Qualified journalist targets ready for the next step: pitch preparation."
    )
    st.info(
        "Being listed here does not approve or send outreach. The next development step "
        "will create a personalized draft for your review, with a separate approval before sending."
    )

    results = st.session_state.opportunity_results
    analysis = st.session_state.analysis
    run_id = st.session_state.research_run_id
    reviews = st.session_state.opportunity_reviews
    journalist_results = st.session_state.journalist_results
    journalist_reviews = st.session_state.journalist_reviews

    qualified_targets = []

    if results is not None and analysis is not None:
        for opportunity_index, opportunity in enumerate(results.opportunities):
            opportunity_key = f"{run_id}:{opportunity_index}"
            opportunity_status = reviews.get(opportunity_key, "Awaiting review")

            # Only opportunities explicitly approved for journalist research can enter this queue.
            if opportunity_status != "Approve for journalist research":
                continue

            journalist_result = journalist_results.get(opportunity_key)
            if journalist_result is None:
                continue

            for person_index, person in enumerate(journalist_result.journalists):
                qualification_key = f"{opportunity_key}:{person_index}"
                status = journalist_reviews.get(qualification_key, "Needs review")

                if status == "Qualified pitch target":
                    qualified_targets.append((opportunity, person))

    if not qualified_targets:
        st.info(
            "No qualified pitch targets yet. Open Journalists, review each writer, and "
            "save 'Qualified pitch target' only when there is a clear editorial reason to contact them."
        )
    else:
        st.metric("Qualified pitch targets", len(qualified_targets))
        for index, (opportunity, person) in enumerate(qualified_targets, start=1):
            with st.container(border=True):
                st.subheader(f"{index}. {person.name}")
                st.write(f"**Publication:** {person.publication}")
                st.write(f"**Related opportunity:** {opportunity.article_title}")
                st.write(f"**Relevant article:** {person.relevant_article_title}")
                st.write(f"**Why they fit:** {person.why_relevant}")
                st.write(f"**Suggested pitch angle:** {person.suggested_pitch_angle}")
                st.caption("Status: Qualified pitch target · Ready for pitch preparation")
                byline_url = person.relevant_article_url.strip()
                profile_url = person.author_profile_or_contact_page.strip()
                if byline_url.startswith("https://"):
                    st.link_button(
                        "Open relevant article",
                        byline_url,
                        key=f"outreach_article_{index}",
                    )
                if profile_url.startswith("https://"):
                    st.link_button(
                        "Open author profile / contact page",
                        profile_url,
                        key=f"outreach_profile_{index}",
                    )

    st.divider()
    st.markdown("**Human approval remains required.** This page does not draft or send emails yet."
    )

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

