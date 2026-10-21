import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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


class AnalyzeRequest(BaseModel):
    article_url: str


class OpportunitiesRequest(BaseModel):
    angle: PRAngle


class JournalistsRequest(BaseModel):
    angle: PRAngle
    opportunity: PROpportunity


class ListiclesRequest(BaseModel):
    search_theme: str
    related_queries: str = ""
    target_audience: str = "All relevant audiences"
    target_market: str = "Global English-language"
    competitors: list[str] = Field(default_factory=list)
    max_results: int = 15


class ListicleItemRequest(BaseModel):
    item: ListicleOpportunity


def _check_url(url: str) -> str:
    url = (url or "").strip()
    if not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Please enter a valid HTTPS URL.")
    return url


@app.get("/")
def root():
    return {"status": "ok", "service": "digital-pr-agent"}


@app.post("/")
@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    url = _check_url(req.article_url)
    try:
        return analyze_article(url).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/opportunities")
def opportunities(req: OpportunitiesRequest):
    try:
        return research_opportunities(req.angle).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/journalists")
def journalists(req: JournalistsRequest):
    try:
        return research_journalists(req.angle, req.opportunity).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/listicles")
def listicles(req: ListiclesRequest):
    try:
        return research_listicles(
            search_theme=req.search_theme,
            related_queries=req.related_queries,
            target_audience=req.target_audience,
            target_market=req.target_market,
            competitors=req.competitors or None,
            max_results=req.max_results,
        ).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/listicle-contact")
def listicle_contact(req: ListicleItemRequest):
    try:
        return research_listicle_contact(req.item).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/publisher-policy")
def publisher_policy(req: ListicleItemRequest):
    try:
        return research_publisher_policy(req.item).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))