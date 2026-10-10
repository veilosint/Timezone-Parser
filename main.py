"""
Timestamp Extraction API

Takes raw text (or an uploaded file) + a username + the timezone the
timestamps were written in, and returns the timestamps found on lines
that contain that username. All parsing rules live in extractor.py;
timezone input handling lives in timezones.py.

Run locally:  uvicorn main:app --reload
"""
from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from extractor import decode_upload, extract_timestamps
from timezones import dropdown_options, display_label, resolve_timezone

app = FastAPI(title="Timestamp Extraction API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # lock this down to your Lovable domain before going live
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _reference_date(timezone: str, reference_date: Optional[date]) -> date:
    """What 'today' means: the given date, or today's date in the chosen timezone."""
    try:
        tz = resolve_timezone(timezone)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return reference_date or datetime.now(tz).date()


def _response(timezone: str, timestamps: list) -> dict:
    # "timezone" is first so it appears at the top of the output
    return {"timezone": display_label(timezone), "timestamps": timestamps}


class ExtractRequest(BaseModel):
    text: str
    target: str
    timezone: str = "UTC"                  # EST, PST, UTC-5, America/New_York, ...
    reference_date: Optional[date] = None  # overrides "today" (YYYY-MM-DD)
    day_first: bool = False                # True for DD/MM dates


@app.get("/api/timezones")
def timezones():
    """Options for the timezone dropdown (EST, PST, ...)."""
    return dropdown_options()


@app.post("/api/extract")
def extract(req: ExtractRequest):
    ref = _reference_date(req.timezone, req.reference_date)
    return _response(req.timezone, extract_timestamps(req.text, req.target, ref, req.day_first))


@app.post("/api/extract-file")
async def extract_file(
    file: UploadFile = File(..., description="A text export (.txt, .log, .csv, ...)"),
    target: str = Form(..., description="Exact username"),
    timezone: str = Form("UTC", description="EST, PST, UTC-5, America/New_York, ..."),
    reference_date: Optional[str] = Form(None, description="YYYY-MM-DD; blank = today"),
    day_first: bool = Form(False),
):
    """Same as /api/extract, but the text comes from an uploaded file."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (10 MB max).")
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")

    ref_date = None
    if reference_date and reference_date.strip():
        try:
            ref_date = date.fromisoformat(reference_date.strip())
        except ValueError:
            raise HTTPException(400, "reference_date must be YYYY-MM-DD.")

    ref = _reference_date(timezone, ref_date)
    text = decode_upload(data)
    return _response(timezone, extract_timestamps(text, target, ref, day_first))
