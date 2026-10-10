"""
Weekday x hour heatmap counts (pure Python, no dependencies).

For each weekday (Mon..Sun) and each hour (0-23), counts how many messages
were sent at that hour across ALL weeks in the data. Totals, not averages.

Times are used exactly as written in the input timezone: the weekday comes
from the date and the hour from the time, so no timezone conversion happens.
"""
from datetime import date, timedelta

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOUR_LABELS = [f"{h:02d}:00" for h in range(24)]


def build_heatmap(items: list[dict], label: str) -> dict:
    grid = [[0] * 24 for _ in range(7)]          # grid[weekday][hour]
    dates = []
    for it in items:
        try:
            d = date.fromisoformat(str(it["date"]))
            hour = int(str(it["time"]).split(":")[0])
            if not 0 <= hour <= 23:
                raise ValueError
        except (KeyError, ValueError):
            raise ValueError(f"Bad timestamp entry: {it!r}. Expected "
                             f'{{"date": "YYYY-MM-DD", "time": "HH:MM"}}.')
        grid[d.weekday()][hour] += 1
        dates.append(d)

    # how many of each weekday fall inside the data's date range (context for the totals)
    occurrences = [0] * 7
    if dates:
        d, last = min(dates), max(dates)
        while d <= last:
            occurrences[d.weekday()] += 1
            d += timedelta(days=1)

    return {
        "timezone": label,
        "total_messages": len(items),
        "max": max((c for row in grid for c in row), default=0),
        "hour_labels": HOUR_LABELS,
        "days": [{"day": DAY_NAMES[w], "hours": grid[w], "total": sum(grid[w]),
                  "occurrences": occurrences[w]} for w in range(7)],
        # grid-ready version: matrix[hour][weekday], columns Mon..Sun, rows 00:00..23:00
        "columns": DAY_NAMES,
        "matrix": [[grid[w][h] for w in range(7)] for h in range(24)],
    }
