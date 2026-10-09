from collections import defaultdict
from datetime import datetime, timedelta


WEEKDAYS_ONLY = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def _find_consistent_dead_zone(by_weekday, min_hours=6, max_hours=9):
    slots = []
    for weekday, hours in by_weekday.items():
        slots.append((weekday, set(hours.keys())))

    if not slots:
        return None

    best = None
    total_slots = len(slots)

    for length in range(max_hours, min_hours - 1, -1):
        for start in range(24):
            window = {(start + i) % 24 for i in range(length)}
            empty_slots = [wd for wd, hours in slots if not (window & hours)]
            coverage = len(empty_slots) / total_slots if total_slots else 0

            if best is None or coverage > best["coverage"] or (
                coverage == best["coverage"] and length > best["length"]
            ):
                best = {
                    "start_hour": start,
                    "end_hour": (start + length) % 24,
                    "length": length,
                    "empty_weekdays": empty_slots,
                    "total_weekdays": total_slots,
                    "coverage": coverage,
                }

    return best if best and best["coverage"] >= 0.6 else None


def analyze(records, username, reference_timezone_offset=0):
    target = username.strip().lower()
    filtered = [
        r for r in records
        if r["name"].strip().lower() == target and r["weekday"] in WEEKDAYS_ONLY
    ]

    if not filtered:
        return {
            "username": username,
            "total_messages": 0,
            "total_days": 0,
            "by_weekday": {},
            "dead_zone": None,
            "estimated_utc_offset_range": None,
            "message": "No weekday messages found for that username.",
        }

    by_weekday = defaultdict(lambda: defaultdict(int))
    dates_seen = set()

    for rec in filtered:
        by_weekday[rec["weekday"]][rec["hour"]] += 1
        dates_seen.add(rec["timestamp"][:10])

    formatted = {}
    for weekday in WEEKDAYS_ONLY:
        if weekday in by_weekday:
            formatted[weekday] = {str(h): c for h, c in sorted(by_weekday[weekday].items())}

    dead_zone = _find_consistent_dead_zone(dict(by_weekday))

    estimated = None
    if dead_zone:
        mid = (dead_zone["start_hour"] + dead_zone["length"] / 2) % 24
        offset = (3 - mid) % 24
        if offset > 12:
            offset -= 24
        estimated = {
            "estimated_utc_offset": round(offset),
            "confidence": "medium" if dead_zone["coverage"] >= 0.8 else "low",
            "sleep_window_reference": {
                "start": dead_zone["start_hour"],
                "end": dead_zone["end_hour"],
            },
        }

    return {
        "username": username,
        "total_messages": len(filtered),
        "total_days": len(dates_seen),
        "by_weekday": formatted,
        "dead_zone": {
            "start_hour": dead_zone["start_hour"],
            "end_hour": dead_zone["end_hour"],
            "length_hours": dead_zone["length"],
            "empty_weekdays": dead_zone["empty_weekdays"],
            "coverage": f"{len(dead_zone['empty_weekdays'])}/{dead_zone['total_weekdays']}",
        } if dead_zone else None,
        "estimated_utc_offset_range": estimated,
        "note": "Saturday and Sunday excluded from analysis.",
    }
