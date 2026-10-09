from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from collections import Counter

from parser import parse_message_log, detect_patterns
from analyzer import analyze

RATE_LIMIT = "5/minute"

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Timezone Analyzer API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.(lovable\.app|lovableproject\.com|lovable\.dev)|http://localhost:\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ParseRequest(BaseModel):
    log_text: str
    username: str | None = None
    reference_timezone_offset: int = 0


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "timezone-analyzer"}


@app.post("/api/parse")
@limiter.limit(RATE_LIMIT)
async def parse_pasted(request: Request, body: ParseRequest):
    if not body.log_text.strip():
        raise HTTPException(status_code=400, detail="Empty log text")

    lines = body.log_text.splitlines()
    patterns = detect_patterns(lines)
    if not patterns:
        raise HTTPException(
            status_code=422,
            detail="Could not detect a repeating pattern. Need at least 3 timestamps.",
        )

    records = parse_message_log(body.log_text, username_filter=body.username)

    if not body.username and records:
        counts = Counter(r["name"] for r in records)
        most_common = counts.most_common(1)[0][0]
        records = [r for r in records if r["name"] == most_common]
        detected_username = most_common
    else:
        detected_username = body.username or "unknown"

    analysis = analyze(records, detected_username, body.reference_timezone_offset)

    return {
        "detected_patterns": patterns[:3],
        "chosen_pattern": patterns[0],
        "total_records": len(records),
        "records": records,
        "analysis": analysis,
    }


@app.post("/api/parse-file")
@limiter.limit(RATE_LIMIT)
async def parse_file(
    request: Request,
    file: UploadFile = File(...),
    username: str | None = Form(None),
    reference_timezone_offset: int = Form(0),
):
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Could not decode file")

    lines = text.splitlines()
    patterns = detect_patterns(lines)
    if not patterns:
        raise HTTPException(
            status_code=422,
            detail="Could not detect a repeating pattern. Need at least 3 timestamps.",
        )

    records = parse_message_log(text, username_filter=username)

    if not username and records:
        counts = Counter(r["name"] for r in records)
        most_common = counts.most_common(1)[0][0]
        records = [r for r in records if r["name"] == most_common]
        detected_username = most_common
    else:
        detected_username = username or "unknown"

    analysis = analyze(records, detected_username, int(reference_timezone_offset))

    return {
        "detected_patterns": patterns[:3],
        "chosen_pattern": patterns[0],
        "total_records": len(records),
        "records": records,
        "analysis": analysis,
    }
