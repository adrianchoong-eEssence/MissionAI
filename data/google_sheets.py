import gspread
import streamlit as st
from google.oauth2.service_account import Credentials
from datetime import datetime

SPREADSHEET_ID = "1XWCW9UVj_1cxA32ItsE8-nAr9q0NEgOhhD5e3C64Hvw"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

REQUIRED_WORKSHEETS = {
    "Participants": ["EventID", "Name", "Team", "Points", "Status"],
    "Events": [
        "EventID", "Client", "Department", "EventName", "EventDate", "Venue",
        "Notes", "Status", "ProgrammeType", "JoinCode", "NumberOfTeams",
    ],
    "Missions": [
        "EventID", "MissionID", "Title", "Description", "Points", "Status",
        "SubmissionType", "Clue", "Answer", "Hint1", "Hint2", "Hint3",
        "AIHelpEnabled",
    ],
    "Teams": ["EventID", "TeamID", "TeamName", "Country", "Language", "Score", "Status"],
    "AIFacilitators": ["Name", "Personality", "Greeting"],
    "Conversations": ["EventID", "Team", "AI", "Role", "Message", "Timestamp"],
    "Submissions": [
        "SubmissionID", "EventID", "MissionID", "TeamName", "ParticipantName",
        "ImageURL", "DriveFileID", "Score", "Judged", "Remarks", "SubmittedAt",
    ],
    "ProgrammeStages": [
        "EventID", "StageNo", "StageName", "StageType", "MissionID",
        "DisplayMode", "ParticipantMessage", "FacilitatorInstruction", "IsActive",
    ],
    "EventState": [
        "EventID", "CurrentStageNo", "State", "StageName", "MissionID",
        "DisplayMode", "LastUpdated",
    ],
}


@st.cache_resource
def get_workbook():
    try:
        credentials = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=SCOPES,
        )
    except Exception:
        credentials = Credentials.from_service_account_file(
            "mission_ai_service_account.json",
            scopes=SCOPES,
        )

    client = gspread.authorize(credentials)
    return client.open_by_key(SPREADSHEET_ID)


def ensure_worksheet(workbook, name, headers):
    try:
        worksheet = workbook.worksheet(name)
    except gspread.WorksheetNotFound:
        worksheet = workbook.add_worksheet(title=name, rows=500, cols=max(len(headers), 10))
        worksheet.append_row(headers)
        return worksheet

    existing = worksheet.row_values(1)
    if not existing:
        worksheet.append_row(headers)

    return worksheet


@st.cache_resource
def get_worksheets():
    workbook = get_workbook()
    return {
        name: ensure_worksheet(workbook, name, headers)
        for name, headers in REQUIRED_WORKSHEETS.items()
    }


@st.cache_data(ttl=30)
def get_sheet_records(sheet_name):
    worksheets = get_worksheets()
    return worksheets[sheet_name].get_all_records()


class GoogleSheetsDB:
    def __init__(self):
        worksheets = get_worksheets()
        self.participants = worksheets["Participants"]
        self.events = worksheets["Events"]
        self.missions = worksheets["Missions"]
        self.teams = worksheets["Teams"]
        self.ai_facilitators = worksheets["AIFacilitators"]
        self.conversations = worksheets["Conversations"]
        self.submissions = worksheets["Submissions"]
        self.programme_stages = worksheets["ProgrammeStages"]
        self.event_state = worksheets["EventState"]

    def clear_cache(self):
        get_sheet_records.clear()

    # -------------------------
    # Events
    # -------------------------

    def create_event(
        self,
        event_id,
        client,
        department,
        event_name,
        event_date,
        venue,
        programme_type,
        join_code,
        number_of_teams,
    ):
        self.events.append_row([
            event_id,
            client,
            department,
            event_name,
            event_date,
            venue,
            "",
            "Draft",
            programme_type,
            join_code,
            number_of_teams,
        ])
        self.clear_cache()

    def get_events(self):
        return get_sheet_records("Events")

    def get_event_by_join_code(self, join_code):
        for event in self.get_events():
            if str(event.get("JoinCode", "")).upper() == str(join_code).upper():
                return event
        return None

    # -------------------------
    # Teams
    # -------------------------

    def create_teams(self, event_id, number_of_teams):
        records = get_sheet_records("Teams")
        rows_to_delete = []

        for index, record in enumerate(records, start=2):
            if str(record.get("EventID", "")) == str(event_id):
                rows_to_delete.append(index)

        for row in reversed(rows_to_delete):
            self.teams.delete_rows(row)

        default_countries = [
            ("Japan", "Japanese", "🇯🇵 Japan"),
            ("Korea", "Korean", "🇰🇷 Korea"),
            ("Brazil", "Portuguese", "🇧🇷 Brazil"),
            ("France", "French", "🇫🇷 France"),
            ("Italy", "Italian", "🇮🇹 Italy"),
            ("Spain", "Spanish", "🇪🇸 Spain"),
            ("Thailand", "Thai", "🇹🇭 Thailand"),
            ("Germany", "German", "🇩🇪 Germany"),
        ]

        for i in range(1, int(number_of_teams) + 1):
            country, language, display_name = default_countries[(i - 1) % len(default_countries)]
            self.teams.append_row([
                event_id,
                f"TEAM-{i:02d}",
                display_name,
                country,
                language,
                0,
                "Active",
            ])

        self.clear_cache()

    def get_teams(self, event_id):
        return [
            team
            for team in get_sheet_records("Teams")
            if str(team.get("EventID", "")) == str(event_id)
        ]

    # -------------------------
    # Participants
    # -------------------------

    def join_player(self, event_id, name):
        clean_name = str(name).strip()

        existing_player = self.get_player(event_id, clean_name)
        if existing_player:
            return {
                "EventID": existing_player.get("EventID", event_id),
                "Name": existing_player.get("Name", clean_name),
                "Team": existing_player.get("Team", ""),
                "Points": existing_player.get("Points", 0),
                "Status": existing_player.get("Status", "Waiting"),
            }

        teams = self.get_teams(event_id)
        participants = [
            p
            for p in self.get_players()
            if str(p.get("EventID", "")) == str(event_id)
        ]

        if teams:
            team = teams[len(participants) % len(teams)]["TeamName"]
        else:
            team = ""

        self.participants.append_row([event_id, clean_name, team, 0, "Waiting"])
        self.clear_cache()

        return {
            "EventID": event_id,
            "Name": clean_name,
            "Team": team,
            "Points": 0,
            "Status": "Waiting",
        }

    def get_players(self):
        return get_sheet_records("Participants")

    def get_player(self, event_id, name):
        for player in self.get_players():
            if (
                str(player.get("EventID", "")) == str(event_id)
                and str(player.get("Name", "")).strip().lower() == str(name).strip().lower()
            ):
                return player
        return None

    def get_participant_count(self, event_id):
        return len([
            p for p in self.get_players()
            if str(p.get("EventID", "")) == str(event_id)
        ])

    def get_team_count(self, event_id):
        return len(self.get_teams(event_id))

    # -------------------------
    # AI Facilitators
    # -------------------------

    def get_ai_facilitators(self):
        return get_sheet_records("AIFacilitators")

    def assign_ai_facilitator(self, team_name):
        facilitators = self.get_ai_facilitators()
        if not facilitators:
            return None
        index = abs(hash(team_name)) % len(facilitators)
        return facilitators[index]

    # -------------------------
    # Conversations
    # -------------------------

    def save_conversation(self, event_id, team, ai, role, message, timestamp):
        self.conversations.append_row([event_id, team, ai, role, message, timestamp])
        self.clear_cache()

    def get_conversation(self, event_id, team):
        return [
            row
            for row in get_sheet_records("Conversations")
            if str(row.get("EventID", "")) == str(event_id)
            and str(row.get("Team", "")) == str(team)
        ]

    # -------------------------
    # Missions
    # -------------------------

    def send_mission(
        self,
        event_id,
        mission_id,
        title,
        description,
        points=100,
        submission_type="Photo",
        clue="",
        answer="",
        hint1="",
        hint2="",
        hint3="",
        ai_help_enabled="Yes",
    ):
        self.missions.append_row([
            event_id,
            mission_id,
            title,
            description,
            points,
            "LIVE",
            submission_type,
            clue,
            answer,
            hint1,
            hint2,
            hint3,
            ai_help_enabled,
        ])
        self.clear_cache()

    def get_current_mission(self, event_id):
        state = self.get_event_state(event_id)
        if state and state.get("MissionID"):
            mission = self.get_mission(event_id, state.get("MissionID"))
            if mission:
                return mission

        missions = [
            mission
            for mission in get_sheet_records("Missions")
            if str(mission.get("EventID", "")) == str(event_id)
            and str(mission.get("Status", "")) == "LIVE"
        ]
        return missions[-1] if missions else None

    def get_mission(self, event_id, mission_id):
        for mission in get_sheet_records("Missions"):
            if (
                str(mission.get("EventID", "")) == str(event_id)
                and str(mission.get("MissionID", "")) == str(mission_id)
            ):
                return mission
        return None

    # -------------------------
    # Submissions
    # -------------------------

    def save_submission(
        self,
        submission_id,
        event_id,
        mission_id,
        team_name,
        participant_name,
        image_url,
        drive_file_id,
        submitted_at,
        score="",
        judged="No",
        remarks="",
    ):
        self.submissions.append_row([
            submission_id,
            event_id,
            mission_id,
            team_name,
            participant_name,
            image_url,
            drive_file_id,
            score,
            judged,
            remarks,
            submitted_at,
        ])
        self.clear_cache()
        return {
            "SubmissionID": submission_id,
            "EventID": event_id,
            "MissionID": mission_id,
            "TeamName": team_name,
            "ParticipantName": participant_name,
            "ImageURL": image_url,
            "DriveFileID": drive_file_id,
            "Score": score,
            "Judged": judged,
            "Remarks": remarks,
            "SubmittedAt": submitted_at,
        }

    def get_team_submission(self, event_id, mission_id, team_name):
        for row in get_sheet_records("Submissions"):
            if (
                str(row.get("EventID", "")) == str(event_id)
                and str(row.get("MissionID", "")) == str(mission_id)
                and str(row.get("TeamName", "")) == str(team_name)
            ):
                return row
        return None

    def get_event_submissions(self, event_id):
        return [
            row
            for row in get_sheet_records("Submissions")
            if str(row.get("EventID", "")) == str(event_id)
        ]

    def get_submissions(self, event_id):
        return self.get_event_submissions(event_id)

    def get_pending_submissions(self, event_id):
        return [
            row
            for row in self.get_event_submissions(event_id)
            if str(row.get("Judged", "")).lower() not in ["yes", "true", "approved"]
        ]

    def update_submission_score(self, submission_id, score, remarks="", judged="Yes"):
        rows = get_sheet_records("Submissions")
        for index, row in enumerate(rows, start=2):
            if str(row.get("SubmissionID", "")) == str(submission_id):
                self.submissions.update_cell(index, 8, score)
                self.submissions.update_cell(index, 9, judged)
                self.submissions.update_cell(index, 10, remarks)
                self.clear_cache()
                return True
        return False

    # -------------------------
    # Programme Stages / Show Control
    # -------------------------

    def get_programme_stages(self, event_id):
        stages = [
            row
            for row in get_sheet_records("ProgrammeStages")
            if str(row.get("EventID", "")) == str(event_id)
            and str(row.get("IsActive", "Yes")) != "No"
        ]
        return sorted(stages, key=lambda row: int(row.get("StageNo") or 0))

    def save_programme_stages(self, event_id, stages):
        existing_rows = []
        for index, row in enumerate(get_sheet_records("ProgrammeStages"), start=2):
            if str(row.get("EventID", "")) == str(event_id):
                existing_rows.append(index)

        for row_index in reversed(existing_rows):
            self.programme_stages.delete_rows(row_index)

        for stage in stages:
            self.programme_stages.append_row([
                event_id,
                stage.get("StageNo", ""),
                stage.get("StageName", ""),
                stage.get("StageType", ""),
                stage.get("MissionID", ""),
                stage.get("DisplayMode", "Hybrid"),
                stage.get("ParticipantMessage", ""),
                stage.get("FacilitatorInstruction", ""),
                stage.get("IsActive", "Yes"),
            ])

        self.clear_cache()

    def get_event_state(self, event_id):
        states = [
            row
            for row in get_sheet_records("EventState")
            if str(row.get("EventID", "")) == str(event_id)
        ]
        return states[-1] if states else None

    def set_event_state(
        self,
        event_id,
        current_stage_no,
        state="",
        stage_name="",
        mission_id="",
        display_mode="Hybrid",
    ):
        rows = get_sheet_records("EventState")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = [
            event_id,
            current_stage_no,
            state,
            stage_name,
            mission_id,
            display_mode,
            timestamp,
        ]

        for index, row in enumerate(rows, start=2):
            if str(row.get("EventID", "")) == str(event_id):
                self.event_state.update(f"A{index}:G{index}", [payload])
                self.clear_cache()
                return True

        self.event_state.append_row(payload)
        self.clear_cache()
        return True

    def set_event_stage(self, event_id, stage):
        return self.set_event_state(
            event_id=event_id,
            current_stage_no=stage.get("StageNo", ""),
            state=stage.get("StageType", ""),
            stage_name=stage.get("StageName", ""),
            mission_id=stage.get("MissionID", ""),
            display_mode=stage.get("DisplayMode", "Hybrid"),
        )

    def seed_aia_saturday_stages(self, event_id):
        stages = [
            {
                "StageNo": 1,
                "StageName": "Registration",
                "StageType": "Registration",
                "MissionID": "",
                "DisplayMode": "Registration",
                "ParticipantMessage": "Scan the QR code, enter the join code, and register your name.",
                "FacilitatorInstruction": "Monitor participant count and support anyone who has trouble joining.",
            },
            {
                "StageNo": 2,
                "StageName": "Country Discovery",
                "StageType": "TeamDiscovery",
                "MissionID": "",
                "DisplayMode": "Registration",
                "ParticipantMessage": "Find your country team. You may only speak the language of your assigned country.",
                "FacilitatorInstruction": "Invite participants to locate their country members and form teams.",
            },
            {
                "StageNo": 3,
                "StageName": "Pipeline Challenge",
                "StageType": "MissionBriefing",
                "MissionID": "M01",
                "DisplayMode": "Current Mission",
                "ParticipantMessage": "Customer Journey: protect the client through every process handoff.",
                "FacilitatorInstruction": "Brief the marble pipeline rules and prepare the trial run.",
            },
            {
                "StageNo": 4,
                "StageName": "Pipeline Results",
                "StageType": "Results",
                "MissionID": "M01",
                "DisplayMode": "Leaderboard",
                "ParticipantMessage": "Submit evidence or wait while facilitators verify successful and lost clients.",
                "FacilitatorInstruction": "Record each team result and lost-client observations.",
            },
            {
                "StageNo": 5,
                "StageName": "Pipeline Debrief",
                "StageType": "Debrief",
                "MissionID": "M01",
                "DisplayMode": "Collaboration",
                "ParticipantMessage": "Reflect on handoffs, process ownership, and lost clients.",
                "FacilitatorInstruction": "Lead the discussion on customer journey and process accountability.",
            },
            {
                "StageNo": 6,
                "StageName": "Helium Stick",
                "StageType": "MissionBriefing",
                "MissionID": "M02",
                "DisplayMode": "Current Mission",
                "ParticipantMessage": "Taking Ownership Together: lower the stick without blame or escalation.",
                "FacilitatorInstruction": "Brief the helium stick rules and watch for blame language.",
            },
            {
                "StageNo": 7,
                "StageName": "Helium Stick Debrief",
                "StageType": "Debrief",
                "MissionID": "M02",
                "DisplayMode": "Collaboration",
                "ParticipantMessage": "Reflect on ownership, escalation, and pointing fingers.",
                "FacilitatorInstruction": "Debrief the escalation metaphor and connect it to branch collaboration.",
            },
            {
                "StageNo": 8,
                "StageName": "Key Punch",
                "StageType": "MissionBriefing",
                "MissionID": "M03",
                "DisplayMode": "Current Mission",
                "ParticipantMessage": "Balancing Speed, Accuracy and Compliance: execute with strategy.",
                "FacilitatorInstruction": "Brief the key punch rules, sequence, and time pressure.",
            },
            {
                "StageNo": 9,
                "StageName": "Key Punch Results",
                "StageType": "Results",
                "MissionID": "M03",
                "DisplayMode": "Leaderboard",
                "ParticipantMessage": "Review your team result and prepare for the learning transfer.",
                "FacilitatorInstruction": "Score results and debrief strategy, stamina, and teamwork.",
            },
            {
                "StageNo": 10,
                "StageName": "Lunch Break",
                "StageType": "Break",
                "MissionID": "",
                "DisplayMode": "Registration",
                "ParticipantMessage": "Lunch break. Please return on time for the enterprise challenge.",
                "FacilitatorInstruction": "Freeze the programme and prepare Catalyst materials.",
            },
            {
                "StageNo": 11,
                "StageName": "Catalyst Challenge",
                "StageType": "MissionBriefing",
                "MissionID": "M04",
                "DisplayMode": "Current Mission",
                "ParticipantMessage": "Creating the Enterprise Success: build one integrated system together.",
                "FacilitatorInstruction": "Brief the simple machine build and integration requirements.",
            },
            {
                "StageNo": 12,
                "StageName": "Enterprise Integration",
                "StageType": "Collaboration",
                "MissionID": "M04",
                "DisplayMode": "Collaboration",
                "ParticipantMessage": "Connect every team's build into one working enterprise system.",
                "FacilitatorInstruction": "Support inter-team integration and prepare final trigger run.",
            },
            {
                "StageNo": 13,
                "StageName": "Mission Reflection",
                "StageType": "Reflection",
                "MissionID": "REF01",
                "DisplayMode": "Collaboration",
                "ParticipantMessage": "Share new ideas, improvements, strengths, and implementation actions.",
                "FacilitatorInstruction": "Run the final learning transfer and collect commitments.",
            },
            {
                "StageNo": 14,
                "StageName": "Closing",
                "StageType": "Closing",
                "MissionID": "",
                "DisplayMode": "Winner",
                "ParticipantMessage": "Thank you for completing the experience together.",
                "FacilitatorInstruction": "Close with enterprise success and collective commitment.",
            },
        ]
        self.save_programme_stages(event_id, stages)
        if stages:
            self.set_event_stage(event_id, stages[0])
        return stages
