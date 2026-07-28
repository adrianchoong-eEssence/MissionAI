from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc)


def parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def new_timer(duration_seconds):
    return {
        "Status": "READY",
        "DurationSeconds": max(int(duration_seconds or 0), 0),
        "RemainingSeconds": max(int(duration_seconds or 0), 0),
        "StartedAt": "",
        "UpdatedAt": utc_now().isoformat(),
    }


def remaining_seconds(timer, now=None):
    state = dict(timer or {})
    remaining = max(int(state.get("RemainingSeconds", 0) or 0), 0)
    if str(state.get("Status", "")).upper() != "RUNNING":
        return remaining
    started_at = parse_timestamp(state.get("StartedAt"))
    if not started_at:
        return remaining
    current = now or utc_now()
    elapsed = max(int((current - started_at).total_seconds()), 0)
    return max(remaining - elapsed, 0)


def transition_timer(timer, action, duration_seconds=None, now=None):
    current = dict(timer or new_timer(duration_seconds or 0))
    action_name = str(action).strip().upper()
    timestamp = now or utc_now()
    remaining = remaining_seconds(current, now=timestamp)

    if action_name in {"START", "RESUME"}:
        if remaining <= 0:
            remaining = max(
                int(duration_seconds or current.get("DurationSeconds", 0) or 0),
                0,
            )
        current.update({
            "Status": "RUNNING",
            "RemainingSeconds": remaining,
            "StartedAt": timestamp.isoformat(),
        })
    elif action_name == "PAUSE":
        current.update({
            "Status": "PAUSED",
            "RemainingSeconds": remaining,
            "StartedAt": "",
        })
    elif action_name == "RESET":
        duration = max(
            int(duration_seconds or current.get("DurationSeconds", 0) or 0),
            0,
        )
        current.update({
            "Status": "READY",
            "DurationSeconds": duration,
            "RemainingSeconds": duration,
            "StartedAt": "",
        })
    elif action_name == "END":
        current.update({
            "Status": "ENDED",
            "RemainingSeconds": 0,
            "StartedAt": "",
        })
    else:
        raise ValueError(f"Unsupported timer action: {action}")

    current["UpdatedAt"] = timestamp.isoformat()
    return current
