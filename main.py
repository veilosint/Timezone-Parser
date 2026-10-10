def _build_response(log_text: str, username: str | None):
    records = parse_message_log(log_text, username_filter=username)

    if not records:
        raise HTTPException(
            status_code=422,
            detail="No lines with both a username and a timestamp were found.",
        )

    timestamps = [
        {
            "timestamp": r["timestamp"],
            "weekday": r["weekday"],
            "hour": r["hour"],
            "minute": r["minute"],
            "ampm": r["ampm"],
        }
        for r in records
    ]

    return {
        "username": username,
        "total_timestamps": len(timestamps),
        "timestamps": timestamps,
    }
