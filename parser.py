import re
from datetime import datetime, timedelta
from typing import Optional


# ------------------------------------------------------------------
# Timestamp detection
# ------------------------------------------------------------------

def _extract_timestamp(line: str):
    """
    Return (hour, minute, date_or_None) if the line has a time.
    Otherwise return None.
    """
    now = datetime.now()
    hour = None
    minute = None

    # AM/PM time (most specific)
    m = re.search(r"\b(\d{1,2}):(\d{2})\s*([AaPp][Mm])\b", line)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        ampm = m.group(3).upper()
        hour = (0 if hour == 12 else hour) if ampm == "AM" else (12 if hour == 12 else hour + 12)
    else:
        # 24-hour or bare HH:MM
        m = re.search(r"\b([01]?\d|2[0-3]):(\d{2})\b", line)
        if not m:
            return None
        hour = int(m.group(1))
        minute = int(m.group(2))

    # Optional date on the same line
    date = None
    if re.search(r"\bToday\b", line, re.IGNORECASE):
        date = now.date()
    elif re.search(r"\bYesterday\b", line, re.IGNORECASE):
        date = (now - timedelta(days=1)).date()
    else:
        m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", line)
        if m:
            try:
                date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
            except ValueError:
                pass
        else:
            m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", line)
            if m:
                try:
                    year = int(m.group(3))
                    if year < 100:
                        year += 2000
                    date = datetime(year, int(m.group(1)), int(m.group(2))).date()
                except ValueError:
                    pass

    return hour, minute, date


# ------------------------------------------------------------------
# Username detection
# ------------------------------------------------------------------

STOP_WORDS = {
    "post", "posts", "profile", "comment", "comments", "forum",
    "thread", "reply", "replies", "message", "messages", "today",
    "yesterday", "at", "on", "in", "by", "from", "to", "the", "a",
    "an", "and", "or", "of", "for", "with", "is", "was", "are",
    "am", "pm", "just", "now", "ok", "okay", "yes", "no", "yeah",
    "hey", "hi", "hello", "morning", "evening", "night", "afternoon",
    "sure", "same", "cool", "done", "back", "meeting", "lunch",
    "working", "wrapping",
}

def _is_username_like(token: str) -> bool:
    if not token or len(token) < 2 or len(token) > 40:
        return False
    if not re.match(r"^[A-Za-z0-9_\-\.]+$", token):
        return False
    if token.lower() in STOP_WORDS:
        return False
    if token.isdigit():
        return False
    return True


def _extract_username(line: str, time_str: str, date_str: str) -> Optional[str]:
    """
    Strip the time and date from the line, then return the first
    token that looks like a username.
    """
    cleaned = line
    if time_str:
        cleaned = cleaned.replace(time_str, " ")
    if date_str:
        cleaned = cleaned.replace(date_str, " ")

    for token in re.findall(r"[A-Za-z0-9_\-\.]+", cleaned):
        if _is_username_like(token):
            return token
    return None


# ------------------------------------------------------------------
# Line-level parser
# ------------------------------------------------------------------

def parse_message_log(text: str, username_filter: Optional[str] = None) -> list[dict]:
    """
    Scan every line. If it contains BOTH a time and a username-like token,
    extract them and return a record.

    No pattern detection. No multi-line handling. Just line-by-line grep.
    """
    records = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        ts = _extract_timestamp(line)
        if not ts:
            continue

        hour, minute, date = ts

        # Find the raw time and date substrings so we can strip them before
        # looking for the username.
        time_match = re.search(r"\d{1,2}:\d{2}\s*[AaPp][Mm]?", line)
        time_str = time_match.group(0) if time_match else ""

        date_match = re.search(
            r"(\d{4}-\d{1,2}-\d{1,2})|(\d{1,2}/\d{1,2}/\d{2,4})|(Today)|(Yesterday)",
            line, re.IGNORECASE
        )
        date_str = date_match.group(0) if date_match else ""

        name = _extract_username(line, time_str, date_str)
        if not name:
            continue

        # If no date on the line, use today
        if date is None:
            date = datetime.now().date()

        dt = datetime.combine(date, datetime.min.time()).replace(hour=hour, minute=minute)

        records.append({
            "name": name,
            "timestamp": dt.isoformat(),
            "hour": hour,
            "minute": minute,
            "weekday": dt.strftime("%A"),
            "ampm": "AM" if hour < 12 else "PM",
            "raw_line": line,
        })

    # Optional filter to one username
    if username_filter:
        target = username_filter.strip().lower()
        records = [r for r in records if r["name"].lower() == target]

    # Sort chronologically
    records.sort(key=lambda r: r["timestamp"])

    return records
