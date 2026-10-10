"""
Timestamp Extraction API
 
Takes raw text + a username and returns the list of timestamps found on
lines that contain that username. Nothing else - no heatmap, no inference.
All parsing rules live in extractor.py.
 
Run locally:  uvicorn main:app --reload
"""
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo, available_timezones
 
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
 
from extractor import extract_timestamps
 
app = FastAPI(title="Timestamp Extraction API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # lock this down to your Lovable domain before going live
    allow_methods=["*"],
    allow_headers=["*"],
)
 
 
def _reference_date(timezone: str, reference_date: Optional[date]) -> date:
    """What 'today' means: the given date, or today's date in the selected timezone."""
    if reference_date:
        return reference_date
    if timezone not in available_timezones():
        raise HTTPException(400, f"Unknown timezone: {timezone}")
    return datetime.now(ZoneInfo(timezone)).date()
 
 
class ExtractRequest(BaseModel):
    text: str
    target: str
    timezone: str = "UTC"                  # used only to decide what "today" is
    reference_date: Optional[date] = None  # overrides "today" (YYYY-MM-DD)
    day_first: bool = False                # True for DD/MM dates
 
 
@app.get("/api/timezones")
def timezones():
    return sorted(available_timezones())
 
 
@app.post("/api/extract")
def extract(req: ExtractRequest):
    ref = _reference_date(req.timezone, req.reference_date)
    return {"timestamps": extract_timestamps(req.text, req.target, ref, req.day_first)}
 
 
@app.post("/api/extract-raw")
def extract_raw(
    text: str = Body(..., media_type="text/plain",
                     description="Paste the raw text here, no JSON needed."),
    target: str = Query(..., description="Exact username"),
    timezone: str = Query("UTC"),
    reference_date: Optional[date] = Query(None, description="YYYY-MM-DD; defaults to today"),
    day_first: bool = Query(False),
):
    """Same as /api/extract, with a plain-text body for easy testing in /docs."""
    ref = _reference_date(timezone, reference_date)
    return {"timestamps": extract_timestamps(text, target, ref, day_first)}
 
