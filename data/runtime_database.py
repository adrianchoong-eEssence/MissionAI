import json
import os
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st


class RuntimeDatabaseError(RuntimeError):
    """Raised when the live EXOS runtime cannot complete a request."""


def _secret(name):
    try:
        value = st.secrets[name]
    except Exception:
        value = os.getenv(name, "")
    return str(value or "").strip()


def get_runtime_database():
    # This client is lightweight and stateless. Do not persist it across code
    # deployments because Streamlit can otherwise retain an instance of an
    # older class definition after runtime methods are added or changed.
    return SupabaseRuntimeDB()


class SupabaseRuntimeDB:
    """Transactional runtime store for live registration.

    Google Sheets remains the programme configuration and reporting layer.
    This service handles concurrent participant joins and live participant reads.
    """

    def __init__(self):
        self.url = _secret("SUPABASE_URL").rstrip("/")
        self.anon_key = (
            _secret("SUPABASE_PUBLISHABLE_KEY")
            or _secret("SUPABASE_ANON_KEY")
        )
        self.service_key = (
            _secret("SUPABASE_SECRET_KEY")
            or _secret("SUPABASE_SERVICE_ROLE_KEY")
        )

    @property
    def is_configured(self):
        return bool(self.url and self.anon_key)

    @property
    def can_publish(self):
        return bool(self.url and self.service_key)

    def _request(
        self,
        method,
        path,
        payload=None,
        query=None,
        admin=False,
        retries=4,
    ):
        key = self.service_key if admin else self.anon_key
        if not self.url or not key:
            required = (
                "SUPABASE_SECRET_KEY"
                if admin
                else "SUPABASE_PUBLISHABLE_KEY"
            )
            raise RuntimeDatabaseError(
                f"Supabase runtime is not configured. Missing {required}."
            )

        endpoint = f"{self.url}/rest/v1/{path.lstrip('/')}"
        if query:
            endpoint = f"{endpoint}?{urlencode(query, doseq=True, safe='(),.*')}"

        body = None
        headers = {
            "apikey": key,
            "Accept": "application/json",
        }
        if key.count(".") == 2:
            headers["Authorization"] = f"Bearer {key}"
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        last_error = None
        for attempt in range(retries):
            request = Request(endpoint, data=body, headers=headers, method=method)
            try:
                with urlopen(request, timeout=20) as response:
                    raw = response.read().decode("utf-8")
                    return json.loads(raw) if raw else None
            except HTTPError as error:
                response_text = error.read().decode("utf-8", errors="replace")
                last_error = RuntimeDatabaseError(
                    f"Runtime request failed ({error.code}): {response_text}"
                )
                if error.code not in {408, 429, 500, 502, 503, 504}:
                    raise last_error
            except (URLError, TimeoutError) as error:
                last_error = RuntimeDatabaseError(
                    f"Runtime request could not connect: {error}"
                )

            if attempt < retries - 1:
                time.sleep(0.35 * (2 ** attempt))

        raise last_error or RuntimeDatabaseError("Runtime request failed.")

    @staticmethod
    def _normalise_result(result):
        if isinstance(result, list):
            return result[0] if result else None
        return result

    @staticmethod
    def _submission_record(row):
        if not row:
            return None
        return {
            "SubmissionID": row.get("submission_id", ""),
            "EventID": row.get("event_id", ""),
            "MissionID": row.get("mission_id", ""),
            "TeamName": row.get("team_name", ""),
            "ParticipantName": row.get("participant_name", ""),
            "ImageURL": row.get("image_url", ""),
            "DriveFileID": row.get("drive_file_id", ""),
            "SubmissionType": row.get("submission_type", ""),
            "Metric1": row.get("metric1", ""),
            "Metric2": row.get("metric2", ""),
            "Metric3": row.get("metric3", ""),
            "Score": row.get("score", ""),
            "Status": row.get("status", "PENDING"),
            "Judged": row.get("judged", "No"),
            "Remarks": row.get("remarks", ""),
            "SubmittedAt": row.get("submitted_at", ""),
        }

    def publish_event(self, event, teams, reset_registration=False):
        if not self.can_publish:
            raise RuntimeDatabaseError(
                "Publishing requires SUPABASE_SECRET_KEY."
            )

        team_payload = []
        for position, team in enumerate(teams):
            team_payload.append({
                "team_id": str(team.get("TeamID", "") or f"TEAM-{position + 1:02d}"),
                "team_name": str(team.get("TeamName", "")).strip(),
                "position": position,
            })

        result = self._request(
            "POST",
            "rpc/exos_publish_event",
            payload={
                "p_event_id": str(event.get("EventID", "")).strip(),
                "p_join_code": str(event.get("JoinCode", "")).strip().upper(),
                "p_event_name": str(event.get("EventName", "")).strip(),
                "p_teams": team_payload,
                "p_reset_registration": bool(reset_registration),
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    def publish_programme(self, event_id, missions):
        if not self.can_publish:
            raise RuntimeDatabaseError(
                "Publishing requires SUPABASE_SECRET_KEY."
            )

        payload = []
        for mission in missions:
            mission_id = str(mission.get("MissionID", "")).strip()
            if not mission_id:
                continue
            payload.append({
                "mission_id": mission_id,
                "mission_payload": dict(mission),
            })

        result = self._request(
            "POST",
            "rpc/exos_publish_programme",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_missions": payload,
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    def set_event_stage(self, event_id, stage):
        if not self.can_publish:
            raise RuntimeDatabaseError(
                "Stage publishing requires SUPABASE_SECRET_KEY."
            )
        result = self._request(
            "POST",
            "rpc/exos_set_event_stage",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_stage_payload": dict(stage or {}),
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    def get_participant_current_mission(self, session_token):
        if not self.is_configured or not str(session_token).strip():
            return None
        result = self._request(
            "POST",
            "rpc/exos_participant_current_mission",
            payload={"p_session_token": str(session_token).strip()},
        )
        return self._normalise_result(result)

    def join_player(self, join_code, participant_name):
        result = self._request(
            "POST",
            "rpc/exos_join_event",
            payload={
                "p_join_code": str(join_code).strip().upper(),
                "p_participant_name": str(participant_name).strip(),
            },
        )
        row = self._normalise_result(result)
        if not row:
            raise RuntimeDatabaseError("Registration returned no participant record.")
        return row

    def get_player_by_token(self, session_token):
        if not self.is_configured or not str(session_token).strip():
            return None
        result = self._request(
            "POST",
            "rpc/exos_restore_participant",
            payload={"p_session_token": str(session_token).strip()},
        )
        return self._normalise_result(result)

    def get_event_by_join_code(self, join_code):
        if not self.is_configured:
            return None
        result = self._request(
            "POST",
            "rpc/exos_event_by_join_code",
            payload={"p_join_code": str(join_code).strip().upper()},
        )
        return self._normalise_result(result)

    def get_players(self, event_id=None):
        if not self.can_publish:
            return []

        query = {
            "select": (
                "event_id,display_name,team_name,points,status,joined_at,session_token"
            ),
            "order": "joined_at.asc",
        }
        if event_id is not None:
            query["event_id"] = f"eq.{event_id}"

        rows = self._request(
            "GET",
            "runtime_participants",
            query=query,
            admin=True,
        ) or []
        return [
            {
                "EventID": row.get("event_id", ""),
                "Name": row.get("display_name", ""),
                "Team": row.get("team_name", ""),
                "Points": row.get("points", 0),
                "Status": row.get("status", "Waiting"),
                "JoinedAt": row.get("joined_at", ""),
                "SessionToken": row.get("session_token", ""),
            }
            for row in rows
        ]

    def reset_event_registration(self, event_id):
        result = self._request(
            "POST",
            "rpc/exos_reset_event_registration",
            payload={"p_event_id": str(event_id)},
            admin=True,
        )
        return self._normalise_result(result) or {}

    def save_submission(self, submission):
        def value(name, default=""):
            raw = submission.get(name, default)
            return str(default if raw is None else raw)

        result = self._request(
            "POST",
            "rpc/exos_save_submission",
            payload={
                "p_submission_id": value("SubmissionID"),
                "p_event_id": value("EventID"),
                "p_mission_id": value("MissionID"),
                "p_team_name": value("TeamName"),
                "p_participant_name": value("ParticipantName"),
                "p_image_url": value("ImageURL"),
                "p_drive_file_id": value("DriveFileID"),
                "p_submission_type": value("SubmissionType"),
                "p_metric1": value("Metric1"),
                "p_metric2": value("Metric2"),
                "p_metric3": value("Metric3"),
                "p_score": value("Score"),
                "p_status": value("Status", "PENDING"),
                "p_judged": value("Judged", "No"),
                "p_remarks": value("Remarks"),
                "p_submitted_at": value("SubmittedAt"),
            },
        )
        return self._submission_record(self._normalise_result(result))

    def get_submission(self, event_id, mission_id, scope_type, scope_value):
        result = self._request(
            "POST",
            "rpc/exos_get_submission",
            payload={
                "p_event_id": str(event_id),
                "p_mission_id": str(mission_id),
                "p_scope_type": str(scope_type),
                "p_scope_value": str(scope_value),
            },
        )
        return self._submission_record(self._normalise_result(result))

    def get_submissions(self, event_id):
        if not self.can_publish:
            return []
        rows = self._request(
            "GET",
            "runtime_submissions",
            query={
                "select": "*",
                "event_id": f"eq.{event_id}",
                "order": "created_at.asc",
            },
            admin=True,
        ) or []
        return [self._submission_record(row) for row in rows]

    def update_submission(
        self,
        submission_id,
        score="",
        remarks="",
        judged="Yes",
        status="APPROVED",
    ):
        result = self._request(
            "POST",
            "rpc/exos_update_submission",
            payload={
                "p_submission_id": str(submission_id),
                "p_score": str(score),
                "p_status": str(status),
                "p_judged": str(judged),
                "p_remarks": str(remarks),
            },
            admin=True,
        )
        return self._normalise_result(result) or {"Updated": False}

    def run_join_load_test(self, join_code, total_participants=100, max_workers=40):
        total = max(1, int(total_participants))
        workers = max(1, min(int(max_workers), total, 50))
        run_id = uuid.uuid4().hex[:8].upper()
        started = time.perf_counter()
        joined = []
        errors = []

        def join_test_participant(number):
            name = f"LOAD-{run_id}-{number:03d}"
            return self.join_player(join_code, name)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(join_test_participant, number): number
                for number in range(1, total + 1)
            }
            for future in as_completed(futures):
                number = futures[future]
                try:
                    joined.append(future.result())
                except Exception as error:
                    errors.append({
                        "Participant": f"LOAD-{run_id}-{number:03d}",
                        "Error": str(error),
                    })

        team_counts = Counter(
            str(player.get("Team", "Unassigned"))
            for player in joined
        )
        counts = list(team_counts.values())
        spread = max(counts) - min(counts) if counts else total
        session_tokens = [
            str(player.get("SessionToken", ""))
            for player in joined
            if player.get("SessionToken")
        ]
        duplicate_tokens = len(session_tokens) - len(set(session_tokens))

        return {
            "RunID": run_id,
            "Requested": total,
            "Joined": len(joined),
            "Failed": len(errors),
            "DurationSeconds": round(time.perf_counter() - started, 2),
            "TeamCounts": dict(sorted(team_counts.items())),
            "DistributionSpread": spread,
            "DuplicateSessionTokens": duplicate_tokens,
            "Passed": (
                len(joined) == total
                and not errors
                and spread <= 1
                and duplicate_tokens == 0
            ),
            "Errors": errors,
        }
