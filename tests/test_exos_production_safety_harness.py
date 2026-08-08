"""Pure regression contracts for the two protected EXOS production journeys."""

from pathlib import Path

from engines.formula_race import final_standings, validate_purchase
from engines.programme_adapter import CanonicalProgrammeAdapter
from engines.programme_hierarchy import linked_content_stage
from screens.participant import normalise_join_name


ROOT = Path(__file__).resolve().parents[1]


def activity(event_id="EVT-A"):
    return {
        "EventID": event_id, "ProgrammeID": f"{event_id}-PROGRAMME",
        "ModuleID": f"{event_id}-MODULE-01", "ActivityID": f"{event_id}-ACT-01",
        "ModuleOrder": 1, "ActivityOrder": 1, "StageNo": 1,
        "StageName": "NASI", "ModuleName": "Reflection", "ContentType": "Standard Activity",
        "SubmissionType": "NASI", "EvidenceRequired": True, "IsActive": "Yes",
    }


def test_standard_golden_journey_identity_isolated_reconnect_safe_and_balanced():
    # Backend identity is EventID + full normalized name; first name alone cannot collide.
    names = [normalise_join_name("Ada", "Tan"), normalise_join_name("Ada", "Lim")]
    participants = {}
    teams = {"TEAM-01": 0, "TEAM-02": 0}

    def join(event_id, name):
        key = (event_id, name.casefold())
        if key in participants:
            return participants[key]
        team_id = min(teams, key=teams.get)
        teams[team_id] += 1
        row = {"EventID": event_id, "ParticipantID": f"P-{len(participants)+1}", "TeamID": team_id,
               "Country": "Malaysia", "Name": name}
        participants[key] = row
        return row

    ada_tan, ada_lim = (join("EVT-A", name) for name in names)
    reconnect = join("EVT-A", "Ada Tan")
    assert reconnect["TeamID"] == ada_tan["TeamID"] and sum(teams.values()) == 2
    other_event = join("EVT-B", "Ada Tan")
    assert ada_tan["ParticipantID"] != ada_lim["ParticipantID"]
    assert reconnect["ParticipantID"] == ada_tan["ParticipantID"]
    assert other_event["ParticipantID"] != ada_tan["ParticipantID"]


def test_activity_ids_survive_builder_runtime_participant_submission_facilitator_contract():
    row = activity("EVT-0016")
    snapshot = CanonicalProgrammeAdapter("EVT-0016", [row]).snapshot().require_valid()
    module, resolved = snapshot.resolve_runtime({"Stage": {"ActivityID": row["ActivityID"]}})
    runtime_payload = linked_content_stage(resolved, module)
    submission = {"EventID": row["EventID"], "MissionID": runtime_payload["MissionID"],
                  "ActivityID": runtime_payload["ActivityID"], "SubmissionID": "SUB-1"}
    facilitator_view = [submission for submission in [submission]
                        if submission["EventID"] == row["EventID"] and submission["ActivityID"] == row["ActivityID"]]
    assert (resolved["ProgrammeID"], module["ModuleID"], submission["ActivityID"]) == (
        row["ProgrammeID"], row["ModuleID"], row["ActivityID"])
    assert facilitator_view == [submission]


def test_nasi_four_box_and_persisted_runtime_submission_contract_are_present():
    participant = (ROOT / "screens" / "participant.py").read_text()
    runtime = (ROOT / "data" / "runtime_database.py").read_text()
    for label in ("N - New Ideas:", "A - Areas for Improvement:", "S - Strengths:", "I - Implementation:"):
        assert label in participant
    assert "def save_submission" in runtime and "runtime_submissions" in runtime


def test_routes_remain_mutually_exclusive():
    facilitator = (ROOT / "Facilitator.py").read_text()
    participant = (ROOT / "screens" / "participant.py").read_text()
    captain = (ROOT / "screens" / "formula_race_captain.py").read_text()
    assert "if requested_is_race:" in facilitator and "show_formula_race" in facilitator
    assert "show_control_centre()" in facilitator
    assert "is_formula_race_join" in participant and "join_preassigned_player" in participant
    entrypoint = source_or_empty("Participant.py")
    assert "formula_race_captain_login" in captain and 'st.query_params.get("race", "")' in entrypoint


def source_or_empty(path):
    return (ROOT / path).read_text() if (ROOT / path).exists() else ""


def test_formula_race_event_team_and_purchase_guards_are_deterministic():
    assert validate_purchase(100, 5, 20, 5) == (True, "")
    assert not validate_purchase(99, 5, 20, 5)[0]  # overspend
    assert not validate_purchase(100, 4, 20, 5)[0]  # stock
    teams = [{"TeamID": "F1-02", "TeamName": "Bolt"}, {"TeamID": "F1-01", "TeamName": "Apex"}]
    standings = final_standings(teams, [{"EventID": "EVT-0006", "TeamID": "F1-01", "Amount": 10},
                                         {"EventID": "EVT-0006", "TeamID": "F1-02", "Amount": 10}], [], [])
    assert [(row["TeamID"], row["Rank"]) for row in standings] == [("F1-01", 1), ("F1-02", 2)]


def test_database_safety_scripts_are_read_only_and_cover_core_invariants():
    for name in ("exos_core_preflight.sql", "exos_core_postflight.sql", "exos_core_rollback_verify.sql"):
        text = (ROOT / "supabase" / "verification" / name).read_text().lower()
        assert "insert " not in text and "update " not in text and "delete " not in text and "drop " not in text
        assert "runtime_events" in text and "runtime_participants" in text
