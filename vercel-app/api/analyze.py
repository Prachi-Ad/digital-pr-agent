import os
import sys
import time
from urllib.parse import urlsplit

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from _security import guard, log_request, remaining_quota
from dr import configured as dr_configured
from dr import get_domain_ratings

from agent import (
    BRAND_DOMAIN as AGENT_BRAND_DOMAIN,
    PRAngle,
    PROpportunity,
    JournalistProfile,
    JournalistResearchResults,
    ListicleOpportunity,
    ListicleContact,
    analyze_article,
    draft_journalist_pitch,
    draft_listicle_inclusion,
    find_opportunity_contact,
    collect_media_contacts,
    safe_website_url,
    sanitize_payload,
    research_opportunities,
    research_journalists,
    research_listicles,
    research_listicle_contact,
    research_publisher_policy,
    research_person_contact,
    scan_domain_articles,
)

app = FastAPI()


class AnalyzeRequest(BaseModel):
    action: str = "analyze"
    article_url: str = ""
    domain: str = ""
    topic_hint: str = ""
    query: str = ""
    domains: list[str] = Field(default_factory=list)
    angle: PRAngle | None = None
    opportunity: PROpportunity | None = None
    person: JournalistProfile | None = None
    angle_context: str = ""
    search_theme: str = ""
    related_queries: str = ""
    target_audience: str = "All relevant audiences"
    target_market: str = "Global English-language"
    competitors: list[str] = Field(default_factory=list)
    max_results: int = 15
    item: ListicleOpportunity | None = None
    contact: ListicleContact | None = None


def _check_url(url: str) -> str:
    url = (url or "").strip()
    if not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Please enter a valid HTTPS URL.")
    return url


def _text(value: object, limit: int) -> str:
    """Cap free-text fields so pasted walls of text cannot bloat a prompt."""
    return str(value or "").strip()[:limit]


def _competitors(values: object) -> list[str]:
    items = values if isinstance(values, list) else []
    return [_text(item, 60) for item in items[:10] if str(item or "").strip()]


def _host_of(url: str) -> str:
    try:
        return urlsplit(str(url or "")).hostname or ""
    except ValueError:
        return ""


def drop_own_domain(payload: dict, key: str, url_field: str) -> dict:
    """Remove candidates hosted on the brand's own site (they are not pitch targets)."""
    if not AGENT_BRAND_DOMAIN:
        return payload
    items = payload.get(key)
    if not isinstance(items, list):
        return payload
    kept = []
    for item in items:
        host = _host_of(item.get(url_field, "")).lower()
        if host == AGENT_BRAND_DOMAIN or host.endswith("." + AGENT_BRAND_DOMAIN):
            continue
        kept.append(item)
    payload[key] = kept
    return payload


def _check_domain(domain: str) -> str:
    domain = (domain or "").strip().lower()
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    if domain.startswith("www."):
        domain = domain[4:]
    domain = domain.split("/")[0].split("?")[0].strip().rstrip(".")
    if not domain or "." not in domain or " " in domain:
        raise HTTPException(status_code=400, detail="Enter a valid domain, e.g. example.com.")
    if AGENT_BRAND_DOMAIN and (
        domain == AGENT_BRAND_DOMAIN or domain.endswith("." + AGENT_BRAND_DOMAIN)
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{domain} is your own site. Enter a publisher domain you want coverage from, "
                "for example hootsuite.com."
            ),
        )
    return domain


def _dispatch(req: AnalyzeRequest):
    action = (req.action or "analyze").strip().lower()
    try:
        if action == "analyze":
            url = _check_url(req.article_url)
            return analyze_article(url).model_dump()
        if action == "opportunities":
            if req.angle is None:
                raise HTTPException(status_code=400, detail="angle is required")
            result = research_opportunities(req.angle).model_dump()
            return drop_own_domain(result, "opportunities", "article_url")
        if action == "draft":
            if req.opportunity is None or req.person is None:
                raise HTTPException(
                    status_code=400,
                    detail="opportunity and person are required",
                )
            return draft_journalist_pitch(
                req.opportunity,
                req.person,
                angle_context=_text(
                    req.angle_context
                    or (req.angle.angle if req.angle is not None else ""),
                    1000,
                ),
            ).model_dump()
        if action == "journalists":
            if req.angle is None or req.opportunity is None:
                raise HTTPException(status_code=400, detail="angle and opportunity are required")
            result = research_journalists(req.angle, req.opportunity)
            if result.journalists:
                return result.model_dump()
            # Never dead-end at "no journalist". Fall back to the publication's
            # content/SEO/link-building contact, which is still a valid prospect.
            contact = find_opportunity_contact(req.opportunity)
            name = (contact.contact_name or "").strip()
            if not name or name.lower() in {"not found", "unknown", "n/a"}:
                name = f"{req.opportunity.publication} content team"
            profile = JournalistProfile(
                name=name,
                publication=req.opportunity.publication,
                current_role=(contact.role or "").strip() or "Content/SEO contact",
                relevant_article_title=req.opportunity.article_title,
                relevant_article_url=req.opportunity.article_url,
                article_date=req.opportunity.published_date,
                topic_covered=req.opportunity.topic,
                why_relevant=contact.evidence or req.opportunity.why_relevant,
                suggested_pitch_angle=contact.route or "Relevant content contribution",
                author_profile_or_contact_page=(
                    contact.contact_page_url or contact.source_url or "Unknown"
                ),
                evidence=contact.evidence or "",
                confidence=contact.confidence or "Medium",
            )
            return JournalistResearchResults(
                selected_opportunity=req.opportunity.article_title,
                research_summary=(
                    "No named writer matched the exact angle. The best verified "
                    "content, SEO, or editorial contact for this publication is "
                    "shown instead."
                ),
                journalists=[profile],
            ).model_dump()
        if action == "listicles":
            if not req.search_theme.strip():
                raise HTTPException(status_code=400, detail="search_theme is required")
            result = research_listicles(
                search_theme=_text(req.search_theme, 200),
                related_queries=_text(req.related_queries, 300),
                target_audience=_text(req.target_audience, 150),
                target_market=_text(req.target_market, 150),
                competitors=_competitors(req.competitors) or None,
                max_results=max(3, min(10, req.max_results)),
            ).model_dump()
            return drop_own_domain(result, "opportunities", "listicle_url")
        if action in ("listicle-contact", "listicle_contact"):
            if req.item is None:
                raise HTTPException(status_code=400, detail="item is required")
            return research_listicle_contact(req.item).model_dump()
        if action in ("publisher-policy", "publisher_policy"):
            if req.item is None:
                raise HTTPException(status_code=400, detail="item is required")
            return research_publisher_policy(req.item).model_dump()
        if action in ("domain-scan", "domain_scan"):
            domain = _check_domain(req.domain)
            result = scan_domain_articles(domain, _text(req.topic_hint, 200)).model_dump()
            return drop_own_domain(result, "articles", "article_url")
        if action in ("person-contact", "person_contact"):
            if req.person is None or req.opportunity is None:
                raise HTTPException(
                    status_code=400,
                    detail="person and opportunity are required",
                )
            return research_person_contact(req.person, req.opportunity).model_dump()
        if action in ("site-metrics", "site_metrics"):
            cleaned: list[str] = []
            for d in req.domains or []:
                try:
                    norm = _check_domain(d)
                except HTTPException:
                    continue
                if norm not in cleaned:
                    cleaned.append(norm)
            if not cleaned:
                raise HTTPException(status_code=400, detail="Send 1-10 valid domains.")
            return {"metrics": get_domain_ratings(cleaned[:10]), "attribution": "Domain Rating by Ahrefs"}
        if action in ("collect-writers", "collect_writers"):
            if not req.query.strip():
                raise HTTPException(status_code=400, detail="query is required")
            return collect_media_contacts(_text(req.query, 300)).model_dump()
        if action in ("listicle-draft", "listicle_draft"):
            if req.item is None or req.contact is None:
                raise HTTPException(status_code=400, detail="item and contact are required")
            return draft_listicle_inclusion(req.item, req.contact).model_dump()
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")
    except HTTPException:
        raise
    except ValueError as e:
        # Intentional, user-facing validation messages only.
        raise HTTPException(status_code=400, detail=str(e)[:300])
    except Exception as e:
        # Log the real error, never leak internals to the browser.
        print(f"dispatch_error action={action} error={type(e).__name__}: {str(e)[:300]}", flush=True)
        raise HTTPException(
            status_code=500,
            detail="That research step failed. Try again; if it repeats, tell Prachi to check the server logs.",
        )


@app.get("/")
@app.get("/analyze")
@app.get("/api/analyze")
def health(request: Request):
    """Health plus the caller's remaining research budget. Never bills a call."""
    return {
        "status": "ok",
        "service": "digital-pr-agent",
        "dr_ready": dr_configured(),
        "brand_domain": AGENT_BRAND_DOMAIN,
        **remaining_quota(request),
    }


@app.post("/")
@app.post("/analyze")
@app.post("/api/analyze")
def handle(req: AnalyzeRequest, request: Request):
    action = (req.action or "analyze").strip().lower()
    # Reject unsafe links before spending a research call.
    if action == "analyze" and not safe_website_url(req.article_url):
        raise HTTPException(
            status_code=400,
            detail="Enter a normal public https article link, like https://example.com/article.",
        )
    guard(request)
    log_request(request, action)
    last = None
    for attempt in range(2):
        try:
            # Model output is untrusted: strip unsafe links, invalid emails and
            # out-of-range scores before anything reaches the browser.
            return sanitize_payload(_dispatch(req))
        except HTTPException:
            raise
        except Exception as e:
            last = e
            if attempt == 0:
                time.sleep(2)
    print(f"handler_error action={action} error={type(last).__name__}: {str(last)[:300]}", flush=True)
    raise HTTPException(
        status_code=500,
        detail="That research step failed. Try again; if it repeats, tell Prachi to check the server logs.",
    )