import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional


# ------------------------------------------------------------------
# Timestamp detection
# ------------------------------------------------------------------

def _extract_timestamp(line: str) -> Optional[tuple[int, int, Optional[datetime.date]]]:
    """If the line contains a time (and optionally a date), return (hour, minute, date_or_None)."""
    now = datetime.now()

    m = re.search(r"\b(\d{1,2}):(\d{2})\s*([AaPp][Mm])\b", line)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        ampm = m.group(3).upper()
        hour = (0 if hour == 12 else hour) if ampm == "AM" else (12 if hour == 12 else hour + 12)
    else:
        m = re.search(r"\b([01]?\d|2[0-3]):(\d{2})\b", line)
        if not m:
            return None
        hour = int(m.group(1))
        minute = int(m.group(2))

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
# Username extraction
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
    """A username is 2+ chars, alphanumeric (with _ - .), and not a stop word."""
    if not token or len(token) < 2 or len(token) > 40:
        return False
    if not re.match(r"^[A-Za-z0-9_\-\.]+$", token):
        return False
    if token.lower() in STOP_WORDS:
        return False
    if token.isdigit():
        return False
    return True


def _extract_name_from_line(line: str) -> Optional[str]:
    """
    Extract a name from a line that has a timestamp on it.
    Removes the timestamp portion first, then finds the first username-like token.
    """
    # Remove time (HH:MM AM/PM or HH:MM)
    cleaned = re.sub(r"\b\d{1,2}:\d{2}\s*([AaPp][Mm])?\b", " ", line)
    # Remove dates
    cleaned = re.sub(r"\b\d{4}-\d{1,2}-\d{1,2}\b", " ", cleaned)
    cleaned = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", " ", cleaned)
    cleaned = re.sub(r"\b(Today|Yesterday)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b",
                     " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b",
                     " ", cleaned, flags=re.IGNORECASE)

    # Find first username-like token
    for token in re.findall(r"[A-Za-z0-9_\-\.]+", cleaned):
        if _is_username_like(token):
            return token
    return None


def _is_short_token(line: str) -> Optional[str]:
    """A line that contains only a username-like token (no spaces)."""
    line = line.strip()
    if not line or len(line) > 40:
        return None
    if " " in line:
        return None
    if _extract_timestamp(line):
        return None
    if _is_username_like(line):
        return line
    return None


# ------------------------------------------------------------------
# Pattern detection
# ------------------------------------------------------------------

def detect_patterns(lines: list[str], min_occurrences: int = 3) -> list[dict]:
    """
    Find repeating (name, timestamp) pairs at various offsets,
    including offset 0 (name on the same line as timestamp).
    """
    ts_indices = [i for i, ln in enumerate(lines) if _extract_timestamp(ln)]
    if len(ts_indices) < min_occurrences:
        return []

    offset_counts = Counter()
    offset_examples = defaultdict(list)

    for idx in ts_indices:
        # Offset 0: name on the same line
        name = _extract_name_from_line(lines[idx])
        if name:
            offset_counts[0] += 1
            if len(offset_examples[0]) < 5:
                offset_examples[0].append(name)

        # Offsets 1-5: name on a line above
        for offset in range(1, 6):
            if idx - offset < 0:
                break
            candidate = _is_short_token(lines[idx - offset])
            if candidate:
                offset_counts[offset] += 1
                if len(offset_examples[offset]) < 5:
                    offset_examples[offset].append(candidate)
                break

    total_ts = len(ts_indices)
    patterns = []
    for offset, count in offset_counts.items():
        score = count / total_ts if total_ts else 0
        patterns.append({
            "token_offset": offset,
            "score": round(score, 3),
            "occurrences": count,
            "examples": offset_examples[offset],
        })

    patterns.sort(key=lambda p: (-p["score"], -p["occurrences"]))
    return patterns


# ------------------------------------------------------------------
# Record extraction
# ------------------------------------------------------------------

def extract_records(lines: list[str], pattern: dict) -> list[dict]:
    """Walk the file and emit records wherever the pattern matches."""
    records = []
    offset = pattern["token_offset"]

    for idx, line in enumerate(lines):
        ts = _extract_timestamp(line)
        if not ts:
            continue
        hour, minute, date = ts
        if date is None:
            continue

        if offset == 0:
            name = _extract_name_from_line(line)
        else:
            token_idx = idx - offset
            if token_idx < 0:
                continue
            name = _is_short_token(lines[token_idx])

        if not name:
            continue

        dt = datetime.combine(date, datetime.min.time()).replace(hour=hour, minute=minute)
        records.append({
            "name": name,
            "timestamp": dt.isoformat(),
            "hour": hour,
            "minute": minute,
            "weekday": dt.strftime("%A"),
            "raw_line": line,
        })

    return records


def filter_by_consistency(records: list[dict], drop_below: float = 0.3) -> list[dict]:
    """
    Drop records whose username is rare.
    Lowered threshold from 0.5 to 0.3 to handle multi-user logs.
    """
    if not records:
        return records
    name_counts = Counter(r["name"] for r in records)
    threshold = len(records) * drop_below
    return [r for r in records if name_counts[r["name"]] >= threshold]


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------

def parse_message_log(text: str, username_filter: Optional[str] = None) -> list[dict]:
    """Parse an unorganized log by detecting the dominant repeating pattern."""
    lines = text.splitlines()

    patterns = detect_patterns(lines)
    if not patterns:
        return []

    best = patterns[0]
    records = extract_records(lines, best)
    if not records:
        return []

    if username_filter:
        target = username_filter.strip().lower()
        records = [r for r in records if r["name"].strip().lower() == target]

    return filter_by_consistency(records)


# ------------------------------------------------------------------
# Quick test
# ------------------------------------------------------------------

if __name__ == "__main__":
    SAMPLE = """
Alice 2026-10-06 09:15
Morning
Bob 2026-10-06 09:20
Morning
Alice 2026-10-06 13:45
Lunch?
Bob 2026-10-06 13:50
Sure
Alice 2026-10-06 18:30
Done for the day
Bob 2026-10-06 18:35
Same
"""
    print("=== PATTERNS ===")
    for p in detect_patterns(SAMPLE.splitlines()):
        print(f"  offset={p['token_offset']}  score={p['score']}  occurrences={p['occurrences']}  examples={p['examples']}")

    print("\n=== RECORDS ===")
    for r in parse_message_log(SAMPLE):
        print(f"  {r['name']:<16} {r['weekday']:<10} {r['hour']:02d}:{r['minute']:02d}")
