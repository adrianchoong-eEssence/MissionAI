"""Deterministic local certification model for hybrid anchored formation.

This module is deliberately not a runtime source of truth. PostgreSQL remains
the canonical allocation authority after the prepared 053 migration is
installed. The model exists to certify the ENCA 134-person arithmetic and to
make the expected invariants executable before any database mutation.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from threading import Lock
from typing import Iterable


class HybridAssignmentError(RuntimeError):
    """A local certification invariant failed."""


def credential_hash(credential: str) -> str:
    return sha256(str(credential).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Anchor:
    name: str
    team_id: str
    credential: str


class HybridAnchoredAssignment:
    """Thread-safe model of the server allocation contract.

    Anchors are provisioned before registration. New general-participant
    credentials receive a team only once, selected from the least-populated
    below-capacity teams, so the pre-existing anchor occupancy is part of every
    choice. A name is presentation data and never a key in this model.
    """

    def __init__(self, *, event_id: str, capacities: dict[str, int], anchors: Iterable[Anchor]):
        self.event_id = str(event_id)
        self.capacities = {str(team_id): int(capacity) for team_id, capacity in capacities.items()}
        if not self.event_id or not self.capacities or any(capacity < 1 for capacity in self.capacities.values()):
            raise HybridAssignmentError("Event and positive team capacities are required.")
        self._lock = Lock()
        self._members: dict[str, dict] = {}
        self._sessions: dict[str, str] = {}
        self._attendance: dict[str, str] = {}
        self._captains: dict[str, str] = {}
        self._next_participant = 0
        self._provision_anchors(list(anchors))

    def _new_participant_id(self) -> str:
        self._next_participant += 1
        return f"{self.event_id}-P-{self._next_participant:03d}"

    def _provision_anchors(self, anchors: list[Anchor]) -> None:
        if len(anchors) != len(self.capacities):
            raise HybridAssignmentError("Each active team requires exactly one HOD anchor.")
        if {anchor.team_id for anchor in anchors} != set(self.capacities):
            raise HybridAssignmentError("HOD anchors must occupy distinct configured teams.")
        hashes = [credential_hash(anchor.credential) for anchor in anchors]
        if len(set(hashes)) != len(hashes):
            raise HybridAssignmentError("HOD Personal Key credentials must be distinct.")
        for anchor, key in zip(anchors, hashes):
            self._members[key] = {
                "ParticipantID": self._new_participant_id(),
                "TeamID": anchor.team_id,
                "Name": anchor.name,
                "AssignmentRole": "HOD_ANCHOR",
            }
            self._attendance[self._members[key]["ParticipantID"]] = "PREASSIGNED"

    def _occupancy(self) -> Counter:
        return Counter(member["TeamID"] for member in self._members.values())

    def _identity(self, member: dict, *, idempotent: bool) -> dict:
        return {
            "EventID": self.event_id,
            "ParticipantID": member["ParticipantID"],
            "TeamID": member["TeamID"],
            "AssignmentRole": member["AssignmentRole"],
            "AttendanceState": self._attendance[member["ParticipantID"]],
            "Idempotent": idempotent,
        }

    def claim_hod(self, credential: str, device_id: str) -> dict:
        """Claim a pre-provisioned HOD once, preserving its assigned country."""
        with self._lock:
            member = self._members.get(credential_hash(credential))
            if not member or member["AssignmentRole"] != "HOD_ANCHOR":
                raise HybridAssignmentError("HOD Personal Key was not recognised.")
            participant_id = member["ParticipantID"]
            existing = self._sessions.get(participant_id)
            if existing and existing != device_id:
                return self._identity(member, idempotent=False) | {"RecoveryRequired": True}
            self._sessions[participant_id] = str(device_id)
            self._attendance[participant_id] = "PRESENT"
            return self._identity(member, idempotent=bool(existing))

    def register_general(self, credential: str, device_id: str, display_name: str) -> dict:
        """Assign a general participant exactly once, using anchored occupancy."""
        del display_name  # Names intentionally do not participate in identity or assignment.
        with self._lock:
            key = credential_hash(credential)
            existing_member = self._members.get(key)
            if existing_member:
                existing = self._sessions.get(existing_member["ParticipantID"])
                if existing and existing != device_id:
                    return self._identity(existing_member, idempotent=False) | {"RecoveryRequired": True}
                self._sessions[existing_member["ParticipantID"]] = str(device_id)
                return self._identity(existing_member, idempotent=True)
            occupancy = self._occupancy()
            eligible = [team_id for team_id, capacity in self.capacities.items() if occupancy[team_id] < capacity]
            if not eligible:
                raise HybridAssignmentError("EVENT_FULL")
            least = min(occupancy[team_id] for team_id in eligible)
            # Stable lexical selection keeps this local certificate reproducible.
            team_id = sorted(team_id for team_id in eligible if occupancy[team_id] == least)[0]
            participant_id = self._new_participant_id()
            member = {
                "ParticipantID": participant_id,
                "TeamID": team_id,
                "AssignmentRole": "GENERAL_PARTICIPANT",
            }
            self._members[key] = member
            self._sessions[participant_id] = str(device_id)
            self._attendance[participant_id] = "PRESENT"
            return self._identity(member, idempotent=False)

    def claim_captain(self, participant_id: str) -> dict:
        with self._lock:
            member = next((row for row in self._members.values() if row["ParticipantID"] == participant_id), None)
            if not member or self._attendance.get(participant_id) != "PRESENT":
                raise HybridAssignmentError("Only a PRESENT canonical team member may be Captain.")
            team_id = member["TeamID"]
            current = self._captains.get(team_id)
            if current and current != participant_id:
                return {"Claimed": False, "CaptainParticipantID": current}
            self._captains[team_id] = participant_id
            return {"Claimed": True, "CaptainParticipantID": participant_id}

    def transfer_captain(self, participant_id: str) -> dict:
        """Facilitator-only transfer model; it deliberately does not prefer an HOD."""
        with self._lock:
            member = next((row for row in self._members.values() if row["ParticipantID"] == participant_id), None)
            if not member or self._attendance.get(participant_id) != "PRESENT":
                raise HybridAssignmentError("Captain transfer requires a PRESENT canonical team member.")
            self._captains[member["TeamID"]] = participant_id
            return {"Transferred": True, "CaptainParticipantID": participant_id}

    @property
    def members(self) -> list[dict]:
        return [dict(member) for member in self._members.values()]

    @property
    def attendance(self) -> dict[str, str]:
        return dict(self._attendance)

    @property
    def captains(self) -> dict[str, str]:
        return dict(self._captains)

    def distribution(self) -> dict[str, int]:
        occupancy = self._occupancy()
        return {team_id: occupancy[team_id] for team_id in sorted(self.capacities)}


def expected_enca_capacities(event_id: str) -> dict[str, int]:
    prefix = str(event_id).strip()
    return {
        f"{prefix}-TEAM-{number:02d}": 14 if number <= 4 else 13
        for number in range(1, 11)
    }
