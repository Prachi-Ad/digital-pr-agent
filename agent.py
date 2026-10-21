import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from agents import Agent, Runner, WebSearchTool
from pydantic import BaseModel, Field


# =========================================================
# MODEL CONFIGURATION
# =========================================================
# Cost-optimized default. Override with an environment variable if needed:
#   VISTA_OPENAI_MODEL=gpt-5-nano       (lowest per-token price)
#   VISTA_OPENAI_MODEL=gpt-4.1-nano
#   VISTA_SEARCH_CONTEXT=medium|low     (fewer search content tokens)
DEFAULT_MODEL = "gpt-5.4-nano"
MODEL = (os.environ.get("OPENAI_MODEL") or os.environ.get("VISTA_OPENAI_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL

SEARCH_CONTEXT_SIZE = (os.environ.get("SEARCH_CONTEXT_SIZE") or os.environ.get("VISTA_SEARCH_CONTEXT") or "high").strip().lower()
if SEARCH_CONTEXT_SIZE not in {"low", "medium", "high"}:
    SEARCH_CONTEXT_SIZE = "high"

# Brand configuration (override to reuse this tool for any product/company)
BRAND_NAME = (os.environ.get("BRAND_NAME") or os.environ.get("VISTA_BRAND_NAME") or "Your Brand").strip() or "Your Brand"
PRODUCT_DESCRIPTION = (os.environ.get("PRODUCT_DESCRIPTION") or os.environ.get("VISTA_PRODUCT_DESCRIPTION") or "a software product").strip() or "a software product"


# =========================================================
# ASSET INTELLIGENCE MODELS
# =========================================================

class Statistic(BaseModel):
    statistic: str = Field(description="The statistic or factual data point.")
    source: str = Field(description="The source of the statistic, if identified.")
    data_provenance: str = Field(
        description=(
            "Classify as {BRAND_NAME} original data, external primary source, "
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
    relevant_asset: str = Field(description="The existing the brand asset supporting the angle.")
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
    brand_contribution: str = Field(description="What the brand could credibly contribute.")
    competitor_mention: str = Field(description="A verified competitor mention, or None identified.")
    topical_relevance: str = Field(description="High, Medium, or Low, with reasoning.")
    editorial_fit: str = Field(description="High, Medium, or Low, with reasoning.")
    recommended_action: str = Field(description="The recommended next action.")
    evidence: str = Field(description="Evidence supporting the recommendation.")
    confidence: str = Field(description="Confidence level: High, Medium, or Low.")


class PRResearchResults(BaseModel):
    selected_angle: str = Field(description="The PR angle being researched.")
    research_summary: str = Field(description="A concise summary of the research findings.")
    opportunities: list[PROpportunity] = Field(description="The strongest relevant editorial candidates.")



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
        description="Use Yes, No, or Unclear, based on whether the article was actually checked for the brand."
    )
    brand_fit: str = Field(
        description="Explain how the brand's known product category and capabilities match this listicle's inclusion criteria."
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
    output_type=AssetAnalysis,
)


# =========================================================
# OPPORTUNITY RESEARCH AGENT
# =========================================================

opportunity_agent = Agent(
    name="PR Opportunity Researcher",
    instructions=f"""
You are a Digital PR opportunity researcher for {BRAND_NAME}.

Find real existing articles and editorial conversations that match the
supplied PR angle.

Research process:
1. Understand the angle and {BRAND_NAME}'s contribution.
2. Search the web using several relevant topic variations.
3. Find specific existing articles, not just website homepages.
4. Evaluate topical and editorial relevance.
5. Check whether {BRAND_NAME} can make a credible contribution.
6. Check competitor mentions when the evidence is available.
7. Exclude generic SEO opportunities that lack a real editorial reason.
8. Return the strongest candidates, up to 10.

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
    output_type=PRResearchResults,
)




# =========================================================
# JOURNALIST RESEARCH AGENT
# =========================================================

journalist_agent = Agent(
    name="Journalist Researcher",
    instructions=f"""
You are a journalist researcher supporting a human-led Digital PR workflow for {BRAND_NAME}.

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
- Prefer a larger set of qualified candidates over a tiny set, while preserving relevance and deduplication.
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
    output_type=ListicleContactResearchResults,
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
    output_type=PublisherPolicyAssessment,
)


# =========================================================
# RUNNER HELPER: USE A SEPARATE THREAD AND EVENT LOOP
# =========================================================

def _run_agent_in_worker(agent_to_run, prompt: str):
    """Run an async agent in a separate worker thread to avoid event-loop conflicts."""

    def execute_with_own_loop():
        return asyncio.run(Runner.run(agent_to_run, prompt))

    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(execute_with_own_loop).result()

    return result.final_output


# =========================================================
# PUBLIC FUNCTIONS USED BY app.py
# =========================================================

def analyze_article(article_url: str) -> AssetAnalysis:
    """Analyze a the brand article and return structured asset intelligence."""
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
Return up to 10 strong candidates.
"""
    return _run_agent_in_worker(opportunity_agent, prompt)


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
    """Find and qualify existing listicles for potential the brand inclusion."""

    if not search_theme or not search_theme.strip():
        raise ValueError("A listicle search theme is required.")

    max_results = max(5, min(int(max_results), 20))
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

{BRAND_NAME} is {PRODUCT_DESCRIPTION}. Its potential inclusion fit may involve
social media management, scheduling and publishing, engagement, analytics, social listening,
team workflows, and tools for agencies or businesses. Do not claim a feature is a fit unless
it is relevant to the listicle topic.

Search broadly across the supplied related queries and useful variants. Look for existing
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

