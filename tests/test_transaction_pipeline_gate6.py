from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import threading

import pytest

from engines.transaction_pipeline import (
    TransactionPipeline, TransactionPipelineError, aggregate_judge_scores,
    leaderboard_projection, submission_authorized, team_balances,
)


ROOT = Path(__file__).resolve().parents[1]


class MemoryTransactions:
    def __init__(self):
        self.lock = threading.RLock()
        self.submission_rows = {}; self.submission_keys = {}
        self.review_rows = {}; self.review_keys = {}
        self.award_rows = {}; self.award_keys = {}; self.locks = set()
        self.judges = []

    def insert_submission_idempotent(self, row):
        logical = (row["EventID"], row["TeamID"], row["ExperienceAssignmentID"])
        key = (row["EventID"], row["IdempotencyKey"])
        with self.lock:
            existing = self.submission_keys.get(key) or (None if row["AllowsMultiple"] else self.submission_keys.get(logical))
            if existing: return deepcopy(self.submission_rows[existing])
            self.submission_rows[row["SubmissionID"]] = deepcopy(row)
            self.submission_keys[key] = row["SubmissionID"]
            if not row["AllowsMultiple"]: self.submission_keys[logical] = row["SubmissionID"]
            return deepcopy(row)
    def get_submission(self, submission_id): return deepcopy(self.submission_rows.get(submission_id))
    def resubmit_revision(self, submission_id, row):
        with self.lock:
            current=self.submission_rows[submission_id]
            current.update({key:deepcopy(row[key]) for key in (
                "TextResponse","MediaAssetID","StorageReference","QRResult","GPSResult","LastUpdatedAt"
            )})
            current["Status"]="PENDING_REVIEW"
            current["AuditMetadata"]={**current.get("AuditMetadata",{}),"RevisionResubmitted":True}
            return deepcopy(current)
    def insert_review_idempotent(self, row):
        key = (row["EventID"], row["IdempotencyKey"])
        with self.lock:
            if key in self.review_keys: return deepcopy(self.review_rows[self.review_keys[key]])
            self.review_rows[row["ReviewDecisionID"]] = deepcopy(row); self.review_keys[key] = row["ReviewDecisionID"]
            return deepcopy(row)
    def insert_award_idempotent(self, row):
        key = (row["EventID"], row["IdempotencyKey"])
        with self.lock:
            if key in self.award_keys: return deepcopy(self.award_rows[self.award_keys[key]])
            self.award_rows[row["AwardTransactionID"]] = deepcopy(row); self.award_keys[key] = row["AwardTransactionID"]
            return deepcopy(row)
    def get_award(self, award_id): return deepcopy(self.award_rows.get(award_id))
    def awards_for_review(self, review_id):
        return [deepcopy(row) for row in self.award_rows.values() if row["ReviewDecisionID"] == review_id]
    def get_lock(self, event_id, activity_id): return (event_id, activity_id) in self.locks
    def insert_judge_score_idempotent(self, row):
        key=(row["EventID"],row["IdempotencyKey"])
        with self.lock:
            existing=next((x for x in self.judges if (x["EventID"],x["IdempotencyKey"])==key),None)
            if existing:return deepcopy(existing)
            self.judges.append(deepcopy(row));return deepcopy(row)
    def submissions(self, event): return [deepcopy(x) for x in self.submission_rows.values() if x["EventID"] == event]
    def reviews(self, event): return [deepcopy(x) for x in self.review_rows.values() if x["EventID"] == event]
    def awards(self, event): return [deepcopy(x) for x in self.award_rows.values() if x["EventID"] == event]
    def judge_scores(self, event): return [deepcopy(x) for x in self.judges if x["EventID"] == event]


def participant(leader=True): return {"ParticipantID": "P1", "TeamID": "T1", "IsLeader": leader}
def assignment(rule="LEADER_ONLY", active=True):
    return {"ExperienceAssignmentID": "A1", "Active": active, "RuntimeEligible": True, "SubmissionRule": rule}
def values(event="E1", idem="submit-1"):
    return {"SubmissionID": f"S-{event}-{idem}", "EventID": event, "TeamID": "T1", "ParticipantID": "P1",
            "ProgrammeID": "PR1", "ModuleID": "M1", "ActivityID": "ACT1",
            "ExperienceDefinitionID": "D1", "ExperienceAssignmentID": "A1",
            "DefinitionVersion": 1, "AssignmentVersion": 1, "SubmissionType": "TEXT",
            "EvidenceType": "NONE", "TextResponse": "Answer", "IdempotencyKey": idem}


def test_leader_submits_once_and_repeated_tap_returns_same_submission():
    repo=MemoryTransactions(); pipeline=TransactionPipeline(repo)
    first=pipeline.submit(values(),participant(),assignment()); second=pipeline.submit(values(),participant(),assignment())
    assert first["SubmissionID"]==second["SubmissionID"] and len(repo.submission_rows)==1


def test_two_concurrent_team_submissions_create_one_record():
    repo=MemoryTransactions(); pipeline=TransactionPipeline(repo)
    with ThreadPoolExecutor(max_workers=20) as pool:
        rows=list(pool.map(lambda i:pipeline.submit(values(idem=f"retry-{i}"),participant(),assignment()),range(100)))
    assert len({row["SubmissionID"] for row in rows})==1 and len(repo.submission_rows)==1


def test_member_authorization_uses_team_event_or_assignment_override():
    assert not submission_authorized(participant(False),assignment())
    assert submission_authorized(participant(False),assignment(),team_override=True)
    assert submission_authorized(participant(False),assignment(),event_override=True)
    assert submission_authorized(participant(False),assignment("ANY_MEMBER"))


def approved_pipeline():
    repo=MemoryTransactions(); pipeline=TransactionPipeline(repo)
    submission=pipeline.submit(values(),participant(),assignment())
    return repo,pipeline,submission


def test_approval_is_append_only_and_repeated_approval_awards_once():
    repo,pipeline,submission=approved_pipeline()
    decision={"Decision":"APPROVE","ReviewerID":"F1","Score":20,"Credits":100,"IdempotencyKey":"approve-1"}
    first=pipeline.decide(submission["SubmissionID"],decision); second=pipeline.decide(submission["SubmissionID"],decision)
    assert first[0]["ReviewDecisionID"]==second[0]["ReviewDecisionID"]
    assert len(repo.review_rows)==1 and len(repo.award_rows)==2


def test_concurrent_approvals_and_credits_are_idempotent():
    repo,pipeline,submission=approved_pipeline()
    decision={"Decision":"APPROVE","ReviewerID":"F1","Credits":100,"IdempotencyKey":"same"}
    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(lambda _:pipeline.decide(submission["SubmissionID"],decision),range(100)))
    assert len(repo.review_rows)==1 and len(repo.award_rows)==1


@pytest.mark.parametrize("decision",["REJECT","RETURN_FOR_REVISION"])
def test_non_approval_creates_no_award(decision):
    repo,pipeline,submission=approved_pipeline()
    pipeline.decide(submission["SubmissionID"],{"Decision":decision,"ReviewerID":"F1","IdempotencyKey":decision})
    assert not repo.award_rows


def test_return_for_revision_resubmits_same_canonical_record_safely():
    repo,pipeline,submission=approved_pipeline()
    pipeline.decide(submission["SubmissionID"],{"Decision":"RETURN_FOR_REVISION","ReviewerID":"F1","IdempotencyKey":"return"})
    repo.submission_rows[submission["SubmissionID"]]["Status"]="RETURNED_FOR_REVISION"
    revised=values(idem="retry-after-return");revised["TextResponse"]="Revised answer"
    saved=pipeline.submit(revised,participant(),assignment())
    assert saved["SubmissionID"]==submission["SubmissionID"]
    assert saved["Status"]=="PENDING_REVIEW" and saved["AuditMetadata"]["RevisionResubmitted"]


def test_corrected_decision_reverses_prior_awards_then_applies_new_values():
    repo,pipeline,submission=approved_pipeline()
    prior,_=pipeline.decide(submission["SubmissionID"],{"Decision":"APPROVE","ReviewerID":"F1","Credits":100,"IdempotencyKey":"d1"})
    pipeline.decide(submission["SubmissionID"],{"Decision":"CORRECT_PREVIOUS_DECISION","ReviewerID":"F1",
      "Credits":40,"IdempotencyKey":"d2","SupersedesDecisionID":prior["ReviewDecisionID"]})
    balance=team_balances(repo.awards("E1"))[("E1","T1")]
    assert balance["IntelligenceCredits"]==40


def test_manual_credit_penalty_spend_and_refund_derive_balance_from_ledger():
    repo=MemoryTransactions(); pipeline=TransactionPipeline(repo)
    for kind,amount in (("MANUAL_ADJUSTMENT",100),("PENALTY",-10),("MARKETPLACE_SPEND",-30),("REFUND",20)):
        pipeline.manual_award({"EventID":"E1","TeamID":"T1","AwardType":kind,"Amount":amount,
          "Source":"MANUAL","Reason":kind,"CreatedBy":"F1","IdempotencyKey":kind})
    row=team_balances(repo.awards("E1"))[("E1","T1")]
    assert row["AvailableBalance"]==80 and row["Penalties"]==-10 and row["MarketplaceSpend"]==-30


def test_weighted_average_median_and_exclusion_are_configured():
    scores=[{"EventID":"E1","TeamID":"T1","RawScore":x,"Weight":2} for x in (1,5,9)]
    assert aggregate_judge_scores(scores,{"AggregationMethod":"AVERAGE"})[("E1","T1")]==10
    assert aggregate_judge_scores(scores,{"AggregationMethod":"MEDIAN","ExcludeHighestLowest":True})[("E1","T1")]==10


def test_duplicate_judge_submission_is_idempotent_and_lock_blocks_changes():
    repo=MemoryTransactions();pipeline=TransactionPipeline(repo)
    score={"EventID":"E1","TeamID":"T1","ActivityID":"A1","JudgeID":"J1",
           "CriterionID":"C1","RawScore":8,"Weight":1,"IdempotencyKey":"J1:C1:T1"}
    first=pipeline.submit_judge_score(score);second=pipeline.submit_judge_score(score)
    assert first["JudgeScoreID"]==second["JudgeScoreID"] and len(repo.judges)==1
    repo.locks.add(("E1","A1"))
    with pytest.raises(TransactionPipelineError): pipeline.submit_judge_score({**score,"IdempotencyKey":"new"})


def test_leaderboard_ties_are_deterministic_and_rebuild_identical():
    awards=[]
    for team in ("T2","T1"):
        awards.append({"EventID":"E1","TeamID":team,"AwardType":"SCORE","Amount":10,"CreatedAt":"1"})
    first=leaderboard_projection(awards,"E1"); second=leaderboard_projection(deepcopy(awards),"E1")
    assert first==second and [row["TeamID"] for row in first]==["T1","T2"] and {row["Rank"] for row in first}=={1}


def test_media_metadata_required_before_submission_and_retry_is_idempotent():
    repo=MemoryTransactions(); pipeline=TransactionPipeline(repo); payload=values(); payload["EvidenceType"]="PHOTO"
    with pytest.raises(TransactionPipelineError): pipeline.submit(payload,participant(),assignment())
    payload["MediaAssetID"]="ASSET-1"
    first=pipeline.submit(payload,participant(),assignment()); second=pipeline.submit(payload,participant(),assignment())
    assert first["MediaAssetID"]==second["MediaAssetID"]=="ASSET-1" and len(repo.submission_rows)==1


def test_final_lock_blocks_normal_review_but_authorised_correction_is_audited():
    repo,pipeline,submission=approved_pipeline(); repo.locks.add(("E1","ACT1"))
    with pytest.raises(TransactionPipelineError):
        pipeline.decide(submission["SubmissionID"],{"Decision":"APPROVE","ReviewerID":"F1","IdempotencyKey":"x"})
    decision,_=pipeline.decide(submission["SubmissionID"],{"Decision":"CORRECT_PREVIOUS_DECISION",
      "ReviewerID":"AUTH","IdempotencyKey":"correction","SupersedesDecisionID":"REV-OLD"})
    assert decision["ReviewerID"]=="AUTH" and decision["SupersedesDecisionID"]=="REV-OLD"


def test_dual_event_reports_and_history_are_isolated_and_reproducible():
    repo=MemoryTransactions(); pipeline=TransactionPipeline(repo)
    for event in ("E1","E2"):
        submission=pipeline.submit(values(event,event),participant(),assignment())
        pipeline.decide(submission["SubmissionID"],{"Decision":"APPROVE","ReviewerID":"F1","Score":10,
          "IdempotencyKey":f"approve-{event}"})
    snapshot=deepcopy(pipeline.report("E1")); assert pipeline.report("E1")==snapshot
    assert all(row["EventID"]=="E1" for row in snapshot["Submissions"]+snapshot["AwardTransactions"])


def test_schema_and_generic_engine_have_no_client_specific_scoring_routes():
    migration=(ROOT/"supabase"/"014_canonical_transaction_pipeline.sql").read_text()
    for table in ("canonical_submissions","review_decisions","award_transactions","judge_scores",
                  "team_balance_projection","leaderboard_projection"):
        assert table in migration
    generic=(ROOT/"engines"/"transaction_pipeline.py").read_text()
    for forbidden in ("EVT-0004","AIA","Bayu Beach","Formula RACE","Mission AI","MAHB"):
        assert forbidden not in generic
