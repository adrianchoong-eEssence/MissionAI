import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1XWCW9UVj_1cxA32ItsE8-nAr9q0NEgOhhD5e3C64Hvw"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


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


@st.cache_resource
def get_worksheets():
    workbook = get_workbook()

    return {
        "Participants": workbook.worksheet("Participants"),
        "Events": workbook.worksheet("Events"),
        "Missions": workbook.worksheet("Missions"),
        "Teams": workbook.worksheet("Teams"),
        "AIFacilitators": workbook.worksheet("AIFacilitators"),
        "Conversations": workbook.worksheet("Conversations"),
        "Submissions": workbook.worksheet("Submissions"),
    }


@st.cache_data(ttl=60)
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

    def clear_cache(self):
        get_sheet_records.clear()

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

    def create_teams(self, event_id, number_of_teams):
        records = get_sheet_records("Teams")
        rows_to_delete = []

        for index, record in enumerate(records, start=2):
            if str(record.get("EventID", "")) == str(event_id):
                rows_to_delete.append(index)

        for row in reversed(rows_to_delete):
            self.teams.delete_rows(row)

        for i in range(1, int(number_of_teams) + 1):
            self.teams.append_row([
                event_id,
                f"TEAM-{i:02d}",
                f"Team {i}",
                "",
                "",
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

    def join_player(self, event_id, name):
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

        self.participants.append_row([
            event_id,
            name,
            team,
            0,
            "Waiting",
        ])

        self.clear_cache()

        return {
            "EventID": event_id,
            "Name": name,
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
                and str(player.get("Name", "")).lower() == str(name).lower()
            ):
                return player
        return None

    def get_participant_count(self, event_id):
        return len([
            p
            for p in self.get_players()
            if str(p.get("EventID", "")) == str(event_id)
        ])

    def get_team_count(self, event_id):
        return len(self.get_teams(event_id))

    def get_ai_facilitators(self):
        return get_sheet_records("AIFacilitators")

    def assign_ai_facilitator(self, team_name):
        facilitators = self.get_ai_facilitators()

        if not facilitators:
            return None

        index = abs(hash(team_name)) % len(facilitators)
        return facilitators[index]

    def save_conversation(
        self,
        event_id,
        team,
        ai,
        role,
        message,
        timestamp,
    ):
        self.conversations.append_row([
            event_id,
            team,
            ai,
            role,
            message,
            timestamp,
        ])
        self.clear_cache()

    def get_conversation(self, event_id, team):
        return [
            row
            for row in get_sheet_records("Conversations")
            if str(row.get("EventID", "")) == str(event_id)
            and str(row.get("Team", "")) == str(team)
        ]

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
        missions = [
            mission
            for mission in get_sheet_records("Missions")
            if str(mission.get("EventID", "")) == str(event_id)
            and str(mission.get("Status", "")) == "LIVE"
        ]

        if not missions:
            return None

        return missions[-1]

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
        rows = get_sheet_records("Submissions")

        for row in rows:
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
            if str(row.get("Judged", "")).lower()
            not in ["yes", "true", "approved"]
        ]

    def update_submission_score(
        self,
        submission_id,
        score,
        remarks="",
        judged="Yes",
    ):
        rows = get_sheet_records("Submissions")

        for index, row in enumerate(rows, start=2):
            if str(row.get("SubmissionID", "")) == str(submission_id):
                self.submissions.update_cell(index, 8, score)
                self.submissions.update_cell(index, 9, judged)
                self.submissions.update_cell(index, 10, remarks)
                self.clear_cache()
                return True

        return False