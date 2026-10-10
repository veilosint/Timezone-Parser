from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from parser import parse_message_log

RATE_LIMIT = "5/minute"

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Timezone Parser API")
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


def _build_response(log_text: str, username: str | None):
    records = parse_message_log(log_text, username_filter=username)

    if not records:
        raise HTTPException(
            status_code=422,
            detail="No lines with both a username and a timestamp were found.",
        )

    timestamps = [
        {
            "timestamp": r["timestamp"],
            "weekday": r["weekday"],
            "hour": r["hour"],
            "minute": r["minute"],
            "ampm": r["ampm"],
        }
        for r in records
    ]

    return {
        "username": username,
        "total_timestamps": len(timestamps),
        "timestamps": timestamps,
    }


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "timezone-parser"}


@app.post("/api/parse")
@limiter.limit(RATE_LIMIT)
async def parse_pasted(request: Request, body: ParseRequest):
    if not body.log_text.strip():
        raise HTTPException(status_code=400, detail="Empty log text")
    return _build_response(body.log_text, body.username)


@app.post("/api/parse-file")
@limiter.limit(RATE_LIMIT)
async def parse_file(
    request: Request,
    file: UploadFile = File(...),
    username: str | None = Form(None),
):
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Could not decode file")

    return _build_response(text, username)
