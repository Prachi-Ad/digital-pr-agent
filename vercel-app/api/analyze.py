import os
import sys

# Vercel mounts this function at /var/task/api/analyze.py; sibling modules live
# in the same directory, which is not on sys.path by default.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent import analyze_article

app = FastAPI()


class AnalyzeRequest(BaseModel):
    article_url: str


@app.get("/")
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/")
@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    url = (req.article_url or "").strip()
    if not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Please enter a valid HTTPS URL.")
    try:
        result = analyze_article(url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result.model_dump()