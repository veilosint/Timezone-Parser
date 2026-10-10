"""
Timestamp extractor (pure Python, no dependencies).

RULES
-----
A line produces a timestamp only if ALL of these are on the SAME line:
  1. the target username (whole word, case-insensitive)
  2. a valid time: either AM/PM ("9:41 AM", "9pm") or 24-hour with a
     two-digit hour ("09:41", "21:05"). A bare "9:41" is ambiguous -> omitted.
  3. a date: today, yesterday, a weekday name ("Friday"), or an explicit
     date ("9/2", "9/23/2026", "September 23", "23 Sep 2026", "2026-09-23",
     "23.09.2026").

OMITTED
-------
  - date but no time
  - time but no date
  - relative times: "2 minutes ago", "an hour ago", "just now"
  - username and time on different lines
"""
import re
from datetime import date, timedelta
from typing import Optional

_MONTH_NAMES = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_MONTH_NUM = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_WEEKDAY_NUM = {d: i for i, d in enumerate(
    ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])}

# ---- relative phrases to discard ("2 minutes ago", "just now") ------------
_RELATIVE_RE = re.compile(
    r"\b(?:\d+|a\s+few|a\s+couple(?:\s+of)?|an?|one|few|several|couple)\s*"
    r"(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?)\s+ago\b"
    r"|\bjust\s+now\b|\b(?:a\s+)?moments?\s+ago\b",
    re.I,
)

# ---- times ----------------------------------------------------------------
_AMPM_RE = re.compile(
    r"(?<![\d:])(\d{1,2})(?::([0-5]\d))?(?::[0-5]\d)?\s*([AaPp])\.?[Mm]\b\.?")
_24H_RE = re.compile(
    r"(?<![\d:.])([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?(?![\d:]|\s*[AaPp]\.?[Mm]\b)")

# ---- dates ----------------------------------------------------------------
_REL_DAY_RE = re.compile(r"\b(today|yesterday)\b", re.I)
_WEEKDAY_FULL_RE = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
# abbreviations only count when directly followed by a time/date ("Sat 9:10 PM"),
# so ordinary words like "sat down" are not mistaken for weekdays
_WEEKDAY_ABBR_RE = re.compile(
    r"\b(mon|tues?|wed|thu(?:rs?)?|fri|sat|sun)\.?,?\s+(?:at\s+)?(?=\d|@T@)", re.I)
_NAMED_MDY_RE = re.compile(
    rf"\b({_MONTH_NAMES})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b", re.I)
_NAMED_DMY_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_NAMES})\.?(?:,?\s+(\d{{4}}))?\b", re.I)
_ISO_RE = re.compile(r"(?<![\d])(\d{4})-(\d{2})-(\d{2})(?![\d])")
_SLASH_RE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])")
_DOT_RE = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{2,4})(?![\d.])")


def _find_time(s: str):
    """Earliest valid time in s -> (start, end, hour24, minute) or None."""
    cands = []
    for m in _AMPM_RE.finditer(s):
        h = int(m.group(1))
        if not 1 <= h <= 12:
            continue
        mi = int(m.group(2) or 0)
        ap = m.group(3).lower()
        h = (0 if h == 12 else h) + (12 if ap == "p" else 0)
        cands.append((m.start(), m.end(), h, mi))
    for m in _24H_RE.finditer(s):
        cands.append((m.start(), m.end(), int(m.group(1)), int(m.group(2))))
    return min(cands, key=lambda c: c[0]) if cands else None


def _year_for(month: int, day: int, year: Optional[int], ref: date) -> Optional[date]:
    try:
        if year is not None:
            return date(year + 2000 if year < 100 else year, month, day)
        d = date(ref.year, month, day)
        return d if d <= ref else date(ref.year - 1, month, day)  # most recent past
    except ValueError:
        return None


def _find_date(s: str, ref: date, day_first: bool) -> Optional[date]:
    """Earliest date expression in s (time already masked as @T@)."""
    cands: list[tuple[int, date]] = []

    for m in _REL_DAY_RE.finditer(s):
        cands.append((m.start(), ref if m.group(1).lower() == "today"
                      else ref - timedelta(days=1)))

    for rx, abbr in ((_WEEKDAY_FULL_RE, False), (_WEEKDAY_ABBR_RE, True)):
        for m in rx.finditer(s):
            target = _WEEKDAY_NUM[m.group(1).lower()[:3]]
            cands.append((m.start(), ref - timedelta(days=(ref.weekday() - target) % 7)))

    for m in _NAMED_MDY_RE.finditer(s):
        d = _year_for(_MONTH_NUM[m.group(1).lower()[:3]], int(m.group(2)),
                      int(m.group(3)) if m.group(3) else None, ref)
        if d:
            cands.append((m.start(), d))
    for m in _NAMED_DMY_RE.finditer(s):
        d = _year_for(_MONTH_NUM[m.group(2).lower()[:3]], int(m.group(1)),
                      int(m.group(3)) if m.group(3) else None, ref)
        if d:
            cands.append((m.start(), d))

    for m in _ISO_RE.finditer(s):
        try:
            cands.append((m.start(), date(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
        except ValueError:
            pass

    for rx in (_SLASH_RE, _DOT_RE):
        for m in rx.finditer(s):
            a, b = int(m.group(1)), int(m.group(2))
            month, day = (b, a) if day_first else (a, b)
            if month > 12:           # unambiguous: first number must be the day
                month, day = day, month
            d = _year_for(month, day, int(m.group(3)) if m.group(3) else None, ref)
            if d:
                cands.append((m.start(), d))

    return min(cands, key=lambda c: c[0])[1] if cands else None


def extract_timestamps(text: str, target: str, ref: date, day_first: bool = False):
    """Returns a chronologically sorted list of {"date": "YYYY-MM-DD", "time": "HH:MM"}."""
    target = target.strip()
    if not target:
        return []
    name_re = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(target) + r"(?![A-Za-z0-9_])", re.I)

    out = []
    for line in text.splitlines():
        if not name_re.search(line):
            continue                                   # username must be on this line
        cleaned = _RELATIVE_RE.sub(" ", line)          # drop "2 minutes ago" etc.
        t = _find_time(cleaned)
        if t is None:
            continue                                   # no valid time -> omit
        start, end, hour, minute = t
        masked = cleaned[:start] + " @T@ " + cleaned[end:]
        d = _find_date(masked, ref, day_first)
        if d is None:
            continue                                   # no date -> omit
        out.append({"date": d.isoformat(), "time": f"{hour:02d}:{minute:02d}"})

    out.sort(key=lambda x: (x["date"], x["time"]))
    return out


def decode_upload(data: bytes) -> str:
    """Decode an uploaded text file: handles UTF-8 (with/without BOM), UTF-16, and legacy 8-bit."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")
