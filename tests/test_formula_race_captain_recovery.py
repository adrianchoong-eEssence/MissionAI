import os
import uuid
from contextlib import contextmanager
from pathlib import Path

from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter


RECOVERY_SQL = (Path(__file__).resolve().parents[1] / "supabase" / "024_exos_core_v2_team_access_recovery.sql").read_text()


@contextmanager
def _staging_env():
    original = os.getenv("EXOS_ENV")
    os.environ["EXOS_ENV"] = "staging"
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("EXOS_ENV", None)
        else:
            os.environ["EXOS_ENV"] = original


class _Runtime:
    is_configured = True
    can_publish = True
    url = "https://staging.exos-core-v2.example.com"

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def _request(self, method, path, payload=None, query=None, admin=True):
        self.calls.append((method, path, payload, query, admin))
        return self.responses.pop(0)


def test_different_device_login_returns_recovery_state_without_token_error():
    runtime = _Runtime([{
        "EventID": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
        "TeamID": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F",
        "Ambiguous": False,
        "RecoveryRequired": True,
        "SessionToken": None,
    }])
    with _staging_env():
        payload = FormulaRaceCoreV2StagingAdapter(runtime).formula_race_captain_login(
            "RACE4CF0CE", "CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "PIN-01", "DEVICE-B"
        )
    assert payload["RecoveryRequired"] is True
    assert payload["SessionToken"] == ""


def test_fresh_login_and_same_device_restore_keep_the_valid_session_token():
    token = str(uuid.uuid4())
    runtime = _Runtime([
        {
            "EventID": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
            "TeamID": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F",
            "Ambiguous": False,
            "RecoveryRequired": False,
            "SessionToken": token,
        },
        {
            "EventID": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
            "TeamID": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F",
            "Ambiguous": False,
            "RecoveryRequired": False,
        },
    ])
    with _staging_env():
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)
        login = adapter.formula_race_captain_login(
            "RACE4CF0CE", "CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "PIN-01", "DEVICE-A"
        )
        restored = adapter.restore_formula_race_captain(login["SessionToken"], "DEVICE-A")
    assert login["SessionToken"] == token
    assert restored["SessionToken"] == token
    assert restored["TeamID"] == login["TeamID"]


def test_recovery_returns_a_valid_new_session_for_the_same_team():
    token = str(uuid.uuid4())
    runtime = _Runtime([{
        "EventID": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
        "TeamID": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F",
        "SessionToken": token,
    }])
    with _staging_env():
        payload = FormulaRaceCoreV2StagingAdapter(runtime).formula_race_captain_recover(
            "RACE4CF0CE", "CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "PIN-01", "DEVICE-B"
        )
    assert payload["SessionToken"] == token
    assert payload["TeamID"] == "CORE-V2-RACE-UAT-T01-4CF0CEAF5F"
    assert runtime.calls[0][1] == "rpc/exos_v2_recover_team_access"


def test_checkpoint_submission_accepts_text_activity_id_and_bootstraps_captain_identity():
    token = str(uuid.uuid4())
    participant_id = str(uuid.uuid4())
    submission_id = str(uuid.uuid4())
    runtime = _Runtime([
        [{"event_id": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F", "team_id": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F"}],
        [],
        [{"join_code": "RACE4CF0CE"}],
        {"ParticipantID": participant_id, "TeamID": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F"},
        {"submission_id": submission_id},
        {},
    ])
    with _staging_env():
        result = FormulaRaceCoreV2StagingAdapter(runtime).formula_race_submit_checkpoint(
            token,
            "DEVICE-B",
            "CORE-V2-RACE-UAT-CP-01-4CF0CEAF5F",
            "checkpoint proof",
            "",
            "submission-key",
        )
    assert result["SubmissionID"] == submission_id
    assert runtime.calls[3][1] == "rpc/exos_v2_join_event_v2"
    assert runtime.calls[4][2]["activity_id"] == "CORE-V2-RACE-UAT-CP-01-4CF0CEAF5F"


def test_recovery_sql_deactivates_old_session_and_records_the_takeover():
    assert "create or replace function public.exos_v2_recover_team_access" in RECOVERY_SQL
    assert "set is_active = false" in RECOVERY_SQL
    assert "takeover_by_session_id" in RECOVERY_SQL
    assert "TEAM_ACCESS_RECOVERED" in RECOVERY_SQL
    assert "insert into public.teams_v2" not in RECOVERY_SQL
    assert "delete from public." not in RECOVERY_SQL
    assert "raise exception 'Invalid PIN'" in RECOVERY_SQL
