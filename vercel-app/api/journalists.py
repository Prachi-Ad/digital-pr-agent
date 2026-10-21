import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent import PRAngle, PROpportunity, research_journalists

app = FastAPI()


class Req(BaseModel):
    angle: PRAngle
    opportunity: PROpportunity


@app.post("/")
def handle(req: Req):
    try:
        return research_journalists(req.angle, req.opportunity).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))