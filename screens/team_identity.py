"""Generic canonical team identity resolution for facilitator displays."""


def team_identity(team):
    """Prefer authored identity, then name, with the identifier as last fallback."""
    row = team if isinstance(team, dict) else {}
    return str(
        row.get("TeamIdentity")
        or row.get("TeamName")
        or row.get("TeamID")
        or "Unknown Team"
    ).strip()


def resolve_leaderboard_rows(rows, teams):
    """Return ``(display identity, score)`` pairs from canonical or tuple rows."""
    by_id = {
        str(team.get("TeamID", "")): team_identity(team)
        for team in teams or []
        if isinstance(team, dict) and team.get("TeamID")
    }
    resolved = []
    for row in rows or []:
        if isinstance(row, dict):
            team_id = str(row.get("TeamID", ""))
            display = (
                by_id.get(team_id)
                or str(row.get("TeamIdentity") or row.get("TeamName") or team_id).strip()
                or "Unknown Team"
            )
            score = float(row.get("Score", 0) or 0)
        else:
            team_id, score = row
            team_id = str(team_id)
            display = by_id.get(team_id, team_id or "Unknown Team")
            score = float(score or 0)
        resolved.append((display, score))
    return resolved
