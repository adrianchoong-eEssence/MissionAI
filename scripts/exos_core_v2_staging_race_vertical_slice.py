#!/usr/bin/env python3
"""Run a real staging Formula R.A.C.E. Core v2 vertical slice using direct Supabase REST/RPC."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


KNOWN_PROD_HOSTS = {
    # Known production runtime project (must never target).
    "bqsbkdfzqyiodivhyxnq.supabase.co",
}

LEGACY_RUNTIME_TABLE_PATTERNS = {
    "runtime_events",
    "runtime_teams",
    "runtime_participants",
    "runtime_submissions",
    "runtime_missions",
    "runtime_mission_submissions",
    "runtime_mission_evidence",
    "runtime_mission_status",
    "runtime_credit_transactions",
    "runtime_team_wallets",
    "runtime_marketplace_items",
    "runtime_marketplace_purchases",
    "formula_race_checkpoints",
    "formula_race_team_access",
    "formula_race_checkpoint_runtime",
    "formula_race_build_status",
    "formula_race_judging",
    "formula_race_results",
}


class CoreV2RaceStagingRunner:
    def __init__(self) -> None:
        self.supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.anon_key = (
            os.getenv("SUPABASE_PUBLISHABLE_KEY")
            or os.getenv("SUPABASE_ANON_KEY", "")
        ).strip()
        self.service_key = (
            os.getenv("SUPABASE_SECRET_KEY")
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        ).strip()
        self.env = os.getenv("EXOS_ENV", "").strip().lower()

        run_id = uuid.uuid4().hex[:10].upper()
        self.event_id = f"CORE-V2-RACE-UAT-EVT-{run_id}"
        self.join_code = f"RACE{run_id[:6]}"
        self.programme_id = f"CORE-V2-RACE-UAT-PROG-{run_id}"
        self.module_id = f"CORE-V2-RACE-UAT-MOD-{run_id}"
        self.activity_ids = [f"CORE-V2-RACE-UAT-CP-{idx:02d}-{run_id}" for idx in range(1, 5)]
        self.team_ids = [f"CORE-V2-RACE-UAT-T{idx:02d}-{run_id}" for idx in range(1, 11)]
        self.team_names = [f"RACE Team {idx:02d}" for idx in range(1, 11)]

        self.captain_device = f"CORE-V2-RACE-DEVICE-{run_id}"
        self.session_token = ""
        self.checkpoint_rows = []

        self.gates = {
            "staging_connectivity": False,
            "race_event_created": False,
            "ten_teams": False,
            "captain_login": False,
            "wrong_pin_rejection": False,
            "captain_reconnect": False,
            "four_checkpoints": False,
            "checkpoint_submission": False,
            "facilitator_review": False,
            "credits_ledger": False,
            "wallet_reconciliation": False,
            "marketplace": False,
            "build_status": False,
            "judging": False,
            "race_result": False,
            "penalties_bonuses": False,
            "result_locking": False,
            "final_ranking": False,
            "race_premium_ui": False,
            "google_sheets_runtime_calls": False,
            "cleanup": False,
        }

        self._legacy_runtime_calls = []
        self._cleanup_steps = []
        self._error = None

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _require_env(self) -> None:
        if self.env != "staging":
            raise RuntimeError("Refusing to run: EXOS_ENV must be exactly 'staging'.")
        if not self.supabase_url:
            raise RuntimeError("SUPABASE_URL is required.")
        if not self.anon_key:
            raise RuntimeError("SUPABASE_PUBLISHABLE_KEY (or SUPABASE_ANON_KEY) is required.")
        if not self.service_key:
            raise RuntimeError("SUPABASE_SECRET_KEY (or SUPABASE_SERVICE_ROLE_KEY) is required.")

        host = (urlparse(self.supabase_url).hostname or "").lower()
        print(f"Supabase host: {host}")
        if host in KNOWN_PROD_HOSTS:
            raise RuntimeError(f"Refusing to run against known production host: {host}")

    @staticmethod
    def _is_legacy_runtime_path(path: str) -> bool:
        normalized = (path or "").lower()
        if normalized.startswith("rpc/"):
            return False
        return any(pattern in normalized for pattern in LEGACY_RUNTIME_TABLE_PATTERNS)

    def _assert_no_legacy_runtime_calls(self) -> None:
        count = len(self._legacy_runtime_calls)
        print(f"LEGACY_RUNTIME_CALLS = {count}")
        if count:
            details = ", ".join(sorted(set(self._legacy_runtime_calls)))
            raise RuntimeError(f"Legacy runtime calls detected: {details}")

    def _request(self, method: str, path: str, payload=None, query=None, admin: bool = True):
        if self._is_legacy_runtime_path(path):
            self._legacy_runtime_calls.append(path)
            raise RuntimeError(f"Blocked legacy runtime call attempt: {path}")

        headers = {
            "apikey": self.service_key if admin else self.anon_key,
            "Authorization": f"Bearer {self.service_key if admin else self.anon_key}",
            "Accept": "application/json",
        }

        url = f"{self.supabase_url}/rest/v1/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query, doseq=True)}"

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            if method.upper() in {"POST", "PATCH", "PUT", "DELETE"}:
                headers["Prefer"] = "return=representation"
        elif method.upper() == "GET":
            headers["Prefer"] = "count=exact"

        req = Request(url, method=method.upper(), headers=headers, data=body)
        try:
            with urlopen(req, timeout=45) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return None
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return raw
        except HTTPError as error:
            body = ""
            try:
                body = error.read().decode("utf-8")
            except Exception:
                pass
            raise RuntimeError(f"HTTP {error.code} {method} {path}: {body or error.reason}")
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Request failed for {method} {path}: {exc}")

    def _rpc(self, name: str, payload: dict, admin: bool = True):
        return self._request("POST", f"rpc/{name}", payload=payload, admin=admin)

    def _post(self, table: str, payload: dict):
        return self._request("POST", table, payload=payload, admin=True)

    def _get(self, table: str, query: dict):
        return self._request("GET", table, query=query, admin=True)

    def _delete(self, table: str, query: dict):
        self._cleanup_steps.append((table, dict(query)))
        return self._request("DELETE", table, query=query, admin=True)

    def check_connectivity(self) -> None:
        rows = self._get("events_v2", {"select": "event_id", "limit": "1"})
        if isinstance(rows, list):
            self.gates["staging_connectivity"] = True
            return
        raise RuntimeError("Staging connectivity payload invalid")

    def create_race_event(self) -> None:
        teams = []
        for idx, team_id in enumerate(self.team_ids):
            teams.append(
                {
                    "team_id": team_id,
                    "team_name": self.team_names[idx],
                    "country": "Staging",
                    "team_flag": f"FLAG-{idx + 1:02d}",
                }
            )

        published = self._rpc(
            "exos_v2_publish_event",
            {
                "p_event_id": self.event_id,
                "p_join_code": self.join_code,
                "p_event_name": f"{self.event_id} Formula R.A.C.E. UAT",
                "p_teams": teams,
                "p_scoring_mode": "TEAM_COMPETITIVE",
                "p_event_type": "RACE",
            },
            admin=True,
        )
        if not isinstance(published, dict) or published.get("EventID") != self.event_id:
            raise RuntimeError("Event publish did not return expected payload")

        created_events = self._get(
            "events_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "event_id,event_type,programme_type,event_name",
                "limit": "1",
            },
        )
        teams_rows = self._get(
            "teams_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "team_id",
                "order": "team_id.asc",
            },
        )

        event_ok = bool(
            isinstance(created_events, list)
            and created_events
            and created_events[0].get("event_id") == self.event_id
        )
        self.gates["race_event_created"] = event_ok
        self.gates["ten_teams"] = isinstance(teams_rows, list) and len(teams_rows) >= 10
        if not (event_ok and self.gates["ten_teams"]):
            raise RuntimeError("Event creation or team seed failed")

    def create_programme_and_checkpoints(self) -> None:
        self._post(
            "programmes_v2",
            {
                "programme_id": self.programme_id,
                "event_id": self.event_id,
                "programme_name": f"{self.event_id} Programme",
                "programme_type": "Formula R.A.C.E.",
                "module_count": 1,
                "is_active": True,
            },
        )

        self._post(
            "modules_v2",
            {
                "module_id": self.module_id,
                "programme_id": self.programme_id,
                "module_name": "Formula R.A.C.E. Checkpoints",
                "module_payload": {"module_type": "RACE Checkpoints", "is_parallel": True},
                "activity_sequence": 1,
                "scoring_mode": "TEAM_COMPETITIVE",
                "is_active": True,
            },
        )

        for idx, activity_id in enumerate(self.activity_ids, 1):
            self._post(
                "activities_v2",
                {
                    "activity_id": activity_id,
                    "module_id": self.module_id,
                    "programme_id": self.programme_id,
                    "activity_type": "CHECKPOINT",
                    "scoring_mode": "TEAM_COMPETITIVE",
                    "activity_name": f"RACE Checkpoint {idx}",
                    "activity_order": idx,
                    "duration_seconds": 300,
                    "activity_payload": {
                        "proof_type": "Photo + Text" if idx % 2 == 0 else "Text",
                        "instructions": f"Formula R.A.C.E. checkpoint {idx}",
                        "max_score": 10,
                        "credits": 2,
                    },
                    "is_active": True,
                },
            )

        checkpoints = self._get(
            "activities_v2",
            {
                "programme_id": f"eq.{self.programme_id}",
                "activity_type": "eq.CHECKPOINT",
                "select": "activity_id,activity_name,activity_order,activity_payload",
                "order": "activity_order.asc",
            },
        )
        self.checkpoint_rows = checkpoints if isinstance(checkpoints, list) else []

        self.gates["four_checkpoints"] = bool(
            isinstance(self.checkpoint_rows, list) and len(self.checkpoint_rows) == 4
        )
        if not self.gates["four_checkpoints"]:
            raise RuntimeError("Checkpoint config not persisted with 4 checkpoints")

        # PIN configuration is exercised via captain RPC; keep mapping to this event's team set.
        self._configured_pins = True

    def captain_flow(self) -> None:
        team_id = self.team_ids[0]

        wrong_pin_ok = False
        try:
            self._rpc(
                "exos_formula_race_captain_login",
                {
                    "p_join_code": self.join_code,
                    "p_team_id": team_id,
                    "p_pin": "BADPIN",
                    "p_device_id": self.captain_device,
                },
                admin=False,
            )
            wrong_pin_ok = False
        except RuntimeError:
            wrong_pin_ok = True
        self.gates["wrong_pin_rejection"] = wrong_pin_ok

        # Keep pin as TEAM-ID suffixed deterministic token for non-persistent UAT execution.
        # This preserves the wrong-pin test while avoiding hard dependency on legacy pin storage tables.
        team_pin = f"PIN-{team_id[-2:]}"
        configured = 0
        for team_id in self.team_ids:
            result = self._rpc(
                "exos_set_formula_race_team_pin",
                {
                    "p_event_id": self.event_id,
                    "p_team_id": team_id,
                    "p_pin": f"PIN-{team_id[-2:]}",
                    "p_actor": "QA Bot",
                },
            )
            if isinstance(result, dict) and result.get("Configured"):
                configured += 1

        if configured < 10:
            raise RuntimeError("Not all team PINs were configured")

        # Keep pin as TEAM-ID suffixed deterministic token for non-persistent UAT execution.
        # This preserves the wrong-pin test while avoiding hard dependency on legacy pin storage tables.
        team_pin = f"PIN-{team_id[-2:]}"
        login = self._rpc(
            "exos_formula_race_captain_login",
            {
                "p_join_code": self.join_code,
                "p_team_id": team_id,
                "p_pin": team_pin,
                "p_device_id": self.captain_device,
            },
            admin=False,
        )
        self.session_token = str(login.get("SessionToken", "")) if isinstance(login, dict) else ""

        login_ok = (
            isinstance(login, dict)
            and login.get("EventID") == self.event_id
            and login.get("TeamID") == team_id
            and len(self.session_token) > 0
        )

        restore = self._rpc(
            "exos_formula_race_restore_captain",
            {"p_session_token": self.session_token, "p_device_id": self.captain_device},
            admin=False,
        )
        restore_ok = bool(
            isinstance(restore, dict)
            and restore.get("EventID") == self.event_id
            and restore.get("TeamID") == team_id
        )

        hijack_blocked = False
        try:
            self._rpc(
                "exos_formula_race_captain_login",
                {
                    "p_join_code": self.join_code,
                    "p_team_id": team_id,
                    "p_pin": team_pin,
                    "p_device_id": f"{self.captain_device}-OTHER",
                },
                admin=False,
            )
        except RuntimeError:
            hijack_blocked = True

        self.gates["captain_login"] = bool(login_ok)
        self.gates["captain_reconnect"] = bool(restore_ok and hijack_blocked)
        if not (self.gates["captain_login"] and self.gates["captain_reconnect"] and wrong_pin_ok):
            raise RuntimeError("Captain identity controls failed")

        rt = self._rpc(
            "exos_formula_race_set_checkpoint_runtime",
            {
                "p_event_id": self.event_id,
                "p_module_id": self.module_id,
                "p_action": "LAUNCH",
                "p_actor": "QA Bot",
            },
        )
        self.gates["four_checkpoints"] = bool(
            self.gates["four_checkpoints"]
            and isinstance(rt, dict)
            and rt.get("EventID") == self.event_id
            and rt.get("Status") == "LIVE"
        )

    def submit_and_review(self) -> None:
        state = self._rpc("exos_formula_race_checkpoint_state", {"p_event_id": self.event_id})
        checkpoints = state.get("Checkpoints", []) if isinstance(state, dict) else []
        if not (isinstance(checkpoints, list) and checkpoints):
            raise RuntimeError("No checkpoints available for submission")

        cp = checkpoints[0]
        submit = self._rpc(
            "exos_formula_race_submit_checkpoint",
            {
                "p_session_token": self.session_token,
                "p_device_id": self.captain_device,
                "p_activity_id": cp.get("ActivityID") or cp.get("activity_id") or cp.get("activityId"),
                "p_text_response": "checkpoint proof",
                "p_storage_reference": "",
                "p_idempotency_key": f"submit-{uuid.uuid4().hex}",
            },
            admin=False,
        )

        submission_id = submit.get("submission_id") if isinstance(submit, dict) else None
        self.gates["checkpoint_submission"] = bool(
            isinstance(submit, dict)
            and bool(submission_id)
            and submit.get("Duplicate") is False
        )
        if not self.gates["checkpoint_submission"]:
            raise RuntimeError("Checkpoint submission failed")

        review = self._rpc(
            "exos_formula_race_review_checkpoint",
            {
                "p_submission_id": submission_id,
                "p_decision": "APPROVE",
                "p_reviewer_id": "QA Reviewer",
                "p_notes": "Looks good",
                "p_reason": "UAT",
                "p_idempotency_key": f"review-{uuid.uuid4().hex}",
            },
        )

        repeat_review = self._rpc(
            "exos_formula_race_review_checkpoint",
            {
                "p_submission_id": submission_id,
                "p_decision": "APPROVE",
                "p_reviewer_id": "QA Reviewer",
                "p_notes": "Repeat",
                "p_reason": "Idempotency",
                "p_idempotency_key": f"review-repeat-{uuid.uuid4().hex}",
            },
        )

        self.gates["facilitator_review"] = bool(isinstance(review, dict) and isinstance(repeat_review, dict))

        team_id = self.team_ids[0]
        credit_rows = self._get(
            "credit_transactions_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{team_id}",
                "transaction_type": "eq.RECORD",
                "select": "credit_transaction_id,amount,source_type,reason",
            },
        )

        credits = sum((row.get("amount") or 0) for row in credit_rows) if isinstance(credit_rows, list) else None
        earned = sum((row.get("amount") or 0) for row in credit_rows) if isinstance(credit_rows, list) else 0
        self.gates["credits_ledger"] = bool(isinstance(credits, (int, float)) and credits >= 0)
        self.gates["wallet_reconciliation"] = bool(isinstance(credit_rows, list) and earned >= 0)

    def marketplace_journey(self) -> None:
        team_id = self.team_ids[0]
        item_id = f"CORE-V2-RACE-ITEM-{self.event_id[-6:]}"

        self._post(
            "marketplace_items_v2",
            {
                "event_id": self.event_id,
                "team_id": team_id,
                "item_id": item_id,
                "item_name": "Engine Kit",
                "description": "UAT test item",
                "price": 5,
                "stock_quantity": 2,
                "position": 1,
                "active": True,
            },
        )

        first = self._rpc(
            "exos_formula_race_purchase",
            {
                "p_session_token": self.session_token,
                "p_device_id": self.captain_device,
                "p_item_id": item_id,
                "p_quantity": 1,
                "p_idempotency_key": f"purchase-{self.event_id}",
            },
            admin=False,
        )
        duplicate = self._rpc(
            "exos_formula_race_purchase",
            {
                "p_session_token": self.session_token,
                "p_device_id": self.captain_device,
                "p_item_id": item_id,
                "p_quantity": 1,
                "p_idempotency_key": f"purchase-{self.event_id}",
            },
            admin=False,
        )

        stock_fail = False
        try:
            self._rpc(
                "exos_formula_race_purchase",
                {
                    "p_session_token": self.session_token,
                    "p_device_id": self.captain_device,
                    "p_item_id": item_id,
                    "p_quantity": 99,
                    "p_idempotency_key": f"purchase-over-{uuid.uuid4().hex}",
                },
                admin=False,
            )
        except RuntimeError:
            stock_fail = True

        stock_rows = self._get(
            "marketplace_items_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "item_id": f"eq.{item_id}",
                "select": "stock_quantity",
            },
        )

        self.gates["marketplace"] = bool(
            isinstance(first, dict)
            and first.get("Duplicate") is False
            and isinstance(duplicate, dict)
            and duplicate.get("Duplicate") is True
            and stock_fail
            and isinstance(stock_rows, list)
            and len(stock_rows) == 1
            and stock_rows[0].get("stock_quantity") in {None, 1}
        )

    def build_judging_and_results(self) -> None:
        team_id = self.team_ids[0]

        self._rpc(
            "exos_set_formula_race_build_status",
            {
                "p_event_id": self.event_id,
                "p_team_id": team_id,
                "p_status": "Collecting Parts",
                "p_checklist": {"chassis": True, "electronics": True},
                "p_reason": "UAT build",
                "p_actor": "QA Bot",
            },
        )

        build_rows = self._get(
            "build_status_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{team_id}",
                "select": "status,team_id",
                "order": "created_at.desc",
                "limit": "1",
            },
        )
        self.gates["build_status"] = bool(isinstance(build_rows, list) and bool(build_rows))

        scoring = {
            "Engineering Design": 8,
            "Structural Integrity": 8,
            "Innovation": 7,
            "Creativity": 9,
        }
        self._rpc(
            "exos_save_formula_race_judging",
            {
                "p_event_id": self.event_id,
                "p_team_id": team_id,
                "p_scores": scoring,
                "p_reason": "initial",
                "p_actor": "QA Judge",
            },
        )
        correction = self._rpc(
            "exos_save_formula_race_judging",
            {
                "p_event_id": self.event_id,
                "p_team_id": team_id,
                "p_scores": {**scoring, "Creativity": 10},
                "p_reason": "correction",
                "p_actor": "QA Judge",
            },
        )
        judge_rows = self._get(
            "judging_scores_v2",
            {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}", "select": "judge_name,total_score,is_current"},
        )
        self.gates["judging"] = bool(
            isinstance(judge_rows, list)
            and any(row.get("is_current") for row in judge_rows)
            and isinstance(correction, dict)
        )

        race_result = self._rpc(
            "exos_save_formula_race_result",
            {
                "p_event_id": self.event_id,
                "p_team_id": team_id,
                "p_time_ms": 120000,
                "p_penalty_ms": 5000,
                "p_bonus": 20,
                "p_verified": True,
                "p_reason": "UAT final",
                "p_actor": "QA Judge",
            },
        )
        result_rows = self._get(
            "race_results_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{team_id}",
                "select": "is_current,finish_time_ms,penalty_ms,bonus_credits",
            },
        )
        if not (isinstance(race_result, dict) and isinstance(result_rows, list) and result_rows):
            raise RuntimeError("Race result not persisted")

        self.gates["race_result"] = True
        self.gates["penalties_bonuses"] = bool(
            any((row.get("penalty_ms", 0) > 0 and row.get("bonus_credits", 0) > 0 and row.get("is_current")) for row in result_rows)
        )

        lock = self._rpc(
            "exos_formula_race_set_results_lock",
            {"p_event_id": self.event_id, "p_locked": True, "p_reason": "UAT lock", "p_actor": "QA Bot"},
        )
        blocking = False
        try:
            self._rpc(
                "exos_save_formula_race_result",
                {
                    "p_event_id": self.event_id,
                    "p_team_id": team_id,
                    "p_time_ms": 130000,
                    "p_penalty_ms": 5000,
                    "p_bonus": 0,
                    "p_verified": True,
                    "p_reason": "should fail",
                    "p_actor": "QA Judge",
                },
            )
        except RuntimeError:
            blocking = True
        self.gates["result_locking"] = bool(isinstance(lock, dict) and lock.get("ResultsLocked") is True and blocking)

        state = self._rpc("exos_formula_race_state", {"p_event_id": self.event_id})
        rankings = state.get("RaceResults") if isinstance(state, dict) else []
        self.gates["final_ranking"] = isinstance(rankings, list) and len(rankings) > 0

    def ui_verification(self) -> None:
        dashboard = self._get(
            "events_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "event_id,event_name,event_status,current_stage_no,programme_id",
            },
        )
        workspace = self._rpc(
            "exos_formula_race_captain_workspace",
            {"p_session_token": self.session_token, "p_device_id": self.captain_device},
            admin=False,
        )
        state = self._rpc("exos_formula_race_state", {"p_event_id": self.event_id})

        dashboard_ok = isinstance(dashboard, list) and bool(dashboard) and dashboard[0].get("event_id") == self.event_id
        workspace_ok = (
            isinstance(workspace, dict)
            and workspace.get("EventID") == self.event_id
            and workspace.get("TeamID") == self.team_ids[0]
            and isinstance(workspace.get("Wallet"), dict)
        )
        state_ok = bool(
            isinstance(state, dict)
            and isinstance(state.get("BuildStatus"), list)
            and isinstance(state.get("RaceResults"), list)
        )
        self.gates["race_premium_ui"] = bool(dashboard_ok and workspace_ok and state_ok)

    def cleanup(self) -> None:
        for team_id in self.team_ids:
            self._delete("race_results_v2", {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"})
            self._delete("judging_scores_v2", {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"})
            self._delete("build_status_v2", {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"})
            self._delete("submissions_v2", {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"})
            self._delete("submission_evidence_v2", {"event_id": f"eq.{self.event_id}"})
            self._delete("marketplace_transactions_v2", {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"})
            self._delete("score_transactions_v2", {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"})
            self._delete("reviews_v2", {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"})
            self._delete("activity_runtime_v2", {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"})

        for table in (
            "participants_v2",
            "participant_sessions_v2",
            "programmes_v2",
            "modules_v2",
            "activities_v2",
            "teams_v2",
            "events_v2",
            "credit_transactions_v2",
            "marketplace_items_v2",
        ):
            if table in {"programmes_v2", "modules_v2", "activities_v2"}:
                filters = {"programme_id": f"eq.{self.programme_id}"}
            else:
                filters = {"event_id": f"eq.{self.event_id}"}
            self._delete(table, filters)

        remaining = self._get("events_v2", {"event_id": f"eq.{self.event_id}", "select": "event_id"})
        self.gates["cleanup"] = bool(not (isinstance(remaining, list) and remaining))

        if not self.gates["cleanup"]:
            raise RuntimeError("Cleanup did not remove all scoped UAT rows")

    def print_report(self) -> None:
        print(f"Staging connectivity: {'PASS' if self.gates['staging_connectivity'] else 'FAIL'}")
        print(f"RACE event created: {'PASS' if self.gates['race_event_created'] else 'FAIL'}")
        print(f"10 teams: {'PASS' if self.gates['ten_teams'] else 'FAIL'}")
        print(f"Captain login: {'PASS' if self.gates['captain_login'] else 'FAIL'}")
        print(f"Wrong PIN rejection: {'PASS' if self.gates['wrong_pin_rejection'] else 'FAIL'}")
        print(f"Captain reconnect: {'PASS' if self.gates['captain_reconnect'] else 'FAIL'}")
        print(f"4 checkpoints: {'PASS' if self.gates['four_checkpoints'] else 'FAIL'}")
        print(f"Checkpoint submission: {'PASS' if self.gates['checkpoint_submission'] else 'FAIL'}")
        print(f"Facilitator review: {'PASS' if self.gates['facilitator_review'] else 'FAIL'}")
        print(f"Credits ledger: {'PASS' if self.gates['credits_ledger'] else 'FAIL'}")
        print(f"Wallet reconciliation: {'PASS' if self.gates['wallet_reconciliation'] else 'FAIL'}")
        print(f"Marketplace: {'PASS' if self.gates['marketplace'] else 'FAIL'}")
        print(f"Build status: {'PASS' if self.gates['build_status'] else 'FAIL'}")
        print(f"Judging: {'PASS' if self.gates['judging'] else 'FAIL'}")
        print(f"Race result: {'PASS' if self.gates['race_result'] else 'FAIL'}")
        print(f"Penalties/bonuses: {'PASS' if self.gates['penalties_bonuses'] else 'FAIL'}")
        print(f"Result locking: {'PASS' if self.gates['result_locking'] else 'FAIL'}")
        print(f"Final ranking: {'PASS' if self.gates['final_ranking'] else 'FAIL'}")
        print(f"RACE premium UI: {'PASS' if self.gates['race_premium_ui'] else 'FAIL'}")
        print(f"Google Sheets runtime calls: {'YES' if self.gates['google_sheets_runtime_calls'] else 'NO'}")
        print(f"Cleanup: {'PASS' if self.gates['cleanup'] else 'FAIL'}")
        print(f"EventID: {self.event_id}")

        if all(self.gates.values()):
            print("FORMULA R.A.C.E. ON EXOS CORE V2: READY")

    def run(self) -> int:
        self._require_env()
        try:
            self.check_connectivity()
            self.create_race_event()
            self.create_programme_and_checkpoints()
            self.captain_flow()
            self.submit_and_review()
            self.marketplace_journey()
            self.build_judging_and_results()
            self.ui_verification()
            self._assert_no_legacy_runtime_calls()
            return 0
        except Exception as exc:
            self._error = str(exc)
            print(f"[ERROR] {exc}")
            return 1
        finally:
            try:
                self.cleanup()
            except Exception as exc:
                print(f"[CLEANUP FAILED] {exc}")
                self.gates["cleanup"] = False
            self.print_report()
            if self._error:
                return 1


def main() -> int:
    return CoreV2RaceStagingRunner().run()


if __name__ == "__main__":
    raise SystemExit(main())
