"""Source-contract and reference-model tests for EXOS Team Formation V1.

The reference model makes the required concurrency outcomes executable without
claiming that a PostgreSQL staging or load test has run. The optional psql test
is deliberately skipped unless an explicit local POSTGRES_TEST_DSN is supplied.
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from random import Random
from shutil import which
import os
import subprocess
import threading

import pytest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/036_exos_core_v2_team_formation_v1.sql"
ROLLBACK = ROOT / "supabase/036_exos_core_v2_team_formation_v1_rollback.sql"
VERIFY = ROOT / "supabase/verification/exos_core_v2_team_formation_v1_verify.sql"
RESULT_CONTRACT = ROOT / "supabase/035_formula_race_result_status_and_placement.sql"
SQL = MIGRATION.read_text()


def opaque_credential(label):
    """Deterministic test stand-in for base64url(32 CSPRNG bytes)."""
    return sha256(f"team-formation-test:{label}".encode()).hexdigest()[:43]


def credential_hash(credential):
    if not credential or len(credential) < 43:
        raise RuntimeError("TEAM_FORMATION_RECOVERY_CREDENTIAL_INVALID")
    return sha256(credential.encode()).hexdigest()


class TeamFormationReference:
    """Small executable specification; it is not an application implementation."""

    def __init__(self, event_id, capacities, *, seed=1):
        self.event_id = event_id
        self.capacities = dict(capacities)
        self._members = {}
        self._sessions = {}
        self._captains = {}
        self._serial = 0
        self._random = Random(seed)
        self._lock = threading.Lock()

    def register_random(self, display_name, enrollment_credential, device_id):
        with self._lock:
            enrollment_credential_hash = credential_hash(enrollment_credential)
            existing = self._members.get(enrollment_credential_hash)
            if existing:
                participant_id, team_id = existing
                if self._sessions.get(participant_id) == device_id:
                    return {
                        "ParticipantID": participant_id,
                        "TeamID": team_id,
                        "Idempotent": True,
                    }
                return {
                    "ParticipantID": participant_id,
                    "TeamID": team_id,
                    "RecoveryRequired": True,
                }

            occupancy = Counter(team_id for _, team_id in self._members.values())
            eligible = [
                team_id for team_id, capacity in self.capacities.items()
                if occupancy[team_id] < capacity
            ]
            if not eligible:
                raise RuntimeError("EVENT_FULL")
            floor = min(occupancy[team_id] for team_id in eligible)
            team_id = self._random.choice(
                [team_id for team_id in eligible if occupancy[team_id] == floor]
            )
            self._serial += 1
            participant_id = f"{self.event_id}-P-{self._serial:03d}"
            self._members[enrollment_credential_hash] = (participant_id, team_id)
            self._sessions[participant_id] = device_id
            return {
                "ParticipantID": participant_id,
                "TeamID": team_id,
                "Idempotent": False,
            }

    def provision_preassigned(self, roster):
        with self._lock:
            if self._members:
                raise RuntimeError("preassignment must precede registration")
            seen = set()
            for enrollment_credential, team_id in roster:
                enrollment_credential_hash = credential_hash(enrollment_credential)
                if enrollment_credential_hash in seen or team_id not in self.capacities:
                    raise RuntimeError("invalid roster")
                seen.add(enrollment_credential_hash)
            counts = Counter(team_id for _, team_id in roster)
            if any(counts[team_id] > self.capacities[team_id] for team_id in counts):
                raise RuntimeError("capacity exceeded")
            for enrollment_credential, team_id in roster:
                self._serial += 1
                self._members[credential_hash(enrollment_credential)] = (
                    f"{self.event_id}-P-{self._serial:03d}", team_id
                )

    def claim_preassigned(self, enrollment_credential, device_id):
        with self._lock:
            participant_id, team_id = self._members[credential_hash(enrollment_credential)]
            existing_device = self._sessions.get(participant_id)
            if existing_device and existing_device != device_id:
                return {
                    "ParticipantID": participant_id,
                    "TeamID": team_id,
                    "RecoveryRequired": True,
                }
            self._sessions[participant_id] = device_id
            return {
                "ParticipantID": participant_id,
                "TeamID": team_id,
                "Idempotent": bool(existing_device),
            }

    def recover(self, enrollment_credential, device_id):
        with self._lock:
            enrollment_credential_hash = credential_hash(enrollment_credential)
            if enrollment_credential_hash not in self._members:
                raise RuntimeError("TEAM_FORMATION_RECOVERY_CREDENTIAL_INVALID")
            participant_id, team_id = self._members[enrollment_credential_hash]
            self._sessions[participant_id] = device_id
            return {"ParticipantID": participant_id, "TeamID": team_id}

    def claim_captain(self, enrollment_credential):
        with self._lock:
            participant_id, team_id = self._members[credential_hash(enrollment_credential)]
            current = self._captains.get(team_id)
            if current and current != participant_id:
                return {"Claimed": False, "CaptainParticipantID": current}
            self._captains[team_id] = participant_id
            return {"Claimed": True, "CaptainParticipantID": participant_id}

    def transfer_captain(self, enrollment_credential):
        with self._lock:
            participant_id, team_id = self._members[credential_hash(enrollment_credential)]
            self._captains[team_id] = participant_id
            return {"Transferred": True, "CaptainParticipantID": participant_id}

    def occupancy(self):
        return Counter(team_id for _, team_id in self._members.values())


def test_migration_is_additive_and_configuration_gated():
    lowered = SQL.lower()
    assert SQL.lstrip().startswith("--")
    assert "begin;" in lowered and SQL.rstrip().endswith("COMMIT;")
    assert "teamformation" in lowered
    assert "'schemaversion', 1" in lowered
    for mode in ("RANDOM_ASSIGN", "PREASSIGNED"):
        assert f"'{mode}'" in SQL
    for phase in (
        "DRAFT", "REGISTRATION_OPEN", "FORMATION_LOCKED",
        "CAPTAIN_SELECTION", "ACTIVE",
    ):
        assert f"'{phase}'" in SQL
    assert "create table public" not in lowered
    assert "delete from public" not in lowered
    assert "drop function if exists public.exos_v2_team_access_login" not in lowered
    assert "drop function if exists public.exos_v2_recover_team_access" not in lowered


def test_integrity_constraints_preserve_existing_models_and_scope_new_writes():
    for fragment in (
        "add column if not exists team_capacity integer",
        "add column if not exists enrollment_credential_hash text",
        "add column if not exists is_team_formation_captain boolean",
        "participants_v2_event_team_tf_fkey",
        "participant_sessions_v2_event_participant_tf_fkey",
        "team_access_credentials_v2_event_team_tf_fkey",
        "team_access_sessions_v2_event_team_tf_fkey",
        "participants_v2_event_enrollment_credential_hash_active_uidx",
        "participants_v2_one_team_formation_captain_uidx",
        "team_access_sessions_v2_one_active_tf_captain_uidx",
        "team formation membership is immutable after assignment",
        "team formation captain session must belong to the effective captain",
    ):
        assert fragment in SQL.lower()
    assert SQL.lower().count("not valid") >= 5


def test_random_assignment_contract_is_server_side_capacity_bounded_and_idempotent():
    function = SQL.split("public.exos_v2_team_formation_register_random", 1)[1].split(
        "public.exos_v2_team_formation_claim_preassigned", 1
    )[0]
    for fragment in (
        "for update",
        "pg_advisory_xact_lock",
        "assigned_count < team_capacity",
        "order by random()",
        "raise exception 'event_full'",
        "on conflict (event_id, idempotency_key) do update",
        "team_formation_random_assign",
        "team_formation_random_assigned",
        "p_enrollment_credential text",
        "exos_v2_team_formation_credential_hash(p_enrollment_credential)",
    ):
        assert fragment in function.lower()
    assert "p_requested_team_id" not in function.lower()
    assert "coalesce(nullif(trim(p_enrollment_credential), ''), p_display_name)" not in function.lower()
    assert "enrollment_key" not in function.lower()


def test_opaque_credential_contract_never_uses_display_name_as_identity_or_secret():
    configure = SQL.split("public.exos_v2_configure_team_formation", 1)[1].split(
        "public.exos_v2_open_team_formation", 1
    )[0]
    claim = SQL.split("public.exos_v2_team_formation_claim_preassigned", 1)[1].split(
        "public.exos_v2_recover_team_formation_participant", 1
    )[0]
    assert "insert into public.participants_v2" in configure.lower()
    assert "'preassigned'" in configure.lower()
    assert "enrollmentcredentialhash" in configure.lower()
    assert "enrollment_key" not in SQL.lower()
    assert "enrollment_credential_hash" in SQL.lower()
    assert "base64url(32 random bytes)" in SQL.lower()
    assert "coalesce(roster.item->>'enrollmentcredentialhash', '')" in configure.lower()
    assert "p_team_id" not in claim.lower()
    assert "p_requested_team_id" not in claim.lower()
    assert "insert into public.participants_v2" not in claim.lower()
    assert "preassigned_enrollment_not_found" in claim.lower()

    participant_recovery = SQL.split(
        "public.exos_v2_recover_team_formation_participant", 1
    )[1].split("public.exos_v2_claim_team_formation_captain", 1)[0]
    assert "p_display_name" not in participant_recovery.lower()
    assert "team_formation_recovery_credential_invalid" in participant_recovery.lower()


def test_security_definer_team_formation_surface_is_narrow_and_search_path_pinned():
    lowered = SQL.lower()
    assert "set search_path = public" not in lowered
    assert lowered.count("security definer") == lowered.count(
        "security definer\nset search_path = ''"
    )
    assert "revoke all on function public.exos_v2_team_formation_credential_hash(text) from public" in lowered
    for function_name in (
        "exos_v2_configure_team_formation",
        "exos_v2_open_team_formation",
        "exos_v2_lock_team_formation",
        "exos_v2_open_team_captain_selection",
        "exos_v2_activate_team_formation",
        "exos_v2_transfer_team_formation_captain",
    ):
        assert f"grant execute on function public.{function_name}" in lowered
    assert "to service_role;" in lowered
    assert "grant execute on function public.exos_v2_team_formation_register_random" in lowered
    assert "to anon, authenticated, service_role;" in lowered


def test_captain_contract_is_participant_bound_audited_and_race_isolated():
    claim = SQL.split("public.exos_v2_claim_team_formation_captain", 1)[1].split(
        "public.exos_v2_recover_team_formation_captain", 1
    )[0]
    recovery = SQL.split("public.exos_v2_recover_team_formation_captain", 1)[1].split(
        "public.exos_v2_transfer_team_formation_captain", 1
    )[0]
    transfer = SQL.split("public.exos_v2_transfer_team_formation_captain", 1)[1]
    for body in (claim, recovery, transfer):
        assert "team_formation_captain_participant_id" in body.lower()
        assert "team_formation_captain" in body.lower()
    assert "captainalreadyclaimed" in claim.lower()
    assert "team_formation_captain_recovery_credential_invalid" in recovery.lower()
    assert "team_formation_captain_transferred" in transfer.lower()
    assert "exos_v2_team_access_login" not in SQL
    assert "exos_v2_recover_team_access" not in SQL
    assert "race4cf0ce" not in SQL.lower()


def test_reference_random_registration_is_idempotent_balanced_and_capacity_safe_at_66():
    model = TeamFormationReference("TF-66", {f"T-{number}": 11 for number in range(6)})
    credentials = [opaque_credential(f"66-{number}") for number in range(66)]

    with ThreadPoolExecutor(max_workers=66) as pool:
        registrations = list(pool.map(
            lambda number: model.register_random(
                f"John Tan {number % 11}", credentials[number], f"device-{number}"
            ),
            range(66),
        ))

    occupancy = model.occupancy()
    assert len({row["ParticipantID"] for row in registrations}) == 66
    assert set(occupancy.values()) == {11}
    assert all(occupancy[team_id] <= 11 for team_id in occupancy)
    repeated = model.register_random("John Tan 7", credentials[7], "device-7")
    assert repeated["Idempotent"] is True
    assert repeated["ParticipantID"] == registrations[7]["ParticipantID"]
    with pytest.raises(RuntimeError, match="EVENT_FULL"):
        model.register_random("John Tan", opaque_credential("66-overflow"), "overflow-device")


def test_reference_random_registration_remains_balanced_at_250_under_concurrency():
    model = TeamFormationReference("TF-250", {f"T-{number:02d}": 10 for number in range(25)})
    credentials = [opaque_credential(f"250-{number}") for number in range(250)]

    with ThreadPoolExecutor(max_workers=100) as pool:
        registrations = list(pool.map(
            lambda number: model.register_random(
                f"John Tan {number % 17}", credentials[number], f"device-{number}"
            ),
            range(250),
        ))

    occupancy = model.occupancy()
    assert len({row["ParticipantID"] for row in registrations}) == 250
    assert min(occupancy.values()) == max(occupancy.values()) == 10
    assert max(occupancy.values()) - min(occupancy.values()) <= 1


def test_reference_duplicate_display_names_are_distinct_and_credential_bound():
    model = TeamFormationReference("TF-DUPLICATE", {"T-1": 2, "T-2": 2})
    first_credential = opaque_credential("john-tan-1")
    second_credential = opaque_credential("john-tan-2")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(
            lambda row: model.register_random("John Tan", row[0], row[1]),
            ((first_credential, "device-one"), (second_credential, "device-two")),
        ))

    assert first["ParticipantID"] != second["ParticipantID"]
    retry = model.register_random("John Tan", first_credential, "device-one")
    assert retry["Idempotent"] is True
    assert retry["ParticipantID"] == first["ParticipantID"]
    assert model.register_random("John Tan", first_credential, "device-three")["RecoveryRequired"] is True
    recovered = model.recover(first_credential, "device-three")
    assert recovered["ParticipantID"] == first["ParticipantID"]
    with pytest.raises(RuntimeError, match="TEAM_FORMATION_RECOVERY_CREDENTIAL_INVALID"):
        model.recover(opaque_credential("wrong-john-tan"), "device-four")
    with pytest.raises(RuntimeError, match="TEAM_FORMATION_RECOVERY_CREDENTIAL_INVALID"):
        model.recover("John Tan", "device-four")


def test_reference_preassigned_claim_recovery_and_cross_event_identity_are_isolated():
    first = TeamFormationReference("TF-A", {"A-1": 2, "A-2": 2})
    second = TeamFormationReference("TF-B", {"B-1": 2, "B-2": 2})
    first_credential = opaque_credential("preassigned-a")
    second_credential = opaque_credential("preassigned-b")
    first.provision_preassigned([(first_credential, "A-1"), (second_credential, "A-2")])

    claim = first.claim_preassigned(first_credential, "device-one")
    recovered = first.recover(first_credential, "device-two")
    other_event = second.register_random("John Tan", first_credential, "device-three")

    assert claim["TeamID"] == recovered["TeamID"] == "A-1"
    assert claim["ParticipantID"] == recovered["ParticipantID"]
    assert other_event["ParticipantID"].startswith("TF-B-")
    assert other_event["TeamID"].startswith("B-")


def test_reference_concurrent_captain_claim_has_one_winner_and_transfer_is_explicit():
    model = TeamFormationReference("TF-CAPTAIN", {"TEAM-1": 4})
    credentials = [opaque_credential(f"captain-{number}") for number in range(4)]
    model.provision_preassigned([(credential, "TEAM-1") for credential in credentials])

    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(model.claim_captain, credentials))

    winners = [row for row in claims if row["Claimed"]]
    assert len(winners) == 1
    transferred = model.transfer_captain(credentials[3])
    assert transferred == {
        "Transferred": True,
        "CaptainParticipantID": "TF-CAPTAIN-P-004",
    }


def test_guarded_rollback_and_read_only_verifier_exist():
    rollback = ROLLBACK.read_text().lower()
    verify = VERIFY.read_text().lower()
    assert "rollback blocked" in rollback
    assert "team formation events exist" in rollback
    assert "enrollment_credential_hash" in rollback
    assert "enrollment_key" not in rollback
    assert "begin read only" in verify
    assert "rollback;" in verify
    assert "insert into" not in verify
    assert "delete from" not in verify
    assert "enrollment_credential_hash" in verify
    assert "search_path_status" in verify
    assert "execute_grantees" in verify
    assert "race4cf0ce" not in verify


def test_035_contract_and_formula_race_migrations_remain_unmodified():
    result = subprocess.run(
        [
            "git", "diff", "--quiet", "bc73d97", "--",
            str(RESULT_CONTRACT),
            "supabase/022_exos_core_v2_team_access.sql",
            "supabase/024_exos_core_v2_team_access_recovery.sql",
            "supabase/027_formula_race_core_v2_atomic_operations.sql",
        ],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0


@pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_DSN") or not which("psql"),
    reason="requires an explicitly supplied local POSTGRES_TEST_DSN and psql",
)
def test_036_executes_after_core_v2_dependencies_on_local_postgres_only():
    """Optional local integration gate; never a staging runner."""
    files = (
        "supabase/020_exos_core_v2_schema.sql",
        "supabase/021_exos_core_v2_pgcrypto_fix.sql",
        "supabase/022_exos_core_v2_team_access.sql",
        "supabase/025_standard_programme_runtime.sql",
        "supabase/026_standard_participant_access_recovery.sql",
        "supabase/036_exos_core_v2_team_formation_v1.sql",
    )
    for path in files:
        proc = subprocess.run(
            [
                "psql", os.environ["POSTGRES_TEST_DSN"],
                "-v", "ON_ERROR_STOP=1", "-f", path,
            ],
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
