import io
from datetime import datetime

import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


SCOPES = ["https://www.googleapis.com/auth/drive"]


@st.cache_resource
def get_drive_service():
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

    return build("drive", "v3", credentials=credentials)


def get_or_create_folder(folder_name, parent_id):
    service = get_drive_service()

    query = (
        f"name='{folder_name}' "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and '{parent_id}' in parents "
        f"and trashed=false"
    )

    results = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name)",
    ).execute()

    folders = results.get("files", [])

    if folders:
        return folders[0]["id"]

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }

    folder = service.files().create(
        body=metadata,
        fields="id",
    ).execute()

    return folder["id"]


def upload_photo(event_id, mission_id, team_name, participant_name, uploaded_file):
    service = get_drive_service()

    root_folder_id = st.secrets["GOOGLE_DRIVE_ROOT_FOLDER"]

    event_folder_id = get_or_create_folder(
        event_id,
        root_folder_id,
    )

    mission_folder_id = get_or_create_folder(
        mission_id,
        event_folder_id,
    )

    team_folder_id = get_or_create_folder(
        team_name,
        mission_folder_id,
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    safe_team = team_name.replace(" ", "_")
    safe_name = participant_name.replace(" ", "_")

    filename = f"{event_id}_{mission_id}_{safe_team}_{safe_name}_{timestamp}.jpg"

    file_bytes = uploaded_file.getvalue()

    media = MediaIoBaseUpload(
        io.BytesIO(file_bytes),
        mimetype=uploaded_file.type,
        resumable=False,
    )

    metadata = {
        "name": filename,
        "parents": [team_folder_id],
    }

    file = service.files().create(
        body=metadata,
        media_body=media,
        fields="id, webViewLink",
    ).execute()

    file_id = file["id"]

    service.permissions().create(
        fileId=file_id,
        body={
            "type": "anyone",
            "role": "reader",
        },
    ).execute()

    return {
        "file_id": file_id,
        "url": file.get("webViewLink", ""),
        "filename": filename,
    }    def get_team_submission(self, event_id, mission_id, team_name):
        rows = self.submissions.get_all_records()

        for row in rows:
            if (
                row.get("EventID") == event_id
                and row.get("MissionID") == mission_id
                and row.get("TeamName") == team_name
            ):
                return row

        return None
