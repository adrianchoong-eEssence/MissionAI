import re
from pathlib import Path

import pytest

from scripts.prepare_maxis_personal_key_uat import (
    EVENT_ID,
    EXPECTED_COUNTS,
    build_certification_sql,
    build_setup_sql,
    load_authoritative_roster,
)
from services.personal_key_credentials import (
    derive_personal_key_credential,
    normalize_personal_key,
    team_formation_credential_hash,
)


WORKBOOK = Path("/Users/adrian/Desktop/Maxis_Mission_AI_Personal_Key_Checkin_Master.xlsx")


def test_personal_key_normalization_is_narrow_and_does_not_autocorrect():
    assert normalize_personal_key(" tmBhMb \n") == "TMBHMB"
    for invalid in ("TMBHM", "TMBHMB7", "TMB MB", "TMB-MB", "TMBH!B", ""):
        with pytest.raises(ValueError):
            normalize_personal_key(invalid)


def test_event_scoped_derivation_is_deterministic_opaque_and_contract_valid():
    first = derive_personal_key_credential(EVENT_ID, "TMBHMB")
    repeat = derive_personal_key_credential(EVENT_ID.lower(), " tmbhmb ")
    other_event = derive_personal_key_credential("MAXIS-UAT-OTHER", "TMBHMB")
    assert first == repeat
    assert first != other_event
    assert first != "TMBHMB"
    assert len(first) == 43
    assert re.fullmatch(r"[A-Za-z0-9_-]{43,128}", first)
    assert re.fullmatch(r"[0-9a-f]{64}", team_formation_credential_hash(first))


@pytest.mark.skipif(not WORKBOOK.exists(), reason="authoritative Maxis workbook is not present")
def test_authoritative_68_person_workbook_and_generated_package_contract():
    roster = load_authoritative_roster(WORKBOOK)
    assert len(roster) == 68
    assert {team: sum(member.team_number == team for member in roster) for team in EXPECTED_COUNTS} == EXPECTED_COUNTS
    assert len({member.personal_key for member in roster}) == 68
    assert all(len(member.personal_key) == 6 for member in roster)
    assert len({member.derived_credential for member in roster}) == 68
    assert all(43 <= len(member.derived_credential) <= 128 for member in roster)
    setup_sql = build_setup_sql(roster)
    certification_sql = build_certification_sql(roster)
    assert all(member.personal_key not in setup_sql for member in roster)
    assert all(member.personal_key not in certification_sql for member in roster)
    assert all(member.derived_credential not in setup_sql for member in roster)
    assert "EnrollmentCredentialHash" in setup_sql
    assert "PREASSIGNED" in setup_sql
    assert "REGISTRATION_OPEN" in setup_sql
    assert "set local role anon;" in certification_sql
    assert "Anonymous RPC execution/identity assertion failed" in certification_sql
    assert certification_sql.rstrip().endswith("rollback;")


def test_login_and_reveal_sources_never_log_or_query_raw_or_derived_credentials():
    root = Path(__file__).resolve().parents[1]
    screen = (root / "screens" / "maxis_personal_key.py").read_text(encoding="utf-8")
    assert "derive_personal_key_credential(EVENT_ID, personal_key)" in screen
    assert "p_enrollment_credential" not in screen
    assert "st.write(personal_key" not in screen
    assert "st.write(derived_credential" not in screen
    assert '"personal_key": "1"' in screen  # URL mode flag, never the entered key.
    assert "get_team_roster" not in screen
    assert "TeamMembers" not in screen
