import os
import uuid
from contextlib import contextmanager

import screens.formula_race_captain as captain_screen
from data.formula_race_core_v2_adapter import FormulaRaceCoreV2StagingAdapter


def test_query_token_normalization_blocks_none_null_and_empty():
    assert captain_screen._normalise_session_token(None) == ""
    assert captain_screen._normalise_session_token("None") == ""
    assert captain_screen._normalise_session_token("null") == ""
    assert captain_screen._normalise_session_token("") == ""
    assert captain_screen._normalise_session_token("not-a-token") == ""
    valid = str(uuid.uuid4())
    assert captain_screen._normalise_session_token(valid) == valid


def test_team_options_fall_back_to_team_name_when_identity_is_blank():
    rows = [
        {
            "TeamID": f"CORE-V2-RACE-UAT-T{number:02d}-4CF0CEAF5F",
            "TeamIdentity": "" if number == 1 else None,
            "TeamName": "SANDSTORM" if number == 1 else f"TEAM {number:02d}",
            "IsActive": True,
        }
        for number in range(1, 11)
    ]

    options = captain_screen._team_options(rows)

    assert len(options) == 10
    assert options["SANDSTORM"] == "CORE-V2-RACE-UAT-T01-4CF0CEAF5F"


class _Query(dict):
    def pop(self, key, default=None):
        return super().pop(key, default)


def test_set_session_only_writes_valid_captain_token():
    class _FakeStreamlit:
        session_state: dict
        query_params: _Query

        def __init__(self):
            self.session_state = {}
            self.query_params = _Query()

    fake_st = _FakeStreamlit()
    original_st = captain_screen.st
    captain_screen.st = fake_st
    try:
        payload = {"SessionToken": "None", "EventID": "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F", "TeamID": "CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "TeamName": "SANDSTORM"}
        try:
            captain_screen._set_session(payload)
            assert False, "Invalid Captain token must not create a session."
        except RuntimeError:
            pass
        assert fake_st.session_state.get("race_captain") is None
        assert "captain_session" not in fake_st.query_params

        valid = str(uuid.uuid4())
        captain_screen._set_session({**payload, "SessionToken": valid})
        assert fake_st.query_params.get("captain_session") == valid
        assert fake_st.query_params.get("race") == "1"
    finally:
        captain_screen.st = original_st


def test_device_id_persists_across_a_new_streamlit_session():
    class _FakeStreamlit:
        def __init__(self):
            self.session_state = {}
            self.query_params = _Query()

    fake_st = _FakeStreamlit()
    original_st = captain_screen.st
    captain_screen.st = fake_st
    try:
        first = captain_screen._device_id()
        assert fake_st.query_params["captain_device"] == first
        fake_st.session_state.clear()
        assert captain_screen._device_id() == first
    finally:
        captain_screen.st = original_st


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


def test_formula_race_restore_rejects_invalid_session_token_before_rpc_call():
    class FakeRuntime:
        is_configured = True
        can_publish = True
        url = "https://staging.exos-core-v2.example.com"

        def __init__(self):
            self.calls = 0

        def _request(self, *args, **kwargs):
            self.calls += 1
            return {}

    runtime = FakeRuntime()
    with _staging_env():
        adapter = FormulaRaceCoreV2StagingAdapter(runtime)

    for token in ("None", "null", "", "not-a-uuid", "123"):
        try:
            adapter.restore_formula_race_captain(token, "DEVICE")
            assert False, f"Expected invalid token {token}"
        except Exception:
            pass
    assert runtime.calls == 0


def test_formula_race_login_rejects_missing_session_token():
    class FakeRuntime:
        is_configured = True
        can_publish = True
        url = "https://staging.exos-core-v2.example.com"

        def _request(self, method, path, payload=None, query=None, admin=True):
            return {"session_token": "None"}

    with _staging_env():
        adapter = FormulaRaceCoreV2StagingAdapter(FakeRuntime())

    try:
        adapter.formula_race_captain_login("RACE4CF0CE", "CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "PIN-01", "DEVICE")
        assert False
    except Exception:
        pass
