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


class GoogleSheetsDB:

    def __init__(self):

        self.sheet = get_google_sheet()

        self.participants = self.sheet.worksheet("Participants")
        self.events = self.sheet.worksheet("Events")
        self.missions = self.sheet.worksheet("Missions")
        self.teams = self.sheet.worksheet("Teams")
        self.ai_facilitators = self.sheet.worksheet("AIFacilitators")
        self.conversations = self.sheet.worksheet("Conversations")
    # Events

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

    def get_events(self):
        return self.events.get_all_records()

    def get_event_by_join_code(self, join_code):
        for event in self.get_events():
            if str(event.get("JoinCode", "")).upper() == join_code.upper():
                return event
        return None

    # Teams

    def create_teams(self, event_id, number_of_teams):
        records = self.teams.get_all_records()
        rows_to_delete = []

        for index, record in enumerate(records, start=2):
            if record.get("EventID") == event_id:
                rows_to_delete.append(index)

        for row in reversed(rows_to_delete):
            self.teams.delete_rows(row)

        for i in range(1, number_of_teams + 1):
            self.teams.append_row([
                event_id,
                f"TEAM-{i:02d}",
                f"Team {i}",
                "",
                "",
                0,
                "Active",
            ])

    def get_teams(self, event_id):
        return [
            team
            for team in self.teams.get_all_records()
            if team.get("EventID") == event_id
        ]

    # Participants

    def join_player(self, event_id, name):
        teams = self.get_teams(event_id)

        if teams:
            participants = [
                p for p in self.get_players()
                if p.get("EventID") == event_id
            ]
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

        return {
            "EventID": event_id,
            "Name": name,
            "Team": team,
            "Points": 0,
            "Status": "Waiting",
        }

    def get_players(self):
        return self.participants.get_all_records()

    def get_player(self, event_id, name):
        for player in self.get_players():
            if (
                player.get("EventID") == event_id
                and str(player.get("Name", "")).lower() == name.lower()
            ):
                return player
        return None

    # Dashboard

    def get_participant_count(self, event_id):
        return len([
            p for p in self.get_players()
            if p.get("EventID") == event_id
        ])

    def get_team_count(self, event_id):
        return len(self.get_teams(event_id))

    # AI Facilitators

    def get_ai_facilitators(self):
        return self.ai_facilitators.get_all_records()

    def assign_ai_facilitator(self, team_name):
        facilitators = self.get_ai_facilitators()

        if not facilitators:
            return None

        index = abs(hash(team_name)) % len(facilitators)
        return facilitators[index]

    # Conversations

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

    def get_conversation(self, event_id, team):
        records = self.conversations.get_all_records()

        return [
            row
            for row in records
            if row.get("EventID") == event_id
            and row.get("Team") == team
        ]

    # Missions

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

    def get_current_mission(self, event_id):
        missions = self.missions.get_all_records()

        live_missions = [
            mission
            for mission in missions
            if mission.get("EventID") == event_id
            and mission.get("Status") == "LIVE"
        ]

        if not live_missions:
            return None

        return live_missions[-1]