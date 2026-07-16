import io
import json
import os
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import streamlit as st
from PIL import Image


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
        published = self._normalise_result(result) or {}
        if reset_registration:
            published["AIReset"] = self.reset_ai_event(
                str(event.get("EventID", "")).strip()
            )
        return published

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
                "participant_id,event_id,display_name,team_name,points,"
                "status,joined_at,session_token"
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

    def reset_ai_event(self, event_id):
        result = self._request(
            "POST",
            "rpc/exos_reset_ai_event",
            payload={"p_event_id": str(event_id).strip()},
            admin=True,
        )
        return self._normalise_result(result) or {}

    def save_submission(self, submission):
        def value(name, default=""):
            raw = submission.get(name, default)
            return str(default if raw is None else raw)

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

    def configure_credit_wallet(self, event_id, enabled=True, reset=False):
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

    def configure_road_hunt(
        self,
        event_id,
        enabled=True,
        location_interval_seconds=20,
        reset=False,
    ):
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
            return self.join_player(join_code, name)

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
