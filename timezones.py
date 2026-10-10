"""
Timezone input handling.

Accepts what people actually type:
  - abbreviations:   EST, PST, CST, GMT, JST ...   (see ABBREVIATIONS)
  - fixed offsets:   UTC-5, GMT+5:30, UTC+09
  - full names:      America/New_York (case-insensitive)

IMPORTANT: abbreviations map to a *region*, not a fixed offset, so daylight
saving is handled automatically. "EST" and "EDT" both mean US Eastern time:
a July timestamp is read as UTC-4 and a January one as UTC-5. People say
"EST" year-round, so treating it as a fixed UTC-5 would be wrong half the year.

Ambiguous abbreviations (IST = India / Israel / Ireland, AST, ...) are
rejected with a message rather than guessed.
"""
import re
from datetime import timedelta, timezone as dt_timezone, tzinfo
from zoneinfo import ZoneInfo, available_timezones

# Order here is the order shown in a dropdown.
ABBREVIATIONS = {
    # US & Canada
    "EST": "America/New_York", "EDT": "America/New_York", "ET": "America/New_York",
    "CST": "America/Chicago", "CDT": "America/Chicago", "CT": "America/Chicago",
    "MST": "America/Denver", "MDT": "America/Denver", "MT": "America/Denver",
    "PST": "America/Los_Angeles", "PDT": "America/Los_Angeles", "PT": "America/Los_Angeles",
    "AKST": "America/Anchorage", "AKDT": "America/Anchorage",
    "HST": "Pacific/Honolulu",
    # Europe / Africa
    "BST": "Europe/London",
    "WET": "Europe/Lisbon", "WEST": "Europe/Lisbon",
    "CET": "Europe/Paris", "CEST": "Europe/Paris",
    "EET": "Europe/Athens", "EEST": "Europe/Athens",
    "MSK": "Europe/Moscow",
    "WAT": "Africa/Lagos", "SAST": "Africa/Johannesburg", "EAT": "Africa/Nairobi",
    # Asia / Pacific
    "PKT": "Asia/Karachi", "SGT": "Asia/Singapore", "HKT": "Asia/Hong_Kong",
    "JST": "Asia/Tokyo", "KST": "Asia/Seoul",
    "AWST": "Australia/Perth", "ACST": "Australia/Adelaide",
    "AEST": "Australia/Sydney", "AEDT": "Australia/Sydney",
    "NZST": "Pacific/Auckland", "NZDT": "Pacific/Auckland",
    # South America
    "BRT": "America/Sao_Paulo",
}
_UTC_LABELS = {"UTC", "GMT", "Z"}

AMBIGUOUS = {
    "IST": "IST could mean India, Israel, or Ireland. Use UTC+5:30 (India), "
           "or a name like Asia/Kolkata, Asia/Jerusalem, or Europe/Dublin.",
    "AST": "AST could mean Atlantic or Arabia time. Use UTC-4, UTC+3, "
           "or a name like America/Halifax or Asia/Riyadh.",
}

_OFFSET_RE = re.compile(r"^(?:UTC|GMT)\s*([+-])\s*(\d{1,2})(?::?([0-5]\d))?$", re.I)


def dropdown_options() -> list[str]:
    return ["UTC"] + list(ABBREVIATIONS.keys())


def resolve_timezone(label: str) -> tzinfo:
    """Turn user input into a tzinfo. Raises ValueError with a friendly message."""
    s = (label or "").strip()
    if not s:
        raise ValueError("Timezone is empty.")
    key = s.upper()

    if key in _UTC_LABELS:
        return dt_timezone.utc
    if key in ABBREVIATIONS:
        return ZoneInfo(ABBREVIATIONS[key])
    if key in AMBIGUOUS:
        raise ValueError(AMBIGUOUS[key])

    m = _OFFSET_RE.match(s)
    if m:
        hours, minutes = int(m.group(2)), int(m.group(3) or 0)
        if hours > 14:
            raise ValueError("UTC offsets must be between -12 and +14.")
        delta = timedelta(hours=hours, minutes=minutes)
        return dt_timezone(delta if m.group(1) == "+" else -delta)

    names = available_timezones()
    if s in names:
        return ZoneInfo(s)
    for name in names:                       # case-insensitive full name
        if name.lower() == s.lower():
            return ZoneInfo(name)

    raise ValueError(f"Unknown timezone '{label}'. Try EST, PST, UTC-5, "
                     f"or a name like America/New_York.")


def display_label(label: str) -> str:
    """How the timezone is echoed back: abbreviations/offsets uppercased, names as typed."""
    s = label.strip()
    key = s.upper()
    if key in ABBREVIATIONS or key in _UTC_LABELS or _OFFSET_RE.match(s):
        return key
    return s
