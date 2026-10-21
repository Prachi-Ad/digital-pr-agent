import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent import analyze_article

app = FastAPI()


class Req(BaseModel):
    article_url: str


@app.post("/")
def handle(req: Req):
    url = (req.article_url or "").strip()
    if not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Please enter a valid HTTPS URL.")
    try:
        return analyze_article(url).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))