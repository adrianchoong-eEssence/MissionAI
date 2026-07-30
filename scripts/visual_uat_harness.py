"""Local screenshot harness using production screens with disposable in-memory data."""

import streamlit as st

import screens.administration as administration
import screens.control_centre as control_centre
import screens.create_event as create_event
import screens.events_home as events_home
import screens.leaderboard_display as leaderboard_display
import screens.live_event_console as live_event_console
import screens.mission_setup as mission_setup
import screens.participant as participant
import screens.programme_builder as programme_builder


EVENT = {
    "EventID": "EVT-0004",
    "Client": "AIA Malaysia",
    "Department": "Customer Experience",
    "EventName": "Weekend Leadership Experience",
    "EventDate": "2026-08-01",
    "Venue": "Bayu Beach Resort",
    "Notes": (
        '{"DurationHours": 8, "ExpectedParticipants": 60, '
        '"TeamTheme": "Formula One", "CurrentStageStatus": "READY"}'
    ),
    "Status": "Draft",
    "ProgrammeType": "Mission AI",
    "JoinCode": "BAYU26",
    "NumberOfTeams": 6,
}

STAGES = [
    {
        "StageNo": 1,
        "StageName": "Welcome & Registration",
        "StageType": "Registration",
        "MissionID": "",
        "DisplayMode": "Registration",
        "ParticipantMessage": "Welcome. Join your team and prepare to begin.",
        "FacilitatorInstruction": "Open registration and monitor arrivals.",
        "DurationMinutes": 15,
        "IsActive": "Yes",
    },
    {
        "StageNo": 2,
        "StageName": "Bridge of Trust",
        "StageType": "ScoredActivity",
        "MissionID": "M01",
        "DisplayMode": "Leaderboard",
        "ParticipantMessage": "Build trust through clear communication.",
        "FacilitatorInstruction": "Brief teams, start the timer and record scores.",
        "DurationMinutes": 30,
        "IsActive": "Yes",
    },
    {
        "StageNo": 3,
        "StageName": "Mission AI",
        "StageType": "MissionActive",
        "MissionID": "M02",
        "DisplayMode": "Hybrid",
        "ParticipantMessage": "Open the Mission Board and begin.",
        "FacilitatorInstruction": "Monitor progress and review evidence.",
        "DurationMinutes": 60,
        "IsActive": "Yes",
    },
]

MISSIONS = [
    {
        "EventID": "EVT-0004",
        "MissionID": "M01",
        "TemplateID": "MT-0001",
        "Title": "Bridge of Trust",
        "Module": "Mission AI",
        "Category": "Customer Experience",
        "Story": "A customer signal is hidden in the noise. Work together to uncover what matters.",
        "Clue": "Listen beneath the words.",
        "MainQuestion": "What outcome would restore the customer's confidence?",
        "Answer": "Clear ownership and an immediate next step",
        "ParticipantInstructions": "Identify the customer need and submit one concise response.",
        "FacilitatorInstructions": "Score each team.",
        "SubmissionType": "TEXT",
        "EvidenceRequired": "Yes",
        "EvidenceInstructions": "Submit one team response.",
        "ScoringRule": "Manual score",
        "Points": 100,
        "CreditValue": 100,
        "MaximumCredits": 100,
        "TimeLimitMinutes": 10,
        "CountdownEnabled": "Yes",
        "AIRequired": "Yes",
        "AIHelpEnabled": "Yes",
        "AIPrompt": "Help the team identify the underlying customer need without giving the answer.",
        "AIRole": "Customer insight coach",
        "Hint1": "Separate facts from feelings.",
        "Hint2": "Look for repeated customer effort.",
        "Hint3": "Define one immediate ownership action.",
        "CheckpointName": "Customer Signal Station",
        "LocationDescription": "Main ballroom, checkpoint one.",
        "Latitude": 3.1390,
        "Longitude": 101.6869,
        "GeofenceRadius": 50,
        "GPSRequired": "Yes",
        "QRRequired": "Yes",
        "QRCodeValue": "EVT-0004:M01:SIGNAL",
        "QRValidationRule": "Exact match",
        "DisplayOrder": 1,
        "Status": "DRAFT",
    },
    {
        "EventID": "EVT-0004",
        "MissionID": "M02",
        "TemplateID": "MT-0002",
        "Title": "Mission AI",
        "ParticipantInstructions": "Solve the live mission as a team.",
        "FacilitatorInstructions": "Review evidence and release credits.",
        "SubmissionType": "PHOTO",
        "ScoringRule": "Evidence review",
        "Points": 150,
        "Status": "LIVE",
    },
]


class FakeRuntime:
    can_publish = False
    is_configured = False


class FakeDB:
    runtime = FakeRuntime()

    def get_events(self, include_archived=False):
        return [dict(EVENT)]

    def get_event(self, event_id):
        return dict(EVENT)

    def get_event_by_join_code(self, join_code):
        return None

    @staticmethod
    def event_metadata(event):
        import json
        return json.loads(event.get("Notes", "{}"))

    def get_programme_stages(self, event_id):
        return [dict(row) for row in STAGES]

    def get_event_state(self, event_id):
        stage_no = int(st.session_state.get("preview_stage_no", 1))
        stage = STAGES[stage_no - 1]
        return {
            "CurrentStageNo": stage_no,
            "StageName": stage["StageName"],
            "DisplayMode": stage["DisplayMode"],
        }

    def set_event_stage(self, event_id, stage):
        st.session_state["preview_stage_no"] = int(stage.get("StageNo", 1))
        return {"SheetUpdated": True, "RuntimeUpdated": False, "Warning": ""}

    def update_event_metadata(self, event_id, updates):
        return dict(updates)

    def update_stage_timer(self, event_id, stage_no, action, duration_minutes=0):
        return self.get_stage_timer(event_id, stage_no, duration_minutes)

    def save_programme_stages(self, event_id, stages):
        return None

    def get_stage_timer(self, event_id, stage_no, duration_minutes=0):
        return {
            "Status": "READY",
            "DurationSeconds": int(duration_minutes) * 60,
            "RemainingSeconds": int(duration_minutes) * 60,
            "StartedAt": "",
        }

    def get_participant_count(self, event_id):
        return 48

    def get_team_count(self, event_id):
        return 6

    def get_teams(self, event_id):
        return [
            {"TeamID": f"T{number}", "TeamName": f"Team {number}"}
            for number in range(1, 7)
        ]

    def get_mission_templates(self, include_archived=False):
        return [
            {
                "TemplateID": "MT-0001",
                "Title": "Bridge of Trust",
                "Status": "ACTIVE",
            },
            {
                "TemplateID": "MT-0002",
                "Title": "Mission AI",
                "Status": "ACTIVE",
            },
        ]

    def get_event_missions(self, event_id, include_closed=True):
        return [dict(row) for row in MISSIONS]

    def get_mission(self, event_id, mission_id):
        return next(
            (dict(row) for row in MISSIONS if row["MissionID"] == mission_id),
            None,
        )

    def upsert_event_mission(self, record):
        return {"MissionID": record["MissionID"], "Action": "Updated"}

    def generate_next_event_mission_id(self, event_id, prefix="M"):
        return "M03"

    def reorder_event_missions(self, event_id, mission_ids):
        return {"Updated": len(mission_ids)}

    def backfill_event_mission_editor_fields(self, event_id, mission_ids=None):
        return {"EventID": event_id, "Updated": []}

    def get_programme_packs(self):
        return []

    def get_current_mission(self, event_id):
        return None

    def get_submissions(self, event_id):
        return []

    def export_backup_snapshot(self):
        return {
            "ExportedAt": "2026-07-28T12:00:00",
            "SpreadsheetID": "UAT-PREVIEW",
            "Worksheets": {
                "Events": [EVENT],
                "Teams": self.get_teams(EVENT["EventID"]),
                "Missions": MISSIONS,
                "Participants": [],
                "Submissions": [],
                "ProgrammeStages": STAGES,
            },
        }


for module in (
    administration,
    control_centre,
    create_event,
    events_home,
    leaderboard_display,
    live_event_console,
    mission_setup,
    programme_builder,
):
    module.GoogleSheetsDB = FakeDB

st.set_page_config(page_title="EXOS Local UAT Preview", layout="wide")
st.sidebar.title("EXOS")
st.sidebar.caption("Local UAT Preview")
page = st.sidebar.radio(
    "Workspace",
    [
        "Events",
        "Create Event",
        "Mission Studio",
        "Programme Builder",
        "Control Centre",
        "Projector",
        "Reports",
        "Administration",
        "Participant Mission Card",
    ],
)

if page == "Events":
    events_home.show_events_home()
elif page == "Create Event":
    create_event.show_create_event()
elif page == "Mission Studio":
    mission_setup.show_mission_setup()
elif page == "Programme Builder":
    programme_builder.show_programme_builder()
elif page == "Control Centre":
    control_centre.show_control_centre()
elif page == "Projector":
    leaderboard_display.show_leaderboard_display()
elif page == "Administration":
    administration.show_administration()
elif page == "Participant Mission Card":
    st.title(MISSIONS[0]["Title"])
    participant.render_mission_content(MISSIONS[0])
else:
    st.title("Results & Reports")
    st.info("Results appear here after the event.")
