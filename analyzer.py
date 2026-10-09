from collections import defaultdict
from datetime import datetime, timedelta


ALL_WEEKDAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]

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

FRIENDLY_NAMES = {
    -12: "Baker Island",
    -11: "Samoa",
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
    offset = int(round(offset))
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
    return f"Week of {monday.strftime('%b %d')} – {sunday.strftime('%b %d')}"


def _find_dead_zone(by_weekday, min_hours=6, max_hours=9):
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
    week_had_activity = {}

    for rec in filtered:
        y, w = _week_key(rec["timestamp"])
        weeks[(y, w)][rec["weekday"]][rec["hour"]] += 1
        by_weekday_all[rec["weekday"]][rec["hour"]] += 1
        dates_seen.add(rec["timestamp"][:10])
        week_had_activity[(y, w)] = True

    # Determine which weekdays should be included per week:
    # Only include weekdays that fall within the span of that week's activity.
    # A weekday with 0 messages still gets listed as 0.
    weeks_out = []
    for (y, w) in sorted(weeks.keys()):
        # Find the min and max dates within this week that have messages
        week_dates = [
            datetime.fromisoformat(r["timestamp"]).date()
            for r in filtered
            if _week_key(r["timestamp"]) == (y, w)
        ]
        if not week_dates:
            continue

        min_date = min(week_dates)
        max_date = max(week_dates)

        # Include all weekdays from min_date's weekday to max_date's weekday
        weekdays_to_include = []
        for weekday in ALL_WEEKDAYS:
            # Compute the actual date of this weekday in this week
            monday = datetime.strptime(f"{y} {w} 1", "%G %V %u").date()
            day_index = ALL_WEEKDAYS.index(weekday)
            this_date = monday + timedelta(days=day_index)

            # Only include if this date falls within the activity range
            if min_date <= this_date <= max_date:
                weekdays_to_include.append(weekday)

        days = {}
        for weekday in weekdays_to_include:
            hours = weeks[(y, w)].get(weekday, {})
            if hours:
                # Hours with messages
                days[weekday] = {str(h): c for h, c in sorted(hours.items())}
            else:
                # Day with no messages — show as 0
                days[weekday] = {}

        weeks_out.append({
            "week_label": _week_label(y, w),
            "days": days,
        })

    dead_zone = _find_dead_zone(dict(by_weekday_all))

    estimated_timezone = None
    if dead_zone:
        mid = (dead_zone["start_hour"] + dead_zone["length"] / 2) % 24
        center_offset = (3 - mid) % 24
        if center_offset > 12:
            center_offset -= 24
        center_offset = int(round(center_offset))

        candidate_offsets = [center_offset - 2, center_offset, center_offset + 2]
        candidates = []
        for i, off in enumerate(candidate_offsets):
            off_clamped = max(-12, min(14, off))
            tz = _offset_to_timezone(off_clamped)
            tz["role"] = "lower" if i == 0 else ("center" if i == 1 else "upper")
            candidates.append(tz)

        confidence = "medium" if dead_zone["coverage"] >= 0.8 else "low"

        estimated_timezone = {
            "center_offset": center_offset,
            "uncertainty_hours": 2,
            "candidates": candidates,
            "confidence": confidence,
            "dead_zone": {
                "start_hour": dead_zone["start_hour"],
                "end_hour": dead_zone["end_hour"],
                "length_hours": dead_zone["length"],
                "coverage": f"{len(dead_zone['empty_weekdays'])}/{dead_zone['total_weekdays']} weekdays",
            },
        }

    return {
        "username": username,
        "total_messages": len(filtered),
        "total_days": len(dates_seen),
        "weeks": weeks_out,
        "estimated_timezone": estimated_timezone,
    }
