import json
from collections import Counter
from pathlib import Path

from content_packs.george_town_walk_hunt_v1.materialize import candidate_plan, load_pack
from scripts.certify_enca_hybrid_assignment import run_harness
from scripts.prepare_enca_george_town_uat import materialization_plan
from services.enca_public_projector import normalise_enca_projection


ROOT = Path(__file__).resolve().parents[1]


def test_enca_pack_has_exact_hod_assignment_capacity_and_no_final_content():
    pack = load_pack()
    formation = pack["TeamFormation"]
    assert pack["Event"]["Capacity"] == 134
    assert formation["Mode"] == "HYBRID_ANCHORED"
    assert formation["GeneralParticipantCapacity"] == 124
    assert len(formation["Teams"]) == len(formation["HODAnchors"]) == 10
    assert Counter(row["Capacity"] for row in formation["Teams"]) == {14: 4, 13: 6}
    assert len({row["TeamID"] for row in formation["HODAnchors"]}) == 10
    assert [row["DisplayName"] for row in formation["HODAnchors"]] == [
        "Mr Chen Yee Chieng", "Mr Andrew Kwan", "Ms Mun Yee", "Mr Huang", "Mr Teoh",
        "Mr Lee Tian Qi", "Mr Yeow", "Mr Adam Chan", "Mr Bagus", "Mr Zairie",
    ]
    assert pack["Missions"] == pack["Checkpoints"] == []
    assert all(row["Scored"] for row in pack["CompetitionStages"])
    assert {row["Name"] for row in pack["NonScoredActivities"]} == {"ENERGIZERS", "ROLLERCOASTER CHALLENGE"}


def test_local_hybrid_certification_proves_source_contract_without_claiming_deployment():
    result = run_harness()
    assert result["EvidenceClass"] == "LOCAL_SOURCE_CERTIFICATION_ONLY"
    assert result["InstallationStatus"] == "NOT_INSTALLED"
    assert result["HumanUAT"] == "NOT_EXECUTED"
    assert result["Registered"] == 134
    assert result["HODDistinctTeams"] and result["HODSameDeviceReconnect"]
    assert result["GeneralRandomAssign"] and result["GeneralSameDeviceRetry"]
    assert not result["DuplicateParticipant"] and not result["DuplicateAttendance"]
    assert result["AttendanceAllPresent"] and not result["CapacityOverflow"]
    assert result["CaptainIndependentFromHOD"] and result["NeraIsolation"]
    assert result["DistributionShape"] == [13] * 6 + [14] * 4
    assert result["CumulativeLedger"]["StageCount"] == 3
    assert result["ParticipantLocationVisibility"]["OFF"] == []


def test_redacted_materialisation_plan_never_outputs_raw_personal_keys():
    pack = load_pack()
    keys = {row["DisplayName"]: f"A{index:05d}" for index, row in enumerate(pack["TeamFormation"]["HODAnchors"], start=1)}
    result = materialization_plan(keys)
    rendered = json.dumps(result)
    assert result["Executed"] is False
    assert result["ReadyForConfigureRPC"] is True
    assert len(result["HODAnchorRoster"]) == 10
    assert all(len(row["EnrollmentCredentialHash"]) == 64 for row in result["HODAnchorRoster"])
    assert all(raw not in rendered for raw in keys.values())
    assert candidate_plan()["Executed"] is False


def test_prepared_sql_enforces_hybrid_assignment_attendance_stage_and_location_contracts():
    sql = (ROOT / "supabase/053_enca_hybrid_event_architecture.sql").read_text(encoding="utf-8")
    for token in (
        "event_competition_stages_v2", "exos_v2_configure_hybrid_anchored_team_formation",
        "exos_v2_open_hybrid_anchored_team_formation", "exos_v2_hybrid_anchored_register_random",
        "exos_v2_hybrid_anchored_claim_personal_key", "HOD_ANCHOR", "assigned_count < team_capacity",
        "ORDER BY random()", "exos_v2_set_participant_attendance", "score_transactions_v2",
        "exos_v2_competition_public_projector_projection", "participant_visibility_mode",
        "TEAM_LEADERS", "is_team_formation_captain", "exos_v2_hunt_submission_competition_stage_guard",
    ):
        assert token in sql
    public_projection = sql.split("CREATE OR REPLACE FUNCTION public.exos_v2_competition_public_projector_projection", 1)[1]
    public_projection = public_projection.split("CREATE OR REPLACE FUNCTION", 1)[0]
    for forbidden in ("ParticipantID", "ParticipantName", "Latitude", "Longitude", "Evidence", "SubmissionPayload"):
        assert forbidden not in public_projection
    assert "t.team_id <> (SELECT team_id FROM own)" in sql
    assert "'AutomaticCaptain', false" in sql


def test_entrypoints_and_operator_surfaces_pin_the_enca_event_without_displaying_a_join_code_input():
    event_source = (ROOT / "services" / "enca_george_town_event.py").read_text(encoding="utf-8")
    participant = (ROOT / "GeorgeTown_Participant.py").read_text(encoding="utf-8")
    projector = (ROOT / "GeorgeTown_Projector.py").read_text(encoding="utf-8")
    control = (ROOT / "GeorgeTown_MissionControl.py").read_text(encoding="utf-8")
    screen = (ROOT / "screens" / "enca_george_town_participant.py").read_text(encoding="utf-8")
    mission_control = (ROOT / "screens" / "hunt_mission_control.py").read_text(encoding="utf-8")
    for source in (participant, projector, control):
        assert "enca_george_town_event" in source
    assert '"ENCA-GEORGETOWN-20261024-UAT"' in event_source
    assert '"ENCAUAT"' in event_source
    assert 'st.text_input("JOIN CODE")' not in screen
    assert "GENERAL PARTICIPANT" in screen
    assert "HOD / PRE-REGISTERED" in screen
    assert '"First / Given Name"' in screen
    assert '"Last / Family Name"' in screen
    assert '"Personal Key"' in screen
    assert "register_hybrid_anchored_random_participant" in screen
    assert "claim_hybrid_anchored_hod_personal_key" in screen
    assert "derive_personal_key_credential" in screen
    assert "participant_device_binding" not in screen
    assert "secrets.token_urlsafe(32)" in screen
    assert "str(error)" not in screen
    assert "apply_branding" not in participant
    for tab in ("HOD ANCHORS", "STAGES", "LIVE MAP", "BONUS / ADJUSTMENT"):
        assert tab in mission_control
    assert "ENCA UAT CAPACITY" in mission_control
    for entrypoint in ("ENCA_Participant.py", "ENCA_MissionControl.py", "ENCA_Projector.py"):
        assert (ROOT / entrypoint).is_file()


def test_enca_kai_operations_stay_event_scoped_and_offer_required_operator_reads():
    source = (ROOT / "services" / "hunt_kai_operations.py").read_text(encoding="utf-8")
    for intent in ("STATUS", "HYBRID_ROSTER", "DISTRIBUTION", "CAPTAINS", "STAGE_STATUS", "LEADERBOARD", "PENDING_REVIEWS", "ANNOUNCE", "ADJUST_SCORE"):
        assert f'"{intent}"' in source
    assert "get_hybrid_anchored_operator_roster(event_id)" in source


def test_public_projector_normalisation_strips_all_but_safe_cumulative_contract():
    projection = normalise_enca_projection({
        "Event": {"EventName": "ENCA", "CurrentStage": "VISION TOWER", "CurrentStageState": "ACTIVE", "ParticipantName": "No"},
        "Teams": [{"Country": "COUNTRY SLOT 01", "Flag": "🌐", "Rank": 1, "Score": 20,
                   "ParticipantName": "No", "Latitude": 5.4, "Evidence": "No"}],
    })
    assert projection == {
        "Event": {"DisplayName": "ENCA", "CurrentStage": "VISION TOWER", "State": "ACTIVE"},
        "Teams": [{"Country": "COUNTRY SLOT 01", "Flag": "🌐", "Rank": 1, "Score": 20.0}],
    }
