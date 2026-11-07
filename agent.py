import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

from openai import AsyncOpenAI
from agents import Agent, Runner, WebSearchTool, ModelSettings, set_default_openai_client
from pydantic import BaseModel, Field


# =========================================================
# MODEL CONFIGURATION
# =========================================================
# Cheapest reliable default. Override with an environment variable if needed:
#   OPENAI_MODEL=gpt-5-nano-flex    (lowest per-token price, slower queue)
#   OPENAI_MODEL=gpt-5-nano         (default)
#   OPENAI_MODEL=gpt-5.4-nano
#   SEARCH_CONTEXT_SIZE=low|medium|high
DEFAULT_MODEL = "gpt-5-nano"
MODEL = (os.environ.get("OPENAI_MODEL") or os.environ.get("VISTA_OPENAI_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL

SEARCH_CONTEXT_SIZE = (os.environ.get("SEARCH_CONTEXT_SIZE") or os.environ.get("VISTA_SEARCH_CONTEXT") or "low").strip().lower()
if SEARCH_CONTEXT_SIZE not in {"low", "medium", "high"}:
    SEARCH_CONTEXT_SIZE = "low"

# Fixed sender identity used in every outreach draft.
HARDCODED_SENDER_NAME = "Prachi"
HARDCODED_SENDER_ROLE = "SEO Specialist"


# Keep responses fast and cheap.
MODEL_SETTINGS = ModelSettings(
    reasoning={"effort": "low"} if MODEL.startswith("gpt-5") else None,
    verbosity="low",
)

MAX_TURNS = int(os.environ.get("MAX_TURNS", "3"))

# The OpenAI client is created lazily inside the persistent agent event loop.
# Creating it at import time can bind its HTTP connections to a loop that later
# gets closed between Streamlit runs. See _ensure_openai_client() below.

# Brand configuration (override to reuse this tool for any product/company).
# Priority: environment variable > data/brand_config.json > neutral default.
_PROJECT_ROOT = Path(__file__).resolve().parent


def _read_brand_config() -> dict:
    data_dir = Path(
        os.environ.get("PR_AGENT_DATA_DIR") or _PROJECT_ROOT / "data"
    )
    config_path = data_dir / "brand_config.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


_BRAND_CONFIG = _read_brand_config()

BRAND_NAME = (
    os.environ.get("BRAND_NAME")
    or os.environ.get("VISTA_BRAND_NAME")
    or _BRAND_CONFIG.get("brand_name")
    or "Your Brand"
).strip() or "Your Brand"
PRODUCT_DESCRIPTION = (
    os.environ.get("PRODUCT_DESCRIPTION")
    or os.environ.get("VISTA_PRODUCT_DESCRIPTION")
    or _BRAND_CONFIG.get("product_description")
    or "a software product"
).strip() or "a software product"
BRAND_DOMAIN = (
    os.environ.get("BRAND_DOMAIN")
    or os.environ.get("VISTA_BRAND_DOMAIN")
    or _BRAND_CONFIG.get("brand_domain")
    or ""
).strip()

# Shared expert lens for every research and writing agent. The full methodology
# is published at /skills/seo-aeo-digital-pr.md and llms.txt.
EXPERT_RULES = """
Think like a senior SEO, AEO, and Digital PR strategist.

- Judge every opportunity on search intent, topical/entity fit, E-E-A-T, and
  answer-engine extractability, not on Domain Rating.
- Prefer pages that answer a real audience question and can host a concise,
  sourced answer. Name that question in your reasoning.
- A backlink is an outcome, not the strategy. Earn coverage with a credible
  asset: original data, expert commentary, a customer story, or a missing
  product category.
- Reject content farms, scraped or duplicated pages, paid-only placements
  disguised as editorial, irrelevant audiences, dead sites, and pages with no
  editorial route. Say which signal you saw.
- For AEO, check whether the page can carry a 40-60 word answer, a comparison,
  a definition, a step list, or a cited statistic, and whether the brand would
  be the source.
- For every pitch: name the news hook, the audience question, the credible
  asset, the evidence, and one low-pressure next step.
- Use only emails explicitly published on public pages. Never guess a pattern
  or use scraped-email sites.
- Never invent statistics, citations, contacts, policies, or coverage. If a
  fact is missing, say what is missing and how to verify it.
"""


# =========================================================
# ASSET INTELLIGENCE MODELS
# =========================================================

class Statistic(BaseModel):
    statistic: str = Field(description="The statistic or factual data point.")
    source: str = Field(description="The source of the statistic, if identified.")
    data_provenance: str = Field(
        description=(
            "Classify as the brand's original data, external primary source, "
            "external survey, company-reported, secondary source, or unknown."
        )
    )
    pr_relevance: str = Field(description="Explain the statistic's relevance to Digital PR.")


class PRAngle(BaseModel):
    angle: str = Field(description="The core Digital PR story angle.")
    story_type: str = Field(description="The category of PR story.")
    recommended_tactic: str = Field(description="The recommended PR tactic.")
    story_hypothesis: str = Field(description="The story a publication could potentially cover.")
    why_useful: str = Field(description="Why this could provide editorial value.")
    brand_contribution: str = Field(description="What the brand can credibly contribute.")
    target_publication_types: list[str] = Field(description="Types of publications that may fit the story.")
    target_journalist_beats: list[str] = Field(description="Relevant journalist topics to research later.")
    relevant_asset: str = Field(description="The existing brand asset supporting the angle.")
    evidence: str = Field(description="Evidence supporting the angle.")
    next_action: str = Field(description="The single most useful next action.")
    confidence: str = Field(description="Confidence level: High, Medium, or Low.")


class AssetAnalysis(BaseModel):
    article_title: str = Field(description="The article title.")
    main_topic: str = Field(description="The main subject of the article.")
    target_audience: list[str] = Field(description="The article's intended audiences.")
    key_claims: list[str] = Field(description="Important claims made or supported by the article.")
    statistics: list[Statistic] = Field(description="Important statistics found in the article.")
    useful_assets: list[str] = Field(description="Existing information and resources useful for PR.")
    pr_angles: list[PRAngle] = Field(description="Evidence-based and actionable PR angles.")
    assessment: str = Field(description="Overall assessment of the article's PR value.")


# =========================================================
# PR OPPORTUNITY RESEARCH MODELS
# =========================================================

class PROpportunity(BaseModel):
    publication: str = Field(description="Publication or website name.")
    article_title: str = Field(description="Title of the relevant existing article.")
    article_url: str = Field(description="Exact URL of the article.")
    published_date: str = Field(description="Publication date, or Unknown if unverified.")
    topic: str = Field(description="The article's main topic.")
    opportunity_type: str = Field(description="The type of PR opportunity.")
    why_relevant: str = Field(description="Why this specific article matches the PR angle.")
    brand_contribution: str = Field(
        default="Not recorded in earlier research.",
        description="What the brand could credibly contribute.",
    )
    competitor_mention: str = Field(description="A verified competitor mention, or None identified.")
    topical_relevance: str = Field(description="High, Medium, or Low, with reasoning.")
    editorial_fit: str = Field(description="High, Medium, or Low, with reasoning.")
    recommended_action: str = Field(description="The recommended next action.")
    evidence: str = Field(description="Evidence supporting the recommendation.")
    confidence: str = Field(description="Confidence level: High, Medium, or Low.")
    pr_fit: str = Field(
        default="Not assessed",
        description=(
            "PR suitability verdict for this publication: Strong fit, Possible fit, "
            "Weak fit, or Not suitable."
        ),
    )
    pr_fit_reason: str = Field(
        default="Not assessed yet.",
        description="One short sentence naming the specific signal behind the verdict.",
    )
    pr_red_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Specific reasons this page or blog is a poor PR target, such as "
            "content-farm signals, no bylines, paid-only placement, syndicated "
            "or duplicated content, an irrelevant audience, or no editorial "
            "contact. Empty when there are none."
        ),
    )


class PRResearchResults(BaseModel):
    selected_angle: str = Field(description="The PR angle being researched.")
    research_summary: str = Field(description="A concise summary of the research findings.")
    opportunities: list[PROpportunity] = Field(description="The strongest relevant editorial candidates.")


class PRFitAssessment(BaseModel):
    publication: str = Field(description="Publication or blog that was assessed.")
    article_title: str = Field(description="Article or page that triggered the assessment.")
    article_url: str = Field(description="Exact URL that was assessed.")
    pr_fit: str = Field(
        description="Use exactly one of: Strong fit, Possible fit, Weak fit, Not suitable."
    )
    reason: str = Field(
        description="One short sentence naming the specific evidence behind the verdict."
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete problems found, such as no bylines, content-farm signals, "
            "paid-only placement, syndicated content, irrelevant audience, or no "
            "editorial contact route. Empty when none were found."
        ),
    )
    recommended_action: str = Field(
        description="Use Pitch, Needs verification, or Skip."
    )


class OpportunityContact(BaseModel):
    contact_name: str = Field(
        description=(
            "The bylined writer or a verified content, SEO, or link-building "
            "contact. Use 'Content team' only when no person can be verified."
        )
    )
    role: str = Field(
        description=(
            "Verified role, such as Content Writer, Content Manager, SEO Manager, "
            "Link Building / Outreach Manager, Editor, or Partnerships contact."
        )
    )
    email: str = Field(
        description=(
            "A professional email only if it is explicitly published on a public "
            "page. Otherwise use Not publicly found."
        )
    )
    contact_page_url: str = Field(
        description="Official author profile, content/SEO team page, editorial contact page, or contact form URL, or Unknown."
    )
    source_url: str = Field(
        description="Exact URL of the page that supports the contact details, or Unknown."
    )
    evidence: str = Field(
        description="Quote or paraphrase the published evidence tying the contact to content, SEO, or link placement."
    )
    confidence: str = Field(description="High, Medium, or Low.")
    route: str = Field(
        description="Best route: Direct email, Author profile, Content/SEO team page, Editorial contact page, or Contact form."
    )



# =========================================================
# JOURNALIST RESEARCH MODELS
# =========================================================

class JournalistProfile(BaseModel):
    name: str = Field(
        description="The journalist, writer, or editor's name. Do not guess."
    )
    publication: str = Field(
        description="The publication where the person writes or edits."
    )
    current_role: str = Field(
        description="Verified current role, or Unknown if it cannot be verified."
    )
    relevant_article_title: str = Field(
        description="A specific relevant article written by this person."
    )
    relevant_article_url: str = Field(
        description="The exact URL of that article."
    )
    article_date: str = Field(
        description="Publication date in YYYY-MM-DD format, or Unknown."
    )
    topic_covered: str = Field(
        description="The subject or beat demonstrated by their published work."
    )
    why_relevant: str = Field(
        description="Why this person's work makes them a relevant target for this exact opportunity."
    )
    suggested_pitch_angle: str = Field(
        description="A specific pitch approach linked to the verified article and the brand's contribution."
    )
    author_profile_or_contact_page: str = Field(
        description="Verified author biography or official publication contact page URL, if available; otherwise Unknown."
    )
    evidence: str = Field(
        description="What the research verified about this person and their relevance."
    )
    confidence: str = Field(
        description="Use High, Medium, or Low, based on the evidence."
    )


class JournalistResearchResults(BaseModel):
    selected_opportunity: str = Field(
        description="The article/opportunity for which journalists were researched."
    )
    publication: str = Field(
        description="The publication associated with the selected opportunity."
    )
    research_summary: str = Field(
        description="Short summary of the journalist research and any limitations."
    )
    journalists: list[JournalistProfile] = Field(
        description="Up to five evidence-supported, relevant journalists or writers."
    )



# =========================================================
# LISTICLE RESEARCH MODELS
# =========================================================

class ListicleOpportunity(BaseModel):
    publication: str = Field(
        description="Name of the publication or website hosting the listicle."
    )
    listicle_title: str = Field(
        description="Exact title of the existing roundup, alternatives article, or tools list."
    )
    listicle_url: str = Field(
        description="Exact URL of the existing listicle. Use an empty string if it cannot be verified."
    )
    published_or_updated: str = Field(
        description="Verified publication or last-updated date, or Unknown. Do not estimate dates."
    )
    listicle_category: str = Field(
        description="The listicle's focus, such as social media management, scheduling, analytics, agency tools, or competitor alternatives."
    )
    target_audience: str = Field(
        description="The audience the listicle appears to serve."
    )
    competitors_listed: list[str] = Field(
        description="Competitors explicitly visible in the article. Do not infer missing names."
    )
    brand_currently_listed: str = Field(
        default="Unclear",
        description="Use Yes, No, or Unclear, based on whether the article was actually checked for the brand.",
    )
    brand_fit: str = Field(
        default="Not recorded in earlier research.",
        description="Explain how the brand's known product category and capabilities match this listicle's inclusion criteria.",
    )
    inclusion_gap: str = Field(
        description="A verified reason to request consideration, or Unknown if the reason the brand is absent cannot be established. Do not guess why it was omitted."
    )
    placement_type: str = Field(
        description="Classify as Editorial, Affiliate, Sponsored/Paid, Directory, User-generated, or Unclear. Use evidence and acknowledge uncertainty."
    )
    contact_route: str = Field(
        description="A verified route such as official submission form, editor/author page, contact page, affiliate program, sponsored-content page, or Unknown. Do not invent email addresses."
    )
    recommended_action: str = Field(
        description="Use one of: Request editorial consideration, Submit via official form, Evaluate paid/affiliate option, Research further, Already listed, or Skip."
    )
    evidence: str = Field(
        description="Specific page evidence supporting the fit, inclusion status, and recommendation."
    )
    confidence: str = Field(
        description="High, Medium, or Low based on verifiable evidence."
    )


class ListicleResearchResults(BaseModel):
    search_theme: str = Field(
        description="The main listicle category or theme searched."
    )
    research_summary: str = Field(
        description="Summarize the search coverage, useful patterns, and limitations."
    )
    opportunities: list[ListicleOpportunity] = Field(
        description="Existing listicle opportunities matching the search criteria, deduplicated, up to the requested result limit."
    )


# =========================================================
# LISTICLE CONTACT RESEARCH MODELS
# =========================================================

class ListicleContact(BaseModel):
    contact_name: str = Field(
        description="Verified public professional contact name, or Not found. Never guess."
    )
    current_role: str = Field(
        description="Verified role, such as article author, editor, editorial team, affiliate manager, or partnerships contact. Use Unknown if unverified."
    )
    professional_email: str = Field(
        description="A professional email only if it is explicitly published on a reliable public source. Otherwise use Not publicly found. Never infer or guess an email."
    )
    author_profile_url: str = Field(
        description="Verified author or staff profile URL, or Unknown."
    )
    contact_page_url: str = Field(
        description="Verified official contact page, editorial submission form, affiliate page, or partnerships page URL, or Unknown."
    )
    contact_method: str = Field(
        description="Most appropriate route for this listicle: email, official form, author/contact page, affiliate program, sponsored content team, or no verified route found."
    )
    why_this_contact: str = Field(
        description="Why this person or route is appropriate for requesting consideration for this specific listicle."
    )
    evidence: str = Field(
        description="What the research verified and where the evidence was found."
    )
    source_url: str = Field(
        description="URL of the page that supports the contact details or route, or Unknown."
    )
    confidence: str = Field(
        description="High, Medium, or Low based on the quality of verification."
    )


class ListicleContactResearchResults(BaseModel):
    publication: str = Field(description="Publication that hosts the listicle.")
    listicle_title: str = Field(description="Title of the listicle being researched.")
    listicle_url: str = Field(description="URL of the listicle.")
    research_summary: str = Field(description="Summary of contact-finding research and limitations.")
    contacts: list[ListicleContact] = Field(
        description="Up to three verified contact people or official contact routes, ordered by suitability. Do not invent missing data."
    )


# =========================================================
# JOURNALIST EMAIL RESEARCH MODELS
# =========================================================

class JournalistEmailCandidate(BaseModel):
    email: str = Field(
        description="An email address only if it appears verbatim on a public page that was actually visited. Use Not publicly found if none was verified."
    )
    source_url: str = Field(
        description="Exact URL of the public page where the address appears, or Unknown."
    )
    source_name: str = Field(
        description="What the source page is, such as author profile, staff page, editorial contact page, personal website, conference bio, or podcast notes."
    )
    evidence: str = Field(
        description="Quote or paraphrase the surrounding published text that ties the address to this person or their publication."
    )
    confidence: str = Field(
        description="High, Medium, or Low based on how directly the public page ties the address to this person."
    )


class JournalistEmailResearch(BaseModel):
    person_name: str = Field(description="Journalist whose contact details were researched.")
    publication: str = Field(description="Publication the journalist writes or edits for.")
    research_summary: str = Field(
        description="Summarize which public pages were checked and what the research could and could not verify."
    )
    candidates: list[JournalistEmailCandidate] = Field(
        description="Up to three published addresses, ordered by reliability. Return an empty list when no address is explicitly published."
    )
    recommended_contact_route: str = Field(
        description="The best verified route: direct email, editorial contact page, author profile contact form, social profile, or no verified route."
    )


class PublisherPolicyAssessment(BaseModel):
    publication: str = Field(description="Name of the publication or directory.")
    listicle_title: str = Field(description="Title of the target listicle, roundup, comparison, or listing page.")
    target_url: str = Field(description="Exact target page URL provided for policy assessment.")
    policy_status: str = Field(
        description=(
            "Use one of: Explicitly accepts editorial suggestions, Explicitly rejects product/link requests, "
            "Paid/sponsored options available, Affiliate/partner route, Directory/vendor listing route, "
            "Already listed, No explicit policy found, Mixed/ambiguous, or Unknown."
        )
    )
    policy_summary: str = Field(
        description="Summarize any explicit policy about product inclusion, unsolicited pitches, link requests, affiliate submissions, sponsorships, or vendor listings. Distinguish explicit policy from absence of evidence."
    )
    policy_evidence: str = Field(
        description="Quote or paraphrase the relevant published policy accurately and explain what it does and does not establish. Do not infer a restriction from silence."
    )
    policy_source_url: str = Field(
        description="Exact URL of the official policy page or target page supporting the assessment, or Unknown."
    )
    recommended_disposition: str = Field(
        description="Use one of: Pursue, Paid option to review, Needs verification, Do not pursue, Use directory submission, or Already listed."
    )
    disposition_reason: str = Field(
        description="Explain the recommendation based on the verified policy and current the brand inclusion status."
    )
    recommended_route: str = Field(
        description="The best next route: editorial consideration, official directory/vendor submission, affiliate/partner route, sponsored-content team, research further, or no outreach."
    )
    confidence: str = Field(description="High, Medium, or Low, based on the directness and recency of source evidence.")


# =========================================================
# OUTREACH DRAFT MODELS
# =========================================================

class OutreachDraft(BaseModel):
    outreach_type: str = Field(
        description="Either 'Digital PR pitch' or 'Listicle inclusion request'."
    )
    channel: str = Field(
        description=(
            "The verified route this draft is written for: email, official contact form, "
            "author profile message, affiliate/partner route, or another named route. "
            "Never invent a route."
        )
    )
    recipient_name: str = Field(
        description="The verified recipient name, or 'Editorial team' if only a team route is known."
    )
    recipient_role: str = Field(
        description="The verified role, or Unknown if it could not be established."
    )
    publication: str = Field(description="The target publication or website.")
    target_title: str = Field(
        description="The exact target article, listicle, roundup, or directory page title."
    )
    target_url: str = Field(description="The exact target page URL supplied in the research.")
    subject_line: str = Field(
        description="A specific subject line under 70 characters. No clickbait, no fake urgency."
    )
    message_body: str = Field(
        description=(
            "The complete draft message. Concise, specific, and ready for human review. "
            "Use the supplied sender name and role exactly; do not invent or alter them."
        )
    )
    personalization_evidence: str = Field(
        description="The exact verified article, page, or policy evidence used to personalize the draft."
    )
    asset_used: str = Field(
        description="The brand asset, data point, or contribution offered. Do not invent assets."
    )
    call_to_action: str = Field(
        description="The single, low-pressure next step requested from the recipient."
    )
    facts_to_verify: list[str] = Field(
        description="Facts, names, links, or claims a human must verify before sending."
    )
    compliance_notes: str = Field(
        description=(
            "Notes on publisher policy, paid/affiliate disclosure, or reasons the message "
            "must not be sent as written."
        )
    )
    confidence: str = Field(
        description="High, Medium, or Low based on the quality of the underlying research."
    )


# =========================================================
# WEB SEARCH TOOL
# =========================================================

web_search = WebSearchTool(
    search_context_size=SEARCH_CONTEXT_SIZE,
    external_web_access=True,
)


# =========================================================
# ASSET ANALYSIS AGENT
# =========================================================

asset_agent = Agent(
    name="PR Asset Analyst",
    instructions=f"""
You are a Digital PR asset analyst and PR strategist for {BRAND_NAME}.

Analyze the {BRAND_NAME} article supplied by the user. Identify useful
content, claims, statistics, sources, data provenance, and credible PR angles.

Rules:
- Do not invent facts, statistics, sources, or claims.
- Use web search to access or verify the article.
- Distinguish {BRAND_NAME}'s own data from external research.
- Never present external statistics as {BRAND_NAME}'s original data.
- Do not turn every statistic into a PR angle.
- A backlink alone is not a Digital PR opportunity.
- Focus on editorial usefulness.
- Explain what {BRAND_NAME} can credibly contribute.
- Recommend a suitable tactic for every angle.
- Identify target publication types and journalist beats.
- Give exactly one useful next action for each angle.
- Do not research individual journalists in this stage.
- Do not send outreach.

Return the requested structured fields.
""",
    tools=[web_search],
    model=MODEL,
    model_settings=MODEL_SETTINGS,
    output_type=AssetAnalysis,
)


# =========================================================
# OPPORTUNITY RESEARCH AGENT
# =========================================================

opportunity_agent = Agent(
    name="PR Opportunity Researcher",
    instructions=f"""
You are a Digital PR opportunity researcher for {BRAND_NAME}.

{EXPERT_RULES}

Find real existing articles and editorial conversations that match the
supplied PR angle.

Research process:
1. Understand the angle and {BRAND_NAME}'s contribution.
2. Search the web using 2-3 relevant topic variations.
3. Find specific existing articles, not just website homepages.
4. Evaluate topical and editorial relevance.
5. Check whether {BRAND_NAME} can make a credible contribution.
6. Check competitor mentions when the evidence is available.
7. Exclude generic SEO opportunities that lack a real editorial reason.
8. Return the strongest candidates, up to 5.
9. Give every candidate a PR suitability verdict for its publication.

PR suitability:
- Strong fit: original editorial content, a named writer or editor, a relevant
  audience, and a credible editorial reason to pitch.
- Possible fit: relevant, but one signal is unclear or missing.
- Weak fit: thin or unclear editorial value, unclear authorship, or a weak
  audience match.
- Not suitable: a content farm, scraped or syndicated content, paid-only
  placement, a directory or aggregator, a dead or abandoned blog, or a page
  with no genuine editorial route.

Red flags include: no bylines, AI-spam or low-effort listicles, duplicated
copy across sites, "write for us" link-selling, sponsored-only placement,
irrelevant audience, and no contact route. Name the specific signal you saw.
Do not call a publication high-quality just because it is well known.

Rules:
- Search the live web.
- Prefer current or reasonably recent coverage.
- Do not invent article titles, URLs, dates, or competitor mentions.
- Use Unknown when a date cannot be verified.
- Do not invent journalist names.
- Do not rank opportunities mainly by Domain Rating.
- A backlink alone is not enough to qualify an opportunity.
- Do not recommend manipulative links or irrelevant guest posts.
- Provide article-specific evidence for every candidate.
- Distinguish genuine PR opportunities from listicle or SEO opportunities.
- Do not contact journalists or send outreach.

Quality matters more than quantity.
Return only the requested structured fields.
""",
    tools=[web_search],
    model=MODEL,
    model_settings=MODEL_SETTINGS,
    output_type=PRResearchResults,
)




# =========================================================
# PR FIT ASSESSOR
# =========================================================

pr_fit_agent = Agent(
    name="PR Fit Assessor",
    instructions=f"""
You decide whether a blog, publication, or website is worth a PR approach for
{BRAND_NAME}. You are blunt and evidence-led.

Assess the publication behind the supplied page, not just the page:
1. Is the content original editorial work, or scraped, syndicated, or
   machine-generated filler?
2. Are there real bylines and a named editorial team?
3. Is the audience relevant to {BRAND_NAME}'s category?
4. Is there a genuine editorial route, or only paid/sponsored placement,
   affiliate links, or a link-selling "write for us" page?
5. Is the site active and credible, or abandoned, a directory, or an
   aggregator?

Verdicts:
- Strong fit: original editorial, named bylines, relevant audience, credible
  editorial route.
- Possible fit: relevant, but one important signal is unclear.
- Weak fit: thin content, unclear authorship, or a weak audience match.
- Not suitable: content farm, scraped/duplicated content, paid-only placement,
  directory/aggregator, dead site, or no genuine editorial route.

Rules:
- Use live web search. Check the about, editorial, contact, and policy pages.
- Do not infer quality from brand recognition, Domain Rating, or design alone.
- Do not invent signals. If you cannot verify something, say so.
- Name the specific red flag you saw. "Low quality" is not enough.
- Do not contact anyone or submit anything.
- Return only the requested structured fields.
""",
    tools=[web_search],
    model=MODEL,
    model_settings=MODEL_SETTINGS,
    output_type=PRFitAssessment,
)


# =========================================================
# OPPORTUNITY CONTACT AGENT
# =========================================================

opportunity_contact_agent = Agent(
    name="SEO and Content Contact Researcher",
    instructions=f"""
You find the best outreach contact for one specific article, on behalf of
{BRAND_NAME}. Work from the exact article URL and publication.

{EXPERT_RULES}

The goal is a content or link placement, not a news pitch. Look for the people
who own content, SEO, or link building:
1. The bylined writer of that exact article (usually a content writer).
2. The content manager, content editor, or managing editor for that section.
3. The SEO manager or SEO lead.
4. The link-building, outreach, or partnerships contact.
5. The publication's official editorial or content contact page or form.

Research process:
- Start with the exact article URL and use the byline or author profile.
- Check the author profile, about/team page, editorial guidelines, "write for
  us" or contributor page, and contact page.
- Search the publication plus "content manager", "SEO manager", "link building",
  "partnerships", and "editorial team".

Rules:
- Only use an email that is explicitly published on a public page you visited.
- Never guess, infer, or construct an email address.
- Never use data-broker, scraped-email, or email-finder sites.
- Prefer a named person with a published email. A general content/editorial
  inbox is acceptable only when it is explicitly published and no person is.
- Do not return sales or advertising contacts unless the only published route
  is paid placement; say so in the evidence.
- Use "Content team" as the contact name only when no person can be verified.
- Use "Not publicly found" for an email that does not exist publicly, and still
  return the best official contact page.
- Do not contact anyone or submit anything.
- Include the exact source URL and the published evidence.

Return only the requested structured fields.
""",
    tools=[web_search],
    model=MODEL,
    model_settings=MODEL_SETTINGS,
    output_type=OpportunityContact,
)


# =========================================================
# JOURNALIST RESEARCH AGENT
# =========================================================

journalist_agent = Agent(
    name="Journalist Researcher",
    instructions=f"""
You are a journalist researcher supporting a human-led Digital PR workflow for {BRAND_NAME}.

{EXPERT_RULES}

Your task is to identify real writers, reporters, or editors whose published work makes
these people relevant to one specific, human-approved PR opportunity.

RESEARCH PROCESS:
1. Start from the supplied opportunity and PR angle.
2. Search the live web for the named publication, the article topic, and related recent articles.
3. Verify the person has actually written or edited relevant work using a specific article,
   an official author page, or another reliable source.
4. Prefer people who have covered the topic recently, ideally within the last 12 months.
   If few relevant people exist, older work can be included with the date clearly shown.
5. Look for a direct connection between the person's beat and the contribution {BRAND_NAME} can offer.
6. Return up to five strong contacts, and return fewer when the evidence is weak.

STRICT RULES:
- Do not invent people's names, job titles, recent articles, dates, or profile URLs.
- Do not infer an email address from naming conventions.
- Do not include a person merely because they work at the publication.
- Do not assume the author of the opportunity article is the correct contact unless evidence supports it.
- Prioritize editorial relevance over seniority or publication authority.
- Do not research or recommend contacts for generic link insertion or SEO-only outreach.
- Do not draft or send emails at this stage.
- If the research cannot establish a relevant person, return an empty journalists list and explain why.
- Use Unknown when a role, date, or profile/contact page cannot be verified.
- Link to the actual relevant article and verified author profile/contact page where available.

For every person, explain exactly why their published work makes them relevant to this opportunity
and suggest an angle that is useful to the journalist, not just promotional for {BRAND_NAME}.

Return only the requested structured fields.
""",
    tools=[web_search],
    model=MODEL,
    model_settings=MODEL_SETTINGS,
    output_type=JournalistResearchResults,
)



# =========================================================
# LISTICLE RESEARCH AGENT
# =========================================================

listicle_agent = Agent(
    name="Listicle Opportunity Researcher",
    instructions=f"""
You are a listicle and software-roundup prospecting researcher for {BRAND_NAME}.

Your goal is to find a broad but relevant pool of existing pages where {BRAND_NAME}
could legitimately be considered for inclusion. This is a separate workflow from
journalist-led Digital PR.

Search themes can include best-of lists, software roundups, product comparisons,
alternatives pages, category guides, resource lists, and relevant directories.

Research instructions:
1. Search the live web using the supplied category and related query variations.
2. Include different search paths: category roundups, use-case roundups, audience-specific lists,
   competitor alternatives, comparison articles, and software directories when relevant.
3. Return specific existing pages, never just publication homepages or search result pages.
4. Prefer pages where {BRAND_NAME}'s actual product category and known capabilities fit the stated criteria.
5. Check whether {BRAND_NAME} is already included when the article can be inspected.
6. Identify competitors only when they are explicitly present in the article.
7. Capture publication or update dates only when verified. Otherwise use Unknown.
8. Identify the likely placement model: editorial, affiliate, paid/sponsored, directory, user-generated, or unclear.
9. Search for an official contact, author, submission, affiliate, or sponsored-content route when possible.
10. Deduplicate repeat URLs and the same article appearing in several search results.

Important rules:
- Do not invent article titles, URLs, dates, competitors, contacts, or contact details.
- Do not guess why {BRAND_NAME} is absent from a page. Use Unknown if the reason is not evidenced.
- Do not describe paid or affiliate placements as independent editorial endorsements.
- Do not automatically dismiss affiliate pages, but label the model clearly so a human can decide.
- Do not prioritize by Domain Rating alone.
- Do not recommend irrelevant sites just to increase volume.
- Do not assume a competitor's inclusion guarantees {BRAND_NAME} qualifies.
- Do not send emails or submit forms.
- Do not invent email addresses.
- Prefer a focused set of qualified candidates over a tiny set, while preserving relevance and deduplication.
- Return no more than the requested maximum number of candidates.
- If results are weak, return fewer candidates and explain the limitation.

For each result, answer:
- What is the exact page?
- Does {BRAND_NAME} fit the category?
- Is {BRAND_NAME} already listed?
- Which competitors are listed?
- What inclusion gap or reasonable next step is evidenced?
- How can the publisher be approached?
- Is the page editorial, affiliate, paid, a directory, or unclear?

Return only the requested structured fields.
""",
    tools=[web_search],
    model=MODEL,
    model_settings=MODEL_SETTINGS,
    output_type=ListicleResearchResults,
)


# =========================================================
# LISTICLE CONTACT RESEARCH AGENT
# =========================================================

listicle_contact_agent = Agent(
    name="Listicle Contact Researcher",
    instructions=f"""
You find the most appropriate public professional contact route for a specific software listicle.

Use live web search. Start with the exact listicle URL and publication name. Look for:
1. The bylined article author and their official author profile.
2. An editor or editorial team responsible for software/tool roundups.
3. An official editorial submission or contact form.
4. If the page is affiliate-driven, the official affiliate or partnerships route.
5. If the page is sponsored/paid, the official sponsored-content or advertising route.
6. A professional email only if it is explicitly published on a reliable public source, preferably the publication's own website or the person's official profile.

Rules:
- Never guess or infer an email address.
- Never provide private/personal contact details unrelated to professional publishing.
- Do not treat a generic contact page as the article author's direct email.
- Prefer the author/editor responsible for the specific listicle, but use an official contact form when no suitable individual can be verified.
- Return up to three options, in order of suitability.
- Use "Not found", "Not publicly found", or "Unknown" for information that could not be verified.
- Include URLs supporting the contact route and explain what each source verifies.
- Do not contact anyone, submit forms, or send outreach.
- The output is research for a human to review, not a guarantee that the person is still responsible for the page.

Return only the requested structured fields.
""",
    tools=[web_search],
    model=MODEL,
    model_settings=MODEL_SETTINGS,
    output_type=ListicleContactResearchResults,
)


# =========================================================
# JOURNALIST EMAIL RESEARCH AGENT
# =========================================================

journalist_email_agent = Agent(
    name="Journalist Email Researcher",
    instructions=f"""
You find contact email addresses for a named journalist, but only when the
address is explicitly published on a public page.

Use live web search. Start with the person's name and publication, then check:
1. The publication's official author/staff profile for that person.
2. The publication's editorial, contact, or masthead page.
3. The person's own website or portfolio.
4. Public conference, podcast, webinar, or association bios.
5. Public social profiles where an address is written out.

Rules:
- Never guess, infer, construct, or complete an email pattern such as
  first.last@publication.com. Only report an address that literally appears on
  a public page you visited.
- Never use a data-broker, scraped-email, or "email finder" site as the source.
- Prefer an address tied directly to the named person. A generic newsroom or
  editorial address may be included only when no personal address is published,
  and it must be labelled as a general contact address.
- Do not include private, personal, or non-professional contact details.
- Do not contact anyone, subscribe to anything, or submit any form.
- If no address is published, return an empty candidate list and say so plainly.
  That is a useful result, not a failure.
- Record the exact source URL and the surrounding published text for every
  candidate, so a human can verify it before use.

Return only the requested structured fields.
""",
    tools=[web_search],
    model=MODEL,
    model_settings=MODEL_SETTINGS,
    output_type=JournalistEmailResearch,
)


# =========================================================
# PUBLISHER POLICY RESEARCH AGENT
# =========================================================

publisher_policy_agent = Agent(
    name="Publisher Policy Researcher",
    instructions=f"""
You assess whether it is appropriate to pursue a specific listicle, roundup,
comparison article, or software directory page for {BRAND_NAME}.

Use live web search. Start with the exact target page, then inspect official
publisher policies, submission instructions, contributor guidelines, affiliate
terms, sponsored-content pages, and vendor listing routes where relevant.

Check specifically for:
- Explicit policies rejecting unsolicited product-insertion or link requests.
- Editorial guidance allowing relevant factual corrections or product suggestions.
- Paid or sponsored placement options, clearly labeled as such.
- Affiliate or partnership requirements.
- Official software directory/vendor submission procedures.
- Whether {BRAND_NAME} is already listed on the exact target page.

Rules:
- Prefer the target page and official publisher sources over third-party summaries.
- Do not infer that a publisher rejects pitches merely because no policy is found.
- Do not treat guest-post/contributor guidelines as permission to insert a product into a roundup.
- Do not treat affiliate terms as proof that an editorial inclusion is guaranteed.
- Do not present paid/sponsored placement as independent editorial endorsement.
- Do not recommend circumventing a stated no-pitch or no-link-request policy.
- If the policy is unclear, use Needs verification rather than guessing.
- Include a source URL supporting the key policy finding; use Unknown if none is verifiable.
- If the page is a directory, recommend its official vendor/listing route rather than an editorial pitch.
- If {BRAND_NAME} is already listed, recommend Already listed.
- Do not contact the publisher, submit forms, or send outreach.

Disposition guidance:
- Pursue: relevant, legitimate route exists and no explicit conflicting policy was found.
- Paid option to review: the suitable documented route is paid/sponsored.
- Needs verification: source evidence is incomplete or ambiguous.
- Do not pursue: the publisher explicitly rejects this type of request or the opportunity is clearly unsuitable.
- Use directory submission: official vendor/profile route is the correct process.
- Already listed: {BRAND_NAME} already appears on the exact target page.

Return only the requested structured fields.
""",
    tools=[web_search],
    model=MODEL,
    model_settings=MODEL_SETTINGS,
    output_type=PublisherPolicyAssessment,
)


# =========================================================
# OUTREACH DRAFT AGENT
# =========================================================

outreach_draft_agent = Agent(
    name="Outreach Draft Writer",
    instructions=f"""
You prepare outreach drafts for a human to review and send manually on behalf of {BRAND_NAME}.

{EXPERT_RULES}

You never send anything. You never claim that a message was sent, a relationship exists,
or a publisher has agreed to anything. The human remains responsible for every send.

Write only from the research supplied in the prompt. Do not invent:
- statistics, customer names, coverage, awards, partnerships, or product capabilities
- email addresses, recipient names, roles, or contact routes
- publication policies, deadlines, or editorial commitments
- familiarity with the recipient's personal life or previous conversations

DIGITAL PR PITCH RULES:
- 120-180 words in the message body.
- Open with the specific article or topic and why it is relevant now.
- Offer one credible asset: original data, expert commentary, a customer story, or a
  concrete perspective. Explain why it helps the journalist's audience.
- Reference the journalist's actual published work when supplied.
- Do not ask for a link, mention Domain Rating, or offer payment.
- End with one low-pressure next step.

LISTICLE INCLUSION REQUEST RULES:
- 100-160 words in the message body.
- Name the exact page and the category where {BRAND_NAME} fits.
- Use only verified product facts from the supplied description.
- If the publisher's documented route is paid, sponsored, affiliate, or a directory
  listing, ask about that route instead of requesting a free editorial inclusion.
- Never imply that a competitor's inclusion guarantees acceptance.
- Never demand a dofollow link or a specific placement.
- End with one clear request: editorial consideration, the correct submission step,
  or confirmation of the paid/affiliate process.

STYLE:
- Plain, professional, specific, and human.
- No hype, flattery, fake urgency, or generic flattery.
- Short paragraphs. No bullet-point walls.
- Subject line under 70 characters and specific to the target.
- Use the supplied sender name and role exactly. Do not invent or alter them.
- Never emit [Your name], [Your role], or [verify: sender ...] placeholders.
- If a necessary fact is missing, leave a clear [verify: ...] placeholder and add it
  to facts_to_verify.

COMPLIANCE:
- Record any publisher policy that affects the message in compliance_notes.
- If the research says Do not pursue or Already listed, do not write a pitch; explain
  the blocking issue in compliance_notes and keep the draft minimal.

Return only the requested structured fields.
""",
    model=MODEL,
    model_settings=MODEL_SETTINGS,
    output_type=OutreachDraft,
)


# =========================================================
# RUNNER HELPER: ONE PERSISTENT EVENT LOOP
# =========================================================
# The OpenAI Agents SDK keeps an AsyncOpenAI client whose HTTP connections are
# bound to the event loop that first uses it. Creating and closing a fresh loop
# for every research call makes the next call fail with "Event loop is closed".
# Keep one loop alive for the life of the process and submit every agent run to
# it instead.

_AGENT_LOOP = asyncio.new_event_loop()
_OPENAI_CLIENT_READY = False
_OPENAI_CLIENT_LOCK = threading.Lock()


def _start_agent_loop():
    asyncio.set_event_loop(_AGENT_LOOP)
    _AGENT_LOOP.run_forever()


_AGENT_LOOP_THREAD = threading.Thread(
    target=_start_agent_loop,
    name="pr-agent-event-loop",
    daemon=True,
)
_AGENT_LOOP_THREAD.start()


def _ensure_openai_client():
    """Create the shared OpenAI client on the agent loop thread, once."""
    global _OPENAI_CLIENT_READY
    if _OPENAI_CLIENT_READY:
        return
    with _OPENAI_CLIENT_LOCK:
        if not _OPENAI_CLIENT_READY:
            # Fail fast (120s) on stalled calls; retry connection errors at the
            # SDK level.
            set_default_openai_client(AsyncOpenAI(timeout=120.0, max_retries=2))
            _OPENAI_CLIENT_READY = True


async def _run_agent_async(agent_to_run, prompt: str):
    _ensure_openai_client()
    return await Runner.run(agent_to_run, prompt, max_turns=MAX_TURNS)


def _run_agent_in_worker(agent_to_run, prompt: str):
    """Run an async agent on the shared event loop."""
    future = asyncio.run_coroutine_threadsafe(
        _run_agent_async(agent_to_run, prompt),
        _AGENT_LOOP,
    )
    return future.result().final_output


# =========================================================
# PUBLIC FUNCTIONS USED BY app.py
# =========================================================

def analyze_article(article_url: str) -> AssetAnalysis:
    """Analyze an article and return structured asset intelligence."""
    prompt = f"""
Analyze this exact {BRAND_NAME} article:

{article_url}

Research the article first, then identify its content, evidence, data
provenance, useful assets, and actionable PR angles.
"""
    return _run_agent_in_worker(asset_agent, prompt)


def research_opportunities(angle: PRAngle) -> PRResearchResults:
    """Research editorial opportunities for a selected PR angle."""
    prompt = f"""
Research this {BRAND_NAME} PR angle.

ANGLE:
{angle.angle}

STORY TYPE:
{angle.story_type}

RECOMMENDED TACTIC:
{angle.recommended_tactic}

STORY HYPOTHESIS:
{angle.story_hypothesis}

BRAND CONTRIBUTION:
{angle.brand_contribution}

TARGET PUBLICATION TYPES:
{", ".join(angle.target_publication_types)}

TARGET JOURNALIST BEATS:
{", ".join(angle.target_journalist_beats)}

RELEVANT BRAND ASSET:
{angle.relevant_asset}

SUPPORTING EVIDENCE:
{angle.evidence}

Find real existing editorial articles that match this angle. Evaluate their
topical relevance, editorial fit, evidence, competitor presence, and next action.
Return up to 5 strong candidates.
"""
    return _run_agent_in_worker(opportunity_agent, prompt)


def assess_pr_fit(opportunity: PROpportunity) -> PRFitAssessment:
    """Check whether a page's publication is worth a PR approach."""

    prompt = f"""
Assess whether this page and its publication are worth a PR approach.

PUBLICATION: {opportunity.publication}
ARTICLE TITLE: {opportunity.article_title}
ARTICLE URL: {opportunity.article_url}
PUBLISHED: {opportunity.published_date}
TOPIC: {opportunity.topic}
WHY THE RESEARCHER LIKED IT: {opportunity.why_relevant}
EDITORIAL FIT: {opportunity.editorial_fit}
RECOMMENDED ACTION: {opportunity.recommended_action}
EVIDENCE SO FAR: {opportunity.evidence}

Check the live site: about page, editorial team and bylines, contact route,
sponsored or paid-placement policy, content originality, and whether the site
is active. Then give one verdict: Strong fit, Possible fit, Weak fit, or Not
suitable.

Be specific. If the blog is a content farm, a paid-placement mill, a directory,
or an aggregator, say so plainly. If it is a credible editorial target, say why.
Do not guess and do not contact anyone.
"""

    return _run_agent_in_worker(pr_fit_agent, prompt)


def research_journalists(
    angle: PRAngle,
    opportunity: PROpportunity,
) -> JournalistResearchResults:
    """Find evidence-supported journalists for an approved PR opportunity."""

    prompt = f"""
Research relevant journalists or writers for this HUMAN-APPROVED {BRAND_NAME} PR opportunity.

PR ANGLE:
{angle.angle}

STORY HYPOTHESIS:
{angle.story_hypothesis}

BRAND CONTRIBUTION:
{angle.brand_contribution}

APPROVED OPPORTUNITY:
Publication: {opportunity.publication}
Article title: {opportunity.article_title}
Article URL: {opportunity.article_url}
Published date: {opportunity.published_date}
Topic: {opportunity.topic}
Opportunity type: {opportunity.opportunity_type}
Why relevant: {opportunity.why_relevant}
Recommended action: {opportunity.recommended_action}
Evidence: {opportunity.evidence}

Find up to five real people whose verified published work is relevant to this precise topic.
Prefer recent bylined articles and official author pages. Return no speculative email addresses.
If you cannot verify relevant people, return an empty list rather than inventing contacts.
"""

    return _run_agent_in_worker(journalist_agent, prompt)


def research_listicles(
    search_theme: str,
    related_queries: str = "",
    target_audience: str = "All relevant audiences",
    target_market: str = "Global English-language",
    competitors: list[str] | None = None,
    max_results: int = 15,
) -> ListicleResearchResults:
    """Find and qualify existing listicles for potential brand inclusion."""

    if not search_theme or not search_theme.strip():
        raise ValueError("A listicle search theme is required.")

    max_results = max(3, min(int(max_results), 20))
    competitors = competitors or []

    prompt = f"""
Research existing listicle opportunities for {BRAND_NAME}.

PRIMARY SEARCH THEME:
{search_theme.strip()}

RELATED SEARCH QUERIES / CATEGORIES:
{related_queries.strip() or "Generate relevant variations from the primary theme."}

TARGET AUDIENCE:
{target_audience}

TARGET MARKET:
{target_market}

COMPETITORS TO CHECK WHEN RELEVANT:
{", ".join(competitors) if competitors else "None supplied."}

RESULT LIMIT:
Return up to {max_results} distinct candidate pages.

{BRAND_NAME} is {PRODUCT_DESCRIPTION}. Only claim a feature is a fit if it is
relevant to the listicle topic. Do not invent capabilities.

Search using 2-3 query variations. Look for existing
best-of articles, product roundups, alternatives pages, comparisons, and directories. Focus
on actual pages a person could review and potentially pursue for inclusion.

Distinguish editorial and affiliate roundups from paid/sponsored opportunities and directories.
Do not assume a page is free to submit. Do not invent why {BRAND_NAME} is missing, contact names,
email addresses, publication dates, competitor mentions, or URLs.

Return a deduplicated shortlist, up to the stated limit. Include fewer results if there are not
enough credible matches. Provide a clear research summary and evidence for every candidate.
"""

    return _run_agent_in_worker(listicle_agent, prompt)


def research_listicle_contact(
    item: ListicleOpportunity,
) -> ListicleContactResearchResults:
    """Find verified public professional contact routes for a specific listicle."""

    prompt = f"""
Find the best public professional contact route for this existing listicle.

PUBLICATION: {item.publication}
LISTICLE TITLE: {item.listicle_title}
LISTICLE URL: {item.listicle_url}
PUBLISHED OR UPDATED: {item.published_or_updated}
PLACEMENT TYPE: {item.placement_type}
CURRENT CONTACT ROUTE FROM INITIAL RESEARCH: {item.contact_route}
RECOMMENDED ACTION: {item.recommended_action}

Research the exact article and official publication pages. Find the bylined author,
relevant editor, official submission/contact page, or the official affiliate or sponsored
content route if applicable. Prefer the contact responsible for tool roundups and inclusion.

Return up to three suitable, verified routes. Include a professional email only if it is
explicitly published on a reliable public page. Do not guess email addresses. If a direct
contact cannot be verified, return the best official contact form/page and explain the limit.
Do not contact the publisher.
"""

    return _run_agent_in_worker(listicle_contact_agent, prompt)


def research_journalist_email(
    person: JournalistProfile,
    opportunity: PROpportunity | None = None,
) -> JournalistEmailResearch:
    """Find only explicitly published contact addresses for one journalist."""

    prompt = f"""
Find a published contact email for this journalist.

NAME: {person.name}
PUBLICATION: {person.publication}
CURRENT ROLE: {person.current_role}
AUTHOR PROFILE OR CONTACT PAGE: {person.author_profile_or_contact_page}
RECENT ARTICLE: {person.relevant_article_title}
ARTICLE URL: {person.relevant_article_url}
ARTICLE DATE: {person.article_date}
TOPIC COVERED: {person.topic_covered}
"""
    if opportunity is not None:
        prompt += f"""
TARGET OPPORTUNITY: {opportunity.article_title}
TARGET URL: {opportunity.article_url}
TARGET PUBLICATION: {opportunity.publication}
"""

    prompt += """
Check the author profile, the publication's contact or masthead page, the
person's own site, and public bios. Return only addresses that are literally
published on a page you visited, with the exact source URL and the surrounding
text. If no address is published, return no candidates and explain the best
verified contact route instead. Never guess an email address.
"""

    return _run_agent_in_worker(journalist_email_agent, prompt)


def find_opportunity_contact(opportunity: PROpportunity) -> OpportunityContact:
    """Find the author or editorial contact for one article in a single call."""

    prompt = f"""
Find the best content, SEO, or link-building contact for this exact article.

PUBLICATION: {opportunity.publication}
ARTICLE TITLE: {opportunity.article_title}
ARTICLE URL: {opportunity.article_url}
PUBLISHED: {opportunity.published_date}
TOPIC: {opportunity.topic}
WHY IT MATTERS: {opportunity.why_relevant}

Start with the exact article URL and identify the bylined writer. Then check the
author profile, the about/team page, the editorial or contributor guidelines,
and the contact page. Look specifically for a content manager, SEO manager,
link-building/outreach manager, or partnerships contact. Prefer a named person
with a published email; otherwise return the official content or editorial
contact page or form. Never guess an email. Include the source URL and evidence.
"""

    return _run_agent_in_worker(opportunity_contact_agent, prompt)



def research_publisher_policy(
    item: ListicleOpportunity,
) -> PublisherPolicyAssessment:
    """Check a listicle publisher's explicit policy before pursuing inclusion."""

    prompt = f"""
Assess the publisher policy and best next route for this exact {BRAND_NAME} listicle prospect.

PUBLICATION: {item.publication}
TARGET PAGE TITLE: {item.listicle_title}
TARGET PAGE URL: {item.listicle_url}
PUBLISHED / UPDATED: {item.published_or_updated}
PLACEMENT TYPE FROM INITIAL RESEARCH: {item.placement_type}
BRAND CURRENTLY LISTED: {item.brand_currently_listed}
INCLUSION GAP: {item.inclusion_gap}
CURRENT CONTACT ROUTE: {item.contact_route}
INITIAL RECOMMENDATION: {item.recommended_action}

Search the target page and official publisher policy pages for rules about product-inclusion
requests, link requests, editorial suggestions, paid/sponsored placements, affiliate routes,
and vendor/directory submissions. Distinguish explicit policies from policies you could not find.

If the exact page is a directory rather than an editorial listicle, clearly state that and recommend
the official vendor listing process if verified. If {BRAND_NAME} is already listed, say so.
Return the specific policy source URL and factual evidence. Never contact the publisher or submit forms.
"""

    return _run_agent_in_worker(publisher_policy_agent, prompt)


# =========================================================
# OUTREACH DRAFT FUNCTIONS
# =========================================================

def draft_journalist_pitch(
    opportunity: PROpportunity,
    person: JournalistProfile,
    angle_context: str = "",
    sender_name: str = HARDCODED_SENDER_NAME,
    sender_role: str = HARDCODED_SENDER_ROLE,
) -> OutreachDraft:
    """Draft a personalized Digital PR pitch for human review. Never sends."""

    sender_line = (
        f"SENDER NAME: {sender_name or HARDCODED_SENDER_NAME}\n"
        f"SENDER ROLE: {sender_role or HARDCODED_SENDER_ROLE}\n"
    )

    prompt = f"""
Write a Digital PR pitch draft for human review. Do not send anything.

{sender_line}
BRAND: {BRAND_NAME}
PRODUCT: {PRODUCT_DESCRIPTION}

PR ANGLE:
{angle_context or opportunity.why_relevant}

TARGET JOURNALIST:
Name: {person.name}
Publication: {person.publication}
Verified role: {person.current_role}
Topic covered: {person.topic_covered}
Relevant published article: {person.relevant_article_title}
Article URL: {person.relevant_article_url}
Article date: {person.article_date}
Why relevant: {person.why_relevant}
Suggested angle from research: {person.suggested_pitch_angle}
Research evidence: {person.evidence}
Known public profile or contact page: {person.author_profile_or_contact_page}

TARGET OPPORTUNITY:
Publication: {opportunity.publication}
Article: {opportunity.article_title}
URL: {opportunity.article_url}
Published: {opportunity.published_date}
Topic: {opportunity.topic}
Why this article matters: {opportunity.why_relevant}
Credible brand contribution: {opportunity.brand_contribution}
Research evidence: {opportunity.evidence}

Write a concise pitch that references the journalist's specific work and offers the
brand's contribution. Use only the verified facts above. Use the supplied sender name
and role exactly; do not invent or alter them. Put any other missing detail in
[verify: ...] placeholders and list it in facts_to_verify. If the journalist profile
or contact route is Unknown, set channel to 'Official publication contact route' and
note in compliance_notes that the route must be verified first.
"""

    return _run_agent_in_worker(outreach_draft_agent, prompt)


def draft_listicle_inclusion_request(
    item: ListicleOpportunity,
    contact: ListicleContact,
    policy: PublisherPolicyAssessment | None = None,
    sender_name: str = HARDCODED_SENDER_NAME,
    sender_role: str = HARDCODED_SENDER_ROLE,
) -> OutreachDraft:
    """Draft a listicle inclusion request for human review. Never sends or submits."""

    disposition = policy.recommended_disposition if policy else "Needs verification"
    policy_text = policy.policy_summary if policy else "No policy assessment was supplied."
    policy_route = policy.recommended_route if policy else "Research further"
    policy_evidence = policy.policy_evidence if policy else "No policy evidence was supplied."

    prompt = f"""
Write a listicle inclusion request for human review. Do not send or submit anything.

SENDER NAME: {sender_name or HARDCODED_SENDER_NAME}
SENDER ROLE: {sender_role or HARDCODED_SENDER_ROLE}

BRAND: {BRAND_NAME}
PRODUCT: {PRODUCT_DESCRIPTION}

TARGET PAGE:
Publication: {item.publication}
Title: {item.listicle_title}
URL: {item.listicle_url}
Published or updated: {item.published_or_updated}
Category: {item.listicle_category}
Target audience: {item.target_audience}
Placement type: {item.placement_type}
Competitors verified on the page: {', '.join(item.competitors_listed) if item.competitors_listed else 'None verified'}
Brand currently listed: {item.brand_currently_listed}
Why the brand may fit: {item.brand_fit}
Inclusion gap: {item.inclusion_gap}
Initial contact route: {item.contact_route}

VERIFIED CONTACT:
Name: {contact.contact_name}
Role: {contact.current_role}
Professional email: {contact.professional_email}
Best contact method: {contact.contact_method}
Contact page: {contact.contact_page_url}
Why this contact: {contact.why_this_contact}
Evidence: {contact.evidence}

PUBLISHER POLICY:
Recommended disposition: {disposition}
Recommended route: {policy_route}
Policy summary: {policy_text}
Policy evidence: {policy_evidence}

Rules:
- If the recommended disposition is Do not pursue or Already listed, do not write a pitch.
  Put the blocking reason in compliance_notes and keep the body to a brief internal note.
- If the documented route is paid, sponsored, affiliate, or a directory listing, ask about
  that documented process. Do not request a free editorial inclusion.
- Do not claim the brand is better than a listed competitor.
- Use only verified product facts. Put missing details in [verify: ...] placeholders.
- The channel must match the verified contact method. If no email is published, use the
  official form or contact page, not an invented email.
"""

    return _run_agent_in_worker(outreach_draft_agent, prompt)

