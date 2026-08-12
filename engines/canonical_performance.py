"""Canonical, UI-independent performance and ranking projection for EXOS."""

from engines.programme_hierarchy import activity_details


def _team_identity(team):
    return str(
        team.get("TeamIdentity") or team.get("TeamName")
        or team.get("TeamID") or "Unknown Team"
    ).strip()


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _flatten(programme):
    rows = []
    for module in programme or []:
        activities = module.get("Activities", []) if isinstance(module, dict) else []
        rows.extend(dict(activity) for activity in activities if isinstance(activity, dict))
    return rows


def activity_scoring_contract(activity):
    """Resolve an extensible scoring contract from canonical activity configuration."""
    activity = dict(activity or {})
    details = activity_details(activity)
    payload = activity.get("ActivityPayload", activity.get("activity_payload", {}))
    payload = payload if isinstance(payload, dict) else {}
    module_details = details.get("ModuleDetails", {})
    module_details = module_details if isinstance(module_details, dict) else {}
    configured = (
        activity.get("ScoringContract")
        or payload.get("scoring_contract")
        or payload.get("ScoringContract")
        or details.get("ScoringContract")
        or module_details.get("ScoringContract")
        or {}
    )
    configured = dict(configured) if isinstance(configured, dict) else {}
    scoring_mode = str(
        configured.get("ScoringMode")
        or activity.get("ScoringMode")
        or details.get("ScoringMode")
        or "TEAM_COMPETITIVE"
    ).upper()
    contract_type = str(configured.get("Type", "")).upper()
    if not contract_type:
        contract_type = "NON_SCORING" if scoring_mode == "NON_SCORING" else "DIRECT_SCORE"
    return {
        "Type": contract_type,
        "ScoringMode": scoring_mode,
        "Target": _number(configured.get("Target", configured.get("Maximum", 0))),
        "Maximum": _number(configured.get("Maximum", details.get("Credits", 0))),
        "CanonicalScore": str(configured.get("CanonicalScore", "SCORE")).upper(),
        "IncludeWhen": str(configured.get("IncludeWhen", "APPROVED")).upper(),
        "Fields": dict(configured.get("Fields", {})) if isinstance(configured.get("Fields", {}), dict) else {},
    }


def _status(submission, contract):
    if contract["Type"] == "NON_SCORING":
        return "Non-Scoring"
    if not submission:
        return "Not Started"
    state = str(submission.get("ReviewState") or submission.get("Status") or "SUBMITTED").upper()
    return {
        "PENDING": "Submitted",
        "SUBMITTED": "Awaiting Review",
        "PENDING_REVIEW": "Awaiting Review",
        "REVISION_REQUESTED": "Revision Requested",
        "RESUBMITTED": "Resubmitted",
        "REJECTED": "Rejected",
        "APPROVED": "Approved / Scored",
    }.get(state, state.replace("_", " ").title())


def evaluate_activity(activity, submission=None):
    contract = activity_scoring_contract(activity)
    submission = dict(submission or {})
    approved = str(submission.get("Status", "")).upper() == "APPROVED"
    result = {
        "ActivityID": str(activity.get("ActivityID", "")),
        "ActivityName": str(activity.get("ParticipantDisplayName") or activity.get("StageName") or "Activity"),
        "Contract": contract,
        "Status": _status(submission, contract),
        "Score": _number(submission.get("Score")) if approved else None,
        "Target": None,
        "Achievement": None,
        "Loss": None,
        "NetAchievement": None,
        "PerformancePercentage": None,
        "Included": False,
    }
    if contract["Type"] == "NON_SCORING" or not approved:
        return result
    if contract["Type"] == "TARGET_ACHIEVEMENT_LOSS":
        fields = {"Target": "Metric1", "Achievement": "Metric2", "Loss": "Metric3", **contract["Fields"]}
        # The official denominator is facilitator/programme-authored. Participant
        # evidence may contain a reported target, but it cannot define ranking.
        target = _number(contract.get("Target"))
        achievement = _number(submission.get(fields["Achievement"]))
        loss = _number(submission.get(fields["Loss"]))
        net = achievement - loss
        result.update({
            "Target": target,
            "Achievement": achievement,
            "Loss": loss,
            "NetAchievement": net,
            "PerformancePercentage": (net / target * 100) if target > 0 else None,
            "Included": target > 0,
        })
        if contract["CanonicalScore"] == "NET_ACHIEVEMENT":
            result["Score"] = net
    else:
        maximum = contract["Maximum"]
        result.update({
            "Target": maximum if maximum > 0 else None,
            "NetAchievement": result["Score"],
            "PerformancePercentage": (result["Score"] / maximum * 100) if maximum > 0 else None,
            "Included": True,
        })
    return result


def build_performance_snapshot(programme, submissions, teams, canonical_leaderboard,
                               earned_credits=(), wallets=()):
    """Build the single participant/facilitator/projector performance contract."""
    activities = _flatten(programme)
    team_rows = [dict(team) for team in teams or []]
    submissions = [dict(row) for row in submissions or []]
    ledger = {str(row.get("TeamID", "")): _number(row.get("Score")) for row in canonical_leaderboard or []}
    earned = {str(row.get("TeamID", "")): _number(row.get("EarnedCredits")) for row in earned_credits or []}
    balances = {str(row.get("TeamID", "")): _number(row.get("Balance")) for row in wallets or []}
    output = []
    for team in team_rows:
        team_id = str(team.get("TeamID", ""))
        breakdown = []
        for activity in activities:
            activity_id = str(activity.get("ActivityID", ""))
            submission = next((row for row in submissions if str(row.get("TeamID", "")) == team_id and str(row.get("ActivityID") or row.get("MissionID", "")) == activity_id), None)
            breakdown.append(evaluate_activity(activity, submission))
        included = [row for row in breakdown if row["Included"]]
        target_rows = [row for row in included if row["Target"] is not None]
        total_target = sum(_number(row["Target"]) for row in target_rows)
        total_net = sum(_number(row["NetAchievement"]) for row in target_rows)
        score = ledger.get(team_id, sum(_number(row["Score"]) for row in included))
        output.append({
            "TeamID": team_id,
            "TeamIdentity": _team_identity(team),
            "TotalScore": score,
            "TotalTarget": total_target,
            "TotalNetAchievement": total_net,
            "PerformancePercentage": (total_net / total_target * 100) if total_target > 0 else None,
            "CreditsEarned": earned.get(team_id),
            "WalletBalance": balances.get(team_id),
            "Activities": breakdown,
        })
    output.sort(key=lambda row: (-row["TotalScore"], row["TeamIdentity"].casefold(), row["TeamID"]))
    last_score = None
    current_rank = 0
    for position, row in enumerate(output, 1):
        if last_score is None or row["TotalScore"] != last_score:
            current_rank = position
            last_score = row["TotalScore"]
        row["Rank"] = current_rank
        row["TeamCount"] = len(output)
    return {"Teams": output, "TeamCount": len(output)}


def load_performance_snapshot(db, event_id):
    programme = db.runtime.get_programme_hierarchy(event_id)
    submissions = db.get_submissions(event_id)
    teams = db.get_teams(event_id)
    leaderboard = db.runtime.get_canonical_leaderboard(event_id) if db.runtime.can_publish else []
    return build_performance_snapshot(programme, submissions, teams, leaderboard)
