#!/usr/bin/env python3
"""Execute the real generic Core v2 staging journey via Supabase REST/RPC."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


KNOWN_PROD_HOSTS = {
    # Historical production runtime project (explicitly blocked).
    "bqsbkdfzqyiodivhyxnq.supabase.co",
}


class CoreV2JourneyRunner:
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
        self.event_id = f"CORE-V2-UAT-EVT-{run_id}"
        self.join_code = f"UAT{run_id[:6]}"
        self.programme_id = f"CORE-V2-UAT-PROG-{run_id}"
        self.module_id = f"CORE-V2-UAT-MOD-{run_id}"
        self.activity_id = f"CORE-V2-UAT-ACT-{run_id}"

        self.participants = [
            {
                "name": "CORE-V2-UAT-ALPHA",
                "device": f"CORE-V2-UAT-DEVICE-{run_id}-01",
            },
            {
                "name": "CORE-V2-UAT-BRAVO",
                "device": f"CORE-V2-UAT-DEVICE-{run_id}-02",
            },
            {
                "name": "CORE-V2-UAT-CHARLIE",
                "device": f"CORE-V2-UAT-DEVICE-{run_id}-03",
            },
        ]

        self.join_results = []

        self.gates = {
            "staging_connectivity": False,
            "event_created": False,
            "teams_created": False,
            "programme_created": False,
            "module_created": False,
            "activity_created": False,
            "hierarchy_intact": False,
            "participant_joins": False,
            "balanced_grouping": False,
            "reconnect_identity_team": False,
            "activity_launch": False,
            "submission": False,
            "review_approval": False,
            "competitive_score_transaction": False,
            "result_retrievable_after_close": False,
            "cleanup": False,
        }

    # ---------------------------------------------------------
    # utilities
    # ---------------------------------------------------------
    @staticmethod
    def _now_iso() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _require_env(self) -> None:
        if self.env != "staging":
            raise RuntimeError("Refusing to run: EXOS_ENV must be exactly 'staging'.")

        if not self.supabase_url:
            raise RuntimeError("SUPABASE_URL is required.")
        if not self.anon_key:
            raise RuntimeError("SUPABASE_PUBLISHABLE_KEY (or SUPABASE_ANON_KEY) is required.")
        if not self.service_key:
            raise RuntimeError("SUPABASE_SECRET_KEY (or SUPABASE_SERVICE_ROLE_KEY) is required.")

        host = urlparse(self.supabase_url).hostname or ""
        print(f"Supabase host: {host}")
        if host in KNOWN_PROD_HOSTS:
            raise RuntimeError(f"Refusing to run against known production host: {host}")

    def _rest_request(self, method: str, path: str, payload=None, query=None, admin=True):
        base = self.supabase_url.rstrip("/")
        url = f"{base}/rest/v1/{path.lstrip('/')}"
        if query:
            q = urlencode(query, doseq=True)
            url = f"{url}?{q}"

        headers = {
            "apikey": self.service_key if admin else self.anon_key,
            "Authorization": f"Bearer {self.service_key if admin else self.anon_key}",
            "Accept": "application/json",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
            if method.upper() in {"POST", "PATCH", "PUT"}:
                headers["Prefer"] = "return=representation"
        if method.upper() == "GET":
            headers["Prefer"] = "count=exact"

        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        req = Request(url, method=method.upper(), headers=headers, data=data)
        try:
            with urlopen(req, timeout=45) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return True
                return json.loads(raw)
        except HTTPError as error:
            body = ""
            try:
                body = error.read().decode("utf-8")
            except Exception:
                pass
            raise RuntimeError(f"HTTP {error.code} {method} {path}: {body or error.reason}")
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Request failed for {method} {path}: {exc}")

    def _rest_request_with_status(self, method: str, path: str, payload=None, query=None, admin=True):
        base = self.supabase_url.rstrip("/")
        url = f"{base}/rest/v1/{path.lstrip('/')}"
        if query:
            q = urlencode(query, doseq=True)
            url = f"{url}?{q}"

        headers = {
            "apikey": self.service_key if admin else self.anon_key,
            "Authorization": f"Bearer {self.service_key if admin else self.anon_key}",
            "Accept": "application/json",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
            if method.upper() in {"POST", "PATCH", "PUT"}:
                headers["Prefer"] = "return=representation"
        if method.upper() == "GET":
            headers["Prefer"] = "count=exact"

        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        req = Request(url, method=method.upper(), headers=headers, data=data)
        try:
            with urlopen(req, timeout=45) as resp:
                raw = resp.read().decode("utf-8")
                payload_data = True
                if raw:
                    try:
                        payload_data = json.loads(raw)
                    except json.JSONDecodeError:
                        payload_data = raw
                return resp.status, payload_data
        except HTTPError as error:
            body = ""
            try:
                body = error.read().decode("utf-8")
            except Exception:
                pass
            return error.code, {
                "error": {
                    "status": error.code,
                    "path": path,
                    "method": method.upper(),
                    "body": body or error.reason,
                }
            }
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Request failed for {method} {path}: {exc}")

    def _rpc(self, name: str, payload: dict):
        return self._rest_request("POST", f"rpc/{name}", payload=payload, admin=True)

    @staticmethod
    def _to_in_list(values):
        if not values:
            return None
        escaped = []
        for value in values:
            escaped_value = str(value).replace("\\", "\\\\").replace('"', '\\"')
            escaped.append(f'"{escaped_value}"')
        return "in.(" + ",".join(escaped) + ")"

    def _fetch(self, table: str, query: dict):
        return self._rest_request("GET", table, query=query, admin=True)

    def _pluck(self, table: str, column: str, query: dict):
        rows = self._fetch(table, query)
        if not isinstance(rows, list):
            return []
        return [row.get(column) for row in rows if isinstance(row, dict) and row.get(column) is not None]

    def _count(self, table: str, query: dict) -> int:
        rows = self._fetch(table, query)
        if isinstance(rows, list):
            return len(rows)
        return 0

    def _delete_rows(self, table: str, query: dict, label: str = ""):
        try:
            self._rest_request("DELETE", table, query=query, admin=True)
        except Exception as exc:
            raise RuntimeError(f"delete failed for {label or table}: {exc}")

    def _ids_filter(self, ids, column: str):
        if not ids:
            return None
        in_clause = self._to_in_list(ids)
        if not in_clause:
            return None
        return {column: in_clause}

    def _delete_by_ids(self, table: str, ids, id_column: str, label: str = ""):
        in_clause = self._to_in_list(ids)
        if not in_clause:
            print(f"CLEANUP STEP SKIPPED — NO IDS | {label or table}")
            return
        self._delete_rows(table, {id_column: in_clause}, label=label or f"{table}.{id_column}")

    @staticmethod
    def _fmt_filter(query: dict) -> str:
        if not query:
            return "<empty>"
        parts = []
        for key in sorted(query.keys()):
            parts.append(f"{key}={query[key]}")
        return ", ".join(parts)

    def _delete_step(self, table: str, query: dict, label: str = "") -> tuple[dict, bool]:
        step_label = label or table
        if query is None:
            result = {
                "table": table,
                "label": step_label,
                "filter": "SKIPPED — NO IDS",
                "rows_matched_before_delete": 0,
                "delete_result": "SKIPPED — NO IDS",
                "rows_remaining_after_delete": 0,
                "http_status": 0,
                "error_body": "",
            }
            print(
                "CLEANUP STEP | "
                f"{step_label} | {result['filter']} | before=0 | result=SKIPPED — NO IDS | after=0 | status=0"
            )
            return result, False

        query_filter = dict(query or {})
        query_filter_repr = self._fmt_filter(query_filter)
        matched_before = self._count(table, query_filter)

        status, response = self._rest_request_with_status(
            "DELETE", table, query=query_filter, admin=True
        )
        rows_remaining = self._count(table, query_filter)

        failure_body = ""
        failed = False
        delete_result = "ok"

        if status >= 400 or (isinstance(response, dict) and response.get("error")):
            failed = True
            delete_result = "failed"
            failure_body = response.get("error", {}).get("body", "") if isinstance(response, dict) else str(response)
        elif isinstance(response, list):
            delete_result = f"deleted rows={len(response)}"
        elif isinstance(response, bool):
            delete_result = "ok (no payload)"
        else:
            delete_result = "ok"

        result = {
            "table": table,
            "label": step_label,
            "filter": query_filter_repr,
            "rows_matched_before_delete": matched_before,
            "delete_result": delete_result,
            "rows_remaining_after_delete": rows_remaining,
            "http_status": status,
            "error_body": failure_body,
        }
        print(
            "CLEANUP STEP | "
            f"{result['table']} | {result['filter']} | "
            f"before={result['rows_matched_before_delete']} | "
            f"result={result['delete_result']} | "
            f"after={result['rows_remaining_after_delete']} | "
            f"status={result['http_status']}"
        )
        if failure_body:
            print(f"CLEANUP STEP ERROR BODY | {failure_body}")
        return result, failed

    def _set(self, key: str, value: bool) -> None:
        self.gates[key] = bool(value)

    # ---------------------------------------------------------
    # journey steps
    # ---------------------------------------------------------
    def check_connectivity(self) -> None:
        rows = self._rest_request(
            "GET",
            "events_v2",
            query={"select": "event_id", "limit": "1"},
            admin=True,
        )
        if isinstance(rows, list):
            self._set("staging_connectivity", True)
            return
        raise RuntimeError("staging connectivity check returned unexpected payload")

    def create_event_and_publish(self) -> None:
        teams_payload = [
            {
                "team_id": f"CORE-V2-UAT-T1-{self.event_id[-6:]}",
                "team_name": "CORE-V2-UAT Team Red",
                "country": "Core-V2-UAT Red",
                "team_flag": "FLAG-RED",
            },
            {
                "team_id": f"CORE-V2-UAT-T2-{self.event_id[-6:]}",
                "team_name": "CORE-V2-UAT Team Blue",
                "country": "Core-V2-UAT Blue",
                "team_flag": "FLAG-BLUE",
            },
        ]

        self._rpc(
            "exos_v2_publish_event",
            {
                "p_event_id": self.event_id,
                "p_join_code": self.join_code,
                "p_event_name": f"{self.event_id} - Standard",
                "p_teams": teams_payload,
                "p_scoring_mode": "TEAM_COMPETITIVE",
                "p_event_type": "STANDARD",
            },
        )

        events = self._rest_request(
            "GET",
            "events_v2",
            query={"event_id": f"eq.{self.event_id}", "select": "event_id,join_code"},
            admin=True,
        )
        if not (isinstance(events, list) and events):
            raise RuntimeError("Event row not found after publish")
        self._set("event_created", True)

        teams = self._rest_request(
            "GET",
            "teams_v2",
            query={"event_id": f"eq.{self.event_id}", "select": "team_id,team_name"},
            admin=True,
        )
        self._set("teams_created", isinstance(teams, list) and len(teams) >= 2)

    def create_programme_module_activity(self) -> None:
        self._rest_request(
            "POST",
            "programmes_v2",
            payload={
                "programme_id": self.programme_id,
                "event_id": self.event_id,
                "programme_name": f"{self.event_id} Programme",
                "programme_type": "STANDARD",
                "programme_schema_version": 1,
                "module_count": 1,
                "is_active": True,
            },
            admin=True,
        )
        programme_rows = self._rest_request(
            "GET",
            "programmes_v2",
            query={"programme_id": f"eq.{self.programme_id}", "select": "programme_id,event_id,programme_type"},
            admin=True,
        )
        if not (isinstance(programme_rows, list) and programme_rows):
            raise RuntimeError("Programme not created")
        self._set("programme_created", True)

        self._rest_request(
            "POST",
            "modules_v2",
            payload={
                "module_id": self.module_id,
                "programme_id": self.programme_id,
                "module_name": f"{self.event_id} Module",
                "activity_sequence": 1,
                "module_payload": {
                    "module": "core-v2-generic",
                    "timing_mins": 60,
                },
                "scoring_mode": "TEAM_COMPETITIVE",
                "is_active": True,
            },
            admin=True,
        )
        module_rows = self._rest_request(
            "GET",
            "modules_v2",
            query={"module_id": f"eq.{self.module_id}", "select": "module_id,programme_id"},
            admin=True,
        )
        if not (isinstance(module_rows, list) and module_rows):
            raise RuntimeError("Module not created")
        self._set("module_created", True)

        self._rest_request(
            "POST",
            "activities_v2",
            payload={
                "activity_id": self.activity_id,
                "module_id": self.module_id,
                "programme_id": self.programme_id,
                "activity_type": "STANDARD",
                "scoring_mode": "TEAM_COMPETITIVE",
                "activity_name": f"{self.event_id} Activity",
                "activity_order": 1,
                "duration_seconds": 600,
                "activity_payload": {
                    "instructions": "Submit one text response.",
                    "max_score": 10,
                },
                "is_active": True,
            },
            admin=True,
        )
        activity_rows = self._rest_request(
            "GET",
            "activities_v2",
            query={
                "activity_id": f"eq.{self.activity_id}",
                "select": "activity_id,module_id,programme_id",
            },
            admin=True,
        )
        if not (isinstance(activity_rows, list) and activity_rows):
            raise RuntimeError("Activity not created")
        self._set("activity_created", True)

        activity = activity_rows[0]
        self._set(
            "hierarchy_intact",
            activity.get("programme_id") == self.programme_id
            and activity.get("module_id") == self.module_id,
        )

    def join_participants(self) -> None:
        joined = []
        for item in self.participants:
            payload = {
                "p_join_code": self.join_code,
                "p_participant_name": item["name"],
                "p_device_id": item["device"],
                "p_requested_team_id": "",
            }
            response = self._rpc("exos_v2_join_event_v2", payload)
            if response.get("RecoveryRequired"):
                raise RuntimeError(f"join returned recovery required: {response.get('Message')}")
            if not response.get("ParticipantID") or not response.get("TeamID"):
                raise RuntimeError("join response missing identity fields")
            joined.append(
                {
                    "name": item["name"],
                    "device": item["device"],
                    "participant_id": response["ParticipantID"],
                    "team_id": response["TeamID"],
                }
            )
        self.join_results = joined

        distinct_participants = {x["participant_id"] for x in joined}
        teams = [x["team_id"] for x in joined]
        self._set("participant_joins", len(distinct_participants) == len(joined))

        if joined:
            counts = {}
            for t in teams:
                counts[t] = counts.get(t, 0) + 1
            if len(counts) < 2:
                self._set("balanced_grouping", False)
            else:
                delta = max(counts.values()) - min(counts.values())
                self._set("balanced_grouping", delta <= 1)
        else:
            self._set("balanced_grouping", False)

    def reconnect_participants(self) -> None:
        ok = True
        for item in self.join_results:
            restored = self._rpc(
                "exos_v2_restore_join",
                {
                    "p_join_code": self.join_code,
                    "p_participant_name": item["name"],
                    "p_device_id": item["device"],
                },
            )
            if restored.get("RecoveryRequired"):
                ok = False
                break
            if restored.get("ParticipantID") != item["participant_id"] or restored.get(
                "TeamID"
            ) != item["team_id"]:
                ok = False
                break
        self._set("reconnect_identity_team", ok)

    def launch_activity(self) -> tuple[str, str]:
        runtime_payload = []
        for item in self.join_results:
            runtime_payload.append(
                {
                    "event_id": self.event_id,
                    "team_id": item["team_id"],
                    "participant_id": item["participant_id"],
                    "activity_id": self.activity_id,
                    "state_payload": {
                        "status": "LAUNCHED",
                        "started_by": "CORE-V2-STAGING-RUNNER",
                    },
                    "activity_started_at": self._now_iso(),
                    "is_completed": False,
                }
            )

        created = self._rest_request(
            "POST",
            "activity_runtime_v2",
            payload=runtime_payload,
            admin=True,
        )
        if not (isinstance(created, list) and len(created) >= 1):
            raise RuntimeError("activity launch failed")

        runtime_rows = self._rest_request(
            "GET",
            "activity_runtime_v2",
            query={
                "event_id": f"eq.{self.event_id}",
                "activity_id": f"eq.{self.activity_id}",
                "select": "runtime_id,participant_id",
            },
            admin=True,
        )
        if not (isinstance(runtime_rows, list) and len(runtime_rows) >= len(self.join_results)):
            raise RuntimeError("runtime rows not found after launch")
        self._set("activity_launch", True)
        return runtime_rows[0]["participant_id"], runtime_rows[0]["runtime_id"]

    def submit_text(self, participant_id: str, runtime_id: str) -> str:
        team_id = next(x["team_id"] for x in self.join_results if x["participant_id"] == participant_id)
        if not team_id:
            raise RuntimeError("Could not determine submitter team")

        submission_key = f"{self.activity_id}:{participant_id}:{self._now_iso()}"
        submission_payload = {
            "event_id": self.event_id,
            "team_id": team_id,
            "participant_id": participant_id,
            "activity_id": self.activity_id,
            "runtime_id": runtime_id,
            "submission_key": submission_key,
            "submission_status": "SUBMITTED",
            "submission_payload": {
                "text": "Core v2 staging journey smoke test submission.",
                "origin": "staging_journey_runner",
            },
        }

        created = self._rest_request(
            "POST", "submissions_v2", payload=submission_payload, admin=True
        )
        if not (isinstance(created, list) and created):
            raise RuntimeError("submission insert failed")
        submission = created[0]
        submission_id = submission["submission_id"]

        got = self._rest_request(
            "GET",
            "submissions_v2",
            query={
                "submission_id": f"eq.{submission_id}",
                "select": "submission_id,submission_status",
            },
            admin=True,
        )
        self._set("submission", bool(got and isinstance(got, list) and got[0].get("submission_status") == "SUBMITTED"))
        return submission_id

    def review_and_score(self, submission_id: str) -> tuple[str, bool]:
        submitter_team = next(
            x["team_id"] for x in self.join_results if x["participant_id"] == self.join_results[0]["participant_id"]
        )

        review = self._rest_request(
            "POST",
            "reviews_v2",
            payload={
                "event_id": self.event_id,
                "submission_id": submission_id,
                "reviewer": "CORE-V2-UAT-FACILITATOR",
                "decision": "APPROVE",
                "score_points": 10,
                "rationale": "Staging journey smoke approval.",
            },
            admin=True,
        )
        if not (isinstance(review, list) and review and review[0].get("decision") == "APPROVE"):
            self._set("review_approval", False)
        else:
            self._rest_request(
                "PATCH",
                "submissions_v2",
                payload={
                    "submission_status": "APPROVED",
                    "score": 10,
                    "reviewed_at": self._now_iso(),
                    "reviewed_by": "CORE-V2-UAT-FACILITATOR",
                },
                query={"submission_id": f"eq.{submission_id}"},
                admin=True,
            )
            tx = self._rpc(
                "exos_v2_ledger_score",
                {
                    "p_event_id": self.event_id,
                    "p_team_id": submitter_team,
                    "p_submission_id": submission_id,
                    "p_amount": 10,
                    "p_reason": "Staging journey smoke approval",
                    "p_scoring_mode": "TEAM_COMPETITIVE",
                    "p_idempotency_key": f"{self.event_id}-{submission_id}-SCORE",
                },
            )
            if not tx:
                self._set("competitive_score_transaction", False)
            else:
                score_rows = self._rest_request(
                    "GET",
                    "score_transactions_v2",
                    query={
                        "score_transaction_id": f"eq.{tx}",
                        "select": "score_transaction_id,scoring_mode",
                    },
                    admin=True,
                )
                self._set(
                    "competitive_score_transaction",
                    bool(
                        score_rows
                        and isinstance(score_rows, list)
                        and score_rows[0].get("scoring_mode") == "TEAM_COMPETITIVE"
                    ),
                )
            self._set(
                "review_approval",
                isinstance(review, list) and review[0].get("decision") == "APPROVE",
            )
        return submitter_team, review[0].get("decision") == "APPROVE" if isinstance(review, list) else False

    def close_activity(self) -> None:
        self._rest_request(
            "PATCH",
            "activity_runtime_v2",
            payload={"is_completed": True, "activity_ended_at": self._now_iso()},
            query={
                "event_id": f"eq.{self.event_id}",
                "activity_id": f"eq.{self.activity_id}",
            },
            admin=True,
        )

    def verify_result_retrievable(self, submission_id: str) -> None:
        rows = self._rest_request(
            "GET",
            "submissions_v2",
            query={
                "event_id": f"eq.{self.event_id}",
                "submission_id": f"eq.{submission_id}",
                "select": "submission_id,submission_payload,submission_status",
            },
            admin=True,
        )
        has_submission = bool(rows and isinstance(rows, list) and rows[0].get("submission_id") == submission_id)

        reviews = self._rest_request(
            "GET",
            "reviews_v2",
            query={
                "submission_id": f"eq.{submission_id}",
                "select": "decision",
            },
            admin=True,
        )
        reviewed = bool(reviews and isinstance(reviews, list) and reviews[0].get("decision") == "APPROVE")
        self._set("result_retrievable_after_close", has_submission and reviewed)

    def cleanup(self) -> None:
        self._cleanup_steps = []
        first_failed_step = None
        try:
            # Resolve all IDs for deterministic dependency cleanup.
            event_id = self.event_id

            programme_ids = self._pluck("programmes_v2", "programme_id", {"event_id": f"eq.{self.event_id}", "select": "programme_id"})
            participant_ids = self._pluck(
                "participants_v2",
                "participant_id",
                {"event_id": f"eq.{self.event_id}", "select": "participant_id"},
            )
            programme_filter = self._ids_filter(programme_ids, "programme_id")
            module_ids = self._pluck(
                "modules_v2",
                "module_id",
                {
                    **(programme_filter or {}),
                    "select": "module_id",
                },
            ) if programme_ids else []
            module_filter = self._ids_filter(module_ids, "module_id")
            activity_ids = self._pluck(
                "activities_v2",
                "activity_id",
                {
                    **(module_filter or {}),
                    "select": "activity_id",
                },
            ) if module_ids else []
            session_ids = self._pluck(
                "participant_sessions_v2",
                "participant_session_id",
                {"event_id": f"eq.{self.event_id}", "select": "participant_session_id"},
            )
            submission_ids = self._pluck("submissions_v2", "submission_id", {"event_id": f"eq.{self.event_id}", "select": "submission_id"})
            ai_job_ids = self._pluck("ai_jobs_v2", "ai_job_id", {"event_id": f"eq.{self.event_id}", "select": "ai_job_id"})
            session_filter = self._ids_filter(session_ids, "participant_session_id")
            submission_filter = self._ids_filter(submission_ids, "submission_id")
            ai_job_filter = self._ids_filter(ai_job_ids, "ai_job_id")
            activity_filter = self._ids_filter(activity_ids, "activity_id")
            module_filter_for_cleanup = self._ids_filter(module_ids, "module_id")
            programme_filter_for_cleanup = self._ids_filter(programme_ids, "programme_id")

            print("CLEANUP TARGET UAT IDs")
            print(f"EventID: {self.event_id}")
            print(f"ProgrammeIDs: {programme_ids}")
            print(f"ModuleIDs: {module_ids}")
            print(f"ActivityIDs: {activity_ids}")
            print(f"ParticipantIDs: {participant_ids}")
            print(f"SessionIDs: {session_ids}")
            print(f"SubmissionIDs: {submission_ids}")
            print(f"AIJobIDs: {ai_job_ids}")

            cleanup_sequence = [
                ("submission_evidence_v2", submission_filter, "submission_evidence_v2"),
                ("location_evidence_v2", submission_filter, "location_evidence_v2 by submission_id"),
                ("location_evidence_v2", session_filter, "location_evidence_v2 by participant_session_id"),
                ("ai_results_v2", ai_job_filter, "ai_results_v2"),
                ("reviews_v2", {"event_id": f"eq.{event_id}"}, "reviews_v2"),
                ("score_transactions_v2", {"event_id": f"eq.{event_id}"}, "score_transactions_v2"),
                ("credit_transactions_v2", {"event_id": f"eq.{event_id}"}, "credit_transactions_v2"),
                ("marketplace_transactions_v2", {"event_id": f"eq.{event_id}"}, "marketplace_transactions_v2"),
                ("build_status_v2", {"event_id": f"eq.{event_id}"}, "build_status_v2"),
                ("judging_scores_v2", {"event_id": f"eq.{event_id}"}, "judging_scores_v2"),
                ("race_results_v2", {"event_id": f"eq.{event_id}"}, "race_results_v2"),
                ("projector_state_v2", {"event_id": f"eq.{event_id}"}, "projector_state_v2"),
                ("location_checkpoints_v2", {"event_id": f"eq.{event_id}"}, "location_checkpoints_v2"),
                ("submissions_v2", submission_filter, "submissions_v2"),
                ("activity_runtime_v2", {"event_id": f"eq.{event_id}"}, "activity_runtime_v2"),
                ("participant_sessions_v2", {"event_id": f"eq.{event_id}"}, "participant_sessions_v2"),
                ("participants_v2", {"event_id": f"eq.{event_id}"}, "participants_v2"),
                ("teams_v2", {"event_id": f"eq.{event_id}"}, "teams_v2"),
                ("activities_v2", activity_filter, "activities_v2"),
                ("modules_v2", module_filter_for_cleanup, "modules_v2"),
                ("programmes_v2", programme_filter_for_cleanup, "programmes_v2"),
                ("marketplace_items_v2", {"event_id": f"eq.{event_id}"}, "marketplace_items_v2"),
                ("ai_jobs_v2", {"event_id": f"eq.{event_id}"}, "ai_jobs_v2"),
                ("audit_log_v2", {"event_id": f"eq.{event_id}"}, "audit_log_v2"),
                ("events_v2", {"event_id": f"eq.{event_id}"}, "events_v2"),
            ]

            for table, query, label in cleanup_sequence:
                step_result, failed = self._delete_step(table, query, label)
                self._cleanup_steps.append(step_result)
                if failed:
                    first_failed_step = step_result
                    raise RuntimeError(f"delete failed for {label}")

            leftovers = self.verify_cleanup()
            self._set("cleanup", all(v == 0 for v in leftovers.values()))
            if not self.gates["cleanup"]:
                self.log("Remaining UAT rows:", leftovers)
        except Exception as exc:
            self.log(f"[ERROR] cleanup failed: {exc}")
            self._set("cleanup", False)

        if first_failed_step is not None:
            print("\nFIRST FAILED CLEANUP STEP:")
            print(f"TABLE: {first_failed_step['table']}")
            print(f"FILTER: {first_failed_step['filter']}")
            print(f"HTTP STATUS: {first_failed_step['http_status']}")
            print(f"ERROR: {first_failed_step['error_body'] or '<none>'}")

        print("\nREMAINING UAT ROWS BY TABLE")
        leftovers = self.verify_cleanup()
        for key, value in leftovers.items():
            print(f"{key}: {value}")

    def verify_cleanup(self) -> dict:
        remaining = {}
        event_filter = self.event_id
        tables_by_event_id = {
            "events_v2": "event_id",
            "programmes_v2": "event_id",
            "teams_v2": "event_id",
            "participants_v2": "event_id",
            "participant_sessions_v2": "event_id",
            "activity_runtime_v2": "event_id",
            "submissions_v2": "event_id",
            "reviews_v2": "event_id",
            "score_transactions_v2": "event_id",
            "credit_transactions_v2": "event_id",
            "marketplace_items_v2": "event_id",
            "marketplace_transactions_v2": "event_id",
            "build_status_v2": "event_id",
            "judging_scores_v2": "event_id",
            "race_results_v2": "event_id",
            "projector_state_v2": "event_id",
            "location_checkpoints_v2": "event_id",
            "ai_jobs_v2": "event_id",
            "ai_results_v2": "event_id",
            "audit_log_v2": "event_id",
        }

        for table, column in tables_by_event_id.items():
            remaining[f"{table}_event"] = self._count(
                table, {column: f"eq.{event_filter}", "select": column}
            )

        # eventless children that depend on known child ids
        submission_ids = self._pluck(
            "submissions_v2",
            "submission_id",
            {"event_id": f"eq.{event_filter}", "select": "submission_id"},
        )
        session_ids = self._pluck(
            "participant_sessions_v2",
            "participant_session_id",
            {"event_id": f"eq.{event_filter}", "select": "participant_session_id"},
        )

        submission_filter = self._ids_filter(submission_ids, "submission_id")
        session_filter = self._ids_filter(session_ids, "participant_session_id")
        if submission_filter is None:
            remaining["submission_evidence_v2_submission"] = 0
            remaining["location_evidence_v2_reference"] = 0
        else:
            remaining["submission_evidence_v2_submission"] = self._count(
                "submission_evidence_v2", {**submission_filter, "select": "evidence_id"}
            )
            remaining["location_evidence_v2_reference"] = self._count(
                "location_evidence_v2",
                {**submission_filter, "select": "location_evidence_id"},
            )

        if session_filter is None:
            remaining["location_evidence_v2_sessions"] = 0
        else:
            remaining["location_evidence_v2_sessions"] = self._count(
                "location_evidence_v2",
                {**session_filter, "select": "location_evidence_id"},
            )

        programme_ids = self._pluck(
            "programmes_v2",
            "programme_id",
            {"event_id": f"eq.{event_filter}", "select": "programme_id"},
        )
        module_ids = self._pluck(
            "modules_v2",
            "module_id",
            {
                "programme_id": self._to_in_list(programme_ids) or None,
                "select": "module_id",
            },
        ) if programme_ids else []
        activity_ids = self._pluck(
            "activities_v2",
            "activity_id",
            {
                "module_id": self._to_in_list(module_ids) or None,
                "select": "activity_id",
            },
        ) if module_ids else []

        remaining["modules_v2_for_event"] = len(module_ids)
        remaining["activities_v2_for_event"] = len(activity_ids)
        return remaining

    # ---------------------------------------------------------
    def print_result_matrix(self) -> None:
        print("\n")
        print(f"Staging connectivity: {'PASS' if self.gates['staging_connectivity'] else 'FAIL'}")
        print(f"Event created: {'PASS' if self.gates['event_created'] else 'FAIL'}")
        print(f"Teams created: {'PASS' if self.gates['teams_created'] else 'FAIL'}")
        print(f"Programme created: {'PASS' if self.gates['programme_created'] else 'FAIL'}")
        print(f"Module created: {'PASS' if self.gates['module_created'] else 'FAIL'}")
        print(f"Activity created: {'PASS' if self.gates['activity_created'] else 'FAIL'}")
        print(f"Hierarchy IDs intact: {'PASS' if self.gates['hierarchy_intact'] else 'FAIL'}")
        print(f"Participant joins: {'PASS' if self.gates['participant_joins'] else 'FAIL'}")
        print(f"Balanced grouping: {'PASS' if self.gates['balanced_grouping'] else 'FAIL'}")
        print(f"Reconnect identity/team: {'PASS' if self.gates['reconnect_identity_team'] else 'FAIL'}")
        print(f"Activity launch: {'PASS' if self.gates['activity_launch'] else 'FAIL'}")
        print(f"Submission: {'PASS' if self.gates['submission'] else 'FAIL'}")
        print(f"Review/approval: {'PASS' if self.gates['review_approval'] else 'FAIL'}")
        print(f"Competitive score transaction: {'PASS' if self.gates['competitive_score_transaction'] else 'FAIL'}")
        print(f"Result retrievable after close: {'PASS' if self.gates['result_retrievable_after_close'] else 'FAIL'}")
        print(f"Cleanup: {'PASS' if self.gates['cleanup'] else 'FAIL'}")

        all_pass = all(self.gates.values())
        if all_pass:
            print("\nEXOS CORE V2 GENERIC LIFECYCLE: READY")

        print("\nEventID:", self.event_id)
        print("ProgrammeID:", self.programme_id)
        print("ModuleID:", self.module_id)
        print("ActivityID:", self.activity_id)

    # ---------------------------------------------------------
    def run(self) -> int:
        self._require_env()
        self.log = print
        try:
            self.check_connectivity()
            self.create_event_and_publish()
            self.create_programme_module_activity()
            self.join_participants()
            self.reconnect_participants()
            participant_id, runtime_id = self.launch_activity()
            submission_id = self.submit_text(participant_id, runtime_id)
            self.review_and_score(submission_id)
            self.close_activity()
            self.verify_result_retrievable(submission_id)
            return 0
        except Exception as exc:
            self.log(f"[ERROR] {exc}")
            return 1
        finally:
            self.cleanup()
            self.print_result_matrix()


def main() -> int:
    return CoreV2JourneyRunner().run()


if __name__ == "__main__":
    raise SystemExit(main())
