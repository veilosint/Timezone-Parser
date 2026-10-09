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
# Username candidate detection
# ------------------------------------------------------------------

def _is_short_token(line: str) -> Optional[str]:
    """A username candidate: short line, no spaces, no timestamp, alphanumeric."""
    line = line.strip()
    if not line or len(line) > 40:
        return None
    if " " in line:
        return None
    if _extract_timestamp(line):
        return None
    if not re.match(r"^[A-Za-z0-9_\-\.]+$", line):
        return None
    return line


# ------------------------------------------------------------------
# Pattern detection
# ------------------------------------------------------------------

def detect_patterns(lines: list[str], min_occurrences: int = 3) -> list[dict]:
    """Find repeating (short_token, timestamp) pairs, ranked by consistency."""
    ts_indices = [i for i, ln in enumerate(lines) if _extract_timestamp(ln)]
    if len(ts_indices) < min_occurrences:
        return []

    offset_counts = Counter()
    offset_examples = defaultdict(list)

    for idx in ts_indices:
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


def filter_by_consistency(records: list[dict], drop_below: float = 0.5) -> list[dict]:
    """Drop records whose username is rare in the file."""
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
# Quick test when run directly
# ------------------------------------------------------------------

if __name__ == "__main__":
    SAMPLE = """
BRO I AM THE BEST ENG
TESTDUMMY123
Today at 12:40 PM
ewgg23t

BRO I AM NOT THE BEST ENG
TESTDUMMY123
Today at 12:41 PM
ewqg3

hello world this is another message
OTHERUSER456
Today at 3:15 PM
hey how are you

TESTDUMMY123
Today at 5:00 PM
back again
"""
    print("=== DETECTED PATTERNS ===")
    for p in detect_patterns(SAMPLE.splitlines()):
        print(f"  offset={p['token_offset']}  score={p['score']}  occurrences={p['occurrences']}")

    print("\n=== RECORDS ===")
    for r in parse_message_log(SAMPLE):
        print(f"  {r['name']:<16} {r['weekday']:<10} {r['hour']:02d}:{r['minute']:02d}")
