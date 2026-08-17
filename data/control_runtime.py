"""The sole application service for facilitator-owned live mutations.

Participant joins and evidence submissions are inbound transactions, not control
plane mutations. Every stage, timer, broadcast, identity correction, approval,
credit and recovery operation must enter the runtime through this facade.
"""

from data.runtime_authority import control_centre_mutation


class ControlRuntime:
    """Capability-scoped Control Centre mutation facade."""

    def __init__(self, db):
        self.db = db
        self.runtime = db.runtime

    def _run(self, method, *args, **kwargs):
        with control_centre_mutation():
            return method(*args, **kwargs)

    def set_stage(self, event_id, stage):
        return self._run(self.db.set_event_stage, event_id, stage)

    def activate_experience_set(self, event_id, experience_set):
        return self._run(self.db.activate_experience_set, event_id, experience_set)

    def timer(self, event_id, stage_no, action, duration=0):
        return self._run(self.db.update_stage_timer, event_id, stage_no, action, duration)

    def control_state(self, event_id, key, value):
        return self._run(self.db.update_event_metadata, event_id, {key: value})

    def broadcast(self, event_id, payload):
        return self.control_state(event_id, "ProjectorBroadcast", payload)

    def review_submission(self, submission_id, score, remarks="", judged="Yes", status="APPROVED"):
        return self._run(
            self.db.update_submission_score, submission_id, score, remarks, judged, status,
        )

    def decide_canonical_submission(self, submission_id, decision, reviewer_id,
                                    score=0, credits=0, notes="", reason="",
                                    idempotency_key="", supersedes_id=""):
        return self._run(
            self.runtime.decide_canonical_submission, submission_id, decision, reviewer_id,
            score, credits, notes, reason, idempotency_key, supersedes_id,
        )

    def set_scoring_lock(self, event_id, scope_type, scope_id, locked, actor, reason):
        return self._run(
            self.runtime.set_scoring_lock, event_id, scope_type, scope_id,
            locked, actor, reason,
        )

    def configure_credit_wallet(self, event_id, enabled=True, reset=False):
        return self._run(self.runtime.configure_credit_wallet, event_id, enabled, reset)

    def set_credit_freeze(self, event_id, frozen):
        return self._run(self.runtime.set_credit_freeze, event_id, frozen)

    def publish_marketplace(self, event_id, items):
        return self._run(self.runtime.publish_marketplace, event_id, items)

    def adjust_credits(self, event_id, team_name, amount, description):
        return self._run(
            self.runtime.create_manual_award, event_id, team_name, amount,
            "MANUAL_ADJUSTMENT", description, "Facilitator",
        )

    def record_manual_arrival(self, event_id, team_name, stop_id):
        return self._run(self.runtime.record_manual_arrival, event_id, team_name, stop_id)

    def release_team_tracker(self, event_id, team_name):
        return self._run(self.runtime.release_team_tracker, event_id, team_name)

    def set_submission_override(self, event_id, team_id, enabled, actor):
        return self._run(
            self.runtime.set_submission_override, event_id, team_id, enabled, actor,
        )

    def transfer_leader(self, event_id, team_id, participant_id, actor):
        return self._run(
            self.runtime.transfer_team_leader, event_id, team_id, participant_id, actor,
        )

    def move_participant(self, participant_id, team_id, reason, actor):
        return self._run(
            self.runtime.move_participant, participant_id, team_id, reason, actor,
        )

    def decide_duplicate(self, event_id, canonical_id, duplicate_id, decision, reason, actor):
        return self._run(
            self.runtime.decide_duplicate,
            event_id, canonical_id, duplicate_id, decision, reason, actor,
        )

    def recover_participant(self, event_id, participant_id):
        """Return the immutable authoritative recovery package; never reallocates."""
        participant = next(
            (row for row in self.runtime.get_players(event_id)
             if str(row.get("ParticipantID", "")) == str(participant_id)),
            None,
        )
        if not participant:
            raise ValueError("Participant is not present in the authoritative runtime.")
        return {
            key: participant.get(key)
            for key in (
                "ParticipantID", "TeamID", "Team", "Country", "Flag", "IsLeader",
                "Points", "SessionToken", "LastSeenAt",
            )
        }

    def pause_event(self, event_id):
        return self.control_state(event_id, "CurrentStageStatus", "PAUSED")

    def resume_event(self, event_id):
        return self.control_state(event_id, "CurrentStageStatus", "RUNNING")

    def restart_runtime(self, event_id):
        """Republish configuration without resetting registrations or identities."""
        return self._run(self.db.publish_event_to_runtime, event_id, False)

    def set_race_build_status(self,event_id,team_id,status,checklist,reason,actor):
        return self._run(self.runtime.set_formula_race_build_status,event_id,team_id,status,checklist,reason,actor)

    def save_race_judging(self,event_id,team_id,scores,reason,actor):
        return self._run(self.runtime.save_formula_race_judging,event_id,team_id,scores,reason,actor)

    def save_race_result(self,event_id,team_id,time_ms,penalty_ms,bonus,verified,reason,actor):
        return self._run(self.runtime.save_formula_race_result,event_id,team_id,time_ms,penalty_ms,bonus,verified,reason,actor)

    def lock_race_results(self,event_id,actor,reason):
        return self._run(self.runtime.lock_formula_race_results,event_id,actor,reason)

    def set_race_checkpoint_runtime(self,event_id,module_id,action,actor):
        return self._run(self.runtime.set_formula_race_checkpoint_runtime,event_id,module_id,action,actor)

    def set_race_marketplace_runtime(self,event_id,action,actor):
        return self._run(self.runtime.set_formula_race_marketplace_runtime,event_id,action,actor)

    def adjust_race_credits(self,event_id,team_id,amount,reason,actor,idempotency_key):
        return self._run(self.runtime.formula_race_manual_credit_adjustment,event_id,team_id,amount,reason,actor,idempotency_key)

    def review_race_checkpoint(self,submission_id,decision,reviewer_id,notes="",reason="",idempotency_key="",official_result=None):
        return self._run(self.runtime.formula_race_review_checkpoint,submission_id,decision,reviewer_id,notes,reason,idempotency_key,official_result)
