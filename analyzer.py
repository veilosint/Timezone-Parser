from collections import defaultdict
from datetime import datetime, timedelta


ALL_WEEKDAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]

# Map of UTC offset (in hours) → a representative timezone name.
# Where multiple zones share an offset, we pick the most commonly used one.
# Source: IANA tz database. Offsets are the standard (non-DST) offset.
OFFSET_TO_TZ = {
    -12: ("Etc/GMT+12", "UTC-12"),
    -11: ("Pacific/Pago_Pago", "SST"),
    -10: ("Pacific/Honolulu", "HST"),
    -9:  ("America/Anchorage", "AKST"),
    -8:  ("America/Los_Angeles", "PST"),
    -7:  ("America/Denver", "MST"),
    -6:  ("America/Chicago", "CST"),
    -5:  ("America/New_York", "EST"),
    -4:  ("America/Halifax", "AST"),
    -3:  ("America/Sao_Paulo", "BRT"),
    -2:  ("Atlantic/South_Georgia", "GST"),
    -1:  ("Atlantic/Azores", "AZOT"),
    0:   ("Europe/London", "GMT"),
    1:   ("Europe/Paris", "CET"),
    2:   ("Europe/Athens", "EET"),
    3:   ("Europe/Moscow", "MSK"),
    4:   ("Asia/Dubai", "GST"),
    5:   ("Asia/Karachi", "PKT"),
    6:   ("Asia/Dhaka", "BST"),
    7:   ("Asia/Bangkok", "ICT"),
    8:   ("Asia/Shanghai", "CST"),
    9:   ("Asia/Tokyo", "JST"),
    10:  ("Australia/Sydney", "AEST"),
    11:  ("Pacific/Noumea", "NCT"),
    12:  ("Pacific/Auckland", "NZST"),
    13:  ("Pacific/Tongatapu", "TOT"),
    14:  ("Pacific/Kiritimati", "LINT"),
}

# Friendlier display names for common zones
FRIENDLY_NAMES = {
    -10: "Hawaii",
    -9:  "Alaska",
    -8:  "Pacific Time (US)",
    -7:  "Mountain Time (US)",
    -6:  "Central Time (US)",
    -5:  "Eastern Time (US & Canada)",
    -4:  "Atlantic Time",
    -3:  "Brasília / Buenos Aires",
    -2:  "Mid-Atlantic",
    -1:  "Azores",
    0:   "London / UTC",
    1:   "Central European Time",
    2:   "Eastern European Time",
    3:   "Moscow / Riyadh",
    4:   "Gulf / Dubai",
    5:   "Pakistan / Karachi",
    6:   "Bangladesh / Dhaka",
    7:   "Bangkok / Jakarta",
    8:   "China / Singapore / Perth",
    9:   "Japan / Korea",
    10:  "Sydney / Melbourne",
    11:  "Nouméa / Solomon Is.",
    12:  "New Zealand",
    13:  "Tonga",
    14:  "Line Islands",
}


def _offset_to_timezone(offset: int) -> dict:
    """Return a friendly timezone dict for a whole-hour UTC offset."""
    offset = int(round(offset))
    # Clamp to valid range
    offset = max(-12, min(14, offset))

    tz_name, abbr = OFFSET_TO_TZ.get(offset, ("UTC", "UTC"))
    friendly = FRIENDLY_NAMES.get(offset, "UTC")

    sign = "+" if offset >= 0 else "-"
    utc_label = f"UTC{sign}{abs(offset)}" if offset != 0 else "UTC"

    return {
        "offset": offset,
        "iana_name": tz_name,
        "abbreviation": abbr,
        "common_name": friendly,
        "utc_label": utc_label,
    }


def _week_key(ts_iso):
    dt = datetime.fromisoformat(ts_iso)
    year, week_num, _ = dt.isocalendar()
    return year, week_num


def _week_label(year, week_num):
    monday = datetime.strptime(f"{year} {week_num} 1", "%G %V %u").date()
    sunday = monday + timedelta(days=6)
    return f"({monday.strftime('%b %d')} – {sunday.strftime('%b %d')})"


def _find_dead_zone(by_weekday, min_hours=6, max_hours=9):
    """Find the longest empty window across all weekdays."""
    slots = [(wd, set(hours.keys())) for wd, hours in by_weekday.items()]
    if not slots:
        return None

    best = None
    total = len(slots)
    for length in range(max_hours, min_hours - 1, -1):
        for start in range(24):
            window = {(start + i) % 24 for i in range(length)}
            empty = [wd for wd, hours in slots if not (window & hours)]
            coverage = len(empty) / total

            if best is None or coverage > best["coverage"] or (
                coverage == best["coverage"] and length > best["length"]
            ):
                best = {
                    "start_hour": start,
                    "end_hour": (start + length) % 24,
                    "length": length,
                    "empty_weekdays": empty,
                    "total_weekdays": total,
                    "coverage": coverage,
                }

    return best if best and best["coverage"] >= 0.6 else None


def analyze(records, username, reference_timezone_offset=0):
    target = username.strip().lower()

    filtered = [r for r in records if r["name"].strip().lower() == target]

    if not filtered:
        return {
            "username": username,
            "total_messages": 0,
            "total_days": 0,
            "weeks": [],
            "message": "No messages found for that username.",
        }

    filtered.sort(key=lambda r: r["timestamp"])

    weeks = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    dates_seen = set()
    by_weekday_all = defaultdict(lambda: defaultdict(int))

    for rec in filtered:
        y, w = _week_key(rec["timestamp"])
        weeks[(y, w)][rec["weekday"]][rec["hour"]] += 1
        by_weekday_all[rec["weekday"]][rec["hour"]] += 1
        dates_seen.add(rec["timestamp"][:10])

    weeks_out = []
    for (y, w) in sorted(weeks.keys()):
        days = {}
        for weekday in ALL_WEEKDAYS:
            if weekday not in weeks[(y, w)]:
                continue
            hours = weeks[(y, w)][weekday]
            if not hours:
                continue
            days[weekday] = {str(h): c for h, c in sorted(hours.items())}
        if days:
            weeks_out.append({
                "week_label": _week_label(y, w),
                "days": days,
            })

    # Timezone estimate from the dead zone (whole-hour precision)
    estimated = None
    dead_zone = _find_dead_zone(dict(by_weekday_all))
    if dead_zone:
        mid = (dead_zone["start_hour"] + dead_zone["length"] / 2) % 24
        offset = (3 - mid) % 24
        if offset > 12:
            offset -= 24
        offset_int = int(round(offset))
        estimated = _offset_to_timezone(offset_int)
        estimated["confidence"] = (
            "medium" if dead_zone["coverage"] >= 0.8 else "low"
        )
        estimated["dead_zone"] = {
            "start_hour": dead_zone["start_hour"],
            "end_hour": dead_zone["end_hour"],
            "length_hours": dead_zone["length"],
            "coverage": f"{len(dead_zone['empty_weekdays'])}/{dead_zone['total_weekdays']} weekdays",
        }

    return {
        "username": username,
        "total_messages": len(filtered),
        "total_days": len(dates_seen),
        "weeks": weeks_out,
        "estimated_timezone": estimated,
    }
