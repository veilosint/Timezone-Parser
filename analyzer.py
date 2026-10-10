"""
Deadzone analyzer (pure Python, no dependencies).

Input : the extractor's timestamps ({"date","time"} list) + the timezone they
        were written in.
Step 1: find each night's DEADZONE = the longest silence between consecutive
        messages in a ~24h stretch. The deadzone starts at the last message
        before the silence and ends at the first message after it. (This does
        not depend on where midnight falls in the input timezone.)
Step 2: average the deadzones: average length in hours, and average start/end
        clock time (circular average, so 23:30 and 00:30 average to 00:00).
Step 3: for every candidate timezone, shift the average deadzone into that
        timezone's local time and score how well it matches a typical sleep
        schedule (a bedtime window and a wake-up window). Return the top 3.

NOTE: the deadzone LENGTH is identical under every candidate timezone, so only
the clock times can tell timezones apart. Length is used as a sanity check.
"""
import math
import re
from datetime import date, datetime, time, timedelta, timezone as dt_timezone, tzinfo

MIN_GAP_H = 3.0       # a silence shorter than this isn't treated as sleep
MAX_GAP_H = 16.0      # longer than this is a skipped day, not a night
SUPPRESS_H = 18.0     # one deadzone per ~day: nearby smaller gaps are ignored
MIN_NIGHTS = 3

# Whole-hour candidates only, one per distinct clock position (24 of them).
# UTC-12/-11/-10 show exactly the same clock times as UTC+12/+13/+14, so they can
# never be told apart; keeping both would just create exact ties. We keep -10..+13
# (Hawaii ... New Zealand/Tonga). Half-hour zones (e.g. India, UTC+5:30) are NOT
# separated: they would split the vote with their whole-hour neighbours, so an
# India-based person will show up as UTC+5 / UTC+6.
OFFSETS = [float(h) for h in range(-10, 14)]


def _wrap(o: float) -> float:
    """Wrap an offset into the candidate range (the clock is circular at the date line)."""
    lo = OFFSETS[0]
    return lo + ((o - lo) % len(OFFSETS))


# Common names for each offset (standard time / daylight-saving time)
_NAMES = {
    -10: ["HST"], -9: ["AKST", "HDT"], -8: ["PST", "AKDT"], -7: ["MST", "PDT"],
    -6: ["CST", "MDT"], -5: ["EST", "CDT"], -4: ["EDT"], -3: ["BRT"],
    0: ["GMT", "UTC"], 1: ["CET", "BST"], 2: ["EET", "CEST"], 3: ["MSK", "EEST"],
    8: ["SGT", "HKT"], 9: ["JST", "KST"], 10: ["AEST"], 11: ["AEDT"], 12: ["NZST"],
}
OUTLIER_MINUTES = 240   # a night whose start or end is >4h from the typical one is ignored

_HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_WINDOW_RE = re.compile(r"^\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*$")


# ---- small helpers --------------------------------------------------------
def _minutes(hhmm: str) -> int:
    m = _HHMM_RE.match(hhmm.strip())
    if not m:
        raise ValueError(f"'{hhmm}' is not a valid HH:MM time.")
    return int(m.group(1)) * 60 + int(m.group(2))


def _fmt(minutes: float) -> str:
    total = int(round(minutes)) % 1440
    return f"{total // 60:02d}:{total % 60:02d}"


def _fmt_offset(o: float) -> str:
    if o == 0:
        return "UTC"
    sign = "+" if o > 0 else "-"
    h, m = divmod(int(round(abs(o) * 60)), 60)
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")


def _circ_dist(a: float, b: float) -> float:
    d = abs(a - b) % 1440
    return min(d, 1440 - d)


def parse_window(s: str):
    """'21:30-00:30' -> (center_minutes, half_width_minutes, normalized_text). May wrap midnight."""
    m = _WINDOW_RE.match(s or "")
    if not m:
        raise ValueError(f"Window '{s}' must look like 21:30-00:30.")
    start, end = _minutes(m.group(1)), _minutes(m.group(2))
    width = (end - start) % 1440
    if width == 0:
        raise ValueError(f"Window '{s}' has zero length.")
    return (start + width / 2) % 1440, max(width / 2, 30.0), f"{_fmt(start)}-{_fmt(end)}"


def circular_stats(minutes: list[float]):
    """(mean minute-of-day, standard deviation in minutes) for clock times."""
    n = len(minutes)
    ang = [m / 1440 * 2 * math.pi for m in minutes]
    s = sum(math.sin(a) for a in ang) / n
    c = sum(math.cos(a) for a in ang) / n
    r = min(1.0, math.hypot(s, c))
    mean = (math.atan2(s, c) % (2 * math.pi)) * 1440 / (2 * math.pi)
    sd = 0.0 if r >= 1.0 else (720.0 if r < 1e-9 else
                               min(720.0, math.sqrt(-2 * math.log(r)) * 1440 / (2 * math.pi)))
    return mean, sd


# ---- step 1: deadzones ----------------------------------------------------
def parse_timestamps(items: list[dict], tz: tzinfo) -> list[datetime]:
    out = []
    for it in items:
        try:
            d = date.fromisoformat(str(it["date"]))
            hh, mm = str(it["time"]).split(":")[:2]
            out.append(datetime.combine(d, time(int(hh), int(mm)), tzinfo=tz))
        except (KeyError, ValueError):
            raise ValueError(f"Bad timestamp entry: {it!r}. Expected "
                             f'{{"date": "YYYY-MM-DD", "time": "HH:MM"}}.')
    return out


def find_deadzones(dts: list[datetime]):
    """Returns [(start_dt, end_dt, hours)] - one per night, oldest first."""
    dts = sorted(dts)
    utc = [d.astimezone(dt_timezone.utc) for d in dts]   # real elapsed time, DST-safe
    gaps = []
    for i in range(len(dts) - 1):
        h = (utc[i + 1] - utc[i]).total_seconds() / 3600
        if h >= MIN_GAP_H:
            gaps.append((h, i))
    gaps.sort(reverse=True)                              # longest silences first

    anchors, nights = [], []
    for h, i in gaps:
        if any(abs((utc[i] - a).total_seconds()) / 3600 < SUPPRESS_H for a in anchors):
            continue                                     # same ~day as a longer silence
        anchors.append(utc[i])
        if h <= MAX_GAP_H:                               # too long = skipped day, discard
            nights.append((dts[i], dts[i + 1], h))
    nights.sort(key=lambda n: n[0])
    return nights


# ---- steps 2 + 3 ----------------------------------------------------------
def analyze(items: list[dict], tz: tzinfo, label: str,
            bed_window: str = "21:30-00:30", wake_window: str = "06:00-09:00",
            uncertainty_hours: int = 1) -> dict:
    bed_c, bed_h, bed_txt = parse_window(bed_window)
    wake_c, wake_h, wake_txt = parse_window(wake_window)
    nights = find_deadzones(parse_timestamps(items, tz))

    result = {
        "timezone": label,
        "status": "ok",
        "deadzone": None,
        "assumed_schedule": {"bedtime_window": bed_txt, "wake_window": wake_txt},
        "best_guess": None,
        "uncertainty": None,
        "confidence": "insufficient",
        "warnings": [],
        "note": ("Percentages compare how well each timezone makes the average deadzone "
                 "look like a normal sleep schedule. They are relative fits, not "
                 "probabilities. Night owls, shift workers, irregular schedules, and travel "
                 "can all shift the result. An offset is a coarse band, not a location."),
    }
    if len(nights) < MIN_NIGHTS:
        result["status"] = "insufficient_data"
        result["warnings"].append(
            f"Found {len(nights)} usable night(s); need at least {MIN_NIGHTS}. "
            "Provide more days of timestamps.")
        return result

    # Drop mistaken "nights" (e.g. a daytime gap on the last day of a file, where
    # the sleep that would have followed isn't in the data).
    def _mins(dt):
        return dt.hour * 60 + dt.minute
    s0, _ = circular_stats([_mins(n[0]) for n in nights])
    e0, _ = circular_stats([_mins(n[1]) for n in nights])
    kept = [n for n in nights
            if _circ_dist(_mins(n[0]), s0) <= OUTLIER_MINUTES
            and _circ_dist(_mins(n[1]), e0) <= OUTLIER_MINUTES]
    ignored = len(nights) - len(kept)
    nights = kept
    if len(nights) < MIN_NIGHTS:
        result["status"] = "insufficient_data"
        result["warnings"].append(
            f"Only {len(nights)} consistent night(s) after ignoring {ignored} outlier(s); "
            f"need at least {MIN_NIGHTS}.")
        return result

    start_mean, start_sd = circular_stats([_mins(n[0]) for n in nights])
    end_mean, end_sd = circular_stats([_mins(n[1]) for n in nights])
    avg_hours = sum(n[2] for n in nights) / len(nights)

    result["deadzone"] = {
        "nights_used": len(nights),
        "nights_ignored_as_outliers": ignored,
        "average_hours": round(avg_hours, 1),
        "average_start": _fmt(start_mean),
        "average_end": _fmt(end_mean),
        "variation_minutes": {"start": round(start_sd), "end": round(end_sd)},
    }

    # offset of the input timezone during the data (handles daylight saving)
    src_off = nights[-1][1].utcoffset().total_seconds() / 3600

    scored = []
    for off in OFFSETS:
        shift = (off - src_off) * 60
        s, e = (start_mean + shift) % 1440, (end_mean + shift) % 1440
        fit_b = math.exp(-0.5 * (_circ_dist(s, bed_c) / bed_h) ** 2)
        fit_w = math.exp(-0.5 * (_circ_dist(e, wake_c) / wake_h) ** 2)
        scored.append((fit_b * fit_w, off, s, e))
    total = sum(x[0] for x in scored) or 1e-12
    scored.sort(key=lambda x: -x[0])

    def window_note(x, center, half, kind, txt):
        out = _circ_dist(x, center) - half
        return (f"{kind} {_fmt(x)} is inside the typical {txt} window" if out <= 0
                else f"{kind} {_fmt(x)} is {round(out)} min outside the typical {txt} window")

    pct = {off: sc / total * 100 for sc, off, _, _ in scored}
    local = {off: (s, e) for _, off, s, e in scored}

    def entry(off):
        return {"label": _fmt_offset(off), "names": _NAMES.get(int(off), []),
                "percent": round(pct[off]),
                "deadzone_local": f"{_fmt(local[off][0])}-{_fmt(local[off][1])}"}

    best_off = scored[0][1]
    bs, be = local[best_off]
    result["best_guess"] = {
        **entry(best_off),
        "reasoning": (f"At {_fmt_offset(best_off)} the average deadzone is {_fmt(bs)}-{_fmt(be)} "
                      f"local: " + window_note(bs, bed_c, bed_h, "bedtime", bed_txt) + "; "
                      + window_note(be, wake_c, wake_h, "wake-up", wake_txt) + "."),
    }
    ordered = [_wrap(best_off + d) for d in range(-uncertainty_hours, uncertainty_hours + 1)]
    neighbours = [o for o in ordered if o != best_off]
    result["uncertainty"] = {
        "range": f"{_fmt_offset(ordered[0])} to {_fmt_offset(ordered[-1])}",
        "range_percent": round(sum(pct[o] for o in ordered)),
        "zones": [entry(o) for o in neighbours],
    }

    worst_sd = max(start_sd, end_sd)
    if len(nights) >= 14 and worst_sd <= 75:
        result["confidence"] = "moderate"
    elif len(nights) >= 7 and worst_sd <= 120:
        result["confidence"] = "low-moderate"
    else:
        result["confidence"] = "low"

    if avg_hours < 5 or avg_hours > 11:
        result["warnings"].append(
            f"Average deadzone is {avg_hours:.1f} hours, outside the usual sleep range. "
            "It may reflect irregular messaging habits rather than sleep.")
    if worst_sd > 120:
        result["warnings"].append(
            "Bedtime or wake time varies a lot night to night, so the average is a weak signal.")
    return result
