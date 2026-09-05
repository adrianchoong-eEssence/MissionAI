"""Clean-state contract for the 7 September Maxis live event package."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.prepare_maxis_live_event import (
    DEFAULT_EVENT_ID,
    DEFAULT_JOIN_CODE,
    build_setup_sql,
    load_final_content,
    validate_final_content,
)
from scripts.prepare_maxis_personal_key_uat import load_authoritative_roster


WORKBOOK = Path("/Users/adrian/Desktop/Maxis_Mission_AI_Personal_Key_Checkin_Master.xlsx")


def test_final_content_composes_the_certified_base_and_approved_delta_to_thirteen_missions():
    content = load_final_content()
    validate_final_content(content)
    assert content["PackageKind"] == "THEME_PARK_RACE_FINAL_LIVE_CONTENT"
    assert content["EventID"] == DEFAULT_EVENT_ID
    assert len(content["Missions"]) == 13
    assert sum(row["MissionClass"] == "RIDE" for row in content["Missions"]) == 4
    assert sum(row["MissionClass"] == "SECRET" for row in content["Missions"]) == 3
    names = {row["DisplayName"]: row for row in content["Missions"]}
    assert names["Boot Camp Training"]["Scoring"]["Maximum"] == 150
    assert names["Mannequin Challenge"]["Scoring"]["Maximum"] == 140
    assert names["Mannequin Challenge"]["EvidenceType"] == "PHOTO_OR_VIDEO"
    assert names["Mannequin Challenge"]["Evidence"]["Video"]["MaximumBytes"] == 50 * 1024 * 1024
    assert all(value == {"OperationalStatus": "AVAILABLE", "SecretState": "RELEASED"}
               for value in content["RaceConfiguration"]["MissionBoard"]["MissionOperations"].values())


@pytest.mark.skipif(not WORKBOOK.exists(), reason="authoritative Maxis workbook is not present")
def test_live_setup_is_one_clean_transaction_and_never_carries_personal_keys():
    roster = load_authoritative_roster(WORKBOOK)
    sql = build_setup_sql(roster, load_final_content(), DEFAULT_EVENT_ID, DEFAULT_JOIN_CODE, "Maxis Corporate & Mid-Market — Mission AI")
    assert sql.startswith("-- Generated final Maxis live-event setup")
    assert "begin;" in sql and sql.rstrip().endswith("commit;")
    assert "exos_v2_theme_park_race_save_configuration" in sql
    assert "exos_v2_open_team_formation" in sql
    assert "activity_runtime_v2" in sql and "submissions_v2" in sql and "score_transactions_v2" in sql
    assert all(member.personal_key not in sql for member in roster)
    assert "create table" not in sql.lower()
    assert "alter table" not in sql.lower()


def test_dedicated_live_deployment_is_event_scoped_without_repointing_uat_by_url():
    root = Path(__file__).resolve().parents[1]
    service = (root / "services/maxis_personal_key_event.py").read_text(encoding="utf-8")
    screen = (root / "screens/maxis_personal_key.py").read_text(encoding="utf-8")
    assert "MAXIS_PERSONAL_KEY_EVENT_ID" in service
    assert "MAXIS_PERSONAL_KEY_JOIN_CODE" in service
    assert "maxis_personal_key_event()" in screen
    assert "derive_personal_key_credential(event_id, personal_key)" in screen
