"""Standard EXOS application adapter backed exclusively by Core v2.

This is the compatibility boundary for the existing Streamlit screens.  It
returns the field names those screens already understand while every read and
write is performed against ``*_v2`` tables or ``exos_v2_*`` RPCs.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import secrets
import string
import uuid
from typing import Any
from urllib.parse import urlparse

import streamlit as st

from data.runtime_database import RuntimeDatabaseError, get_runtime_database
from engines.programme_duplication import clone_programme_stages
from engines.programme_hierarchy import activity_details, build_programme_hierarchy
from engines.stage_timer import new_timer, transition_timer
from engines.theme_park_race import (
    facilitator_projection as theme_park_race_facilitator_projection,
    is_theme_park_race,
    normalise_configuration as normalise_theme_park_race_configuration,
    participant_projection as theme_park_race_participant_projection,
    project_stations as project_theme_park_race_stations,
)


_V2_TABLES = {
    "events_v2", "programmes_v2", "modules_v2", "activities_v2", "teams_v2",
    "participants_v2", "participant_sessions_v2", "activity_runtime_v2",
    "submissions_v2", "submission_evidence_v2", "reviews_v2",
    "score_transactions_v2", "credit_transactions_v2", "audit_log_v2",
    "projector_state_v2", "marketplace_items_v2", "marketplace_transactions_v2",
    "team_access_sessions_v2",
}
_KNOWN_PRODUCTION_HOSTS = {"bqsbkdfzqyiodivhyxnq.supabase.co"}


def _deployment_environment() -> str:
    value = str(os.getenv("EXOS_ENV", "") or "").strip()
    if value:
        return value.casefold()
    try:
        return str(st.secrets.get("EXOS_ENV", "") or "").strip().casefold()
    except Exception:
        return ""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


class StandardCoreV2Adapter:
    """Legacy-shaped screen API with a strict Core v2 implementation."""

    def __init__(self, runtime=None):
        self._client = runtime or get_runtime_database()
        if not self._client.is_configured:
            raise RuntimeDatabaseError("Core v2 is not configured. SUPABASE_URL and a publishable key are required.")
        if _deployment_environment() == "staging":
            host = (urlparse(str(self._client.url)).hostname or "").casefold()
            if not host or host in _KNOWN_PRODUCTION_HOSTS:
                raise RuntimeDatabaseError(
                    f"Staging isolation blocked non-staging Supabase host: {host or 'missing'}"
                )
        self.runtime = self
        self.legacy_runtime_calls = 0
        self.google_sheets_runtime_calls = 0

    @property
    def is_configured(self):
        return self._client.is_configured

    @property
    def can_publish(self):
        return self._client.can_publish

    def _guard(self, path: str):
        bare = path.split("?", 1)[0].strip("/")
        if bare.startswith("rpc/"):
            if not bare[4:].startswith("exos_v2_"):
                self.legacy_runtime_calls += 1
                raise RuntimeDatabaseError(f"Blocked non-Core-v2 RPC: {bare}")
            return
        if bare not in _V2_TABLES:
            self.legacy_runtime_calls += 1
            raise RuntimeDatabaseError(f"Blocked non-Core-v2 table: {bare}")

    def _request(self, method, path, payload=None, query=None, admin=True, retries=4):
        self._guard(path)
        return self._client._request(method, path, payload=payload, query=query, admin=admin, retries=retries)

    def _rows(self, path, query=None, *, admin=True):
        result = self._request("GET", path, query=query, admin=admin)
        return result if isinstance(result, list) else []

    def _one(self, path, query=None, *, admin=True):
        rows = self._rows(path, query, admin=admin)
        return rows[0] if rows else {}

    def _rpc(self, name, payload, *, admin=True):
        result = self._request("POST", f"rpc/{name}", payload=payload, admin=admin)
        if isinstance(result, list):
            return result[0] if result else {}
        return result or {}

    def get_staging_call_counts(self):
        return {
            "LEGACY_RUNTIME_CALLS": self.legacy_runtime_calls,
            "GOOGLE_SHEETS_RUNTIME_CALLS": self.google_sheets_runtime_calls,
        }

    def assert_core_v2_only(self):
        counts = self.get_staging_call_counts()
        if any(counts.values()):
            raise RuntimeDatabaseError(str(counts))
        return counts

    # Event administration -------------------------------------------------
    @staticmethod
    def event_metadata(event):
        return _dict((event or {}).get("_EventPayload"))

    @staticmethod
    def _event(row):
        payload = _dict(row.get("event_payload"))
        identity_config = _dict(payload.get("TeamIdentityConfig"))
        return {
            "EventID": str(row.get("event_id", "")),
            "EventName": str(row.get("event_name", "")),
            "JoinCode": str(row.get("join_code", "")),
            "ProgrammeType": str(row.get("programme_type", "STANDARD")),
            "ScoringMode": str(row.get("scoring_mode", "TEAM_COMPETITIVE")),
            "Status": str(row.get("lifecycle_status", "DRAFT")).title(),
            "Client": str(payload.get("Client", "")),
            "Department": str(payload.get("Department", "")),
            "EventDate": str(payload.get("EventDate", "")),
            "Venue": str(payload.get("Venue", "")),
            "Facilitator": str(payload.get("Facilitator", "")),
            "NumberOfTeams": int(payload.get("NumberOfTeams", 0) or 0),
            "ThemeType": str(
                identity_config.get("ThemeType") or payload.get("ThemeType")
                or ("COUNTRY" if payload.get("CountryPool") else "CUSTOM")
            ),
            "ThemeName": str(identity_config.get("ThemeName", payload.get("TeamTheme", "Teams"))),
            "_CreatedAt": str(row.get("created_at", "")),
            "_UpdatedAt": str(row.get("updated_at", "")),
            "_EventPayload": payload,
        }

    def get_events(self, include_archived=False):
        rows = self._rows("events_v2", {
            "select": "event_id,event_name,join_code,event_type,programme_type,scoring_mode,lifecycle_status,event_payload,published_at,created_at,updated_at",
            "order": "created_at.desc",
        })
        events = [self._event(row) for row in rows]
        return events if include_archived else [e for e in events if e["Status"].upper() != "ARCHIVED"]

    def get_event(self, event_id):
        row = self._one("events_v2", {
            "event_id": f"eq.{str(event_id).strip()}",
            "select": "event_id,event_name,join_code,event_type,programme_type,scoring_mode,lifecycle_status,event_payload,published_at,created_at,updated_at",
            "limit": "1",
        })
        return self._event(row) if row else None

    def get_event_by_join_code(self, join_code):
        row = self._one("events_v2", {
            "join_code": f"eq.{str(join_code).strip().upper()}",
            "select": "event_id,event_name,join_code,event_type,programme_type,scoring_mode,lifecycle_status,event_payload,published_at,created_at,updated_at",
            "limit": "1",
        })
        return self._event(row) if row else None

    @staticmethod
    def is_theme_park_race_event(event):
        """Select the generic engine only from RaceConfiguration.EngineKind."""
        return is_theme_park_race(event)

    def get_theme_park_race_configuration(self, event_id):
        event = self.get_event(event_id)
        if not event or not self.is_theme_park_race_event(event):
            return {}
        return normalise_theme_park_race_configuration(event)

    def save_theme_park_race_configuration(self, event_id, configuration, actor):
        """Persist the generic engine contract through its guarded Core RPC."""
        return self._rpc("exos_v2_theme_park_race_save_configuration", {
            "p_event_id": str(event_id),
            "p_configuration": dict(configuration or {}),
            "p_actor": str(actor),
        })

    def set_theme_park_race_runtime_phase(self, event_id, runtime_phase, actor):
        return self._rpc("exos_v2_set_theme_park_race_runtime_phase", {
            "p_event_id": str(event_id),
            "p_runtime_phase": str(runtime_phase),
            "p_actor": str(actor),
        })

    def create_new_join_code(self):
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            if not self.get_event_by_join_code(code):
                return code
        raise RuntimeDatabaseError("Could not allocate a unique join code.")

    def generate_next_event_id(self):
        return f"EVT-{datetime.now(timezone.utc):%y%m%d}-{secrets.token_hex(2).upper()}"

    @staticmethod
    def _team_rows(event_id, count):
        return [{
            "team_id": f"{event_id}-TEAM-{position:02d}",
            "team_name": f"Team {position}",
            "country": "",
            "team_flag": "",
        } for position in range(1, int(count) + 1)]

    def create_event(self, event_id, client, department, event_name, event_date, venue,
                     programme_type, join_code, number_of_teams, facilitator=""):
        teams = self._team_rows(event_id, number_of_teams)
        result = self._rpc("exos_v2_publish_event", {
            "p_event_id": event_id, "p_join_code": join_code, "p_event_name": event_name,
            "p_teams": teams, "p_scoring_mode": "TEAM_COMPETITIVE", "p_event_type": "STANDARD",
        })
        self.update_event(event_id, {
            "Client": client, "Department": department, "EventDate": event_date,
            "Venue": venue, "Facilitator": facilitator, "ProgrammeType": programme_type,
            "NumberOfTeams": int(number_of_teams), "Status": "DRAFT",
        })
        return result

    def update_event(self, event_id, updates):
        current = self.get_event(event_id)
        if not current:
            raise ValueError(f"Event {event_id} was not found.")
        updates = dict(updates or {})
        payload = self.event_metadata(current)
        column_payload = {}
        field_map = {
            "EventName": "event_name", "JoinCode": "join_code", "ProgrammeType": "programme_type",
            "ScoringMode": "scoring_mode", "Status": "lifecycle_status",
        }
        for key, value in updates.items():
            if key in field_map:
                column_payload[field_map[key]] = str(value).upper() if key in {"JoinCode", "Status"} else value
            else:
                payload[key] = value
        column_payload["event_payload"] = payload
        column_payload["updated_at"] = _now()
        self._request("PATCH", "events_v2", payload=column_payload,
                      query={"event_id": f"eq.{event_id}"})
        return self.get_event(event_id)

    def update_event_metadata(self, event_id, updates):
        current = self.get_event(event_id)
        payload = self.event_metadata(current)
        updates = dict(updates or {})
        control = _dict(payload.get("control_state"))
        for key in ("StageTimers", "ProjectorBroadcast", "CurrentStageStatus", "RegistrationOpen"):
            if key in updates:
                control[key] = updates.pop(key)
        if control:
            payload["control_state"] = control
        payload.update(updates)
        self._request("PATCH", "events_v2", payload={"event_payload": payload, "updated_at": _now()},
                      query={"event_id": f"eq.{event_id}"})
        return payload

    def archive_event(self, event_id):
        return self.update_event(event_id, {"Status": "ARCHIVED"})

    def restore_event(self, event_id):
        return self.update_event(event_id, {"Status": "DRAFT"})

    # Teams and participants -----------------------------------------------
    def get_teams(self, event_id):
        event = self.get_event(event_id) or {}
        metadata = self.event_metadata(event)
        identity_config = _dict(metadata.get("TeamIdentityConfig"))
        theme_type = str(identity_config.get("ThemeType") or event.get("ThemeType", "CUSTOM"))
        theme_name = str(identity_config.get("ThemeName") or event.get("ThemeName", "Teams"))
        configured = {
            str(item.get("TeamID", "")): _dict(item)
            for item in identity_config.get("Identities", [])
            if isinstance(item, dict) and item.get("TeamID")
        }
        rows = self._rows("teams_v2", {
            "event_id": f"eq.{event_id}", "select": "team_id,team_name,country,team_flag,is_active,created_at",
            "order": "team_id.asc",
        })
        output = []
        for row in rows:
            team_id = str(row["team_id"])
            extra = configured.get(team_id, {})
            identity = str(extra.get("TeamIdentity") or row.get("team_name", ""))
            output.append({
                "EventID": event_id, "TeamID": team_id,
                "TeamName": identity, "TeamIdentity": identity,
                "ThemeType": theme_type,
                "ThemeName": theme_name,
                "Country": str(extra.get("Country", row.get("country", "")) or ""),
                "Flag": str(extra.get("Emoji", extra.get("Icon", row.get("team_flag", ""))) or ""),
                "Icon": str(extra.get("Icon", "") or ""),
                "Emoji": str(extra.get("Emoji", "") or ""),
                "Image": str(extra.get("Image", "") or ""),
                "Status": "Active" if row.get("is_active", True) else "Inactive",
            })
        return output

    get_runtime_teams = get_teams

    def get_team_count(self, event_id):
        return len(self.get_teams(event_id))

    def get_participant_count(self, event_id):
        return len(self._rows("participants_v2", {
            "event_id": f"eq.{event_id}", "is_archived": "eq.false", "select": "participant_id",
        }))

    def create_teams(self, event_id, count):
        return self.replace_event_teams(event_id, [
            {"TeamID": f"{event_id}-TEAM-{i:02d}", "TeamName": f"Team {i}"}
            for i in range(1, int(count) + 1)
        ])

    def replace_event_teams(self, event_id, teams):
        teams = [dict(team) for team in teams]
        if self.get_participant_count(event_id):
            raise RuntimeDatabaseError("Teams cannot be replaced after participants register.")
        event = self.get_event(event_id)
        payload = []
        identities = []
        for i, team in enumerate(teams, 1):
            team_identity = str(
                team.get("TeamIdentity") or team.get("TeamName") or f"Team {i}"
            ).strip()
            identity = team_identity.casefold()
            if identity in identities:
                raise RuntimeDatabaseError(
                    f"Duplicate team identity is not allowed within an event: {team_identity}"
                )
            identities.append(identity)
            country = str(team.get("Country", "") or "").strip()
            emoji = str(team.get("Emoji", team.get("Flag", "")) or "").strip()
            icon = str(team.get("Icon", "") or "").strip()
            payload.append({
                "team_id": str(team.get("TeamID") or f"{event_id}-TEAM-{i:02d}"),
                "team_name": team_identity,
                "country": country,
                "team_flag": emoji or icon,
            })
        result = self._rpc("exos_v2_publish_event", {
            "p_event_id": event_id, "p_join_code": event["JoinCode"], "p_event_name": event["EventName"],
            "p_teams": payload, "p_scoring_mode": event["ScoringMode"], "p_event_type": "STANDARD",
        })
        current_config = _dict(self.event_metadata(event).get("TeamIdentityConfig"))
        first_team = teams[0] if teams else {}
        current_config.update({
            "ThemeType": str(first_team.get("ThemeType", current_config.get("ThemeType", "CUSTOM"))),
            "ThemeName": str(first_team.get("ThemeName", current_config.get("ThemeName", "Teams"))),
            "Identities": [{
                "TeamID": row["team_id"],
                "TeamIdentity": row["team_name"],
                "Country": str(team.get("Country", "") or ""),
                "Icon": str(team.get("Icon", "") or ""),
                "Emoji": str(team.get("Emoji", team.get("Flag", "")) or ""),
                "Image": str(team.get("Image", "") or ""),
            } for row, team in zip(payload, teams)],
        })
        self.update_event_metadata(event_id, {
            "NumberOfTeams": len(payload),
            "TeamIdentityConfig": current_config,
        })
        return result

    @staticmethod
    def _identity(value):
        value = _dict(value)
        if not value:
            return None
        value.setdefault("Found", True)
        value.setdefault("Rejoined", False)
        return value

    def join_player(self, join_code, participant_name, device_id, requested_team_id=""):
        return self._identity(self._rpc("exos_v2_join_event_v2", {
            "p_join_code": join_code, "p_participant_name": participant_name,
            "p_device_id": device_id, "p_requested_team_id": requested_team_id,
        }, admin=False))

    def join_player_by_code(self, join_code, name, *, device_id=""):
        return self.join_player(join_code, name, device_id)

    def restore_join(self, join_code, participant_name, device_id):
        return self._identity(self._rpc("exos_v2_restore_join", {
            "p_join_code": join_code, "p_participant_name": participant_name, "p_device_id": device_id,
        }, admin=False))

    def recover_participant_access(self, join_code, participant_name, device_id):
        return self._identity(self._rpc("exos_v2_recover_participant_access", {
            "p_join_code": join_code,
            "p_participant_name": participant_name,
            "p_device_id": device_id,
        }, admin=False))

    def get_player_by_token(self, session_token):
        return self._identity(self._rpc("exos_v2_standard_participant_state", {
            "p_session_token": session_token,
        }, admin=False))

    def get_player(self, event_id, participant_name):
        rows = self.get_players(event_id)
        target = " ".join(str(participant_name).casefold().split())
        return next((row for row in rows if " ".join(row["Name"].casefold().split()) == target), None)

    def get_players(self, event_id=None):
        query = {
            "select": "participant_id,event_id,team_id,display_name,country,flag,participant_status,is_leader,intelligence_credits,created_at,last_seen_at,is_archived",
            "is_archived": "eq.false", "order": "created_at.asc",
        }
        if event_id:
            query["event_id"] = f"eq.{event_id}"
        rows = self._rows("participants_v2", query)
        team_names = {t["TeamID"]: t["TeamName"] for t in self.get_teams(event_id)} if event_id else {}
        return [{
            "ParticipantID": str(r["participant_id"]), "EventID": r["event_id"], "TeamID": r["team_id"],
            "Team": team_names.get(r["team_id"], r["team_id"]), "Name": r["display_name"],
            "Country": r.get("country", ""), "Flag": r.get("flag", ""),
            "IsLeader": bool(r.get("is_leader")), "Points": int(r.get("intelligence_credits", 0) or 0),
            "JoinedAt": r.get("created_at", ""), "LastSeenAt": r.get("last_seen_at", ""),
        } for r in rows]

    def get_theme_park_race_players(self, event_id):
        """Read the additive Captain bit only for a configured Team Formation event."""
        rows = self._rows("participants_v2", {
            "event_id": f"eq.{event_id}", "is_archived": "eq.false",
            "select": "participant_id,event_id,team_id,display_name,is_team_formation_captain,is_leader,created_at,last_seen_at",
            "order": "created_at.asc",
        })
        return [{
            "ParticipantID": str(row.get("participant_id", "")),
            "EventID": str(row.get("event_id", "")),
            "TeamID": str(row.get("team_id", "")),
            "Name": str(row.get("display_name", "")),
            "IsTeamFormationCaptain": bool(row.get("is_team_formation_captain")),
            "IsLeader": bool(row.get("is_leader")),
            "JoinedAt": row.get("created_at", ""),
            "LastSeenAt": row.get("last_seen_at", ""),
        } for row in rows]

    def get_team_roster(self, event_id, team_name):
        team = next((t for t in self.get_teams(event_id) if t["TeamName"] == team_name or t["TeamID"] == team_name), {})
        return [p for p in self.get_players(event_id) if p["TeamID"] == team.get("TeamID")]

    # Team Formation V1 / Theme Park Race --------------------------------
    def team_formation_configuration(self, event_id):
        event = self.get_event(event_id) or {}
        return _dict(self.event_metadata(event).get("TeamFormation"))

    def team_formation_enabled(self, event_id):
        return str(self.team_formation_configuration(event_id).get("SchemaVersion", "")) == "1"

    def register_team_formation_participant(self, join_code, display_name, device_id,
                                            enrollment_credential):
        event = self.get_event_by_join_code(join_code) or {}
        formation = _dict(self.event_metadata(event).get("TeamFormation"))
        mode = str(formation.get("Mode", "")).upper()
        if mode == "RANDOM_ASSIGN":
            rpc = "exos_v2_team_formation_register_random"
            payload = {
                "p_join_code": join_code, "p_display_name": display_name,
                "p_device_id": device_id, "p_enrollment_credential": enrollment_credential,
            }
        elif mode == "PREASSIGNED":
            rpc = "exos_v2_team_formation_claim_preassigned"
            payload = {
                "p_join_code": join_code, "p_enrollment_credential": enrollment_credential,
                "p_device_id": device_id,
            }
        else:
            raise RuntimeDatabaseError("Team Formation is not open for this event.")
        return self._identity(self._rpc(rpc, payload, admin=False))

    def recover_team_formation_participant(self, join_code, enrollment_credential, device_id):
        return self._identity(self._rpc("exos_v2_recover_team_formation_participant", {
            "p_join_code": join_code, "p_enrollment_credential": enrollment_credential,
            "p_device_id": device_id,
        }, admin=False))

    def claim_team_formation_captain(self, participant_session_token, device_id):
        return self._rpc("exos_v2_claim_team_formation_captain", {
            "p_participant_session_token": participant_session_token,
            "p_device_id": device_id,
        }, admin=False)

    def recover_team_formation_captain(self, join_code, enrollment_credential, device_id):
        return self._identity(self._rpc("exos_v2_recover_team_formation_captain", {
            "p_join_code": join_code, "p_enrollment_credential": enrollment_credential,
            "p_device_id": device_id,
        }, admin=False))

    def open_team_formation(self, event_id, actor):
        return self._rpc("exos_v2_open_team_formation", {
            "p_event_id": event_id, "p_actor": actor,
        })

    def lock_team_formation(self, event_id, actor):
        return self._rpc("exos_v2_lock_team_formation", {
            "p_event_id": event_id, "p_actor": actor,
        })

    def open_team_captain_selection(self, event_id, actor):
        return self._rpc("exos_v2_open_team_captain_selection", {
            "p_event_id": event_id, "p_actor": actor,
        })

    def activate_team_formation(self, event_id, actor):
        return self._rpc("exos_v2_activate_team_formation", {
            "p_event_id": event_id, "p_actor": actor,
        })

    def transfer_team_formation_captain(self, event_id, team_id, participant_id, actor, reason):
        return self._rpc("exos_v2_transfer_team_formation_captain", {
            "p_event_id": event_id, "p_team_id": team_id,
            "p_target_participant_id": participant_id,
            "p_actor": actor, "p_reason": reason,
        })

    def get_theme_park_race_stations(self, event_id):
        return project_theme_park_race_stations(self.get_programme_stages(event_id))

    def get_theme_park_race_mission_runtime(self, event_id, team_id=""):
        """Return existing activity runtime rows used as canonical board selection state."""
        query = {
            "event_id": f"eq.{event_id}",
            "select": "runtime_id,event_id,team_id,participant_id,activity_id,state_payload,is_completed,updated_at",
            "order": "updated_at.desc",
        }
        if team_id:
            query["team_id"] = f"eq.{team_id}"
        return [{
            "RuntimeID": str(row.get("runtime_id", "")),
            "EventID": str(row.get("event_id", "")),
            "TeamID": str(row.get("team_id", "")),
            "ParticipantID": str(row.get("participant_id", "")),
            "ActivityID": str(row.get("activity_id", "")),
            "StatePayload": _dict(row.get("state_payload")),
            "IsCompleted": bool(row.get("is_completed")),
            "UpdatedAt": row.get("updated_at", ""),
        } for row in self._rows("activity_runtime_v2", query)]

    def theme_park_race_participant_workspace(self, session_token):
        participant = self.get_player_by_token(session_token)
        if not participant:
            raise RuntimeDatabaseError("Participant session is required.")
        event_id = str(participant.get("EventID", ""))
        event = self.get_event(event_id)
        if not event or not self.is_theme_park_race_event(event):
            raise RuntimeDatabaseError("Event is not configured for Theme Park Race.")
        captain_rows = self.get_theme_park_race_players(event_id)
        canonical = next((row for row in captain_rows if row["ParticipantID"] == str(participant.get("ParticipantID", ""))), {})
        participant = {**participant, **canonical}
        participant_session = self._one("participant_sessions_v2", {
            "session_token": f"eq.{session_token}", "is_active": "eq.true",
            "select": "device_id", "limit": "1",
        })
        participant["DeviceID"] = str(participant_session.get("device_id", ""))
        captain_session = self._one("team_access_sessions_v2", {
            "event_id": f"eq.{event_id}",
            "team_id": f"eq.{participant.get('TeamID', '')}",
            "team_formation_captain_participant_id": f"eq.{participant.get('ParticipantID', '')}",
            "device_id": f"eq.{str(participant.get('DeviceID', ''))}",
            "is_active": "eq.true",
            "select": "team_access_session_id",
            "limit": "1",
        }) if participant.get("IsTeamFormationCaptain") else {}
        participant["CaptainSessionActive"] = bool(captain_session)
        submissions = [row for row in self.get_submissions(event_id)
                       if str(row.get("TeamID", "")) == str(participant.get("TeamID", ""))]
        team_members = [row for row in captain_rows if str(row.get("TeamID", "")) == str(participant.get("TeamID", ""))]
        return theme_park_race_participant_projection(
            event=event, participant=participant,
            stations=self.get_theme_park_race_stations(event_id), submissions=submissions,
            mission_runtime=self.get_theme_park_race_mission_runtime(event_id, participant.get("TeamID", "")),
            team_members=team_members,
            reviews=self._theme_park_race_rejection_reviews(event_id, submissions),
        )

    def _theme_park_race_rejection_reviews(self, event_id, submissions):
        """Canonical facilitator feedback for this team's REJECTED submissions.

        Reviews carry no team_id, so this is scoped by submission id and to the
        REJECT decision only — nothing is fetched for a team with no rejection,
        and no other team's review ever reaches this query.
        """
        submission_ids = sorted({
            str(row.get("SubmissionID", "")) for row in submissions
            if str(row.get("Status", "")).upper() == "REJECTED" and row.get("SubmissionID")
        })
        if not submission_ids:
            return []
        rows = self._rows("reviews_v2", {
            "event_id": f"eq.{event_id}",
            "submission_id": f"in.({','.join(submission_ids)})",
            "decision": "eq.REJECT",
            "select": "submission_id,decision,rationale,reviewed_at",
            "order": "reviewed_at.desc",
        })
        return [{
            "SubmissionID": str(row.get("submission_id", "")),
            "Decision": str(row.get("decision", "")).upper(),
            "Reason": str(row.get("rationale", "") or ""),
            "ReviewedAt": str(row.get("reviewed_at", "") or ""),
        } for row in rows]

    def select_theme_park_race_mission(self, session_token, activity_id):
        """Atomically select an available OPEN_MISSION_BOARD activity server-side."""
        return self._rpc("exos_v2_theme_park_race_board_select", {
            "p_session_token": session_token,
            "p_activity_id": activity_id,
        }, admin=False)

    def save_theme_park_race_submission(self, session_token, activity_id, submission_payload, strategy_mode=""):
        """Submit through the Captain-guarded engine RPC for the caller's own known strategy.

        The caller already knows StrategyMode from the same workspace read that
        rendered the form; pass it here.  Only when it is omitted does this fall
        back to a participant/event lookup to derive it — a second network
        round-trip that ran unconditionally before every write in the previous
        implementation, was a needless extra point of failure ahead of the
        canonical RPC, and could silently misroute an OPEN_MISSION_BOARD
        submission to the generic route contract if that lookup ever came back
        empty (a transient participant-state read failure, for example).
        """
        mode = str(strategy_mode or "").upper()
        if not mode:
            participant = self.get_player_by_token(session_token)
            event = self.get_event(str((participant or {}).get("EventID", ""))) if participant else {}
            mode = normalise_theme_park_race_configuration(event).get("StrategyMode", "")
        rpc = "exos_v2_theme_park_race_board_submit" if mode == "OPEN_MISSION_BOARD" else "exos_v2_theme_park_race_submit"
        return self._rpc(rpc, {
            "p_session_token": session_token,
            "p_activity_id": activity_id,
            "p_submission_payload": dict(submission_payload or {}),
        }, admin=False)

    def record_theme_park_race_ride_outcome(self, session_token, activity_id, attempt_status, payload=None):
        return self._rpc("exos_v2_theme_park_race_board_record_ride_outcome", {
            "p_session_token": session_token,
            "p_activity_id": activity_id,
            "p_ride_attempt_status": attempt_status,
            "p_payload": dict(payload or {}),
        }, admin=False)

    def review_theme_park_race_board_submission(self, submission_id, expected_submitted_at, decision,
                                                score=0, actor="", reason="", idempotency_key=""):
        """Review an OPEN_MISSION_BOARD submission through the installed 039 contract.

        The engine re-validates EngineKind, StrategyMode and the reviewed
        revision server-side and derives the score ledger identity itself, so
        the caller key travels only as audit metadata.
        """
        submission = str(submission_id or "").strip()
        revision = str(expected_submitted_at or "").strip()
        reviewer = str(actor or "").strip()
        if not submission or not revision or not reviewer:
            raise RuntimeDatabaseError(
                "Theme Park Race board review requires a submission, its submitted-at revision, and a facilitator identity."
            )
        approved = str(decision).upper() in {"APPROVE", "APPROVED"}
        mapped = "APPROVE" if approved else "REJECT"
        return self._rpc("exos_v2_theme_park_race_board_review", {
            "p_submission_id": submission,
            "p_expected_submitted_at": revision,
            "p_decision": mapped,
            "p_score": float(score or 0) if approved else 0.0,
            "p_actor": reviewer,
            "p_reason": str(reason or ""),
            "p_idempotency_key": str(idempotency_key or "").strip()
            or f"theme-park-race-board-review|{submission}|{revision}|{mapped}",
        })

    def set_theme_park_race_mission_operation(self, event_id, activity_id, operational_status, secret_state, actor):
        return self._rpc("exos_v2_theme_park_race_board_set_mission_operation", {
            "p_event_id": event_id,
            "p_activity_id": activity_id,
            "p_operational_status": operational_status,
            "p_secret_state": secret_state,
            "p_actor": actor,
        })

    def theme_park_race_facilitator_workspace(self, event_id):
        event = self.get_event(event_id)
        if not event or not self.is_theme_park_race_event(event):
            raise RuntimeDatabaseError("Event is not configured for Theme Park Race.")
        return theme_park_race_facilitator_projection(
            event=event,
            teams=self.get_teams(event_id),
            participants=self.get_theme_park_race_players(event_id),
            stations=self.get_theme_park_race_stations(event_id),
            submissions=self.get_submissions(event_id),
            leaderboard=self.get_canonical_leaderboard(event_id),
            mission_runtime=self.get_theme_park_race_mission_runtime(event_id),
        )

    def can_participant_submit(self, session_token):
        return {"Allowed": bool(self.get_player_by_token(session_token)), "Reason": "REGISTERED_PARTICIPANT"}

    def assign_ai_facilitator(self, team_name):
        return {}

    @staticmethod
    def _participant_country(status):
        return ""

    def audit_participant_duplicates(self, event_id):
        return {"EventID": event_id, "DuplicateGroups": []}

    def identity_migration_audit(self, event_id):
        return {"EventID": event_id, "DuplicateGroups": 0, "CoreV2": True}

    # Programme configuration ---------------------------------------------
    def get_programme_stages(self, event_id):
        return self._client.get_programme_hierarchy(event_id)

    # Control Centre review helpers historically call through ``db.runtime``.
    # On the Standard adapter that facade is this same guarded Core v2 object.
    get_programme_hierarchy = get_programme_stages

    def _safe_save_programme(self, event_id, modules, programme_name=""):
        event = self.get_event(event_id)
        if not event:
            raise RuntimeDatabaseError(f"Event {event_id} is not in Core v2.")
        programme_id = f"{event_id}-PROGRAMME"
        existing_programme = self._one("programmes_v2", {"programme_id": f"eq.{programme_id}", "select": "programme_id"})
        programme_row = {
            "event_id": event_id, "programme_name": programme_name or event["EventName"],
            "programme_type": event["ProgrammeType"], "programme_schema_version": 2,
            "module_count": len(modules), "is_active": True, "published_at": _now(), "updated_at": _now(),
        }
        if existing_programme:
            self._request("PATCH", "programmes_v2", payload=programme_row, query={"programme_id": f"eq.{programme_id}"})
        else:
            self._request("POST", "programmes_v2", payload={"programme_id": programme_id, **programme_row})

        old_modules = self._rows("modules_v2", {"programme_id": f"eq.{programme_id}", "select": "module_id"})
        old_activities = self._rows("activities_v2", {"programme_id": f"eq.{programme_id}", "select": "activity_id,module_id,activity_order"})
        for row in old_activities:
            self._request("PATCH", "activities_v2", payload={"activity_order": 50000 + int(row.get("activity_order", 0) or 0)},
                          query={"activity_id": f"eq.{row['activity_id']}"})

        expected_modules, expected_activities = set(), set()
        activity_count = 0
        for module_position, module in enumerate(modules, 1):
            module = dict(module)
            module_id = str(module.get("ModuleID") or f"{programme_id}-MOD-{module_position:03d}")
            expected_modules.add(module_id)
            module_payload = self._client._normalise_module_payload({**module, "ModuleOrder": module_position})
            module_row = {
                "programme_id": programme_id, "module_name": module_payload["module_name"],
                "activity_sequence": module_position, "module_payload": module_payload["module_payload"],
                "is_active": True, "updated_at": _now(),
            }
            exists = any(r["module_id"] == module_id for r in old_modules)
            self._request("PATCH" if exists else "POST", "modules_v2",
                          payload=module_row if exists else {"module_id": module_id, **module_row},
                          query={"module_id": f"eq.{module_id}"} if exists else None)
            for activity_position, activity in enumerate(module.get("Activities", []), 1):
                activity = dict(activity)
                activity_id = str(activity.get("ActivityID") or f"{module_id}-ACT-{activity_position:03d}")
                expected_activities.add(activity_id)
                normal = self._client._normalise_activity_payload(event_id, {**module, "ModuleID": module_id}, {
                    **activity, "ActivityID": activity_id, "ProgrammeID": programme_id,
                    "ModuleID": module_id, "ActivityOrder": activity_position,
                })
                row = {key: normal[key] for key in (
                    "programme_id", "module_id", "activity_type", "scoring_mode", "activity_name",
                    "activity_order", "duration_seconds", "activity_payload", "is_active",
                )}
                row["updated_at"] = _now()
                exists = any(r["activity_id"] == activity_id for r in old_activities)
                self._request("PATCH" if exists else "POST", "activities_v2",
                              payload=row if exists else {"activity_id": activity_id, **row},
                              query={"activity_id": f"eq.{activity_id}"} if exists else None)
                activity_count += 1

        for row in old_activities:
            if row["activity_id"] not in expected_activities:
                self._request("PATCH", "activities_v2", payload={"is_active": False},
                              query={"activity_id": f"eq.{row['activity_id']}"})
        for row in old_modules:
            if row["module_id"] not in expected_modules:
                self._request("PATCH", "modules_v2", payload={"is_active": False},
                              query={"module_id": f"eq.{row['module_id']}"})
        return {"ProgrammeID": programme_id, "EventID": event_id,
                "ModuleCount": len(expected_modules), "ActivityCount": activity_count}

    def save_programme_stages(self, event_id, stages):
        return self._safe_save_programme(event_id, build_programme_hierarchy(stages))

    def duplicate_programme_configuration(self, source_event_id, destination_event_id):
        source = self.get_programme_stages(source_event_id)
        if not source:
            raise ValueError("The source event has no programme configuration.")
        cloned, _ = clone_programme_stages(source, source_event_id, destination_event_id)
        result = self.save_programme_stages(destination_event_id, cloned)
        return {**result, "OperationalDataCopied": False, "RuntimeLaunched": False,
                "SourceEventID": source_event_id, "DestinationEventID": destination_event_id}

    def get_event_missions(self, event_id, include_closed=False):
        return [self._activity_as_mission(row) for row in self.get_programme_stages(event_id)]

    def get_mission(self, event_id, mission_id):
        return next((m for m in self.get_event_missions(event_id) if m["MissionID"] == mission_id), None)

    @staticmethod
    def _activity_as_mission(row):
        return {"EventID": row.get("EventID", ""), "MissionID": row.get("ActivityID", ""),
                "Title": row.get("StageName", ""), "Description": row.get("ParticipantMessage", ""),
                "ParticipantInstructions": row.get("ParticipantMessage", ""),
                "SubmissionType": str(row.get("StageName", "")).upper().replace(" ", ""), "Status": "ACTIVE"}

    def get_mission_templates(self): return []
    def get_programme_packs(self): return []
    def get_programme_pack(self, *args, **kwargs): return None
    def get_experience_sets(self, event_id): return []
    def get_assets(self, *args, **kwargs): return []
    def get_character_portrait(self, *args, **kwargs): return None
    def upsert_event_mission(self, mission): return mission
    def build_event_programme(self, *args, **kwargs): raise RuntimeDatabaseError("Use the canonical Programme Builder.")
    def clear_cache(self): return None

    # Live activity state --------------------------------------------------
    def set_event_stage(self, event_id, stage):
        content_type = str(
            stage.get("ContentType", "")
            or activity_details(stage).get("ContentType", "")
        ).strip()
        if content_type.casefold() == "break":
            raise RuntimeDatabaseError(
                "Lunch / Break is a programme marker and cannot be launched."
            )
        activity_id = str(stage.get("ActivityID") or stage.get("ProgrammeActivityID") or "")
        if not activity_id:
            raise RuntimeDatabaseError("A canonical ActivityID is required for launch.")
        return self._rpc("exos_v2_standard_launch_activity", {
            "p_event_id": event_id, "p_activity_id": activity_id, "p_actor": "Facilitator",
        })

    def get_event_state(self, event_id):
        event = self.get_event(event_id)
        return _dict(self.event_metadata(event).get("live_state"))

    def get_event_stage(self, event_id): return self.get_event_state(event_id)

    def get_runtime_control_state(self, event_id):
        event = self.get_event(event_id)
        return _dict(self.event_metadata(event).get("control_state"))

    def set_runtime_control_state(self, event_id, key, value):
        return self.update_event_metadata(event_id, {key: value})

    def get_broadcast_state(self, event_id):
        return _dict(self.get_runtime_control_state(event_id).get("ProjectorBroadcast"))

    def get_stage_timer(self, event_id, stage_no, duration_minutes=0):
        timers = _dict(self.get_runtime_control_state(event_id).get("StageTimers"))
        return _dict(timers.get(str(stage_no))) or new_timer(int(float(duration_minutes or 0) * 60))

    def update_stage_timer(self, event_id, stage_no, action, duration_minutes=0):
        state = self.get_runtime_control_state(event_id)
        timers = _dict(state.get("StageTimers"))
        key = str(stage_no)
        timers[key] = transition_timer(timers.get(key) or new_timer(int(float(duration_minutes or 0) * 60)),
                                       action, duration_seconds=int(float(duration_minutes or 0) * 60))
        self.update_event_metadata(event_id, {"StageTimers": timers})
        return timers[key]

    def get_participant_current_mission(self, session_token):
        return self.get_player_by_token(session_token)

    def get_current_mission(self, event_id, session_token=""):
        state = self.get_player_by_token(session_token) if session_token else {"Stage": self.get_event_state(event_id)}
        stage = _dict((state or {}).get("Stage"))
        if not stage:
            return None
        mission = {"MissionID": stage.get("ActivityID", ""), "Title": stage.get("StageName", ""),
                   "Description": stage.get("ParticipantMessage", ""),
                   "ParticipantInstructions": stage.get("ParticipantMessage", ""),
                   "SubmissionType": _dict(stage.get("ActivityPayload")).get("submission_type", ""),
                   "_RuntimeStage": stage}
        return mission

    # Submissions, reviews and results -------------------------------------
    @staticmethod
    def _submission(row):
        payload = _dict(row.get("submission_payload"))
        return {
            "SubmissionID": str(row.get("submission_id", "")), "EventID": row.get("event_id", ""),
            "TeamID": row.get("team_id", ""), "ParticipantID": str(row.get("participant_id", "")),
            "MissionID": row.get("activity_id", ""), "ActivityID": row.get("activity_id", ""),
            "TeamName": payload.get("TeamName", row.get("team_id", "")),
            "ParticipantName": payload.get("ParticipantName", ""),
            "SubmissionType": payload.get("SubmissionType", ""), "Metric1": payload.get("Metric1", ""),
            "Metric2": payload.get("Metric2", ""), "Metric3": payload.get("Metric3", ""),
            "Remarks": payload.get("Remarks", ""), "ImageURL": payload.get("ImageURL", ""),
            "DriveFileID": payload.get("DriveFileID", ""), "Status": row.get("submission_status", "SUBMITTED"),
            "Score": row.get("score", ""), "Judged": "Yes" if row.get("reviewed_at") else "No",
            "SubmittedAt": row.get("submitted_at", ""),
            "RideEvidencePathway": payload.get("RideEvidencePathway", ""),
            "RideAttemptStatus": payload.get("RideAttemptStatus", ""),
            "RiderParticipantIDs": list(payload.get("RiderParticipantIDs", [])) if isinstance(payload.get("RiderParticipantIDs"), list) else [],
            "GroundControlParticipantIDs": list(payload.get("GroundControlParticipantIDs", [])) if isinstance(payload.get("GroundControlParticipantIDs"), list) else [],
            "QueueEntryEvidence": payload.get("QueueEntryEvidence", ""),
            "PostRideEvidence": payload.get("PostRideEvidence", ""),
            "FacilitatorVerificationRequest": payload.get("FacilitatorVerificationRequest", ""),
            "CanonicalTeamMemberCount": payload.get("CanonicalTeamMemberCount", ""),
            "RequiredRideParticipants": payload.get("RequiredRideParticipants", ""),
        }

    def get_submissions(self, event_id):
        return [self._submission(r) for r in self._rows("submissions_v2", {
            "event_id": f"eq.{event_id}",
            "select": "submission_id,event_id,team_id,participant_id,activity_id,submission_status,submission_payload,submitted_at,reviewed_at,reviewed_by,score",
            "order": "submitted_at.desc",
        })]

    get_canonical_submissions = get_submissions
    get_event_submissions = get_submissions

    def get_team_submission(self, event_id, mission_id, team_name):
        teams = {t["TeamName"]: t["TeamID"] for t in self.get_teams(event_id)}
        team_id = teams.get(team_name, team_name)
        return next((r for r in self.get_submissions(event_id)
                     if r["ActivityID"] == mission_id and r["TeamID"] == team_id), None)

    def get_participant_submission(self, event_id, mission_id, participant_name, session_token=""):
        player = self.get_player_by_token(session_token) if session_token else self.get_player(event_id, participant_name)
        participant_id = str((player or {}).get("ParticipantID", ""))
        return next((r for r in self.get_submissions(event_id)
                     if r["ActivityID"] == mission_id and r["ParticipantID"] == participant_id), None)

    def save_submission(self, submission_id="", event_id="", mission_id="", team_name="",
                        participant_name="", image_url="", drive_file_id="", submitted_at="",
                        score="", judged="No", remarks="", submission_type="", metric1="",
                        metric2="", metric3="", status="PENDING", session_token="", canonical_context=None, **kwargs):
        player = self.get_player_by_token(session_token)
        if not player:
            raise RuntimeDatabaseError("Participant session is required.")
        activity = self._one("activities_v2", {"activity_id": f"eq.{mission_id}", "select": "activity_payload", "limit": "1"})
        scope = str(_dict(activity.get("activity_payload")).get("participant_scope", "TEAM")).upper()
        owner = player["ParticipantID"] if scope == "INDIVIDUAL" or submission_type.upper() == "NASI" else player["TeamID"]
        key = f"{event_id}|{mission_id}|{owner}"
        payload = {
            "TeamName": team_name, "ParticipantName": participant_name, "SubmissionType": submission_type,
            "Metric1": metric1, "Metric2": metric2, "Metric3": metric3, "Remarks": remarks,
            "ImageURL": image_url, "DriveFileID": drive_file_id, "CanonicalContext": canonical_context or {},
        }
        result = self._rpc("exos_v2_standard_submit", {
            "p_session_token": session_token, "p_activity_id": mission_id,
            "p_submission_key": key, "p_submission_payload": payload,
        }, admin=False)
        return result

    def update_submission_score(self, submission_id, score, remarks="", judged="Yes", status="APPROVED"):
        decision = "APPROVE" if str(status).upper() == "APPROVED" else "REJECT"
        return self._rpc("exos_v2_standard_review_submission", {
            "p_submission_id": submission_id, "p_decision": decision, "p_score": float(score or 0),
            "p_reviewer": "Facilitator", "p_rationale": remarks,
            "p_idempotency_key": f"standard-review|{submission_id}",
        })

    def decide_canonical_submission(self, submission_id, decision, reviewer_id, score=0, credits=0,
                                    notes="", reason="", idempotency_key="", supersedes_id=""):
        requested = str(decision).upper()
        mapped = (
            "APPROVE" if requested in {"APPROVE", "APPROVED"}
            else "PENDING" if requested in {"PENDING", "RETURN_FOR_REVISION"}
            else "REJECT"
        )
        return self._rpc("exos_v2_standard_review_submission", {
            "p_submission_id": submission_id, "p_decision": mapped, "p_score": float(score or 0),
            "p_reviewer": reviewer_id, "p_rationale": notes or reason,
            "p_idempotency_key": idempotency_key or f"standard-review|{submission_id}",
        })

    def get_canonical_reviews(self, event_id, submission_id=""):
        query = {"event_id": f"eq.{event_id}", "select": "review_id,event_id,submission_id,reviewer,decision,score_points,rationale,reviewed_at"}
        if submission_id: query["submission_id"] = f"eq.{submission_id}"
        return self._rows("reviews_v2", query)

    def get_canonical_leaderboard(self, event_id):
        teams = {t["TeamID"]: t["TeamName"] for t in self.get_teams(event_id)}
        totals = {team_id: 0.0 for team_id in teams}
        for row in self._rows("score_transactions_v2", {
            "event_id": f"eq.{event_id}", "scoring_mode": "eq.TEAM_COMPETITIVE",
            "select": "team_id,score_delta",
        }):
            totals[row["team_id"]] = totals.get(row["team_id"], 0.0) + float(row.get("score_delta", 0) or 0)
        return [{"TeamID": team_id, "TeamName": teams.get(team_id, team_id), "Score": score}
                for team_id, score in sorted(totals.items(), key=lambda item: (-item[1], item[0]))]

    def get_canonical_transaction_report(self, event_id):
        return {"Leaderboard": self.get_canonical_leaderboard(event_id),
                "Submissions": self.get_submissions(event_id),
                "Reviews": self.get_canonical_reviews(event_id)}

    # Optional standard-screen compatibility ------------------------------
    def get_conversation(self, *args, **kwargs): return []
    def save_conversation(self, *args, **kwargs): return None
    def get_ai_conversation(self, *args, **kwargs): return []
    def advance_ai_hint(self, *args, **kwargs): return {}
    def claim_team_tracker(self, *args, **kwargs): return {}
    def submit_team_location(self, *args, **kwargs): return {}
    def get_road_hunt_participant_state(self, *args, **kwargs): return {}
    def get_road_hunt_unlocked_missions(self, *args, **kwargs):
        return {
            "Enabled": False,
            "AvailableMissions": [],
            "TotalMissions": 0,
            "UnlockedMissions": 0,
            "SubmittedMissions": 0,
        }
    def get_team_wallet(self, *args, **kwargs): return {"Enabled": False, "Balance": 0, "Items": []}
    def purchase_marketplace_item(self, *args, **kwargs):
        raise RuntimeDatabaseError("No marketplace is configured for this standard programme.")
    def set_submission_override(self, *args, **kwargs): return {}
    def set_scoring_lock(self, *args, **kwargs): return {}
    def activate_experience_set(self, *args, **kwargs): return {"ExperiencesPublished": 0}
    def publish_event_to_runtime(self, event_id, reset=False): return self.get_event(event_id)
    def assign_ai_facilitator(self, team_name): return {}
    def get_participant_count_warning(self, *args, **kwargs): return ""
    def ensure_existing_assets_catalogue(self, *args, **kwargs): return []
    def get_formula_race_checkpoints(self, *args, **kwargs):
        raise RuntimeDatabaseError("Formula R.A.C.E. uses its dedicated Core v2 application.")
    def save_formula_race_checkpoints(self, *args, **kwargs):
        raise RuntimeDatabaseError("Formula R.A.C.E. uses its dedicated Core v2 application.")
    def join_preassigned_player(self, *args, **kwargs):
        raise RuntimeDatabaseError("Preassigned R.A.C.E. identity is not part of the standard application.")
    def install_programme_pack(self, *args, **kwargs):
        raise RuntimeDatabaseError("Use Template or Duplicate Existing Programme in the canonical builder.")
    def save_event_as_programme_pack(self, *args, **kwargs):
        raise RuntimeDatabaseError("Use Duplicate Existing Programme for Core v2 reuse.")
    def launch_event_mission(self, *args, **kwargs):
        raise RuntimeDatabaseError("Launch the canonical programme activity from Control Centre.")
    def send_mission(self, *args, **kwargs):
        raise RuntimeDatabaseError("Launch the canonical programme activity from Control Centre.")


def get_standard_database(runtime=None):
    return StandardCoreV2Adapter(runtime=runtime)
