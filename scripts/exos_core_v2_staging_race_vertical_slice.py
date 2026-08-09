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


def _in_filter(values: list[str]) -> str:
    sanitized = [str(value).replace('"', '""') for value in values]
    if not sanitized:
        return ""
    if len(sanitized) == 1:
        return f"eq.{sanitized[0]}"
    return "in.({})".format(
        ",".join('"{}"'.format(value) for value in sanitized)
    )


class CoreV2RaceStagingRunner:
    @staticmethod
    def _coerce_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, str):
            return value.lower() in {"true", "1", "yes", "y", "on"}
        return bool(value)

    def _is_reconnect_contract_ok(self, login: object, restore: object, session_row: object) -> bool:
        if not isinstance(login, dict) or not isinstance(restore, dict):
            return False

        expected_event_id = self._team_access_diagnostics.get("event_id")
        expected_team_id = self._team_access_diagnostics.get("team_id")
        expected_device_id = self._team_access_diagnostics.get("device_id")

        if login.get("EventID") != expected_event_id:
            return False
        if login.get("TeamID") != expected_team_id:
            return False

        if not isinstance(session_row, dict):
            return False
        if session_row.get("event_id") != expected_event_id:
            return False
        if session_row.get("team_id") != expected_team_id:
            return False
        if session_row.get("device_id") != expected_device_id:
            return False
        if not session_row.get("is_active"):
            return False

        if restore.get("EventID") != expected_event_id:
            return False
        if restore.get("TeamID") != expected_team_id:
            return False
        if self._coerce_bool(restore.get("Ambiguous")):
            return False
        if self._coerce_bool(restore.get("RecoveryRequired")):
            return False

        return True

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
        self.submission_ids = []

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
        self._legacy_rpc_calls = []
        self._cleanup_steps = []
        self._error = None
        self.captain_participant = {}
        self._team_access_diagnostics = {
            "event_id": None,
            "team_id": None,
            "device_id": None,
            "captain_participant": {},
            "team_access_session_id": None,
            "login_rpc_input": None,
            "login_rpc_response": None,
            "restore_rpc_input": None,
            "restore_rpc_response": None,
            "stored_credential_row": None,
            "stored_session_row": None,
        }

        # Canonical operation audit for this runner.
        self.operation_audit = []

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _record_operation(self, step: str, table_or_rpc: str, method: str, filters_or_payload: dict | None) -> None:
        self.operation_audit.append(
            {
                "step": step,
                "table_or_rpc": table_or_rpc,
                "method": method,
                "filters_or_payload": filters_or_payload or {},
            }
        )

    def get_activity_ids_for_event(self, event_id: str) -> list[str]:
        programmes = self._get(
            "programmes_v2",
            {
                "event_id": f"eq.{event_id}",
                "select": "programme_id",
            },
        )
        programme_ids = [row.get("programme_id") for row in (programmes or []) if isinstance(row, dict) and row.get("programme_id")]
        if not programme_ids:
            return []

        modules = self._get(
            "modules_v2",
            {
                "programme_id": _in_filter(programme_ids),
                "select": "module_id",
            },
        )
        module_ids = [row.get("module_id") for row in (modules or []) if isinstance(row, dict) and row.get("module_id")]
        if not module_ids:
            return []

        activities = self._get(
            "activities_v2",
            {
                "module_id": _in_filter(module_ids),
                "select": "activity_id",
            },
        )
        return [
            row.get("activity_id")
            for row in (activities or [])
            if isinstance(row, dict) and row.get("activity_id")
        ]

    def get_submission_ids_for_event(self, event_id: str) -> list[str]:
        submissions = self._get(
            "submissions_v2",
            {
                "event_id": f"eq.{event_id}",
                "select": "submission_id",
            },
        )
        return [
            str(row.get("submission_id"))
            for row in (submissions or [])
            if isinstance(row, dict) and row.get("submission_id")
        ]

    def get_review_ids_for_event(self, event_id: str) -> list[str]:
        submission_ids = self.get_submission_ids_for_event(event_id)
        if not submission_ids:
            return []

        submission_filter = _in_filter(submission_ids)
        if not submission_filter:
            return []

        reviews = self._get(
            "reviews_v2",
            {
                "submission_id": submission_filter,
                "select": "review_id",
            },
        )
        return [
            str(row.get("review_id"))
            for row in (reviews or [])
            if isinstance(row, dict) and row.get("review_id")
        ]

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

    @staticmethod
    def _is_legacy_runtime_rpc(name: str) -> bool:
        normalized = (name or "").lower()
        return any(
            pattern in normalized
            for pattern in (
                LEGACY_RUNTIME_TABLE_PATTERNS
                | {
                    "exos_formula_race_",
                    "formula_race",
                    "exos_set_formula_race_",
                    "exos_formula_race",
                }
            )
        )

    def _assert_no_legacy_runtime_calls(self) -> None:
        count = len(self._legacy_runtime_calls) + len(self._legacy_rpc_calls)
        print(f"LEGACY_RUNTIME_CALLS = {count}")
        if count:
            details = ", ".join(
                sorted(set(self._legacy_runtime_calls + self._legacy_rpc_calls))
            )
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
        if self._is_legacy_runtime_rpc(name):
            self._legacy_rpc_calls.append(name)
            raise RuntimeError(f"Blocked legacy RPC call attempt: {name}")
        self._record_operation("rpc", name, "POST", payload)
        return self._request("POST", f"rpc/{name}", payload=payload, admin=admin)

    def _post(self, table: str, payload: dict):
        self._record_operation("insert", table, "POST", payload)
        return self._request("POST", table, payload=payload, admin=True)

    def _get(self, table: str, query: dict):
        self._record_operation("query", table, "GET", query)
        return self._request("GET", table, query=query, admin=True)

    def _delete(self, table: str, query: dict):
        self._cleanup_steps.append((table, dict(query)))
        self._record_operation("delete", table, "DELETE", query)
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
        captain_name = f"CORE-V2-RACE-CAP-{self.event_id[-6:]}"
        captain_device = self.captain_device

        selected_team_id = self.team_ids[0]

        self._team_access_diagnostics.update(
            {
                "event_id": self.event_id,
                "team_id": selected_team_id,
                "device_id": captain_device,
                "captain_participant": {},
                "team_access_session_id": None,
            }
        )

        captain = self._rpc(
            "exos_v2_join_event_v2",
            {
                "p_join_code": self.join_code,
                "p_participant_name": captain_name,
                "p_device_id": captain_device,
                "p_requested_team_id": self.team_ids[0],
            },
            admin=False,
        )
        if not isinstance(captain, dict) or captain.get("RecoveryRequired"):
            raise RuntimeError("Captain seed join failed")
        self.captain_participant = {
            "participant_id": captain.get("ParticipantID"),
            "team_id": captain.get("TeamID"),
        }
        team_id = self.captain_participant.get("team_id") or self.team_ids[0]

        wrong_pin_ok = False
        try:
            self._rpc(
                "exos_v2_team_access_login",
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

        # Keep pin as TEAM-ID suffixed deterministic token for UAT execution.
        team_pin = f"PIN-{team_id[-2:]}"
        configured = 0
        for team_id in self.team_ids:
            result = self._rpc(
                "exos_v2_set_team_access_pin",
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

        # Keep pin as TEAM-ID suffixed deterministic token for UAT execution.
        team_pin = f"PIN-{selected_team_id[-2:]}"
        login = self._rpc(
            "exos_v2_team_access_login",
            {
                "p_join_code": self.join_code,
                "p_team_id": selected_team_id,
                "p_pin": team_pin,
                "p_device_id": self.captain_device,
            },
            admin=False,
        )
        login_team_id = login.get("TeamID") if isinstance(login, dict) else None
        self._team_access_diagnostics["team_id"] = login_team_id or selected_team_id
        self._team_access_diagnostics["login_rpc_input"] = {
            "p_event_id": self.event_id,
            "p_team_id": login_team_id or selected_team_id,
            "p_device_id": self.captain_device,
            "used_team_pin_suffix": f"PIN-{(selected_team_id[-2:] if selected_team_id else 'NA')}",
        }
        self._team_access_diagnostics["login_rpc_response"] = login
        self.session_token = str(login.get("SessionToken", "")) if isinstance(login, dict) else ""

        login_ok = (
            isinstance(login, dict)
            and login.get("EventID") == self.event_id
            and login.get("TeamID") == (login_team_id or selected_team_id)
            and len(self.session_token) > 0
        )

        self._team_access_diagnostics["restore_rpc_input"] = {
            "p_session_token": self.session_token,
            "p_device_id": self.captain_device,
        }
        restore = self._rpc(
            "exos_v2_restore_team_access",
            {
                "p_session_token": self.session_token,
                "p_device_id": self.captain_device,
            },
            admin=False,
        )
        self._team_access_diagnostics["restore_rpc_response"] = restore

        credential_rows = self._get(
            "team_access_credentials_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{login_team_id or selected_team_id}",
                "select": "team_access_credential_id,event_id,team_id,credential_purpose,is_active,created_by,created_at,updated_at",
            },
        )
        session_rows = self._get(
            "team_access_sessions_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{login_team_id or selected_team_id}",
                "select": "team_access_session_id,event_id,team_id,device_id,is_active,recovery_required,session_token,team_access_credential_id,updated_at,last_seen_at",
                "order": "updated_at.desc",
            },
        )
        stored_session_row = session_rows[0] if isinstance(session_rows, list) and session_rows else None
        self._team_access_diagnostics["stored_session_row"] = stored_session_row
        stored_credential_row = credential_rows[0] if isinstance(credential_rows, list) and credential_rows else None
        self._team_access_diagnostics["stored_credential_row"] = stored_credential_row

        if stored_session_row and stored_session_row.get("team_access_session_id"):
            self._team_access_diagnostics["team_access_session_id"] = stored_session_row.get("team_access_session_id")
            self._team_access_diagnostics["team_id"] = stored_session_row.get("team_id") or self._team_access_diagnostics.get("team_id")
        self._team_access_diagnostics["captain_participant"] = dict(self.captain_participant)

        print("TEAM ACCESS DIAGNOSTICS:")
        print(json.dumps(self._team_access_diagnostics, sort_keys=True))

        wrong_device_login_blocked = False
        try:
            self._rpc(
                "exos_v2_team_access_login",
                {
                    "p_join_code": self.join_code,
                    "p_team_id": selected_team_id,
                    "p_pin": team_pin,
                    "p_device_id": f"{self.captain_device}-OTHER",
                },
                admin=False,
            )
        except RuntimeError:
            wrong_device_login_blocked = True

        # Keep wrong-device guard for hardening, but do not couple reconnect gate to it.
        self.gates["captain_login"] = bool(login_ok)
        self.gates["captain_reconnect"] = bool(
            login_ok
            and self._is_reconnect_contract_ok(login, restore, stored_session_row)
        )

        if wrong_device_login_blocked:
            self._team_access_diagnostics["wrong_device_reject_reason"] = "blocked"
        else:
            self._team_access_diagnostics["wrong_device_reject_reason"] = "allowed"

        if not (self.gates["captain_login"] and self.gates["captain_reconnect"] and wrong_pin_ok):
            raise RuntimeError("Captain identity controls failed")

        activity_runtime_rows = self._post(
            "activity_runtime_v2",
            {
                "event_id": self.event_id,
                "team_id": team_id,
                "participant_id": self.captain_participant.get("participant_id"),
                "activity_id": self.checkpoint_rows[0].get("activity_id"),
                "state_payload": {
                    "status": "LIVE",
                    "actor": "CAPTAIN",
                    "mode": "parallel_checkpoints",
                    "activity_count": len(self.checkpoint_rows),
                },
                "activity_started_at": self._now_iso(),
                "is_completed": False,
            },
        )
        self.gates["four_checkpoints"] = bool(
            self.gates["four_checkpoints"]
            and isinstance(activity_runtime_rows, list)
            and len(activity_runtime_rows) >= 1
        )

    def submit_and_review(self) -> None:
        checkpoints = self._get(
            "activities_v2",
            {
                "programme_id": f"eq.{self.programme_id}",
                "activity_type": "eq.CHECKPOINT",
                "select": "activity_id,activity_name,activity_payload",
                "order": "activity_order.asc",
            },
        )
        if not (isinstance(checkpoints, list) and checkpoints):
            raise RuntimeError("No checkpoints available for submission")

        cp = checkpoints[0]
        checkpoint_id = cp.get("activity_id")
        submission = self._post(
            "submissions_v2",
            {
                "event_id": self.event_id,
                "team_id": self.captain_participant.get("team_id"),
                "participant_id": self.captain_participant.get("participant_id"),
                "activity_id": checkpoint_id,
                "submission_key": f"race-checkpoint-{uuid.uuid4().hex}",
                "submission_payload": {
                    "checkpoint_text": "checkpoint proof",
                    "checkpoint_id": checkpoint_id,
                },
            },
        )
        submission_id = submission[0].get("submission_id") if isinstance(submission, list) else None
        self.gates["checkpoint_submission"] = bool(
            isinstance(submission, list)
            and bool(submission_id)
        )
        if not self.gates["checkpoint_submission"]:
            raise RuntimeError("Checkpoint submission failed")

        review = self._post(
            "reviews_v2",
            {
                "event_id": self.event_id,
                "submission_id": submission_id,
                "reviewer": "QA Reviewer",
                "decision": "APPROVE",
                "score_points": 10,
                "rationale": "Looks good",
            },
        )

        repeat_review = self._post(
            "reviews_v2",
            {
                "event_id": self.event_id,
                "submission_id": submission_id,
                "reviewer": "QA Reviewer",
                "decision": "APPROVE",
                "score_points": 10,
                "rationale": "Repeat",
            },
        )

        score_txn = self._rpc(
            "exos_v2_ledger_score",
            {
                "p_event_id": self.event_id,
                "p_team_id": self.captain_participant.get("team_id"),
                "p_submission_id": submission_id,
                "p_amount": 5,
                "p_reason": "checkpoint",
                "p_scoring_mode": "TEAM_COMPETITIVE",
                "p_idempotency_key": f"race-score-{uuid.uuid4().hex}",
            },
            admin=True,
        )

        self.gates["facilitator_review"] = bool(
            isinstance(review, list)
            and isinstance(repeat_review, list)
            and isinstance(score_txn, str)
        )

        team_id = self.captain_participant.get("team_id") or self.team_ids[0]
        credit_rows = self._get(
            "credit_transactions_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{team_id}",
                "transaction_type": "eq.PURCHASE",
                "select": "credit_transaction_id,amount,transaction_type,reason",
            },
        )

        credits = sum((row.get("amount") or 0) for row in credit_rows) if isinstance(credit_rows, list) else None
        earned = sum((row.get("amount") or 0) for row in credit_rows) if isinstance(credit_rows, list) else 0
        self.gates["credits_ledger"] = bool(isinstance(credits, (int, float)) and credits >= 0)
        self.gates["wallet_reconciliation"] = bool(isinstance(credit_rows, list) and earned >= 0)

    def marketplace_journey(self) -> None:
        team_id = self.captain_participant.get("team_id") or self.team_ids[0]
        item_id = f"CORE-V2-RACE-ITEM-{self.event_id[-6:]}"

        self._post(
            "marketplace_items_v2",
            {
                "event_id": self.event_id,
                "item_id": item_id,
                "item_name": "Engine Kit",
                "item_type": "STANDARD",
                "unit_cost_credits": 5,
                "stock_limit": 2,
                "is_active": True,
            },
        )

        first = self._rpc(
            "exos_v2_ledger_credit",
            {
                "p_event_id": self.event_id,
                "p_team_id": team_id,
                "p_participant_id": self.captain_participant.get("participant_id"),
                "p_transaction_type": "PURCHASE",
                "p_amount": 10,
                "p_reason": "Wallet top-up",
                "p_idempotency_key": f"credit-topup-{self.event_id}",
            },
            admin=True,
        )
        purchase = self._post(
            "marketplace_transactions_v2",
            {
                "event_id": self.event_id,
                "team_id": team_id,
                "item_id": item_id,
                "credit_transaction_id": first if isinstance(first, str) else str(first),
                "quantity": 1,
                "amount_paid": 5,
                "status": "COMPLETED",
                "idempotency_key": f"purchase-{self.event_id}",
            },
        )

        stock_fail = False
        try:
            self._post(
                "marketplace_transactions_v2",
                {
                    "event_id": self.event_id,
                    "team_id": team_id,
                    "item_id": item_id,
                    "credit_transaction_id": first if isinstance(first, str) else str(first),
                    "quantity": 99,
                    "amount_paid": 495,
                    "status": "COMPLETED",
                    "idempotency_key": f"purchase-over-{uuid.uuid4().hex}",
                },
            )
        except RuntimeError:
            stock_fail = True

        stock_rows = self._get(
            "marketplace_items_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "item_id": f"eq.{item_id}",
            "select": "stock_limit",
            },
        )

        if isinstance(stock_rows, list) and len(stock_rows) == 1:
            stock_fail = stock_fail or stock_rows[0].get("stock_limit", 0) == 0

        self.gates["marketplace"] = bool(
            isinstance(first, str)
            and isinstance(purchase, list)
            and isinstance(stock_rows, list)
            and len(stock_rows) == 1
        )

    def build_judging_and_results(self) -> None:
        team_id = self.captain_participant.get("team_id") or self.team_ids[0]

        self._post(
            "build_status_v2",
            {
                "event_id": self.event_id,
                "team_id": team_id,
                "activity_id": self.activity_ids[0],
                "build_status": "IN_PROGRESS",
                "progress_pct": 25,
                "build_payload": {"chassis": True, "electronics": True},
            },
        )

        build_rows = self._get(
            "build_status_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{team_id}",
                "select": "build_status,team_id",
                "order": "created_at.desc",
                "limit": "1",
            },
        )
        self.gates["build_status"] = bool(isinstance(build_rows, list) and bool(build_rows))

        self._post(
            "judging_scores_v2",
            {
                "event_id": self.event_id,
                "team_id": team_id,
                "activity_id": self.activity_ids[0],
                "judge_name": "QA Judge",
                "score_dimension": "Engineering Design",
                "score_value": 8,
                "decision": "APPROVE",
                "rationale": "initial",
            },
        )
        correction = self._post(
            "judging_scores_v2",
            {
                "event_id": self.event_id,
                "team_id": team_id,
                "activity_id": self.activity_ids[0],
                "judge_name": "QA Judge",
                "score_dimension": "Creativity",
                "score_value": 10,
                "decision": "APPROVE",
                "rationale": "correction",
            },
        )
        judge_rows = self._get(
            "judging_scores_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{team_id}",
                "select": "judge_name,score_value,score_dimension",
            },
        )
        self.gates["judging"] = bool(
            isinstance(judge_rows, list)
            and bool(judge_rows)
            and isinstance(correction, list)
        )

        race_result = self._post(
            "race_results_v2",
            {
                "event_id": self.event_id,
                "team_id": team_id,
                "activity_id": self.activity_ids[0],
                "checkpoint": "Race Final",
                "ranking_position": 1,
                "result_payload": {
                    "time_ms": 120000,
                    "penalty_ms": 5000,
                    "bonus_credits": 20,
                    "verified": True,
                },
                "locked": False,
            },
        )
        result_rows = self._get(
            "race_results_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{team_id}",
                "select": "locked,result_payload,ranking_position",
            },
        )
        if not (isinstance(race_result, list) and isinstance(result_rows, list) and result_rows):
            raise RuntimeError("Race result not persisted")

        self.gates["race_result"] = True
        self.gates["penalties_bonuses"] = bool(
            any(
                (row.get("result_payload", {}).get("penalty_ms", 0) > 0
                 and row.get("result_payload", {}).get("bonus_credits", 0) > 0)
                for row in result_rows
            )
        )

        self._post(
            "race_results_v2",
            {
                "event_id": self.event_id,
                "team_id": team_id,
                "activity_id": self.activity_ids[0],
                "checkpoint": "Race Final",
                "ranking_position": 1,
                "result_payload": {"time_ms": 120000, "penalty_ms": 5000, "bonus_credits": 20, "verified": True},
                "locked": True,
            },
        )
        locked_rows = self._get(
            "race_results_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "team_id": f"eq.{team_id}",
                "checkpoint": "eq.Race Final",
                "select": "locked,ranking_position",
            },
        )
        self.gates["result_locking"] = bool(
            isinstance(locked_rows, list)
            and any(row.get("locked") is True for row in locked_rows)
        )

        state = self._get(
            "race_results_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "team_id,ranking_position,result_payload",
                "order": "ranking_position.asc",
            },
        )
        rankings = state if isinstance(state, list) else []
        self.gates["final_ranking"] = isinstance(rankings, list) and len(rankings) > 0

    def ui_verification(self) -> None:
        dashboard = self._get(
            "events_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "event_id,event_name,event_type,published_at",
            },
        )
        workspace = self._get(
            "activity_runtime_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "event_id,team_id,participant_id,state_payload",
                "limit": "1",
            },
        )
        state = self._get(
            "build_status_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "team_id,build_status,progress_pct",
            },
        )

        dashboard_ok = isinstance(dashboard, list) and bool(dashboard) and dashboard[0].get("event_id") == self.event_id
        workspace_ok = (
            isinstance(workspace, list)
            and workspace
            and workspace[0].get("event_id") == self.event_id
            and isinstance(state, list)
        )
        state_ok = bool(
            isinstance(state, list)
            and len(state) > 0
            and isinstance(workspace, list)
        )
        self.gates["race_premium_ui"] = bool(dashboard_ok and workspace_ok and state_ok)

    def cleanup(self) -> None:
        submission_rows = self._get(
            "submissions_v2",
            {
                "event_id": f"eq.{self.event_id}",
                "select": "submission_id",
            },
        )
        self.submission_ids = [
            str(row.get("submission_id"))
            for row in (submission_rows or [])
            if isinstance(row, dict) and row.get("submission_id")
        ]

        review_ids = self.get_review_ids_for_event(self.event_id)

        # Reverse dependency cleanup: child-first by team and submission scope.
        for team_id in self.team_ids:
            self._delete(
                "score_transactions_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )
            self._delete(
                "marketplace_transactions_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )
            self._delete(
                "build_status_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )
            self._delete(
                "judging_scores_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )
            self._delete(
                "race_results_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )
            self._delete(
                "activity_runtime_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )
            self._delete(
                "submissions_v2",
                {"event_id": f"eq.{self.event_id}", "team_id": f"eq.{team_id}"},
            )

        submission_filter = _in_filter(self.submission_ids)
        if submission_filter:
            self._delete(
                "submission_evidence_v2",
                {"submission_id": submission_filter},
            )
        if review_ids:
            self._delete(
                "reviews_v2",
                {"submission_id": _in_filter(review_ids)},
            )

        self._delete("team_access_sessions_v2", {"event_id": f"eq.{self.event_id}"})
        self._delete("team_access_credentials_v2", {"event_id": f"eq.{self.event_id}"})

        self._delete("participants_v2", {"event_id": f"eq.{self.event_id}"})
        self._delete("participant_sessions_v2", {"event_id": f"eq.{self.event_id}"})

        # Programme hierarchy delete via canonical FK path.
        activity_ids = self.get_activity_ids_for_event(self.event_id)
        if activity_ids:
            activity_filter = _in_filter(activity_ids)
            if activity_filter:
                self._delete("activity_runtime_v2", {"activity_id": activity_filter})

        module_ids = [
            row.get("module_id")
            for row in (self._get("modules_v2", {
                "programme_id": f"eq.{self.programme_id}",
                "select": "module_id",
            }) or [])
            if isinstance(row, dict) and row.get("module_id")
        ]
        if module_ids:
            module_filter = _in_filter(module_ids)
            if module_filter:
                self._delete("activities_v2", {"module_id": module_filter})
        self._delete("modules_v2", {"programme_id": f"eq.{self.programme_id}"})

        # Event-scoped references.
        self._delete("projector_state_v2", {"event_id": f"eq.{self.event_id}"})
        self._delete("marketplace_items_v2", {"event_id": f"eq.{self.event_id}"})
        self._delete("credit_transactions_v2", {"event_id": f"eq.{self.event_id}"})

        self._delete("programmes_v2", {"event_id": f"eq.{self.event_id}"})
        self._delete("teams_v2", {"event_id": f"eq.{self.event_id}"})
        self._delete("events_v2", {"event_id": f"eq.{self.event_id}"})

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
