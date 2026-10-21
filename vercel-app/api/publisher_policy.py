import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent import ListicleOpportunity, research_publisher_policy

app = FastAPI()


class Req(BaseModel):
    item: ListicleOpportunity


@app.post("/")
def handle(req: Req):
    try:
        return research_publisher_policy(req.item).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))