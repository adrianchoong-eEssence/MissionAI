import os
import uuid
from contextlib import contextmanager

from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter


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
