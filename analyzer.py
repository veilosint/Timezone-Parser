from collections import defaultdict


WEEKDAYS_ONLY = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def analyze(records, username, reference_timezone_offset=0):
    """
    Organize parsed records into a weekday → hour breakdown.
    No inference, no dead-zone detection — just clean bucketing.
    Saturday and Sunday are excluded.
    """
    target = username.strip().lower()

    filtered = [
        r for r in records
        if r["name"].strip().lower() == target
        and r["weekday"] in WEEKDAYS_ONLY
    ]

    if not filtered:
        return {
            "username": username,
            "total_messages": 0,
            "total_days": 0,
            "by_weekday": {},
            "hourly_totals": {},
            "message": "No weekday messages found for that username.",
        }

    # Bucket: weekday → hour → count
    by_weekday = defaultdict(lambda: defaultdict(int))
    hour_totals = defaultdict(int)
    dates_seen = set()

    for rec in filtered:
        by_weekday[rec["weekday"]][rec["hour"]] += 1
        hour_totals[rec["hour"]] += 1
        dates_seen.add(rec["timestamp"][:10])

    # Format: only include hours that have messages, sorted ascending
    formatted = {}
    for weekday in WEEKDAYS_ONLY:
        if weekday not in by_weekday:
            continue
        hours = by_weekday[weekday]
        formatted[weekday] = {str(h): c for h, c in sorted(hours.items())}

    hourly = {str(h): c for h, c in sorted(hour_totals.items())}

    return {
        "username": username,
        "total_messages": len(filtered),
        "total_days": len(dates_seen),
        "by_weekday": formatted,
        "hourly_totals": hourly,
        "note": "Saturday and Sunday excluded. Empty hours omitted.",
    }
