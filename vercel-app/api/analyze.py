import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent import (
    PRAngle,
    PROpportunity,
    ListicleOpportunity,
    analyze_article,
    research_opportunities,
    research_journalists,
    research_listicles,
    research_listicle_contact,
    research_publisher_policy,
)

app = FastAPI()


class AnalyzeReq(BaseModel):
    action: str = "analyze"
    article_url: str = ""
    angle: PRAngle | None = None
    opportunity: PROpportunity | None = None
    search_theme: str = ""
    related_queries: str = ""
    target_audience: str = "All relevant audiences"
    target_market: str = "Global English-language"
    competitors: list[str] = Field(default_factory=list)
    max_results: int = 15
    item: ListicleOpportunity | None = None


def _check_url(url: str) -> str:
    url = (url or "").strip()
    if not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Please enter a valid HTTPS URL.")
    return url


@app.get("/")
def root():
    return {"status": "ok", "service": "digital-pr-agent"}


@app.post("/")
def handle(req: AnalyzeReq):
    action = (req.action or "analyze").strip().lower()
    try:
        if action == "analyze":
            url = _check_url(req.article_url)
            return analyze_article(url).model_dump()
        if action == "opportunities":
            if req.angle is None:
                raise HTTPException(status_code=400, detail="angle is required")
            return research_opportunities(req.angle).model_dump()
        if action == "journalists":
            if req.angle is None or req.opportunity is None:
                raise HTTPException(status_code=400, detail="angle and opportunity are required")
            return research_journalists(req.angle, req.opportunity).model_dump()
        if action == "listicles":
            if not req.search_theme.strip():
                raise HTTPException(status_code=400, detail="search_theme is required")
            return research_listicles(
                search_theme=req.search_theme,
                related_queries=req.related_queries,
                target_audience=req.target_audience,
                target_market=req.target_market,
                competitors=req.competitors or None,
                max_results=req.max_results,
            ).model_dump()
        if action == "listicle-contact":
            if req.item is None:
                raise HTTPException(status_code=400, detail="item is required")
            return research_listicle_contact(req.item).model_dump()
        if action == "publisher-policy":
            if req.item is None:
                raise HTTPException(status_code=400, detail="item is required")
            return research_publisher_policy(req.item).model_dump()
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))