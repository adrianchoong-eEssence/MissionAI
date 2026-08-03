"""Canonical submission, review, award, scoring and projection model."""

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from statistics import mean, median
import uuid


SUBMISSION_STATUSES = {
    "DRAFT", "SUBMITTED", "PENDING_REVIEW", "APPROVED", "REJECTED",
    "RETURNED_FOR_REVISION", "CANCELLED",
}
DECISIONS = {"APPROVE", "REJECT", "RETURN_FOR_REVISION", "VOID", "CORRECT_PREVIOUS_DECISION"}
AWARD_TYPES = {
    "INTELLIGENCE_CREDITS", "SCORE", "BONUS", "PENALTY",
    "MANUAL_ADJUSTMENT", "MARKETPLACE_SPEND", "REFUND", "CORRECTION",
}


class TransactionPipelineError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix):
    return f"{prefix}-{uuid.uuid4()}"


def submission_authorized(participant, assignment, *, team_override=False, event_override=False):
    if not participant or not participant.get("ParticipantID") or not participant.get("TeamID"):
        return False
    if not assignment or not assignment.get("Active") or not assignment.get("RuntimeEligible"):
        return False
    rule = str(assignment.get("SubmissionRule", "LEADER_ONLY")).upper()
    return bool(
        participant.get("IsLeader") or team_override or event_override
        or rule in {"ANY_MEMBER", "MULTIPLE"}
    )


def canonical_submission(values):
    source = dict(values or {})
    required = (
        "EventID", "TeamID", "ParticipantID", "ProgrammeID", "ModuleID", "ActivityID",
        "ExperienceDefinitionID", "ExperienceAssignmentID", "DefinitionVersion", "AssignmentVersion",
    )
    missing = [field for field in required if source.get(field) in (None, "")]
    if missing:
        raise TransactionPipelineError("Submission is missing stable references: " + ", ".join(missing))
    submitted_at = str(source.get("SubmittedAt") or now())
    return {
        "SubmissionID": str(source.get("SubmissionID") or stable_id("SUB")),
        **{field: source[field] for field in required},
        "SubmissionType": str(source.get("SubmissionType", "TEXT")).upper(),
        "EvidenceType": str(source.get("EvidenceType", "NONE")).upper(),
        "TextResponse": str(source.get("TextResponse", "")),
        "MediaAssetID": str(source.get("MediaAssetID", "")),
        "StorageReference": str(source.get("StorageReference", "")),
        "QRResult": deepcopy(source.get("QRResult")),
        "GPSResult": deepcopy(source.get("GPSResult")),
        "SubmittedAt": submitted_at,
        "Status": str(source.get("Status", "PENDING_REVIEW")).upper(),
        "IdempotencyKey": str(source.get("IdempotencyKey", "")),
        "CreatedBy": str(source.get("CreatedBy") or source["ParticipantID"]),
        "LastUpdatedAt": submitted_at,
        "AllowsMultiple": bool(source.get("AllowsMultiple", False)),
        "AuditMetadata": deepcopy(source.get("AuditMetadata", {})),
    }


def review_decision(values):
    source = dict(values or {})
    decision = str(source.get("Decision", "")).upper()
    if decision not in DECISIONS:
        raise TransactionPipelineError(f"Unsupported review decision: {decision}")
    return {
        "ReviewDecisionID": str(source.get("ReviewDecisionID") or stable_id("REV")),
        "SubmissionID": str(source.get("SubmissionID", "")),
        "EventID": str(source.get("EventID", "")), "TeamID": str(source.get("TeamID", "")),
        "ReviewerID": str(source.get("ReviewerID", "")), "Decision": decision,
        "Score": float(source.get("Score", 0) or 0), "Credits": float(source.get("Credits", 0) or 0),
        "ReviewerNotes": str(source.get("ReviewerNotes", "")),
        "RejectionReason": str(source.get("RejectionReason", "")),
        "DecidedAt": str(source.get("DecidedAt") or now()),
        "IdempotencyKey": str(source.get("IdempotencyKey", "")),
        "SupersedesDecisionID": str(source.get("SupersedesDecisionID", "")),
        "AuditMetadata": deepcopy(source.get("AuditMetadata", {})),
    }


def award_transaction(values):
    source = dict(values or {})
    award_type = str(source.get("AwardType", "")).upper()
    if award_type not in AWARD_TYPES:
        raise TransactionPipelineError(f"Unsupported Award type: {award_type}")
    return {
        "AwardTransactionID": str(source.get("AwardTransactionID") or stable_id("AWD")),
        "EventID": str(source.get("EventID", "")), "TeamID": str(source.get("TeamID", "")),
        "SubmissionID": str(source.get("SubmissionID", "")),
        "ReviewDecisionID": str(source.get("ReviewDecisionID", "")),
        "ActivityID": str(source.get("ActivityID", "")), "AwardType": award_type,
        "Amount": float(source.get("Amount", 0) or 0), "Source": str(source.get("Source", "")),
        "Reason": str(source.get("Reason", "")), "IdempotencyKey": str(source.get("IdempotencyKey", "")),
        "CreatedBy": str(source.get("CreatedBy", "")), "CreatedAt": str(source.get("CreatedAt") or now()),
        "ReversalOfTransactionID": str(source.get("ReversalOfTransactionID", "")),
        "AuditMetadata": deepcopy(source.get("AuditMetadata", {})),
    }


def team_balances(awards, *, at=None):
    balances = defaultdict(lambda: {
        "IntelligenceCredits": 0.0, "Score": 0.0, "Bonuses": 0.0,
        "Penalties": 0.0, "MarketplaceSpend": 0.0, "AvailableBalance": 0.0,
    })
    for transaction in awards or []:
        if at and str(transaction.get("CreatedAt", "")) > str(at):
            continue
        row = balances[(transaction["EventID"], transaction["TeamID"])]
        amount, kind = float(transaction.get("Amount", 0)), transaction.get("AwardType")
        if kind in {"INTELLIGENCE_CREDITS", "MANUAL_ADJUSTMENT", "CORRECTION", "REFUND"}:
            row["IntelligenceCredits"] += amount
        elif kind == "SCORE": row["Score"] += amount
        elif kind == "BONUS": row["Bonuses"] += amount
        elif kind == "PENALTY": row["Penalties"] += amount
        elif kind == "MARKETPLACE_SPEND": row["MarketplaceSpend"] += amount
        row["AvailableBalance"] = (
            row["IntelligenceCredits"] + row["Bonuses"] + row["Penalties"]
            + row["MarketplaceSpend"]
        )
    return dict(balances)


def leaderboard_projection(awards, event_id, *, metric="Score", tie_breaker=None):
    balances = team_balances([row for row in awards if row.get("EventID") == event_id])
    rows = [{"EventID": event_id, "TeamID": team_id, **values}
            for (row_event, team_id), values in balances.items() if row_event == event_id]
    rows.sort(key=lambda row: (-float(row.get(metric, 0)), str(row["TeamID"])))
    previous = None
    rank = 0
    for position, row in enumerate(rows, 1):
        value = float(row.get(metric, 0))
        if previous is None or value != previous:
            rank = position
        row["Rank"] = rank
        row["TieBreak"] = tie_breaker or "STABLE_TEAM_ID"
        previous = value
    return rows


def aggregate_judge_scores(scores, config):
    method = str(config.get("AggregationMethod", "AVERAGE")).upper()
    excluded = bool(config.get("ExcludeHighestLowest", False))
    by_team = defaultdict(list)
    for score in scores or []:
        by_team[(score["EventID"], score["TeamID"])].append(
            float(score["RawScore"]) * float(score.get("Weight", 1))
        )
    result = {}
    for key, values in by_team.items():
        ordered = sorted(values)
        if excluded and len(ordered) >= 3:
            ordered = ordered[1:-1]
        result[key] = median(ordered) if method == "MEDIAN" else mean(ordered)
    return result


def judge_score(values):
    source = dict(values or {})
    return {
        "JudgeScoreID": str(source.get("JudgeScoreID") or stable_id("JDG")),
        "EventID": str(source.get("EventID", "")), "TeamID": str(source.get("TeamID", "")),
        "ActivityID": str(source.get("ActivityID", "")),
        "ExperienceAssignmentID": str(source.get("ExperienceAssignmentID", "")),
        "JudgeID": str(source.get("JudgeID", "")), "CriterionID": str(source.get("CriterionID", "")),
        "RawScore": float(source.get("RawScore", 0)), "Weight": float(source.get("Weight", 1)),
        "SubmittedAt": str(source.get("SubmittedAt") or now()), "LockedAt": source.get("LockedAt"),
        "IdempotencyKey": str(source.get("IdempotencyKey", "")),
        "AuditMetadata": deepcopy(source.get("AuditMetadata", {})),
    }


class TransactionPipeline:
    """Repository-backed application service with database-compatible idempotency."""

    def __init__(self, repository):
        self.repository = repository

    def submit(self, values, participant, assignment, *, team_override=False, event_override=False):
        if not submission_authorized(
            participant, assignment, team_override=team_override, event_override=event_override,
        ):
            raise TransactionPipelineError("Participant is not authorised to submit.")
        submission = canonical_submission(values)
        if submission["EvidenceType"] != "NONE" and not (
            submission["MediaAssetID"] or submission["StorageReference"]
            or submission["QRResult"] or submission["GPSResult"]
        ):
            raise TransactionPipelineError("Evidence metadata must exist before Submission creation.")
        saved = self.repository.insert_submission_idempotent(submission)
        if saved.get("Status") == "RETURNED_FOR_REVISION":
            return self.repository.resubmit_revision(saved["SubmissionID"], submission)
        return saved

    def decide(self, submission_id, values):
        submission = self.repository.get_submission(submission_id)
        if not submission:
            raise TransactionPipelineError("Submission was not found.")
        decision = review_decision({**values, "SubmissionID": submission_id,
                                    "EventID": submission["EventID"], "TeamID": submission["TeamID"]})
        lock = self.repository.get_lock(submission["EventID"], submission["ActivityID"])
        if lock and not decision["SupersedesDecisionID"]:
            raise TransactionPipelineError("Scoring is final-locked; an authorised correction is required.")
        saved = self.repository.insert_review_idempotent(decision)
        awards = []
        if saved["Decision"] == "CORRECT_PREVIOUS_DECISION" and saved["SupersedesDecisionID"]:
            for prior in self.repository.awards_for_review(saved["SupersedesDecisionID"]):
                awards.append(self.reverse_award(
                    prior["AwardTransactionID"], saved["ReviewerID"], "Correct previous decision",
                ))
        if saved["Decision"] in {"APPROVE", "CORRECT_PREVIOUS_DECISION"}:
            for kind, amount in (("SCORE", saved["Score"]), ("INTELLIGENCE_CREDITS", saved["Credits"])):
                if amount:
                    awards.append(self.repository.insert_award_idempotent(award_transaction({
                        "EventID": saved["EventID"], "TeamID": saved["TeamID"],
                        "SubmissionID": submission_id, "ReviewDecisionID": saved["ReviewDecisionID"],
                        "ActivityID": submission["ActivityID"], "AwardType": kind, "Amount": amount,
                        "Source": "REVIEW", "Reason": saved["Decision"],
                        "IdempotencyKey": f"{saved['IdempotencyKey']}:{kind}",
                        "CreatedBy": saved["ReviewerID"],
                    })))
        return saved, awards

    def manual_award(self, values):
        transaction = award_transaction(values)
        if not transaction["Reason"] or not transaction["CreatedBy"]:
            raise TransactionPipelineError("Manual awards require reason and facilitator.")
        return self.repository.insert_award_idempotent(transaction)

    def submit_judge_score(self, values):
        score = judge_score(values)
        if self.repository.get_lock(score["EventID"], score["ActivityID"]):
            raise TransactionPipelineError("Judging is final-locked.")
        return self.repository.insert_judge_score_idempotent(score)

    def reverse_award(self, transaction_id, actor, reason):
        original = self.repository.get_award(transaction_id)
        if not original:
            raise TransactionPipelineError("Award transaction was not found.")
        return self.manual_award({
            **original, "AwardTransactionID": stable_id("AWD"), "Amount": -float(original["Amount"]),
            "AwardType": original["AwardType"], "Source": "REVERSAL", "Reason": reason,
            "CreatedBy": actor, "ReversalOfTransactionID": transaction_id,
            "IdempotencyKey": f"REVERSAL:{transaction_id}",
        })

    def report(self, event_id):
        return {
            "EventID": event_id,
            "Submissions": self.repository.submissions(event_id),
            "ReviewDecisions": self.repository.reviews(event_id),
            "AwardTransactions": self.repository.awards(event_id),
            "JudgeScores": self.repository.judge_scores(event_id),
            "TeamBalances": team_balances(self.repository.awards(event_id)),
            "Leaderboard": leaderboard_projection(self.repository.awards(event_id), event_id),
        }
