from collections import defaultdict
from datetime import datetime, timedelta


ALL_WEEKDAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]


def _week_key(ts_iso):
    """Return (year, week_number) from an ISO timestamp."""
    dt = datetime.fromisoformat(ts_iso)
    year, week_num, _ = dt.isocalendar()
    return year, week_num


def _week_label(year, week_num):
    """Human label like 'Week 1 (Oct 06 – Oct 12)'."""
    monday = datetime.strptime(f"{year} {week_num} 1", "%G %V %u").date()
    sunday = monday + timedelta(days=6)
    return f"({monday.strftime('%b %d')} – {sunday.strftime('%b %d')})"


def analyze(records, username, reference_timezone_offset=0):
    """
    Organize records into a week-by-week, day-by-day layout.
    Each day lists only the hours that had messages: "14:00 (3)".
    """
    target = username.strip().lower()

    filtered = [
        r for r in records
        if r["name"].strip().lower() == target
    ]

    if not filtered:
        return {
            "username": username,
            "total_messages": 0,
            "total_days": 0,
            "weeks": [],
            "message": "No messages found for that username.",
        }

    # Sort chronologically so weeks come out in order
    filtered.sort(key=lambda r: r["timestamp"])

    # Bucket: (year, week) → weekday → hour → count
    weeks = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    dates_seen = set()

    for rec in filtered:
        y, w = _week_key(rec["timestamp"])
        weeks[(y, w)][rec["weekday"]][rec["hour"]] += 1
        dates_seen.add(rec["timestamp"][:10])

    # Build output: ordered list of weeks
    weeks_out = []
    for (y, w) in sorted(weeks.keys()):
        week_label = _week_label(y, w)
        days = {}
        for weekday in ALL_WEEKDAYS:
            if weekday not in weeks[(y, w)]:
                continue
            hours = weeks[(y, w)][weekday]
            if not hours:
                continue
            # Format: {"14": 3, "18": 1}
            days[weekday] = {str(h): c for h, c in sorted(hours.items())}

        if days:
            weeks_out.append({
                "week_label": week_label,
                "days": days,
            })

    return {
        "username": username,
        "total_messages": len(filtered),
        "total_days": len(dates_seen),
        "weeks": weeks_out,
    }
