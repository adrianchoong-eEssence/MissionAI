import io
import json
import os
import time
import uuid
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import streamlit as st
from PIL import Image

from data.runtime_authority import require_control_centre


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

    def _storage_request(
        self,
        method,
        path,
        payload=None,
        binary_body=None,
        content_type="application/json",
        extra_headers=None,
        return_bytes=False,
        retries=4,
    ):
        if not self.url or not self.service_key:
            raise RuntimeDatabaseError(
                "Supabase Storage requires SUPABASE_SECRET_KEY."
            )

        endpoint = f"{self.url}/storage/v1/{path.lstrip('/')}"
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Accept": "application/json",
            "Content-Type": content_type,
        }
        headers.update(extra_headers or {})

        if binary_body is not None:
            body = binary_body
        elif payload is not None:
            body = json.dumps(payload).encode("utf-8")
        else:
            body = None

        last_error = None
        for attempt in range(retries):
            request = Request(
                endpoint,
                data=body,
                headers=headers,
                method=method,
            )
            try:
                with urlopen(request, timeout=30) as response:
                    raw = response.read()
                    if return_bytes:
                        return raw
                    text = raw.decode("utf-8")
                    return json.loads(text) if text else None
            except HTTPError as error:
                response_text = error.read().decode(
                    "utf-8",
                    errors="replace",
                )
                last_error = RuntimeDatabaseError(
                    f"Storage request failed ({error.code}): {response_text}"
                )
                if error.code not in {408, 429, 500, 502, 503, 504}:
                    raise last_error
            except (URLError, TimeoutError) as error:
                last_error = RuntimeDatabaseError(
                    f"Storage request could not connect: {error}"
                )

            if attempt < retries - 1:
                time.sleep(0.35 * (2 ** attempt))

        raise last_error or RuntimeDatabaseError("Storage request failed.")

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
            "ParticipantID": row.get("participant_id", ""),
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
            "ExperienceAssignmentID": row.get("experience_assignment_id", ""),
            "ExperienceDefinitionID": row.get("experience_definition_id", ""),
            "ExperienceDefinitionVersion": row.get("experience_definition_version", ""),
            "ExperienceAssignmentVersion": row.get("experience_assignment_version", ""),
        }

    def publish_event(self, event, teams, reset_registration=False):
        require_control_centre("Runtime event publication")
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
        published = self._normalise_result(result) or {}
        if reset_registration:
            published["AIReset"] = self.reset_ai_event(
                str(event.get("EventID", "")).strip()
            )
        return published

    def ensure_event_teams(self, event, teams):
        """Publish missing/mismatched runtime teams without resetting participants."""
        event_id = str(event.get("EventID", "")).strip()
        rows = self._request(
            "GET",
            "runtime_teams",
            query={
                "event_id": f"eq.{event_id}",
                "select": "team_id,team_name,position",
                "order": "position.asc",
            },
            admin=True,
        ) or []
        expected = [str(team.get("TeamName", "")).strip() for team in teams]
        actual = [str(row.get("team_name", "")).strip() for row in rows]
        if actual == expected:
            return {"EventID": event_id, "TeamsPublished": len(actual)}
        return self.publish_event(event, teams, reset_registration=False)

    def publish_programme(self, event_id, missions):
        require_control_centre("Runtime programme publication")
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
        require_control_centre("Live stage mutation")
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

    def get_event_stage(self, event_id):
        """Return the authoritative live stage from Supabase."""
        if not self.can_publish:
            return None

        result = self._request(
            "GET",
            "runtime_events",
            query={
                "event_id": f"eq.{str(event_id).strip()}",
                "select": (
                    "event_id,current_stage_no,stage_state,stage_name,"
                    "current_mission_id,display_mode,state_version,"
                    "state_updated_at"
                ),
                "limit": "1",
            },
            admin=True,
        )
        row = self._normalise_result(result)
        if not row:
            return None

        return {
            "EventID": row.get("event_id", ""),
            "CurrentStageNo": row.get("current_stage_no", 0),
            "State": row.get("stage_state", ""),
            "StageName": row.get("stage_name", ""),
            "MissionID": row.get("current_mission_id", ""),
            "DisplayMode": row.get("display_mode", "Hybrid"),
            "StateVersion": row.get("state_version", 0),
            "LastUpdated": row.get("state_updated_at", ""),
        }

    def has_event_mission(self, event_id, mission_id):
        """Return whether a mission payload exists in the live runtime."""
        if not self.can_publish:
            return False
        result = self._request(
            "GET",
            "runtime_missions",
            query={
                "event_id": f"eq.{str(event_id).strip()}",
                "mission_id": f"eq.{str(mission_id).strip()}",
                "select": "mission_id",
                "limit": "1",
            },
            admin=True,
        )
        return bool(self._normalise_result(result))

    def upload_submission_image(
        self,
        storage_path,
        image_bytes,
        content_type="image/jpeg",
    ):
        if not image_bytes:
            raise RuntimeDatabaseError("The submission image is empty.")
        safe_path = quote(str(storage_path).strip().lstrip("/"), safe="/")
        result = self._storage_request(
            "POST",
            f"object/exos-submissions/{safe_path}",
            binary_body=image_bytes,
            content_type=content_type,
            extra_headers={"x-upsert": "false"},
        ) or {}
        return {
            "Bucket": "exos-submissions",
            "Path": str(storage_path).strip().lstrip("/"),
            "StorageID": result.get("Id", ""),
        }

    def create_submission_image_url(self, storage_path, expires_in=3600):
        safe_path = quote(str(storage_path).strip().lstrip("/"), safe="/")
        result = self._storage_request(
            "POST",
            f"object/sign/exos-submissions/{safe_path}",
            payload={"expiresIn": max(int(expires_in), 60)},
        ) or {}
        signed_path = result.get("signedURL") or result.get("signedUrl") or ""
        if not signed_path:
            return ""
        if str(signed_path).startswith("http"):
            return str(signed_path)
        return f"{self.url}/storage/v1/{str(signed_path).lstrip('/')}"

    def download_submission_image(self, storage_path):
        safe_path = quote(str(storage_path).strip().lstrip("/"), safe="/")
        image_bytes = self._storage_request(
            "GET",
            f"object/authenticated/exos-submissions/{safe_path}",
            content_type="application/octet-stream",
            return_bytes=True,
        )
        if not image_bytes:
            raise RuntimeDatabaseError("The submission image is empty.")
        return image_bytes

    def delete_submission_images(self, storage_paths):
        paths = [
            str(path).strip().lstrip("/")
            for path in storage_paths
            if str(path).strip()
        ]
        if not paths:
            return []
        return self._storage_request(
            "DELETE",
            "object/exos-submissions",
            payload={"prefixes": paths},
        ) or []

    def upload_mission_media(
        self,
        storage_path,
        media_bytes,
        content_type,
    ):
        if not media_bytes:
            raise RuntimeDatabaseError("The mission media file is empty.")
        safe_path = quote(str(storage_path).strip().lstrip("/"), safe="/")
        result = self._storage_request(
            "POST",
            f"object/exos-mission-media/{safe_path}",
            binary_body=media_bytes,
            content_type=str(content_type or "application/octet-stream"),
            extra_headers={"x-upsert": "true"},
        ) or {}
        return {
            "Bucket": "exos-mission-media",
            "Path": str(storage_path).strip().lstrip("/"),
            "StorageID": result.get("Id", ""),
        }

    def create_mission_media_url(self, storage_path, expires_in=3600):
        safe_path = quote(str(storage_path).strip().lstrip("/"), safe="/")
        result = self._storage_request(
            "POST",
            f"object/sign/exos-mission-media/{safe_path}",
            payload={"expiresIn": max(int(expires_in), 60)},
        ) or {}
        signed_path = result.get("signedURL") or result.get("signedUrl") or ""
        if not signed_path:
            return ""
        if str(signed_path).startswith("http"):
            return str(signed_path)
        return f"{self.url}/storage/v1/{str(signed_path).lstrip('/')}"

    def delete_mission_media(self, storage_paths):
        paths = [
            str(path).strip().lstrip("/")
            for path in storage_paths
            if str(path).strip()
        ]
        if not paths:
            return []
        return self._storage_request(
            "DELETE",
            "object/exos-mission-media",
            payload={"prefixes": paths},
        ) or []

    def get_participant_current_mission(self, session_token):
        if not self.is_configured or not str(session_token).strip():
            return None
        result = self._request(
            "POST",
            "rpc/exos_participant_current_mission",
            payload={"p_session_token": str(session_token).strip()},
        )
        return self._normalise_result(result)

    def get_ai_conversation(self, session_token, mission_id):
        if not self.is_configured or not str(session_token).strip():
            return {
                "HintLevel": 0,
                "Messages": [],
            }
        result = self._request(
            "POST",
            "rpc/exos_ai_conversation",
            payload={
                "p_session_token": str(session_token).strip(),
                "p_mission_id": str(mission_id).strip(),
            },
        )
        return self._normalise_result(result) or {
            "HintLevel": 0,
            "Messages": [],
        }

    def save_ai_message(
        self,
        session_token,
        mission_id,
        facilitator_name,
        role,
        message,
        hint_level=0,
    ):
        result = self._request(
            "POST",
            "rpc/exos_ai_add_message",
            payload={
                "p_session_token": str(session_token).strip(),
                "p_mission_id": str(mission_id).strip(),
                "p_facilitator_name": str(facilitator_name).strip(),
                "p_role": str(role).strip().lower(),
                "p_message": str(message).strip(),
                "p_hint_level": max(0, min(int(hint_level or 0), 3)),
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    def advance_ai_hint(self, session_token, mission_id):
        result = self._request(
            "POST",
            "rpc/exos_ai_advance_hint",
            payload={
                "p_session_token": str(session_token).strip(),
                "p_mission_id": str(mission_id).strip(),
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    @staticmethod
    def _participant_status(country="", leader=False):
        value = f"COUNTRY:{str(country or '').strip()}"
        return value + ("|LEADER" if leader else "")

    @staticmethod
    def _participant_country(status):
        value = str(status or "")
        return value.split("COUNTRY:", 1)[1].split("|", 1)[0] if "COUNTRY:" in value else ""

    @classmethod
    def _participant_record(cls, row):
        """Return a consistent durable identity payload from every restore path."""
        if not row:
            return None
        player = dict(row)
        status = str(player.get("Status", "") or "")
        player["Country"] = str(
            player.get("Country", "") or cls._participant_country(status)
        )
        player["IsLeader"] = bool(
            player.get("IsLeader", False) or "|LEADER" in status
        )
        return player

    def join_player(self, join_code, participant_name, device_id, requested_team_id=""):
        result = self._request(
            "POST",
            "rpc/exos_join_event_v2",
            payload={
                "p_join_code": str(join_code).strip().upper(),
                "p_participant_name": str(participant_name).strip(),
                "p_device_id": str(device_id).strip(),
                "p_requested_team_id": str(requested_team_id).strip(),
            },
        )
        row = self._normalise_result(result)
        if not row:
            raise RuntimeDatabaseError("Registration returned no participant record.")
        return self._participant_record(row)

    def join_preassigned_player(self, join_code, first_name, last_name, device_id):
        """Restore an existing participant/team; never create or allocate identity."""
        result = self._request(
            "POST",
            "rpc/exos_join_preassigned_event",
            payload={
                "p_join_code": str(join_code).strip().upper(),
                "p_first_name": str(first_name).strip(),
                "p_last_name": str(last_name).strip(),
                "p_device_id": str(device_id).strip(),
            },
        )
        row = self._normalise_result(result)
        if not row:
            raise RuntimeDatabaseError("Pre-assigned identity lookup returned no result.")
        return self._participant_record(row)

    def formula_race_captain_login(self, join_code, team_id, pin, device_id):
        result = self._request("POST", "rpc/exos_formula_race_captain_login", payload={
            "p_join_code": str(join_code).strip().upper(), "p_team_id": str(team_id).strip(),
            "p_pin": str(pin).strip(), "p_device_id": str(device_id).strip(),
        })
        row = self._normalise_result(result)
        if not row:
            raise RuntimeDatabaseError("Captain login returned no team session.")
        return row

    def restore_formula_race_captain(self, session_token, device_id):
        result = self._request("POST", "rpc/exos_formula_race_restore_captain", payload={
            "p_session_token": str(session_token).strip(), "p_device_id": str(device_id).strip(),
        })
        return self._normalise_result(result)

    def formula_race_team_status(self, event_id):
        rows = self._request("POST", "rpc/exos_formula_race_team_status", payload={
            "p_event_id": str(event_id).strip(),
        }, admin=True) or []
        if isinstance(rows, dict):
            rows = [rows]
        return [{
            "TeamID": row.get("team_id", ""), "Connected": bool(row.get("connected", False)),
            "ConnectedAt": row.get("connected_at"), "LastSeenAt": row.get("last_seen_at"),
        } for row in rows]

    def get_formula_race_state(self, event_id):
        result=self._request("POST","rpc/exos_formula_race_state",payload={"p_event_id":str(event_id).strip()},admin=True)
        return self._normalise_result(result) or {}

    def set_formula_race_build_status(self,event_id,team_id,status,checklist,reason,actor):
        require_control_centre("Formula R.A.C.E. build status")
        return self._normalise_result(self._request("POST","rpc/exos_set_formula_race_build_status",payload={
            "p_event_id":str(event_id),"p_team_id":str(team_id),"p_status":str(status),
            "p_checklist":dict(checklist or {}),"p_reason":str(reason),"p_actor":str(actor)},admin=True)) or {}

    def save_formula_race_judging(self,event_id,team_id,scores,reason,actor):
        require_control_centre("Formula R.A.C.E. judging")
        return self._normalise_result(self._request("POST","rpc/exos_save_formula_race_judging",payload={
            "p_event_id":str(event_id),"p_team_id":str(team_id),"p_scores":dict(scores),
            "p_reason":str(reason),"p_actor":str(actor)},admin=True)) or {}

    def save_formula_race_result(self,event_id,team_id,time_ms,penalty_ms,bonus,verified,reason,actor):
        require_control_centre("Formula R.A.C.E. race result")
        return self._normalise_result(self._request("POST","rpc/exos_save_formula_race_result",payload={
            "p_event_id":str(event_id),"p_team_id":str(team_id),"p_time_ms":int(time_ms),
            "p_penalty_ms":int(penalty_ms),"p_bonus":float(bonus),"p_verified":bool(verified),
            "p_reason":str(reason),"p_actor":str(actor)},admin=True)) or {}

    def get_runtime_control_state(self, event_id):
        if not self.can_publish:
            raise RuntimeDatabaseError("Runtime control state requires SUPABASE_SECRET_KEY.")
        result = self._request(
            "POST", "rpc/exos_runtime_control_state",
            payload={"p_event_id": str(event_id).strip()}, admin=True,
        )
        return self._normalise_result(result) or {}

    def set_runtime_control_state(self, event_id, key, value):
        require_control_centre("Runtime control state mutation")
        if not self.can_publish:
            raise RuntimeDatabaseError("Runtime control mutation requires SUPABASE_SECRET_KEY.")
        result = self._request(
            "POST", "rpc/exos_set_runtime_control_state",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_key": str(key).strip(),
                "p_value": value,
            }, admin=True,
        )
        return self._normalise_result(result) or {}

    def restore_join(self, join_code, participant_name, device_id):
        result = self._request(
            "POST",
            "rpc/exos_restore_join",
            payload={
                "p_join_code": str(join_code).strip().upper(),
                "p_participant_name": str(participant_name).strip(),
                "p_device_id": str(device_id).strip(),
            },
        )
        return self._participant_record(self._normalise_result(result))

    def assign_participant_country_team(self, session_token, team_name, country):
        raise RuntimeDatabaseError(
            "Automatic post-join team mutation is disabled. New assignments "
            "must be committed by exos_join_event_v2; corrections require "
            "the audited facilitator move operation."
        )

    def get_team_roster(self, event_id, team_name):
        rows = self._request(
            "GET", "runtime_participants",
            query={
                "event_id": f"eq.{str(event_id).strip()}",
                "team_name": f"eq.{str(team_name).strip()}",
                "select": "participant_id,display_name,team_name,status,session_token",
                "order": "joined_at.asc",
            },
            admin=True,
        ) or []
        return [{
            "ParticipantID": row.get("participant_id", ""),
            "Name": row.get("display_name", ""),
            "Team": row.get("team_name", ""),
            "Country": self._participant_country(row.get("status", "")),
            "IsLeader": "|LEADER" in str(row.get("status", "")),
            "SessionToken": row.get("session_token", ""),
        } for row in rows]

    def claim_team_leader(self, session_token):
        result = self._request(
            "POST", "rpc/exos_claim_team_leader",
            payload={"p_session_token": str(session_token).strip()},
        )
        return self._normalise_result(result) or {}

    def get_player_by_token(self, session_token):
        if not self.is_configured or not str(session_token).strip():
            return None
        result = self._request(
            "POST",
            "rpc/exos_restore_participant",
            payload={"p_session_token": str(session_token).strip()},
        )
        return self._participant_record(self._normalise_result(result))

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
                "participant_id,event_id,display_name,team_name,team_id,country,flag,points,"
                "status,joined_at,last_seen_at,session_token"
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
                "ParticipantID": row.get("participant_id", ""),
                "EventID": row.get("event_id", ""),
                "Name": row.get("display_name", ""),
                "Team": row.get("team_name", ""),
                "TeamID": row.get("team_id", ""),
                "Points": row.get("points", 0),
                "Status": row.get("status", "Waiting"),
                "Country": row.get("country", "") or self._participant_country(row.get("status", "")),
                "Flag": row.get("flag", ""),
                "IsLeader": "|LEADER" in str(row.get("status", "")),
                "JoinedAt": row.get("joined_at", ""),
                "LastSeenAt": row.get("last_seen_at", ""),
                "SessionToken": row.get("session_token", ""),
            }
            for row in rows
        ]

    def audit_participant_duplicates(self, event_id):
        """Report likely duplicates without changing participant records."""
        rows = self._request(
            "GET", "runtime_participants",
            query={
                "event_id": f"eq.{str(event_id).strip()}",
                "select": (
                    "participant_id,event_id,normalized_name,display_name,"
                    "team_name,status,joined_at,session_token,idempotency_key"
                ),
                "order": "normalized_name.asc,joined_at.asc",
            },
            admin=True,
        ) or []
        grouped = {}
        for row in rows:
            normalized = " ".join(
                str(row.get("normalized_name") or row.get("display_name") or "")
                .strip().lower().split()
            )
            grouped.setdefault(normalized, []).append(row)

        duplicates = []
        for normalized, matches in grouped.items():
            if not normalized or len(matches) < 2:
                continue
            duplicates.append({
                "EventID": str(event_id).strip(),
                "NormalizedName": normalized,
                "Count": len(matches),
                "ParticipantIDs": [row.get("participant_id", "") for row in matches],
                "DisplayNames": [row.get("display_name", "") for row in matches],
                "Teams": [row.get("team_name", "") for row in matches],
                "Countries": [self._participant_country(row.get("status", "")) for row in matches],
                "JoinedAt": [row.get("joined_at", "") for row in matches],
                "SessionTokens": [row.get("session_token", "") for row in matches],
                "IdempotencyKeys": [row.get("idempotency_key", "") for row in matches],
            })
        return {"Participants": len(rows), "DuplicateGroups": duplicates}

    def identity_migration_audit(self, event_id):
        """Read-only production identity audit; never mutates participant rows."""
        result = self._request(
            "POST", "rpc/exos_identity_migration_audit",
            payload={"p_event_id": str(event_id).strip()}, admin=True,
        )
        return self._normalise_result(result) or {}

    def set_submission_override(self, event_id, team_id="", enabled=False, actor="Facilitator"):
        require_control_centre("Submission override")
        result = self._request(
            "POST", "rpc/exos_admin_set_submission_override",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_team_id": str(team_id).strip() or "*",
                "p_enabled": bool(enabled),
                "p_actor": str(actor).strip() or "Facilitator",
            }, admin=True,
        )
        return self._normalise_result(result) or {}

    def transfer_team_leader(self, event_id, team_id, participant_id, actor="Facilitator"):
        require_control_centre("Leader transfer")
        result = self._request(
            "POST", "rpc/exos_admin_transfer_leader",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_team_id": str(team_id).strip(),
                "p_participant_id": str(participant_id).strip(),
                "p_actor": str(actor).strip() or "Facilitator",
            }, admin=True,
        )
        return self._normalise_result(result) or {}

    def move_participant(self, participant_id, team_id, reason, actor="Facilitator"):
        require_control_centre("Participant team correction")
        result = self._request(
            "POST", "rpc/exos_admin_move_participant",
            payload={
                "p_participant_id": str(participant_id).strip(),
                "p_team_id": str(team_id).strip(),
                "p_actor": str(actor).strip() or "Facilitator",
                "p_reason": str(reason).strip(),
            }, admin=True,
        )
        return self._normalise_result(result) or {}

    def can_participant_submit(self, session_token):
        result = self._request(
            "POST", "rpc/exos_can_participant_submit",
            payload={"p_session_token": str(session_token).strip()},
        )
        return self._normalise_result(result) or {"Allowed": False, "Reason": "NO_SESSION"}

    def decide_duplicate(self, event_id, canonical_id, duplicate_id, decision, reason, actor="Facilitator"):
        require_control_centre("Duplicate identity decision")
        result = self._request(
            "POST", "rpc/exos_admin_duplicate_decision",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_canonical_participant_id": str(canonical_id).strip(),
                "p_duplicate_participant_id": str(duplicate_id).strip(),
                "p_decision": str(decision).strip().upper(),
                "p_actor": str(actor).strip() or "Facilitator",
                "p_reason": str(reason).strip(),
            }, admin=True,
        )
        return self._normalise_result(result) or {}

    def delete_load_test_participants(self, event_id, run_id):
        """Delete only participants carrying one explicit LOAD run marker."""
        marker = str(run_id).strip().upper()
        if not marker or any(character not in "0123456789ABCDEF" for character in marker):
            raise ValueError("A valid LOAD run ID is required.")
        return self._request(
            "DELETE", "runtime_participants",
            query={
                "event_id": f"eq.{str(event_id).strip()}",
                "display_name": f"ilike.LOAD-{marker}-%",
            },
            admin=True,
        ) or []

    def reset_event_registration(self, event_id):
        result = self._request(
            "POST",
            "rpc/exos_reset_event_registration",
            payload={"p_event_id": str(event_id)},
            admin=True,
        )
        return self._normalise_result(result) or {}

    def reset_ai_event(self, event_id):
        result = self._request(
            "POST",
            "rpc/exos_reset_ai_event",
            payload={"p_event_id": str(event_id).strip()},
            admin=True,
        )
        return self._normalise_result(result) or {}

    def export_event_records(self, event_id):
        """Return every runtime row scoped to one event for backup."""
        clean_event_id = str(event_id).strip()
        tables = (
            "runtime_events",
            "runtime_teams",
            "runtime_participants",
            "runtime_missions",
            "runtime_submissions",
            "runtime_team_wallets",
            "runtime_credit_transactions",
            "runtime_marketplace_items",
            "runtime_marketplace_purchases",
            "runtime_ai_messages",
            "runtime_ai_hint_state",
            "runtime_route_stops",
            "runtime_team_trackers",
            "runtime_team_locations",
            "runtime_location_history",
            "runtime_geofence_arrivals",
        )
        return {
            table: self._request(
                "GET",
                table,
                query={
                    "event_id": f"eq.{clean_event_id}",
                    "select": "*",
                },
                admin=True,
            ) or []
            for table in tables
        }

    def permanently_delete_event(self, event_id):
        """Delete one runtime event; event foreign keys cascade to child rows."""
        clean_event_id = str(event_id).strip()
        if not clean_event_id:
            raise ValueError("Event ID is required.")
        self._request(
            "DELETE",
            "runtime_events",
            query={"event_id": f"eq.{clean_event_id}"},
            admin=True,
        )
        return {"EventID": clean_event_id, "RuntimeDeleted": True}

    def reset_event_data(self, event_id, reset_type):
        """Reset event-scoped runtime data while preserving event configuration."""
        clean_event_id = str(event_id).strip()
        clean_type = str(reset_type).strip().upper()
        if not clean_event_id:
            raise ValueError("Event ID is required.")
        if clean_type not in {"PARTICIPANTS", "RUNTIME", "FACTORY", "UAT"}:
            raise ValueError("Select a valid event reset type.")

        deleted = {}

        def delete_table(table):
            result = self._request(
                "DELETE",
                table,
                query={"event_id": f"eq.{clean_event_id}"},
                admin=True,
            )
            deleted[table] = len(result or []) if isinstance(result, list) else 0

        if clean_type in {"RUNTIME", "FACTORY", "UAT"}:
            for table in (
                "runtime_marketplace_purchases",
                "runtime_credit_transactions",
                "runtime_team_wallets",
                "runtime_ai_messages",
                "runtime_ai_hint_state",
                "runtime_team_trackers",
                "runtime_team_locations",
                "runtime_location_history",
                "runtime_geofence_arrivals",
                "runtime_submissions",
            ):
                delete_table(table)

            if clean_type == "RUNTIME":
                self._request(
                    "PATCH",
                    "runtime_participants",
                    payload={"points": 0, "status": "Waiting"},
                    query={"event_id": f"eq.{clean_event_id}"},
                    admin=True,
                )

        if clean_type in {"PARTICIPANTS", "FACTORY", "UAT"}:
            delete_table("runtime_participants")

        if clean_type == "FACTORY":
            delete_table("runtime_marketplace_items")
        if clean_type in {"FACTORY", "UAT"}:
            delete_table("runtime_teams")

        event_updates = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if clean_type in {"RUNTIME", "FACTORY", "UAT"}:
            event_updates.update({
                "current_stage_no": 0,
                "stage_state": "",
                "stage_name": "",
                "current_mission_id": "",
                "display_mode": "Welcome" if clean_type == "UAT" else "Registration",
                "stage_payload": {},
                "state_version": 0,
                "credit_earning_frozen": False,
                "credit_leaderboard_frozen_at": None,
            })
        if clean_type in {"PARTICIPANTS", "FACTORY", "UAT"}:
            event_updates["next_team_index"] = 0
        self._request(
            "PATCH",
            "runtime_events",
            payload=event_updates,
            query={"event_id": f"eq.{clean_event_id}"},
            admin=True,
        )

        return {
            "EventID": clean_event_id,
            "ResetType": clean_type,
            "Deleted": deleted,
        }

    def save_submission(self, submission):
        def value(name, default=""):
            raw = submission.get(name, default)
            return str(default if raw is None else raw)

        canonical = dict(submission.get("CanonicalContext", {}) or {})
        if canonical.get("ExperienceAssignmentID"):
            result = self._request(
                "POST", "rpc/exos_create_canonical_submission",
                payload={
                    "p_session_token": value("SessionToken"),
                    "p_experience_assignment_id": str(canonical["ExperienceAssignmentID"]),
                    "p_submission_id": value("SubmissionID"),
                    "p_idempotency_key": value("IdempotencyKey", value("SubmissionID")),
                    "p_submission_type": value("SubmissionType"),
                    "p_evidence_type": str(canonical.get("EvidenceType", "NONE")),
                    "p_text_response": value("Remarks"),
                    "p_media_asset_id": value("DriveFileID"),
                    "p_storage_reference": value("ImageURL"),
                    "p_qr_result": canonical.get("QRResult"),
                    "p_gps_result": canonical.get("GPSResult"),
                },
            )
            return self._normalise_result(result) or {}
        result = self._request(
            "POST",
            "rpc/exos_save_submission_v2",
            payload={
                "p_submission_id": value("SubmissionID"),
                "p_event_id": value("EventID"),
                "p_mission_id": value("MissionID"),
                "p_team_name": value("TeamName"),
                "p_participant_name": value("ParticipantName"),
                "p_session_token": value("SessionToken"),
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

    def get_submission(
        self,
        event_id,
        mission_id,
        scope_type,
        scope_value,
        session_token="",
    ):
        result = self._request(
            "POST",
            "rpc/exos_get_submission_v2",
            payload={
                "p_event_id": str(event_id),
                "p_mission_id": str(mission_id),
                "p_scope_type": str(scope_type),
                "p_scope_value": str(scope_value),
                "p_session_token": str(session_token),
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

    def get_canonical_submissions(self, event_id):
        if not self.can_publish:
            return []
        rows = self._request("GET", "canonical_submissions", query={
            "event_id": f"eq.{event_id}", "select": "*", "order": "submitted_at.asc",
        }, admin=True) or []
        return [{
            "SubmissionID": row.get("submission_id", ""), "EventID": row.get("event_id", ""),
            "TeamID": row.get("team_id", ""), "ParticipantID": row.get("participant_id", ""),
            "ProgrammeID": row.get("programme_id", ""), "ModuleID": row.get("module_id", ""),
            "ActivityID": row.get("activity_id", ""),
            "ExperienceDefinitionID": row.get("experience_definition_id", ""),
            "ExperienceAssignmentID": row.get("experience_assignment_id", ""),
            "DefinitionVersion": row.get("definition_version", ""),
            "AssignmentVersion": row.get("assignment_version", ""),
            "SubmissionType": row.get("submission_type", ""), "EvidenceType": row.get("evidence_type", ""),
            "TextResponse": row.get("text_response", ""), "MediaAssetID": row.get("media_asset_id", ""),
            "StorageReference": row.get("storage_reference", ""), "QRResult": row.get("qr_result"),
            "GPSResult": row.get("gps_result"), "SubmittedAt": row.get("submitted_at", ""),
            "Status": row.get("status", "PENDING_REVIEW"), "CreatedBy": row.get("created_by", ""),
        } for row in rows]

    def get_canonical_leaderboard(self, event_id):
        if not self.can_publish:
            return []
        rows = self._request("GET", "leaderboard_projection", query={
            "event_id": f"eq.{event_id}", "select": "*", "order": "rank.asc,team_id.asc",
        }, admin=True) or []
        return [{
            "EventID": row.get("event_id", ""), "TeamID": row.get("team_id", ""),
            "Score": row.get("score", 0), "IntelligenceCredits": row.get("intelligence_credits", 0),
            "AvailableBalance": row.get("available_balance", 0), "Rank": row.get("rank", 0),
        } for row in rows]

    def get_canonical_reviews(self, event_id, submission_id=""):
        query = {"event_id": f"eq.{event_id}", "select": "*", "order": "decided_at.asc"}
        if submission_id:
            query["submission_id"] = f"eq.{submission_id}"
        return self._request("GET", "review_decisions", query=query, admin=True) or []

    def get_canonical_transaction_report(self, event_id):
        if not self.can_publish:
            return {}
        def rows(table, order):
            return self._request("GET", table, query={
                "event_id": f"eq.{event_id}", "select": "*", "order": order,
            }, admin=True) or []
        return {
            "Submissions": self.get_canonical_submissions(event_id),
            "ReviewDecisions": rows("review_decisions", "decided_at.asc"),
            "AwardTransactions": rows("award_transactions", "created_at.asc"),
            "JudgeScores": rows("judge_scores", "submitted_at.asc"),
            "TeamBalances": self._request("GET", "team_balance_projection", query={
                "event_id": f"eq.{event_id}", "select": "*", "order": "team_id.asc",
            }, admin=True) or [],
            "Leaderboard": self.get_canonical_leaderboard(event_id),
        }

    def set_scoring_lock(self, event_id, scope_type, scope_id, locked, actor, reason):
        require_control_centre("Canonical scoring final lock")
        lock_id = f"LOCK-{event_id}-{str(scope_type).upper()}-{scope_id}"
        if not locked:
            return self._request("DELETE", "scoring_locks", query={
                "scoring_lock_id": f"eq.{lock_id}",
            }, admin=True, retries=1) or {"Locked": False}
        return self._request("POST", "scoring_locks", payload={
            "scoring_lock_id": lock_id, "event_id": str(event_id),
            "scope_type": str(scope_type).upper(), "scope_id": str(scope_id),
            "locked": True, "locked_by": str(actor), "reason": str(reason),
            "audit_metadata": {"Actor": str(actor)},
        }, query={"on_conflict": "event_id,scope_type,scope_id"}, admin=True, retries=1) or {"Locked": True}

    def update_submission(
        self,
        submission_id,
        score="",
        remarks="",
        judged="Yes",
        status="APPROVED",
    ):
        require_control_centre("Submission approval mutation")
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

    def decide_canonical_submission(self, submission_id, decision, reviewer_id,
                                    score=0, credits=0, notes="", reason="",
                                    idempotency_key="", supersedes_id=""):
        require_control_centre("Canonical review decision")
        result = self._request(
            "POST", "rpc/exos_decide_canonical_submission", payload={
                "p_submission_id": str(submission_id), "p_decision": str(decision).upper(),
                "p_reviewer_id": str(reviewer_id), "p_score": float(score or 0),
                "p_credits": float(credits or 0), "p_notes": str(notes),
                "p_rejection_reason": str(reason),
                "p_idempotency_key": str(idempotency_key or f"{submission_id}:{decision}"),
                "p_supersedes_decision_id": str(supersedes_id),
            }, admin=True,
        )
        return self._normalise_result(result) or {}

    def configure_credit_wallet(self, event_id, enabled=True, reset=False):
        require_control_centre("Credit wallet configuration")
        result = self._request(
            "POST",
            "rpc/exos_configure_credit_wallet",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_enabled": bool(enabled),
                "p_reset": bool(reset),
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    def get_credit_wallet_status(self, event_id):
        result = self._request(
            "POST",
            "rpc/exos_credit_wallet_status",
            payload={"p_event_id": str(event_id).strip()},
            admin=True,
        )
        return self._normalise_result(result) or {}

    def publish_marketplace(self, event_id, items):
        require_control_centre("Runtime marketplace publication")
        payload = []
        for position, item in enumerate(items):
            item_id = str(item.get("ItemID", "")).strip().upper()
            item_name = str(item.get("ItemName", "")).strip()
            if not item_id or not item_name:
                continue
            stock = item.get("StockQuantity")
            if stock in ("", None):
                stock = None
            else:
                stock = max(int(float(stock)), 0)
            payload.append({
                "item_id": item_id,
                "item_name": item_name,
                "description": str(item.get("Description", "")).strip(),
                "credit_cost": max(float(item.get("CreditCost", 0) or 0), 0),
                "stock_quantity": stock,
                "active": bool(item.get("Active", True)),
                "position": int(item.get("Position", position) or position),
            })

        result = self._request(
            "POST",
            "rpc/exos_publish_marketplace",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_items": payload,
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    def set_credit_freeze(self, event_id, frozen=True):
        require_control_centre("Credit freeze mutation")
        result = self._request(
            "POST",
            "rpc/exos_set_credit_freeze",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_frozen": bool(frozen),
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    def get_team_wallet(self, session_token):
        result = self._request(
            "POST",
            "rpc/exos_team_wallet",
            payload={"p_session_token": str(session_token).strip()},
        )
        return self._normalise_result(result) or {}

    def purchase_marketplace_item(self, session_token, item_id, quantity=1):
        result = self._request(
            "POST",
            "rpc/exos_purchase_marketplace_item",
            payload={
                "p_session_token": str(session_token).strip(),
                "p_item_id": str(item_id).strip().upper(),
                "p_quantity": max(int(quantity), 1),
            },
        )
        return self._normalise_result(result) or {}

    def adjust_team_credits(self, event_id, team_name, amount, description):
        require_control_centre("Manual credit adjustment")
        result = self._request(
            "POST",
            "rpc/exos_adjust_team_credits",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_team_name": str(team_name).strip(),
                "p_amount": float(amount),
                "p_description": str(description).strip(),
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    def create_manual_award(self, event_id, team_id, amount, award_type, reason,
                            facilitator, activity_id="", idempotency_key=""):
        require_control_centre("Canonical manual Award Transaction")
        transaction_id = str(uuid.uuid4())
        key = str(idempotency_key or f"MANUAL:{transaction_id}")
        result = self._request(
            "POST", "award_transactions", payload={
                "award_transaction_id": transaction_id, "event_id": str(event_id),
                "team_id": str(team_id), "activity_id": str(activity_id) or None,
                "award_type": str(award_type).upper(), "amount": float(amount),
                "source": "MANUAL", "reason": str(reason), "idempotency_key": key,
                "created_by": str(facilitator), "audit_metadata": {"Actor": str(facilitator)},
            }, query={"on_conflict": "event_id,idempotency_key"}, admin=True, retries=1,
        )
        return self._normalise_result(result) or {"AwardTransactionID": transaction_id}

    def configure_road_hunt(
        self,
        event_id,
        enabled=True,
        location_interval_seconds=20,
        reset=False,
    ):
        require_control_centre("Road Hunt runtime configuration")
        result = self._request(
            "POST",
            "rpc/exos_configure_road_hunt",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_enabled": bool(enabled),
                "p_location_interval_seconds": max(
                    10,
                    min(int(location_interval_seconds or 20), 120),
                ),
                "p_reset": bool(reset),
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    def publish_road_hunt_route(self, event_id, stops):
        require_control_centre("Road Hunt route publication")
        route_payload = []
        for position, stop in enumerate(stops or [], start=1):
            stop_id = str(stop.get("StopID", "")).strip().upper()
            stop_name = str(stop.get("StopName", "")).strip()
            if not stop_id and not stop_name:
                continue
            if not stop_id or not stop_name:
                raise ValueError("Every route stop needs a Stop ID and Stop Name.")

            try:
                latitude = float(stop.get("Latitude"))
                longitude = float(stop.get("Longitude"))
            except (TypeError, ValueError):
                raise ValueError(
                    f"{stop_name} needs valid latitude and longitude."
                ) from None
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError(
                    f"{stop_name} has latitude or longitude outside the valid range."
                )

            mission_ids = stop.get("MissionIDs", [])
            if isinstance(mission_ids, str):
                mission_ids = [
                    value.strip()
                    for value in mission_ids.split(",")
                    if value.strip()
                ]
            else:
                mission_ids = [
                    str(value).strip()
                    for value in (mission_ids or [])
                    if str(value).strip()
                ]

            route_payload.append({
                "stop_id": stop_id,
                "position": int(stop.get("Position", position) or position),
                "stop_name": stop_name,
                "latitude": latitude,
                "longitude": longitude,
                "radius_meters": max(
                    20,
                    min(int(stop.get("RadiusMeters", 150) or 150), 5000),
                ),
                "mission_ids": mission_ids,
                "instructions": str(stop.get("Instructions", "")).strip(),
                "active": bool(stop.get("Active", True)),
            })

        result = self._request(
            "POST",
            "rpc/exos_publish_route",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_stops": route_payload,
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    def get_road_hunt_participant_state(self, session_token):
        if not self.is_configured or not str(session_token).strip():
            return {}
        result = self._request(
            "POST",
            "rpc/exos_road_hunt_state",
            payload={"p_session_token": str(session_token).strip()},
        )
        return self._normalise_result(result) or {}

    def get_road_hunt_unlocked_missions(self, session_token):
        if not self.is_configured or not str(session_token).strip():
            return {}
        result = self._request(
            "POST",
            "rpc/exos_road_hunt_missions",
            payload={"p_session_token": str(session_token).strip()},
        )
        return self._normalise_result(result) or {}

    def claim_team_tracker(self, session_token):
        result = self._request(
            "POST",
            "rpc/exos_claim_team_tracker",
            payload={"p_session_token": str(session_token).strip()},
        )
        return self._normalise_result(result) or {}

    def submit_team_location(
        self,
        session_token,
        latitude,
        longitude,
        accuracy_meters=None,
        heading_degrees=None,
        speed_mps=None,
        captured_at=None,
    ):
        result = self._request(
            "POST",
            "rpc/exos_submit_team_location",
            payload={
                "p_session_token": str(session_token).strip(),
                "p_latitude": float(latitude),
                "p_longitude": float(longitude),
                "p_accuracy_meters": (
                    None
                    if accuracy_meters in (None, "")
                    else max(float(accuracy_meters), 0)
                ),
                "p_heading_degrees": (
                    None
                    if heading_degrees in (None, "")
                    else float(heading_degrees)
                ),
                "p_speed_mps": (
                    None
                    if speed_mps in (None, "")
                    else float(speed_mps)
                ),
                "p_captured_at": captured_at,
            },
        )
        return self._normalise_result(result) or {}

    def get_road_hunt_status(self, event_id):
        result = self._request(
            "POST",
            "rpc/exos_road_hunt_status",
            payload={"p_event_id": str(event_id).strip()},
            admin=True,
        )
        return self._normalise_result(result) or {}

    def release_team_tracker(self, event_id, team_name):
        require_control_centre("Road Hunt tracker recovery")
        result = self._request(
            "POST",
            "rpc/exos_release_team_tracker",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_team_name": str(team_name).strip(),
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    def record_manual_arrival(self, event_id, team_name, stop_id):
        require_control_centre("Manual road-hunt arrival")
        result = self._request(
            "POST",
            "rpc/exos_record_manual_arrival",
            payload={
                "p_event_id": str(event_id).strip(),
                "p_team_name": str(team_name).strip(),
                "p_stop_id": str(stop_id).strip().upper(),
            },
            admin=True,
        )
        return self._normalise_result(result) or {}

    def run_join_load_test(self, join_code, total_participants=100, max_workers=100):
        """Exercise atomic joins and retries through the real production RPC."""
        total = max(1, int(total_participants))
        workers = max(1, min(int(max_workers), total * 2, 100))
        run_id = uuid.uuid4().hex[:8].upper()
        started = time.perf_counter()
        joined = []
        errors = []
        latencies = []

        def join_test_participant(number):
            name = f"LOAD-{run_id}-{number:03d} Tester"
            call_started = time.perf_counter()
            player = self.join_player(
                join_code, name, f"LOAD-DEVICE-{run_id}-{number:03d}",
            )
            return player, time.perf_counter() - call_started

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(join_test_participant, number): number
                for number in range(1, total + 1)
            }
            futures.update({
                executor.submit(join_test_participant, number): number
                for number in range(1, total + 1)
            })
            for future in as_completed(futures):
                number = futures[future]
                try:
                    player, latency = future.result()
                    joined.append(player)
                    latencies.append(latency)
                except Exception as error:
                    errors.append({
                        "Participant": f"LOAD-{run_id}-{number:03d}",
                        "Error": str(error),
                    })

        session_tokens = [
            str(player.get("SessionToken", ""))
            for player in joined
            if player.get("SessionToken")
        ]
        duplicate_tokens = len(session_tokens) - len(set(session_tokens))
        participant_ids = [
            str(player.get("ParticipantID", ""))
            for player in joined if player.get("ParticipantID")
        ]
        unique_participant_ids = len(set(participant_ids))
        unique_players = {
            str(player.get("ParticipantID", "")): player
            for player in joined if player.get("ParticipantID")
        }
        team_counts = Counter(
            str(player.get("Team", "Unassigned"))
            for player in unique_players.values()
        )
        counts = list(team_counts.values())
        spread = max(counts) - min(counts) if counts else total

        restored = 0
        for token in sorted(set(session_tokens)):
            try:
                if self.get_player_by_token(token):
                    restored += 1
            except RuntimeDatabaseError:
                pass

        def percentile(values, fraction):
            if not values:
                return 0.0
            ordered = sorted(values)
            index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction) - 1))
            return round(ordered[index] * 1000, 1)

        error_text = " ".join(item["Error"] for item in errors)

        return {
            "RunID": run_id,
            "Requested": total,
            "Requests": total * 2,
            "Joined": unique_participant_ids,
            "Failed": len(errors),
            "DurationSeconds": round(time.perf_counter() - started, 2),
            "MedianLatencyMs": round(statistics.median(latencies) * 1000, 1) if latencies else 0.0,
            "P95LatencyMs": percentile(latencies, 0.95),
            "P99LatencyMs": percentile(latencies, 0.99),
            "TeamCounts": dict(sorted(team_counts.items())),
            "DistributionSpread": spread,
            "DuplicateRows": max(0, unique_participant_ids - total),
            "IdempotentRetries": duplicate_tokens,
            "SessionRestorationSuccess": restored,
            "GoogleSheets429Errors": error_text.count("429"),
            "ApplicationTimeouts": error_text.lower().count("timed out"),
            "Passed": (
                unique_participant_ids == total
                and not errors
                and spread <= 1
                and duplicate_tokens == total
                and restored == total
            ),
            "Errors": errors,
        }

    def run_submission_load_test(
        self,
        event_id,
        join_code,
        total_participants=100,
        max_workers=40,
    ):
        total = max(1, int(total_participants))
        workers = max(1, min(int(max_workers), total, 50))
        run_id = uuid.uuid4().hex[:8].upper()
        reflection_mission = f"LOAD-NASI-{run_id}"
        photo_mission = f"LOAD-PHOTO-{run_id}"
        started = time.perf_counter()
        joined = []
        submission_errors = []
        photo_errors = []
        photo_paths = []
        cleanup_errors = []
        result = None

        event_rows = self._request(
            "GET",
            "runtime_events",
            query={
                "event_id": f"eq.{str(event_id).strip()}",
                "select": "event_id,next_team_index",
                "limit": "1",
            },
            admin=True,
        ) or []
        event_row = self._normalise_result(event_rows) or {}
        original_team_index = int(event_row.get("next_team_index", 0) or 0)

        def join_test_participant(number):
            name = f"LOAD-{run_id}-{number:03d} Tester"
            return self.join_player(
                join_code, name, f"LOAD-DEVICE-{run_id}-{number:03d}",
            )

        try:
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
                        submission_errors.append({
                            "Stage": "Join",
                            "Record": f"Participant {number}",
                            "Error": str(error),
                        })

            def save_reflection(player):
                return self.save_submission({
                    "SubmissionID": str(uuid.uuid4()),
                    "EventID": event_id,
                    "MissionID": reflection_mission,
                    "TeamName": player.get("Team", ""),
                    "ParticipantName": player.get("Name", ""),
                    "SessionToken": player.get("SessionToken", ""),
                    "SubmissionType": "NASI",
                    "Remarks": f"Concurrent test {run_id}",
                    "Status": "PENDING",
                    "Judged": "No",
                    "SubmittedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                })

            reflection_results = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(save_reflection, player): player
                    for player in joined
                }
                for future in as_completed(futures):
                    player = futures[future]
                    try:
                        reflection_results.append(future.result())
                    except Exception as error:
                        submission_errors.append({
                            "Stage": "Individual submission",
                            "Record": player.get("Name", ""),
                            "Error": str(error),
                        })

            representatives = {}
            for player in joined:
                representatives.setdefault(str(player.get("Team", "")), player)

            image_buffer = io.BytesIO()
            Image.new("RGB", (2, 2), color=(30, 120, 220)).save(
                image_buffer,
                format="JPEG",
                quality=80,
            )
            tiny_jpeg = image_buffer.getvalue()

            def save_team_photo(item):
                position, (team_name, player) = item
                storage_path = (
                    f"{event_id}/{photo_mission}/team-{position:03d}/"
                    f"{run_id}.jpg"
                )
                self.upload_submission_image(
                    storage_path,
                    tiny_jpeg,
                    content_type="image/jpeg",
                )
                photo_paths.append(storage_path)
                saved = self.save_submission({
                    "SubmissionID": str(uuid.uuid4()),
                    "EventID": event_id,
                    "MissionID": photo_mission,
                    "TeamName": team_name,
                    "ParticipantName": player.get("Name", ""),
                    "SessionToken": player.get("SessionToken", ""),
                    "SubmissionType": "PHOTO",
                    "ImageURL": (
                        "supabase://exos-submissions/" + storage_path
                    ),
                    "DriveFileID": storage_path,
                    "Status": "PENDING",
                    "Judged": "No",
                    "SubmittedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
                downloaded = self.download_submission_image(storage_path)
                return saved, storage_path, downloaded == tiny_jpeg

            photo_results = []
            photo_items = list(enumerate(representatives.items(), start=1))
            with ThreadPoolExecutor(
                max_workers=max(1, min(len(photo_items), 50))
            ) as executor:
                futures = {
                    executor.submit(save_team_photo, item): item
                    for item in photo_items
                }
                for future in as_completed(futures):
                    _, (team_name, _) = futures[future]
                    try:
                        saved, storage_path, downloaded = future.result()
                        photo_results.append(saved)
                        if not downloaded:
                            raise RuntimeDatabaseError(
                                "Uploaded image could not be downloaded."
                            )
                    except Exception as error:
                        photo_errors.append({
                            "Stage": "Team photo",
                            "Record": team_name,
                            "Error": str(error),
                        })

            runtime_rows = self.get_submissions(event_id)
            reflection_rows = [
                row for row in runtime_rows
                if row.get("MissionID") == reflection_mission
            ]
            photo_rows = [
                row for row in runtime_rows
                if row.get("MissionID") == photo_mission
            ]

            passed = (
                len(joined) == total
                and len(reflection_results) == total
                and len(reflection_rows) == total
                and len(photo_results) == len(representatives)
                and len(photo_rows) == len(representatives)
                and not submission_errors
                and not photo_errors
            )

            result = {
                "RunID": run_id,
                "Requested": total,
                "Joined": len(joined),
                "IndividualSubmissions": len(reflection_rows),
                "TeamPhotoSubmissions": len(photo_rows),
                "Teams": len(representatives),
                "Failed": len(submission_errors) + len(photo_errors),
                "DurationSeconds": round(time.perf_counter() - started, 2),
                "Passed": passed,
                "Errors": submission_errors + photo_errors,
            }
        finally:
            if photo_paths:
                try:
                    self.delete_submission_images(photo_paths)
                except Exception as error:
                    cleanup_errors.append({
                        "Stage": "Cleanup",
                        "Record": "Storage objects",
                        "Error": str(error),
                    })
            try:
                self._request(
                    "DELETE",
                    "runtime_submissions",
                    query={
                        "event_id": f"eq.{str(event_id).strip()}",
                        "mission_id": (
                            f"in.({reflection_mission},{photo_mission})"
                        ),
                    },
                    admin=True,
                )
            except Exception as error:
                cleanup_errors.append({
                    "Stage": "Cleanup",
                    "Record": "Runtime test submissions",
                    "Error": str(error),
                })
            try:
                self._request(
                    "DELETE",
                    "runtime_participants",
                    query={
                        "event_id": f"eq.{str(event_id).strip()}",
                        "display_name": f"like.LOAD-{run_id}-*",
                    },
                    admin=True,
                )
            except Exception as error:
                cleanup_errors.append({
                    "Stage": "Cleanup",
                    "Record": "Runtime test participants",
                    "Error": str(error),
                })
            try:
                self._request(
                    "PATCH",
                    "runtime_events",
                    payload={"next_team_index": original_team_index},
                    query={"event_id": f"eq.{str(event_id).strip()}"},
                    admin=True,
                )
            except Exception as error:
                cleanup_errors.append({
                    "Stage": "Cleanup",
                    "Record": "Team allocation pointer",
                    "Error": str(error),
                })

        result["CleanupPassed"] = not cleanup_errors
        result["Errors"].extend(cleanup_errors)
        result["Failed"] += len(cleanup_errors)
        result["Passed"] = result["Passed"] and not cleanup_errors
        return result

    def run_dual_event_load_test(
        self,
        events,
        total_participants_each=100,
        max_workers_each=40,
    ):
        event_configs = [dict(event) for event in events]
        if len(event_configs) != 2:
            raise ValueError("Exactly two events are required.")

        event_ids = [
            str(event.get("EventID", "")).strip()
            for event in event_configs
        ]
        if not all(event_ids) or len(set(event_ids)) != 2:
            raise ValueError("Select two different published test events.")

        started = time.perf_counter()
        event_results = []

        def test_event(event):
            result = self.run_submission_load_test(
                event_id=event.get("EventID", ""),
                join_code=event.get("JoinCode", ""),
                total_participants=total_participants_each,
                max_workers=max_workers_each,
            )
            return {
                "EventID": event.get("EventID", ""),
                "EventName": event.get("EventName", ""),
                **result,
            }

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(test_event, event): event
                for event in event_configs
            }
            for future in as_completed(futures):
                event = futures[future]
                try:
                    event_results.append(future.result())
                except Exception as error:
                    event_results.append({
                        "EventID": event.get("EventID", ""),
                        "EventName": event.get("EventName", ""),
                        "Requested": int(total_participants_each),
                        "Joined": 0,
                        "IndividualSubmissions": 0,
                        "TeamPhotoSubmissions": 0,
                        "Failed": int(total_participants_each),
                        "Passed": False,
                        "CleanupPassed": False,
                        "Errors": [{
                            "Stage": "Two-event test",
                            "Record": event.get("EventID", ""),
                            "Error": str(error),
                        }],
                    })

        event_results.sort(key=lambda row: str(row.get("EventID", "")))
        run_ids = [
            str(result.get("RunID", ""))
            for result in event_results
            if result.get("RunID")
        ]
        isolated_runs = len(run_ids) == 2 and len(set(run_ids)) == 2
        passed = (
            len(event_results) == 2
            and isolated_runs
            and all(result.get("Passed") for result in event_results)
        )

        return {
            "RequestedPerEvent": int(total_participants_each),
            "RequestedTotal": int(total_participants_each) * 2,
            "DurationSeconds": round(time.perf_counter() - started, 2),
            "EventResults": event_results,
            "IsolatedRuns": isolated_runs,
            "Passed": passed,
        }
