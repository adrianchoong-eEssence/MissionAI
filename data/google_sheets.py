import time
import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1XWCW9UVj_1cxA32ItsE8-nAr9q0NEgOhhD5e3C64Hvw"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource
def get_google_sheet():
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


@st.cache_data(ttl=20)
def cached_records(sheet_name):
    sheet = get_google_sheet()
    return sheet.worksheet(sheet_name).get_all_records()


class GoogleSheetsDB:
    def __init__(self):
        self.sheet = get_google_sheet()
        self.participants = self.sheet.worksheet("Participants")
        self.events = self.sheet.worksheet("Events")
        self.missions = self.sheet.worksheet("Missions")
        self.teams = self.sheet.worksheet("Teams")
        self.ai_facilitators = self.sheet.worksheet("AIFacilitators")
        self.conversations = self.sheet.worksheet("Conversations")
        self.submissions = self.sheet.worksheet("Submissions")

    def clear_cache(self):
        cached_records.clear()

    def create_event(self, event_id, client, department, event_name, event_date, venue, programme_type, join_code, number_of_teams):
        self.events.append_row([event_id, client, department, event_name, event_date, venue, "", "Draft", programme_type, join_code, number_of_teams])
        self.clear_cache()

    def get_events(self):
        return cached_records("Events")

    def get_event_by_join_code(self, join_code):
        for event in self.get_events():
            if str(event.get("JoinCode", "")).upper() == join_code.upper():
                return event
        return None

    def create_teams(self, event_id, number_of_teams):
        records = self.teams.get_all_records()
        rows_to_delete = []

        for index, record in enumerate(records, start=2):
            if record.get("EventID") == event_id:
                rows_to_delete.append(index)

        for row in reversed(rows_to_delete):
            self.teams.delete_rows(row)

        for i in range(1, int(number_of_teams) + 1):
            self.teams.append_row([event_id, f"TEAM-{i:02d}", f"Team {i}", "", "", 0, "Active"])

        self.clear_cache()

    def get_teams(self, event_id):
        return [team for team in cached_records("Teams") if str(team.get("EventID", "")) == str(event_id)]

    def join_player(self, event_id, name):
        teams = self.get_teams(event_id)
        participants = [p for p in self.get_players() if str(p.get("EventID", "")) == str(event_id)]

        team = teams[len(participants) % len(teams)]["TeamName"] if teams else ""

        self.participants.append_row([event_id, name, team, 0, "Waiting"])
        self.clear_cache()

        return {
            "EventID": event_id,
            "Name": name,
            "Team": team,
            "Points": 0,
            "Status": "Waiting",
        }

    def get_players(self):
        return cached_records("Participants")

    def get_player(self, event_id, name):
        for player in self.get_players():
            if str(player.get("EventID", "")) == str(event_id) and str(player.get("Name", "")).lower() == str(name).lower():
                return player
        return None

    def get_participant_count(self, event_id):
        return len([p for p in self.get_players() if str(p.get("EventID", "")) == str(event_id)])

    def get_team_count(self, event_id):
        return len(self.get_teams(event_id))

    def get_ai_facilitators(self):
        return cached_records("AIFacilitators")

    def assign_ai_facilitator(self, team_name):
        facilitators = self.get_ai_facilitators()

        if not facilitators:
            return None

        index = abs(hash(team_name)) % len(facilitators)
        return facilitators[index]

    def save_conversation(self, event_id, team, ai, role, message, timestamp):
        self.conversations.append_row([event_id, team, ai, role, message, timestamp])
        self.clear_cache()

    def get_conversation(self, event_id, team):
        return [
            row for row in cached_records("Conversations")
            if str(row.get("EventID", "")) == str(event_id)
            and str(row.get("Team", "")) == str(team)
        ]

    def send_mission(self, event_id, mission_id, title, description, points=100, submission_type="Photo", clue="", answer="", hint1="", hint2="", hint3="", ai_help_enabled="Yes"):
        self.missions.append_row([event_id, mission_id, title, description, points, "LIVE", submission_type, clue, answer, hint1, hint2, hint3, ai_help_enabled])
        self.clear_cache()

    def get_current_mission(self, event_id):
        missions = [
            mission for mission in cached_records("Missions")
            if str(mission.get("EventID", "")) == str(event_id)
            and str(mission.get("Status", "")) == "LIVE"
        ]

        return missions[-1] if missions else None

    def save_submission(self, submission_id, event_id, mission_id, team_name, participant_name, image_url, drive_file_id, submitted_at, score="", judged="No", remarks=""):
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
        rows = cached_records("Submissions")

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
            row for row in cached_records("Submissions")
            if str(row.get("EventID", "")) == str(event_id)
        ]

    def get_pending_submissions(self, event_id):
        return [
            row for row in self.get_event_submissions(event_id)
            if str(row.get("Judged", "")).lower() not in ["yes", "true", "approved"]
        ]

    def update_submission_score(self, submission_id, score, remarks="", judged="Yes"):
        rows = self.submissions.get_all_records()

        for index, row in enumerate(rows, start=2):
            if str(row.get("SubmissionID", "")) == str(submission_id):
                self.submissions.update_cell(index, 8, score)
                self.submissions.update_cell(index, 9, judged)
                self.submissions.update_cell(index, 10, remarks)
                self.clear_cache()
                return True

        return False