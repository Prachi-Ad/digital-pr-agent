import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent import research_listicles

app = FastAPI()


class Req(BaseModel):
    search_theme: str
    related_queries: str = ""
    target_audience: str = "All relevant audiences"
    target_market: str = "Global English-language"
    competitors: list[str] = Field(default_factory=list)
    max_results: int = 15


@app.post("/")
def handle(req: Req):
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