import gspread
import streamlit as st
from google.oauth2.service_account import Credentials
from datetime import datetime
import random
import re
import string

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
        "NextTeamIndex",
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
        "ImageURL", "DriveFileID", "SubmissionType", "Metric1", "Metric2",
        "Metric3", "Score", "Status", "Judged", "Remarks", "SubmittedAt",
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

    missing_headers = [header for header in headers if header not in existing]
    if missing_headers:
        worksheet.update(
            f"{gspread.utils.rowcol_to_a1(1, len(existing) + 1)}:{gspread.utils.rowcol_to_a1(1, len(existing) + len(missing_headers))}",
            [missing_headers],
        )

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
            0,
        ])
        self.clear_cache()

    def get_events(self):
        return get_sheet_records("Events")

    def get_event_by_join_code(self, join_code):
        for event in self.get_events():
            if str(event.get("JoinCode", "")).upper() == str(join_code).upper():
                return event
        return None

    def get_event(self, event_id):
        for event in self.get_events():
            if str(event.get("EventID", "")) == str(event_id):
                return event
        return None

    def generate_next_event_id(self):
        highest_number = 0
        for event in self.get_events():
            event_id = str(event.get("EventID", "")).strip()
            match = re.search(r"(\d+)$", event_id)
            if match:
                highest_number = max(highest_number, int(match.group(1)))
        return f"EVT-{highest_number + 1:04d}"

    def create_new_join_code(self, length=6):
        existing_codes = {
            str(event.get("JoinCode", "")).strip().upper()
            for event in self.get_events()
        }
        characters = string.ascii_uppercase + string.digits
        while True:
            join_code = "".join(random.choice(characters) for _ in range(length))
            if join_code not in existing_codes:
                return join_code

    @staticmethod
    def _append_record(worksheet, record, overrides=None):
        payload = dict(record)
        if overrides:
            payload.update(overrides)
        headers = worksheet.row_values(1)
        worksheet.append_row([payload.get(header, "") for header in headers])

    def copy_teams(self, source_event_id, new_event_id):
        source_rows = self.get_teams(source_event_id)
        for row in source_rows:
            self._append_record(
                self.teams,
                row,
                {
                    "EventID": new_event_id,
                    "Score": 0,
                    "Status": "Active",
                },
            )
        return len(source_rows)

    def copy_missions(self, source_event_id, new_event_id):
        source_rows = [
            row for row in get_sheet_records("Missions")
            if str(row.get("EventID", "")) == str(source_event_id)
        ]
        for row in source_rows:
            self._append_record(
                self.missions,
                row,
                {
                    "EventID": new_event_id,
                    "Status": "DRAFT",
                },
            )
        return len(source_rows)

    def copy_programme_stages(self, source_event_id, new_event_id):
        source_rows = [
            row for row in get_sheet_records("ProgrammeStages")
            if str(row.get("EventID", "")) == str(source_event_id)
        ]
        source_rows = sorted(
            source_rows,
            key=lambda row: int(row.get("StageNo") or 0),
        )
        for row in source_rows:
            self._append_record(
                self.programme_stages,
                row,
                {"EventID": new_event_id},
            )
        return source_rows

    def duplicate_event(self, source_event_id, new_event_name):
        source_event = self.get_event(source_event_id)
        if not source_event:
            raise ValueError(f"Event {source_event_id} was not found.")

        clean_event_name = str(new_event_name).strip()
        if not clean_event_name:
            raise ValueError("New event name is required.")

        new_event_id = self.generate_next_event_id()
        new_join_code = self.create_new_join_code()

        self._append_record(
            self.events,
            source_event,
            {
                "EventID": new_event_id,
                "EventName": clean_event_name,
                "Status": "Draft",
                "JoinCode": new_join_code,
                "NextTeamIndex": 0,
            },
        )

        teams_copied = self.copy_teams(source_event_id, new_event_id)
        missions_copied = self.copy_missions(source_event_id, new_event_id)
        stages = self.copy_programme_stages(source_event_id, new_event_id)

        if stages:
            first_stage = stages[0]
            self.set_event_state(
                event_id=new_event_id,
                current_stage_no=first_stage.get("StageNo", 1),
                state="Draft",
                stage_name=first_stage.get("StageName", ""),
                mission_id=first_stage.get("MissionID", ""),
                display_mode=first_stage.get("DisplayMode", "Hybrid"),
            )
        else:
            self.set_event_state(
                event_id=new_event_id,
                current_stage_no=0,
                state="Draft",
                stage_name="",
                mission_id="",
                display_mode="Hybrid",
            )

        self.clear_cache()
        return {
            "EventID": new_event_id,
            "JoinCode": new_join_code,
            "EventName": clean_event_name,
            "TeamsCopied": teams_copied,
            "MissionsCopied": missions_copied,
            "StagesCopied": len(stages),
        }

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

        # Existing participant rejoins
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

        if not teams:
            self.participants.append_row(
                [event_id, clean_name, "", 0, "Waiting"]
            )
            self.clear_cache()

            return {
                "EventID": event_id,
                "Name": clean_name,
                "Team": "",
                "Points": 0,
                "Status": "Waiting",
            }

        # ---------- Read Event ----------
        events = self.events.get_all_records()

        event_row = None
        next_team_index = 0

        for idx, event in enumerate(events, start=2):
            if str(event.get("EventID")) == str(event_id):
                event_row = idx
                try:
                    next_team_index = int(event.get("NextTeamIndex", 0))
                except Exception:
                    next_team_index = 0
                break

        if event_row is None:
            next_team_index = 0

        # ---------- Assign Team ----------
        team = teams[next_team_index % len(teams)]["TeamName"]

        # ---------- Update Pointer ----------
        new_index = (next_team_index + 1) % len(teams)

        if event_row:
            event_headers = self.events.row_values(1)
            if "NextTeamIndex" in event_headers:
                self.events.update_cell(
                    event_row,
                    event_headers.index("NextTeamIndex") + 1,
                    new_index,
                )

        # ---------- Save Participant ----------
        self.participants.append_row(
            [
                event_id,
                clean_name,
                team,
                0,
                "Waiting",
            ]
        )

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
        # Only one mission may be LIVE for an event.
        rows = get_sheet_records("Missions")
        for index, row in enumerate(rows, start=2):
            if (
                str(row.get("EventID", "")) == str(event_id)
                and str(row.get("Status", "")).upper() == "LIVE"
            ):
                self.missions.update_cell(index, 6, "CLOSED")

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
        image_url="",
        drive_file_id="",
        submitted_at="",
        score="",
        judged="No",
        remarks="",
        submission_type="",
        metric1="",
        metric2="",
        metric3="",
        status="PENDING",
    ):
        """Save a submission using the universal EXOS submission schema.

        The optional defaults preserve compatibility with older screens while
        allowing new mission forms to save structured metrics.
        """
        self.submissions.append_row([
            submission_id,
            event_id,
            mission_id,
            team_name,
            participant_name,
            image_url,
            drive_file_id,
            submission_type,
            metric1,
            metric2,
            metric3,
            score,
            status,
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
            "SubmissionType": submission_type,
            "Metric1": metric1,
            "Metric2": metric2,
            "Metric3": metric3,
            "Score": score,
            "Status": status,
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

    def get_pending_submissions(self, event_id, mission_id=None):
        rows = self.get_event_submissions(event_id)
        if mission_id is not None:
            rows = [
                row for row in rows
                if str(row.get("MissionID", "")) == str(mission_id)
            ]
        return [
            row for row in rows
            if str(row.get("Status", "PENDING")).upper() == "PENDING"
            or str(row.get("Judged", "No")).lower() not in ["yes", "true", "approved"]
        ]

    def update_submission_score(
        self,
        submission_id,
        score,
        remarks="",
        judged="Yes",
        status="APPROVED",
    ):
        rows = get_sheet_records("Submissions")
        for index, row in enumerate(rows, start=2):
            if str(row.get("SubmissionID", "")) == str(submission_id):
                self.submissions.update(f"L{index}:O{index}", [[
                    score,
                    status,
                    judged,
                    remarks,
                ]])
                self.clear_cache()
                return True
        return False

    def approve_all_pending(
        self,
        event_id,
        mission_id=None,
        default_score="",
        remarks="Bulk approved",
    ):
        pending = self.get_pending_submissions(event_id, mission_id)
        approved_count = 0
        for row in pending:
            current_score = row.get("Score", "")
            score = current_score if current_score != "" else default_score
            if self.update_submission_score(
                submission_id=row.get("SubmissionID"),
                score=score,
                remarks=remarks,
                judged="Yes",
                status="APPROVED",
            ):
                approved_count += 1
        return approved_count

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
