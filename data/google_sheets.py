import gspread
import copy
import hashlib
import json
import streamlit as st
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import random
import re
import string
import threading
import time

from data.runtime_database import RuntimeDatabaseError, get_runtime_database
from engines.stage_timer import new_timer, transition_timer

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
        "AIHelpEnabled", "TemplateID", "Story", "ParticipantInstructions",
        "FacilitatorInstructions", "LearningObjectives", "ScoringRule",
        "VideoURL", "ImageURL", "DocumentURL", "DebriefQuestions", "Version",
        "UpdatedAt", "Module", "Category", "IsMandatory", "DisplayOrder",
        "MainQuestion", "AlternativeAnswers", "FacilitatorEvaluationNotes",
        "AIRequired", "AIPrompt", "AIRole", "AIHintPrompt", "MaxAIHints",
        "AIUsageRules", "HintUnlockRules", "HintCreditPenalty",
        "CheckpointName", "LocationDescription", "Latitude", "Longitude",
        "GeofenceRadius", "GPSRequired", "QRRequired", "QRCodeValue",
        "QRValidationRule", "EvidenceRequired", "EvidenceInstructions",
        "MaximumUploads", "CreditValue", "MaximumCredits", "TimeBonus",
        "HintPenalty", "WrongAnswerPenalty", "ManualReviewRequired",
        "AutoApprovalAllowed", "TimeLimitMinutes", "AvailabilityStart",
        "AvailabilityEnd", "CountdownEnabled", "ReferenceImageURL",
        "LearningPoint", "FacilitatorDebriefNotes",
        "NarrativeTitle", "MissionContext", "Transmission", "MissionType",
        "Interaction", "ReasoningPrompt", "Difficulty",
        "EstimatedTimeMinutes", "MissionCompleteMessage",
        "AIRestrictions", "FacilitatorIntent", "LearningIntent", "SafetyNotes",
        "CropFramingNote", "OriginalAssetID", "CropCoordinates",
        "CharacterSource", "CharacterPortraitURL",
    ],
    "MissionTemplates": [
        "TemplateID", "Title", "Story", "ParticipantInstructions",
        "FacilitatorInstructions", "LearningObjectives", "SubmissionType",
        "ScoringRule", "Points", "VideoURL", "ImageURL", "DocumentURL",
        "Clue", "Answer", "Hint1", "Hint2", "Hint3", "DebriefQuestions",
        "AIHelpEnabled", "Status", "Version", "UpdatedAt",
        "CharacterSource", "CharacterPortraitURL",
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
        "StartTime", "DurationMinutes",
    ],
    "EventState": [
        "EventID", "CurrentStageNo", "State", "StageName", "MissionID",
        "DisplayMode", "LastUpdated",
    ],
    "ProgrammePacks": [
        "PackID", "PackName", "Description", "SourceEventID",
        "TeamsJSON", "MissionsJSON", "StagesJSON", "MarketplaceJSON",
        "CreditWalletEnabled", "Status", "Version", "CreatedAt", "UpdatedAt",
    ],
    "Assets": [
        "AssetID", "Category", "Name", "MediaReference", "FileName",
        "ContentType", "CreatedAt", "UpdatedAt",
    ],
}

RETRYABLE_SHEETS_STATUS_CODES = {429, 500, 502, 503, 504}
PARTICIPANT_COUNT_WARNING = (
    "Participant data is temporarily unavailable. Showing the last known value."
)
_LAST_SUCCESSFUL_PARTICIPANT_COUNTS = {}
_LAST_SUCCESSFUL_SHEET_RECORDS = {}
_PARTICIPANT_COUNT_LOCK = threading.RLock()
_SHEET_RECORDS_LOCK = threading.RLock()


def _sheet_status_code(error):
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is None:
        status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(error, "code", None)
    try:
        return int(status_code)
    except (TypeError, ValueError):
        return None


def _is_retryable_sheet_error(error):
    return (
        _sheet_status_code(error) in RETRYABLE_SHEETS_STATUS_CODES
        or isinstance(error, (ConnectionError, TimeoutError))
    )


def _call_sheets_with_retry(
    operation,
    *,
    attempts=4,
    base_delay_seconds=0.35,
    max_delay_seconds=3.0,
):
    last_error = None
    for attempt in range(max(1, int(attempts))):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if (
                not _is_retryable_sheet_error(error)
                or attempt >= attempts - 1
            ):
                raise

            delay = min(
                max_delay_seconds,
                base_delay_seconds * (2 ** attempt),
            )
            jitter = random.uniform(0, max(delay * 0.25, 0.01))
            time.sleep(delay + jitter)

    raise last_error


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
    return _call_sheets_with_retry(
        lambda: client.open_by_key(SPREADSHEET_ID)
    )


def ensure_worksheet(workbook, name, headers):
    try:
        worksheet = _call_sheets_with_retry(
            lambda: workbook.worksheet(name)
        )
    except gspread.WorksheetNotFound:
        worksheet = _call_sheets_with_retry(
            lambda: workbook.add_worksheet(
                title=name,
                rows=500,
                cols=max(len(headers), 10),
            )
        )
        _call_sheets_with_retry(lambda: worksheet.append_row(headers))
        return worksheet

    existing = _call_sheets_with_retry(lambda: worksheet.row_values(1))
    missing_headers = [header for header in headers if header not in existing]
    required_columns = len(existing) + len(missing_headers)
    current_columns = int(getattr(worksheet, "col_count", required_columns))
    if current_columns < required_columns:
        _call_sheets_with_retry(
            lambda: worksheet.add_cols(required_columns - current_columns)
        )

    if not existing:
        _call_sheets_with_retry(lambda: worksheet.append_row(headers))
        return worksheet

    if missing_headers:
        _call_sheets_with_retry(
            lambda: worksheet.update(
                values=[missing_headers],
                range_name=f"{gspread.utils.rowcol_to_a1(1, len(existing) + 1)}:{gspread.utils.rowcol_to_a1(1, len(existing) + len(missing_headers))}",
            )
        )

    return worksheet


@st.cache_resource
def get_worksheets():
    workbook = get_workbook()
    existing = {
        worksheet.title: worksheet
        for worksheet in _call_sheets_with_retry(workbook.worksheets)
    }

    worksheets = {}
    for name, headers in REQUIRED_WORKSHEETS.items():
        worksheets[name] = ensure_worksheet(workbook, name, headers)

    return worksheets


@st.cache_data(ttl=30)
def get_sheet_records(sheet_name):
    worksheets = get_worksheets()
    try:
        records = _call_sheets_with_retry(
            worksheets[sheet_name].get_all_records
        )
    except Exception as error:
        if not _is_retryable_sheet_error(error):
            raise
        with _SHEET_RECORDS_LOCK:
            if sheet_name not in _LAST_SUCCESSFUL_SHEET_RECORDS:
                raise
            return copy.deepcopy(
                _LAST_SUCCESSFUL_SHEET_RECORDS[sheet_name]
            )

    with _SHEET_RECORDS_LOCK:
        _LAST_SUCCESSFUL_SHEET_RECORDS[sheet_name] = copy.deepcopy(records)
    return records


@st.cache_data(ttl=30, show_spinner=False)
def get_sheet_participant_count(event_id):
    worksheets = get_worksheets()
    event_ids = _call_sheets_with_retry(
        lambda: worksheets["Participants"].col_values(1)
    )
    clean_event_id = str(event_id).strip()
    return sum(
        1
        for row_event_id in event_ids[1:]
        if str(row_event_id).strip() == clean_event_id
    )


class GoogleSheetsDB:
    def __init__(self):
        worksheets = get_worksheets()
        # Streamlit can retain the cached worksheet mapping across a hot
        # deployment. Refresh it when a newly required worksheet is absent.
        missing_worksheets = set(REQUIRED_WORKSHEETS).difference(worksheets)
        if missing_worksheets:
            get_worksheets.clear()
            worksheets = get_worksheets()
        self.runtime = get_runtime_database()
        self._participant_count_warnings = {}
        self.participants = worksheets["Participants"]
        self.events = worksheets["Events"]
        self.missions = worksheets["Missions"]
        self.mission_templates = worksheets["MissionTemplates"]
        self.teams = worksheets["Teams"]
        self.ai_facilitators = worksheets["AIFacilitators"]
        self.conversations = worksheets["Conversations"]
        self.submissions = worksheets["Submissions"]
        self.programme_stages = worksheets["ProgrammeStages"]
        self.event_state = worksheets["EventState"]
        self.programme_packs = worksheets["ProgrammePacks"]
        self.assets = worksheets["Assets"]

    def clear_cache(self):
        get_sheet_records.clear()
        get_sheet_participant_count.clear()

    # -------------------------
    # Asset Library
    # -------------------------

    def get_assets(self, category=""):
        wanted = str(category or "").strip().casefold()
        assets = list(get_sheet_records("Assets"))
        if wanted:
            assets = [
                asset for asset in assets
                if str(asset.get("Category", "")).strip().casefold() == wanted
            ]
        return sorted(
            assets,
            key=lambda asset: (
                str(asset.get("Name", "")).strip().casefold(),
                str(asset.get("AssetID", "")).strip(),
            ),
        )

    @staticmethod
    def _catalogue_asset_id(category, name, reference):
        prefix = re.sub(r"[^A-Z0-9]+", "-", str(category).upper()).strip("-")
        identity = f"{category}|{name}|{reference}".encode("utf-8")
        digest = hashlib.sha1(identity).hexdigest()[:12].upper()
        return f"{prefix}-{digest}"

    def ensure_existing_assets_catalogue(self):
        existing_references = {
            str(asset.get("MediaReference", "")).strip()
            for asset in self.get_assets()
            if str(asset.get("MediaReference", "")).strip()
        }
        candidates = {}
        records = (
            list(get_sheet_records("Missions"))
            + list(get_sheet_records("MissionTemplates"))
        )
        for record in records:
            character_name = str(record.get("CharacterSource", "")).strip()
            portrait = str(record.get("CharacterPortraitURL", "")).strip()
            if character_name and character_name.casefold() != "none" and portrait:
                candidates.setdefault(
                    portrait,
                    ("Characters", character_name),
                )

            title = str(record.get("Title", "")).strip() or "Mission Image"
            reference = str(record.get("ReferenceImageURL", "")).strip()
            if reference:
                candidates.setdefault(
                    reference,
                    ("Mission Images", title),
                )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        added = 0
        for reference, (category, name) in candidates.items():
            if reference in existing_references:
                continue
            asset_id = self._catalogue_asset_id(category, name, reference)
            self._append_record(
                self.assets,
                {
                    "AssetID": asset_id,
                    "Category": category,
                    "Name": name,
                    "MediaReference": reference,
                    "CreatedAt": now,
                    "UpdatedAt": now,
                },
            )
            existing_references.add(reference)
            added += 1
        if added:
            self.clear_cache()
        return {"Added": added}

    def ensure_existing_assets_catalogued(self):
        """Compatibility alias for deployments using the former spelling."""
        return self.ensure_existing_assets_catalogue()

    def create_asset(self, category, name, uploaded_file):
        clean_category = str(category or "").strip()
        clean_name = str(name or "").strip()
        if clean_category not in {
            "Characters", "Mission Images", "Logos", "Backgrounds",
        }:
            raise ValueError("Select a valid Asset Library category.")
        if not clean_name:
            raise ValueError("Asset name is required.")
        if uploaded_file is None:
            raise ValueError("Choose an image to upload.")

        asset_id = self._catalogue_asset_id(
            clean_category,
            clean_name,
            datetime.now().isoformat(),
        )
        from data.mission_media import upload_library_asset

        reference = upload_library_asset(uploaded_file, asset_id)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._append_record(
            self.assets,
            {
                "AssetID": asset_id,
                "Category": clean_category,
                "Name": clean_name,
                "MediaReference": reference,
                "FileName": str(getattr(uploaded_file, "name", "") or ""),
                "ContentType": str(getattr(uploaded_file, "type", "") or ""),
                "CreatedAt": now,
                "UpdatedAt": now,
            },
        )
        self.clear_cache()
        return {"AssetID": asset_id, "MediaReference": reference}

    def update_asset(self, asset_id, name="", uploaded_file=None):
        wanted = str(asset_id or "").strip()
        assets = list(get_sheet_records("Assets"))
        row_number = next(
            (
                index for index, asset in enumerate(assets, start=2)
                if str(asset.get("AssetID", "")).strip() == wanted
            ),
            None,
        )
        if row_number is None:
            raise ValueError(f"Asset {wanted} was not found.")

        payload = dict(assets[row_number - 2])
        clean_name = str(name or payload.get("Name", "")).strip()
        if not clean_name:
            raise ValueError("Asset name is required.")
        payload["Name"] = clean_name
        if uploaded_file is not None:
            from data.mission_media import upload_library_asset

            previous_reference = str(
                payload.get("MediaReference", "") or ""
            ).strip()
            payload["MediaReference"] = upload_library_asset(
                uploaded_file,
                wanted,
                current_reference=previous_reference,
            )
            payload["FileName"] = str(
                getattr(uploaded_file, "name", "") or ""
            )
            payload["ContentType"] = str(
                getattr(uploaded_file, "type", "") or ""
            )
            if payload["MediaReference"] != previous_reference:
                self._replace_asset_reference(
                    previous_reference,
                    payload["MediaReference"],
                )
        payload["UpdatedAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        headers = self.assets.row_values(1)
        values = [payload.get(header, "") for header in headers]
        end_cell = gspread.utils.rowcol_to_a1(row_number, len(headers))
        self.assets.update(
            values=[values],
            range_name=f"A{row_number}:{end_cell}",
        )
        self.clear_cache()
        return {"AssetID": wanted, "Action": "Updated"}

    def _replace_asset_reference(self, previous_reference, new_reference):
        if not previous_reference or previous_reference == new_reference:
            return 0
        updated = 0
        for sheet_name, worksheet in (
            ("Missions", self.missions),
            ("MissionTemplates", self.mission_templates),
        ):
            headers = worksheet.row_values(1)
            updates = []
            for row_number, record in enumerate(
                get_sheet_records(sheet_name),
                start=2,
            ):
                for field in (
                    "ImageURL",
                    "ReferenceImageURL",
                    "CharacterPortraitURL",
                ):
                    if (
                        field in headers
                        and str(record.get(field, "")).strip()
                        == previous_reference
                    ):
                        column = headers.index(field) + 1
                        updates.append({
                            "range": gspread.utils.rowcol_to_a1(
                                row_number,
                                column,
                            ),
                            "values": [[new_reference]],
                        })
                        updated += 1
            if updates:
                worksheet.batch_update(updates)
        return updated

    def delete_asset(self, asset_id):
        wanted = str(asset_id or "").strip()
        assets = list(get_sheet_records("Assets"))
        row_number = next(
            (
                index for index, asset in enumerate(assets, start=2)
                if str(asset.get("AssetID", "")).strip() == wanted
            ),
            None,
        )
        if row_number is None:
            raise ValueError(f"Asset {wanted} was not found.")

        asset = assets[row_number - 2]
        reference = str(asset.get("MediaReference", "")).strip()
        used_by = []
        for sheet_name in ("Missions", "MissionTemplates"):
            for record in get_sheet_records(sheet_name):
                if reference and reference in {
                    str(record.get("ImageURL", "")).strip(),
                    str(record.get("ReferenceImageURL", "")).strip(),
                    str(record.get("CharacterPortraitURL", "")).strip(),
                }:
                    used_by.append(
                        str(
                            record.get("MissionID")
                            or record.get("TemplateID")
                            or record.get("Title")
                            or "record"
                        )
                    )
        if used_by:
            raise ValueError(
                "This asset is still used by "
                + ", ".join(sorted(set(used_by))[:8])
                + ". Replace those selections before deleting it."
            )

        self.assets.delete_rows(row_number)
        if reference:
            from data.mission_media import delete_mission_media_references

            delete_mission_media_references([reference])
        self.clear_cache()
        return {"AssetID": wanted, "Action": "Deleted"}

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

    def get_events(self, include_archived=False):
        events = get_sheet_records("Events")
        if include_archived:
            return events
        return [
            event for event in events
            if str(event.get("Status", "")).strip().upper() != "ARCHIVED"
        ]

    def update_event(self, event_id, updates):
        clean_event_id = str(event_id).strip()
        rows = get_sheet_records("Events")
        row_number = next(
            (
                index for index, row in enumerate(rows, start=2)
                if str(row.get("EventID", "")).strip() == clean_event_id
            ),
            None,
        )
        if row_number is None:
            raise ValueError(f"Event {clean_event_id} was not found.")

        headers = self.events.row_values(1)
        payload = dict(rows[row_number - 2])
        payload.update({
            key: value
            for key, value in dict(updates or {}).items()
            if key in headers and key != "EventID"
        })
        values = [payload.get(header, "") for header in headers]
        end_cell = gspread.utils.rowcol_to_a1(row_number, len(headers))
        _call_sheets_with_retry(
            lambda: self.events.update(
                values=[values],
                range_name=f"A{row_number}:{end_cell}",
            )
        )
        self.clear_cache()
        return payload

    @staticmethod
    def event_metadata(event):
        raw = str((event or {}).get("Notes", "") or "").strip()
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return {"LegacyNotes": raw}
        return value if isinstance(value, dict) else {}

    def update_event_metadata(self, event_id, updates):
        event = self.get_event(event_id)
        if not event:
            raise ValueError(f"Event {event_id} was not found.")
        metadata = self.event_metadata(event)
        metadata.update(dict(updates or {}))
        return self.update_event(
            event_id,
            {"Notes": json.dumps(metadata, ensure_ascii=False, sort_keys=True)},
        )

    def get_stage_timer(self, event_id, stage_no, duration_minutes=0):
        event = self.get_event(event_id)
        metadata = self.event_metadata(event)
        timers = metadata.get("StageTimers", {}) or {}
        key = str(stage_no)
        return dict(
            timers.get(key)
            or new_timer(max(int(float(duration_minutes or 0) * 60), 0))
        )

    def update_stage_timer(
        self,
        event_id,
        stage_no,
        action,
        duration_minutes=0,
    ):
        event = self.get_event(event_id)
        metadata = self.event_metadata(event)
        timers = dict(metadata.get("StageTimers", {}) or {})
        key = str(stage_no)
        timer = timers.get(key) or new_timer(
            max(int(float(duration_minutes or 0) * 60), 0)
        )
        timers[key] = transition_timer(
            timer,
            action,
            duration_seconds=max(
                int(float(duration_minutes or 0) * 60),
                0,
            ),
        )
        metadata["StageTimers"] = timers
        self.update_event(
            event_id,
            {"Notes": json.dumps(metadata, ensure_ascii=False, sort_keys=True)},
        )
        return timers[key]

    def archive_event(self, event_id):
        return self.update_event(event_id, {"Status": "Archived"})

    def restore_event(self, event_id):
        return self.update_event(event_id, {"Status": "Draft"})

    def export_backup_snapshot(self):
        worksheets = {
            name: get_sheet_records(name)
            for name in REQUIRED_WORKSHEETS
        }
        return {
            "ExportedAt": datetime.now().isoformat(timespec="seconds"),
            "SpreadsheetID": SPREADSHEET_ID,
            "Worksheets": worksheets,
            "Events": worksheets.get("Events", []),
            "Teams": worksheets.get("Teams", []),
            "Missions": worksheets.get("Missions", []),
            "Participants": worksheets.get("Participants", []),
            "Submissions": worksheets.get("Submissions", []),
            "ProgrammeStages": worksheets.get("ProgrammeStages", []),
            "Scores": [
                row for row in worksheets.get("Submissions", [])
                if row.get("Score", "") not in ("", None)
            ],
        }

    def export_event_backup(self, event_id):
        clean_event_id = str(event_id).strip()
        event = self.get_event(clean_event_id)
        if not event:
            raise ValueError(f"Event {clean_event_id} was not found.")

        sheet_names = (
            "Events",
            "ProgrammeStages",
            "Missions",
            "Teams",
            "Participants",
            "Submissions",
            "Conversations",
            "EventState",
        )
        worksheets = {
            name: [
                row for row in get_sheet_records(name)
                if str(row.get("EventID", "")).strip() == clean_event_id
            ]
            for name in sheet_names
        }
        worksheets["ProgrammePacks"] = [
            row for row in get_sheet_records("ProgrammePacks")
            if str(row.get("SourceEventID", "")).strip() == clean_event_id
        ]

        runtime = {}
        if self.runtime.can_publish:
            runtime = self.runtime.export_event_records(clean_event_id)

        return {
            "BackupType": "EXOS Event Backup",
            "EventID": clean_event_id,
            "ExportedAt": datetime.now().isoformat(timespec="seconds"),
            "SpreadsheetID": SPREADSHEET_ID,
            "Worksheets": worksheets,
            "Runtime": runtime,
        }

    @staticmethod
    def _event_media_references(backup):
        references = []
        worksheets = (backup or {}).get("Worksheets", {}) or {}
        for mission in worksheets.get("Missions", []) or []:
            references.extend(
                mission.get(field, "")
                for field in (
                    "ImageURL", "ReferenceImageURL", "VideoURL", "DocumentURL",
                    "CharacterPortraitURL",
                )
            )
        for submission in worksheets.get("Submissions", []) or []:
            references.append(submission.get("ImageURL", ""))
        runtime = (backup or {}).get("Runtime", {}) or {}
        for submission in runtime.get("runtime_submissions", []) or []:
            references.append(submission.get("image_url", ""))
        return [str(value).strip() for value in references if str(value).strip()]

    def permanently_delete_event(self, event_id, backup):
        clean_event_id = str(event_id).strip()
        event = self.get_event(clean_event_id)
        if not event:
            raise ValueError(f"Event {clean_event_id} was not found.")
        if str(event.get("Status", "")).strip().upper() != "ARCHIVED":
            raise ValueError("Only archived events can be permanently deleted.")
        if str((backup or {}).get("EventID", "")).strip() != clean_event_id:
            raise ValueError("A successful backup for this event is required.")

        references = self._event_media_references(backup)
        submission_paths = list(dict.fromkeys([
            value.split("supabase://exos-submissions/", 1)[1]
            for value in references
            if value.startswith("supabase://exos-submissions/")
        ]))
        mission_paths = list(dict.fromkeys([
            value.split("supabase://exos-mission-media/", 1)[1]
            for value in references
            if value.startswith("supabase://exos-mission-media/")
        ]))
        protected_media = set()
        for mission in get_sheet_records("Missions"):
            if str(mission.get("EventID", "")).strip() == clean_event_id:
                continue
            protected_media.update(
                str(mission.get(field, "")).strip()
                for field in (
                    "ImageURL", "ReferenceImageURL", "VideoURL", "DocumentURL",
                    "CharacterPortraitURL",
                )
            )
        for template in get_sheet_records("MissionTemplates"):
            protected_media.update(
                str(template.get(field, "")).strip()
                for field in (
                    "ImageURL", "VideoURL", "DocumentURL",
                    "CharacterPortraitURL",
                )
            )
        mission_paths = [
            path for path in mission_paths
            if f"supabase://exos-mission-media/{path}" not in protected_media
        ]
        if self.runtime.can_publish:
            if submission_paths:
                self.runtime.delete_submission_images(submission_paths)
            if mission_paths:
                self.runtime.delete_mission_media(mission_paths)
            self.runtime.permanently_delete_event(clean_event_id)

        sheets = (
            ("Participants", self.participants),
            ("Submissions", self.submissions),
            ("Conversations", self.conversations),
            ("ProgrammeStages", self.programme_stages),
            ("Missions", self.missions),
            ("Teams", self.teams),
            ("EventState", self.event_state),
            ("Events", self.events),
        )
        deleted = {}
        for name, worksheet in sheets:
            rows = get_sheet_records(name)
            row_numbers = [
                index for index, row in enumerate(rows, start=2)
                if str(row.get("EventID", "")).strip() == clean_event_id
            ]
            for row_number in reversed(row_numbers):
                _call_sheets_with_retry(
                    lambda row_number=row_number, worksheet=worksheet:
                    worksheet.delete_rows(row_number)
                )
            deleted[name] = len(row_numbers)
        self.clear_cache()
        return {
            "EventID": clean_event_id,
            "Deleted": deleted,
            "EvidenceReferencesRemoved": len(submission_paths) + len(mission_paths),
        }

    def reset_event(self, event_id, reset_type):
        """Reset operational event data without touching programme or content."""
        clean_event_id = str(event_id).strip()
        clean_type = str(reset_type).strip().upper()
        if clean_type not in {"PARTICIPANTS", "RUNTIME", "FACTORY"}:
            raise ValueError("Select a valid event reset type.")
        if not self.get_event(clean_event_id):
            raise ValueError(f"Event {clean_event_id} was not found.")
        if self.runtime.is_configured and not self.runtime.can_publish:
            raise RuntimeDatabaseError(
                "Event reset requires the Supabase service role secret."
            )

        records = {
            name: get_sheet_records(name)
            for name in (
                "Participants",
                "Teams",
                "Submissions",
                "Conversations",
                "EventState",
            )
        }
        runtime_submissions = []
        if (
            clean_type in {"RUNTIME", "FACTORY"}
            and self.runtime.can_publish
        ):
            runtime_submissions = self.runtime.get_submissions(clean_event_id)

        submission_references = [
            str(row.get("ImageURL", "")).strip()
            for row in (
                records["Submissions"] + list(runtime_submissions or [])
            )
            if str(row.get("EventID", "")).strip() == clean_event_id
            and str(row.get("ImageURL", "")).strip().startswith(
                "supabase://exos-submissions/"
            )
        ]
        submission_paths = list(dict.fromkeys(
            reference.split("supabase://exos-submissions/", 1)[1]
            for reference in submission_references
        ))

        if clean_type in {"RUNTIME", "FACTORY"} and self.runtime.can_publish:
            if submission_paths:
                self.runtime.delete_submission_images(submission_paths)
            runtime_result = self.runtime.reset_event_data(
                clean_event_id,
                clean_type,
            )
        elif clean_type == "PARTICIPANTS" and self.runtime.can_publish:
            runtime_result = self.runtime.reset_event_data(
                clean_event_id,
                clean_type,
            )
        else:
            runtime_result = {
                "EventID": clean_event_id,
                "ResetType": clean_type,
                "RuntimeSkipped": True,
            }

        sheet_map = {
            "Participants": self.participants,
            "Teams": self.teams,
            "Submissions": self.submissions,
            "Conversations": self.conversations,
            "EventState": self.event_state,
        }
        delete_targets = {
            "PARTICIPANTS": ("Participants",),
            "RUNTIME": ("Submissions", "EventState"),
            "FACTORY": (
                "Participants",
                "Teams",
                "Submissions",
                "Conversations",
                "EventState",
            ),
        }[clean_type]
        deleted = {}
        for name in delete_targets:
            row_numbers = [
                index
                for index, row in enumerate(records[name], start=2)
                if str(row.get("EventID", "")).strip() == clean_event_id
            ]
            for row_number in reversed(row_numbers):
                worksheet = sheet_map[name]
                _call_sheets_with_retry(
                    lambda row_number=row_number, worksheet=worksheet:
                    worksheet.delete_rows(row_number)
                )
            deleted[name] = len(row_numbers)

        if clean_type == "RUNTIME":
            for name, field_updates in (
                ("Participants", {"Points": 0, "Status": "Waiting"}),
                ("Teams", {"Score": 0}),
            ):
                worksheet = sheet_map[name]
                headers = worksheet.row_values(1)
                updates = []
                for row_number, row in enumerate(records[name], start=2):
                    if str(row.get("EventID", "")).strip() != clean_event_id:
                        continue
                    for field, value in field_updates.items():
                        if field in headers:
                            updates.append({
                                "range": gspread.utils.rowcol_to_a1(
                                    row_number,
                                    headers.index(field) + 1,
                                ),
                                "values": [[value]],
                            })
                if updates:
                    _call_sheets_with_retry(
                        lambda worksheet=worksheet, updates=updates:
                        worksheet.batch_update(updates)
                    )

        event = self.get_event(clean_event_id)
        event_updates = {}
        if clean_type in {"RUNTIME", "FACTORY"}:
            metadata = self.event_metadata(event)
            metadata.pop("StageTimers", None)
            event_updates["Notes"] = (
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                if metadata else ""
            )
        if clean_type in {"PARTICIPANTS", "FACTORY"}:
            event_updates["NextTeamIndex"] = 0
        if clean_type == "FACTORY":
            event_updates["NumberOfTeams"] = 0
        self.update_event(clean_event_id, event_updates)
        self.clear_cache()
        return {
            "EventID": clean_event_id,
            "ResetType": clean_type,
            "Deleted": deleted,
            "SubmissionPhotosRemoved": len(submission_paths),
            "Runtime": runtime_result,
            "Preserved": [
                "Events",
                "ProgrammeStages",
                "Missions",
                "Assets",
            ],
        }

    def get_event_by_join_code(self, join_code):
        if self.runtime.is_configured:
            runtime_event = self.runtime.get_event_by_join_code(join_code)
            if runtime_event:
                return runtime_event

        for event in self.get_events():
            if str(event.get("JoinCode", "")).upper() == str(join_code).upper():
                return event
        return None

    def runtime_status(self):
        if not self.runtime.is_configured:
            return {
                "Configured": False,
                "PublishReady": False,
                "Message": "Supabase runtime keys have not been added.",
            }
        if not self.runtime.can_publish:
            return {
                "Configured": True,
                "PublishReady": False,
                "Message": "Runtime joins are configured, but publishing needs the secret key.",
            }
        return {
            "Configured": True,
            "PublishReady": True,
            "Message": "Transactional runtime is ready.",
        }

    def publish_event_to_runtime(self, event_id, reset_registration=False):
        event = self.get_event(event_id)
        if not event:
            raise ValueError(f"Event {event_id} was not found.")

        teams = self.get_teams(event_id)
        if not teams:
            raise ValueError("Create at least one team before publishing the event.")

        result = self.runtime.publish_event(
            event=event,
            teams=teams,
            reset_registration=reset_registration,
        )
        missions = self.get_event_missions(event_id)
        programme_result = self.runtime.publish_programme(event_id, missions)
        result.update(programme_result)

        state = self.get_event_state(event_id)
        if state:
            current_stage = next(
                (
                    stage for stage in self.get_programme_stages(event_id)
                    if str(stage.get("StageNo", ""))
                    == str(state.get("CurrentStageNo", ""))
                ),
                {
                    "StageNo": state.get("CurrentStageNo", 0),
                    "StageType": state.get("State", ""),
                    "StageName": state.get("StageName", ""),
                    "MissionID": state.get("MissionID", ""),
                    "DisplayMode": state.get("DisplayMode", "Hybrid"),
                },
            )
            self.runtime.set_event_stage(event_id, current_stage)

        return result

    def sync_runtime_participants_to_sheet(self, event_id):
        if not self.runtime.can_publish:
            raise RuntimeDatabaseError(
                "Runtime participant export requires the secret key."
            )

        runtime_players = self.runtime.get_players(event_id)
        existing_keys = {
            (
                str(player.get("EventID", "")),
                str(player.get("Name", "")).strip().lower(),
            )
            for player in get_sheet_records("Participants")
        }

        new_rows = []
        for player in runtime_players:
            key = (
                str(player.get("EventID", "")),
                str(player.get("Name", "")).strip().lower(),
            )
            if key in existing_keys:
                continue
            new_rows.append([
                player.get("EventID", ""),
                player.get("Name", ""),
                player.get("Team", ""),
                player.get("Points", 0),
                player.get("Status", "Waiting"),
            ])
            existing_keys.add(key)

        if new_rows:
            self.participants.append_rows(new_rows, value_input_option="RAW")
            self.clear_cache()

        return {
            "RuntimeParticipants": len(runtime_players),
            "RowsAdded": len(new_rows),
        }

    def sync_runtime_submissions_to_sheet(self, event_id):
        if not self.runtime.can_publish:
            raise RuntimeDatabaseError(
                "Runtime submission export requires the secret key."
            )

        runtime_submissions = self.runtime.get_submissions(event_id)
        existing_ids = {
            str(row.get("SubmissionID", ""))
            for row in get_sheet_records("Submissions")
        }
        headers = self.submissions.row_values(1)
        new_rows = []

        for submission in runtime_submissions:
            submission_id = str(submission.get("SubmissionID", ""))
            if not submission_id or submission_id in existing_ids:
                continue
            new_rows.append([
                submission.get(header, "")
                for header in headers
            ])
            existing_ids.add(submission_id)

        if new_rows:
            self.submissions.append_rows(new_rows, value_input_option="RAW")
            self.clear_cache()

        return {
            "RuntimeSubmissions": len(runtime_submissions),
            "RowsAdded": len(new_rows),
        }

    def get_event(self, event_id):
        for event in self.get_events(include_archived=True):
            if str(event.get("EventID", "")) == str(event_id):
                return event
        return None

    def generate_next_event_id(self):
        highest_number = 0
        for event in self.get_events(include_archived=True):
            event_id = str(event.get("EventID", "")).strip()
            match = re.search(r"(\d+)$", event_id)
            if match:
                highest_number = max(highest_number, int(match.group(1)))
        return f"EVT-{highest_number + 1:04d}"

    def create_new_join_code(self, length=6):
        existing_codes = {
            str(event.get("JoinCode", "")).strip().upper()
            for event in self.get_events(include_archived=True)
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
            and str(row.get("IsActive", "Yes")) != "No"
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

        runtime_published = False
        runtime_error = ""
        marketplace_items_copied = 0
        credit_wallet_copied = False
        if self.runtime.can_publish:
            try:
                self.publish_event_to_runtime(
                    new_event_id,
                    reset_registration=True,
                )
                runtime_published = True

                source_wallet = self.runtime.get_credit_wallet_status(
                    source_event_id,
                )
                source_items = source_wallet.get("Items", []) or []
                wallet_enabled = bool(source_wallet.get("Enabled"))
                if wallet_enabled or source_items:
                    self.runtime.configure_credit_wallet(
                        new_event_id,
                        enabled=wallet_enabled,
                        reset=True,
                    )
                    credit_wallet_copied = wallet_enabled
                if source_items:
                    marketplace_result = self.runtime.publish_marketplace(
                        new_event_id,
                        source_items,
                    )
                    marketplace_items_copied = int(
                        marketplace_result.get("ItemsPublished", 0) or 0
                    )
            except Exception as error:
                runtime_error = str(error)

        self.clear_cache()
        return {
            "EventID": new_event_id,
            "JoinCode": new_join_code,
            "EventName": clean_event_name,
            "TeamsCopied": teams_copied,
            "MissionsCopied": missions_copied,
            "StagesCopied": len(stages),
            "CreditWalletCopied": credit_wallet_copied,
            "MarketplaceItemsCopied": marketplace_items_copied,
            "RuntimePublished": runtime_published,
            "RuntimeError": runtime_error,
        }

    # -------------------------
    # Reusable Programme Packs
    # -------------------------

    @staticmethod
    def _decode_pack_records(value, field_name):
        if value in (None, ""):
            return []
        try:
            records = json.loads(str(value))
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Programme pack {field_name} data is invalid."
            ) from error
        if not isinstance(records, list):
            raise ValueError(
                f"Programme pack {field_name} data must be a list."
            )
        return [dict(record) for record in records if isinstance(record, dict)]

    def generate_next_pack_id(self):
        highest_number = 0
        for pack in self.get_programme_packs(include_archived=True):
            pack_id = str(pack.get("PackID", "")).strip()
            match = re.search(r"(\d+)$", pack_id)
            if match:
                highest_number = max(highest_number, int(match.group(1)))
        return f"PACK-{highest_number + 1:04d}"

    def get_programme_packs(self, include_archived=False):
        packs = get_sheet_records("ProgrammePacks")
        if not include_archived:
            packs = [
                pack for pack in packs
                if str(pack.get("Status", "ACTIVE")).strip().upper()
                != "ARCHIVED"
            ]
        return sorted(
            packs,
            key=lambda pack: (
                str(pack.get("PackName", "")).strip().lower(),
                str(pack.get("PackID", "")).strip(),
            ),
        )

    def get_programme_pack(self, pack_id):
        wanted = str(pack_id).strip()
        row = next(
            (
                pack
                for pack in self.get_programme_packs(include_archived=True)
                if str(pack.get("PackID", "")).strip() == wanted
            ),
            None,
        )
        if row is None:
            return None

        pack = dict(row)
        pack["Teams"] = self._decode_pack_records(
            row.get("TeamsJSON", "[]"),
            "teams",
        )
        pack["Missions"] = self._decode_pack_records(
            row.get("MissionsJSON", "[]"),
            "missions",
        )
        pack["Stages"] = self._decode_pack_records(
            row.get("StagesJSON", "[]"),
            "stages",
        )
        pack["Marketplace"] = self._decode_pack_records(
            row.get("MarketplaceJSON", "[]"),
            "marketplace",
        )
        pack["CreditWalletEnabled"] = str(
            row.get("CreditWalletEnabled", "")
        ).strip().lower() in {"yes", "true", "1"}
        return pack

    def save_event_as_programme_pack(
        self,
        event_id,
        pack_name,
        description="",
    ):
        event = self.get_event(event_id)
        if not event:
            raise ValueError(f"Event {event_id} was not found.")

        clean_name = str(pack_name).strip()
        if not clean_name:
            raise ValueError("Programme pack name is required.")
        for existing in self.get_programme_packs():
            if str(existing.get("PackName", "")).strip().casefold() == clean_name.casefold():
                raise ValueError(
                    "A programme pack with this name already exists."
                )

        teams = self.get_teams(event_id)
        missions = self.get_event_missions(event_id)
        stages = self.get_programme_stages(event_id)
        if not teams:
            raise ValueError("The source event has no teams.")
        if not missions:
            raise ValueError("The source event has no missions.")
        if not stages:
            raise ValueError("The source event has no programme timeline.")

        wallet_status = {}
        if self.runtime.can_publish:
            try:
                wallet_status = self.runtime.get_credit_wallet_status(event_id)
            except Exception:
                wallet_status = {}
        marketplace = wallet_status.get("Items", []) or []
        wallet_enabled = bool(wallet_status.get("Enabled"))

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pack_id = self.generate_next_pack_id()
        payload = {
            "PackID": pack_id,
            "PackName": clean_name,
            "Description": str(description).strip(),
            "SourceEventID": str(event_id),
            "TeamsJSON": json.dumps(teams, ensure_ascii=False, default=str),
            "MissionsJSON": json.dumps(missions, ensure_ascii=False, default=str),
            "StagesJSON": json.dumps(stages, ensure_ascii=False, default=str),
            "MarketplaceJSON": json.dumps(
                marketplace,
                ensure_ascii=False,
                default=str,
            ),
            "CreditWalletEnabled": "Yes" if wallet_enabled else "No",
            "Status": "ACTIVE",
            "Version": "1.0",
            "CreatedAt": timestamp,
            "UpdatedAt": timestamp,
        }
        headers = self.programme_packs.row_values(1)
        self.programme_packs.append_row(
            [payload.get(header, "") for header in headers],
            value_input_option="RAW",
        )
        self.clear_cache()
        return {
            "PackID": pack_id,
            "PackName": clean_name,
            "Teams": len(teams),
            "Missions": len(missions),
            "Stages": len(stages),
            "MarketplaceItems": len(marketplace),
        }

    def replace_event_missions(self, event_id, missions):
        clean_event_id = str(event_id).strip()
        prepared = []
        seen_ids = set()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for position, mission in enumerate(missions, start=1):
            payload = dict(mission)
            mission_id = str(
                payload.get("MissionID", "") or f"M{position:02d}"
            ).strip().upper()
            if not mission_id:
                continue
            if mission_id in seen_ids:
                raise ValueError(f"Mission ID {mission_id} is duplicated.")
            seen_ids.add(mission_id)
            payload.update({
                "EventID": clean_event_id,
                "MissionID": mission_id,
                "Status": "DRAFT",
                "UpdatedAt": timestamp,
            })
            prepared.append(payload)

        if not prepared:
            raise ValueError("The programme pack has no missions.")

        existing_rows = [
            index
            for index, row in enumerate(get_sheet_records("Missions"), start=2)
            if str(row.get("EventID", "")) == clean_event_id
        ]
        for row_number in reversed(existing_rows):
            self.missions.delete_rows(row_number)

        headers = self.missions.row_values(1)
        self.missions.append_rows(
            [
                [mission.get(header, "") for header in headers]
                for mission in prepared
            ],
            value_input_option="RAW",
        )
        self.clear_cache()
        return len(prepared)

    def install_programme_pack(self, pack_id, event_id):
        event = self.get_event(event_id)
        if not event:
            raise ValueError(f"Event {event_id} was not found.")
        pack = self.get_programme_pack(pack_id)
        if not pack:
            raise ValueError(f"Programme pack {pack_id} was not found.")

        if self.runtime.can_publish and self.runtime.get_players(event_id):
            raise ValueError(
                "Participants already exist for this event. Create or select "
                "an empty event before installing a programme pack."
            )

        teams = pack.get("Teams", [])
        missions = pack.get("Missions", [])
        stages = pack.get("Stages", [])
        marketplace = pack.get("Marketplace", [])
        if not stages:
            raise ValueError("The programme pack has no timeline stages.")

        team_result = self.replace_event_teams(event_id, teams)
        missions_installed = self.replace_event_missions(event_id, missions)
        self.save_programme_stages(event_id, stages)

        runtime_published = False
        if self.runtime.can_publish:
            self.publish_event_to_runtime(
                event_id,
                reset_registration=True,
            )
            runtime_published = True

        first_stage = sorted(
            stages,
            key=lambda stage: int(stage.get("StageNo") or 0),
        )[0]
        self.set_event_stage(event_id, first_stage)

        marketplace_items = 0
        wallet_enabled = bool(pack.get("CreditWalletEnabled"))
        if self.runtime.can_publish and (wallet_enabled or marketplace):
            self.runtime.configure_credit_wallet(
                event_id,
                enabled=wallet_enabled,
                reset=True,
            )
            if marketplace:
                marketplace_result = self.runtime.publish_marketplace(
                    event_id,
                    marketplace,
                )
                marketplace_items = int(
                    marketplace_result.get("ItemsPublished", 0) or 0
                )

        self.clear_cache()
        return {
            "PackID": str(pack_id),
            "PackName": pack.get("PackName", ""),
            "EventID": str(event_id),
            "Teams": int(team_result.get("TeamsUpdated", 0) or 0),
            "Missions": missions_installed,
            "Stages": len(stages),
            "MarketplaceItems": marketplace_items,
            "RuntimePublished": runtime_published,
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

    def replace_event_teams(self, event_id, teams):
        clean_event_id = str(event_id).strip()
        prepared = []
        seen_names = set()
        for position, team in enumerate(teams, start=1):
            team_name = str(team.get("TeamName", "")).strip()
            if not team_name:
                continue
            normalised_name = team_name.casefold()
            if normalised_name in seen_names:
                raise ValueError(f"Team name {team_name} is duplicated.")
            seen_names.add(normalised_name)
            prepared.append({
                "EventID": clean_event_id,
                "TeamID": str(
                    team.get("TeamID", "") or f"TEAM-{position:02d}"
                ).strip(),
                "TeamName": team_name,
                "Country": str(team.get("Country", "")).strip(),
                "Language": str(team.get("Language", "")).strip(),
                "Score": 0,
                "Status": "Active",
            })

        if not prepared:
            raise ValueError("Add at least one team.")

        existing_rows = [
            index
            for index, row in enumerate(get_sheet_records("Teams"), start=2)
            if str(row.get("EventID", "")) == clean_event_id
        ]
        for row_number in reversed(existing_rows):
            self.teams.delete_rows(row_number)

        headers = self.teams.row_values(1)
        self.teams.append_rows(
            [
                [team.get(header, "") for header in headers]
                for team in prepared
            ],
            value_input_option="RAW",
        )

        event_rows = get_sheet_records("Events")
        event_row_number = next(
            (
                index
                for index, row in enumerate(event_rows, start=2)
                if str(row.get("EventID", "")) == clean_event_id
            ),
            None,
        )
        if event_row_number:
            event_headers = self.events.row_values(1)
            updates = []
            if "NumberOfTeams" in event_headers:
                column = event_headers.index("NumberOfTeams") + 1
                updates.append({
                    "range": gspread.utils.rowcol_to_a1(
                        event_row_number,
                        column,
                    ),
                    "values": [[len(prepared)]],
                })
            if "NextTeamIndex" in event_headers:
                column = event_headers.index("NextTeamIndex") + 1
                updates.append({
                    "range": gspread.utils.rowcol_to_a1(
                        event_row_number,
                        column,
                    ),
                    "values": [[0]],
                })
            if updates:
                self.events.batch_update(updates)

        self.clear_cache()
        return {
            "EventID": clean_event_id,
            "TeamsUpdated": len(prepared),
        }

    # -------------------------
    # Participants
    # -------------------------

    def join_player_by_code(self, join_code, name):
        if self.runtime.is_configured:
            return self.runtime.join_player(join_code, name)

        event = self.get_event_by_join_code(join_code)
        if event is None:
            raise ValueError("Invalid Join Code")

        player = self.join_player(event["EventID"], name)
        player["EventName"] = event.get("EventName", "EXOS Event")
        player["SessionToken"] = ""
        return player

    def get_player_by_session_token(self, session_token):
        if not self.runtime.is_configured:
            return None
        return self.runtime.get_player_by_token(session_token)

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
        sheet_players = get_sheet_records("Participants")
        if not self.runtime.can_publish:
            return sheet_players

        try:
            runtime_players = self.runtime.get_players()
        except RuntimeDatabaseError:
            return sheet_players

        merged = {}
        for player in sheet_players + runtime_players:
            key = (
                str(player.get("EventID", "")),
                str(player.get("Name", "")).strip().lower(),
            )
            merged[key] = player
        return list(merged.values())

    def get_player(self, event_id, name):
        for player in self.get_players():
            if (
                str(player.get("EventID", "")) == str(event_id)
                and str(player.get("Name", "")).strip().lower() == str(name).strip().lower()
            ):
                return player
        return None

    def get_participant_count(self, event_id):
        clean_event_id = str(event_id).strip()
        if not hasattr(self, "_participant_count_warnings"):
            self._participant_count_warnings = {}
        self._participant_count_warnings[clean_event_id] = False

        runtime_count = None
        if self.runtime.can_publish:
            try:
                runtime_count = len(
                    self.runtime.get_players(clean_event_id)
                )
            except RuntimeDatabaseError:
                runtime_count = None

        try:
            sheet_count = get_sheet_participant_count(clean_event_id)
        except Exception as error:
            if not _is_retryable_sheet_error(error):
                raise

            if runtime_count is not None and runtime_count > 0:
                with _PARTICIPANT_COUNT_LOCK:
                    _LAST_SUCCESSFUL_PARTICIPANT_COUNTS[
                        clean_event_id
                    ] = runtime_count
                return runtime_count

            with _PARTICIPANT_COUNT_LOCK:
                last_known_count = _LAST_SUCCESSFUL_PARTICIPANT_COUNTS.get(
                    clean_event_id,
                    runtime_count or 0,
                )
            self._participant_count_warnings[clean_event_id] = True
            return last_known_count

        participant_count = max(runtime_count or 0, sheet_count)
        with _PARTICIPANT_COUNT_LOCK:
            _LAST_SUCCESSFUL_PARTICIPANT_COUNTS[
                clean_event_id
            ] = participant_count
        return participant_count

    def get_participant_count_warning(self, event_id):
        clean_event_id = str(event_id).strip()
        if not hasattr(self, "_participant_count_warnings"):
            return ""
        if self._participant_count_warnings.get(clean_event_id, False):
            return PARTICIPANT_COUNT_WARNING
        return ""

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

    def save_conversation(
        self,
        event_id,
        team,
        ai,
        role,
        message,
        timestamp,
        session_token="",
        mission_id="",
        hint_level=0,
    ):
        if str(session_token).strip() and self.runtime.is_configured:
            return self.runtime.save_ai_message(
                session_token=session_token,
                mission_id=mission_id,
                facilitator_name=ai,
                role=role,
                message=message,
                hint_level=hint_level,
            )

        self.conversations.append_row([event_id, team, ai, role, message, timestamp])
        self.clear_cache()
        return {
            "EventID": event_id,
            "TeamName": team,
            "FacilitatorName": ai,
            "Role": role,
            "Message": message,
            "HintLevel": hint_level,
            "CreatedAt": timestamp,
        }

    def get_ai_conversation(self, session_token, mission_id):
        if str(session_token).strip() and self.runtime.is_configured:
            return self.runtime.get_ai_conversation(
                session_token,
                mission_id,
            )
        return {
            "HintLevel": 0,
            "Messages": [],
        }

    def get_conversation(
        self,
        event_id,
        team,
        session_token="",
        mission_id="",
    ):
        if str(session_token).strip() and self.runtime.is_configured:
            state = self.get_ai_conversation(session_token, mission_id)
            return list(state.get("Messages", []) or [])

        return [
            row
            for row in get_sheet_records("Conversations")
            if str(row.get("EventID", "")) == str(event_id)
            and str(row.get("Team", "")) == str(team)
        ]

    def advance_ai_hint(self, session_token, mission_id):
        if not str(session_token).strip() or not self.runtime.is_configured:
            raise RuntimeDatabaseError(
                "Controlled hints require an active Supabase participant session."
            )
        return self.runtime.advance_ai_hint(session_token, mission_id)

    # -------------------------
    # Missions
    # -------------------------

    @staticmethod
    def _clean_record(record):
        return {
            re.sub(r"[^a-z0-9]", "", str(key).strip().lower()): value
            for key, value in dict(record or {}).items()
        }

    def generate_next_template_id(self):
        highest_number = 0
        for template in self.get_mission_templates(include_archived=True):
            template_id = str(template.get("TemplateID", "")).strip()
            match = re.search(r"(\d+)$", template_id)
            if match:
                highest_number = max(highest_number, int(match.group(1)))
        return f"MT-{highest_number + 1:04d}"

    def get_mission_templates(self, include_archived=False):
        templates = get_sheet_records("MissionTemplates")
        if not include_archived:
            templates = [
                row for row in templates
                if str(row.get("Status", "ACTIVE")).strip().upper() != "ARCHIVED"
            ]
        return sorted(
            templates,
            key=lambda row: (
                str(row.get("Title", "")).strip().lower(),
                str(row.get("TemplateID", "")).strip(),
            ),
        )

    def get_mission_template(self, template_id):
        wanted = str(template_id).strip()
        for template in self.get_mission_templates(include_archived=True):
            if str(template.get("TemplateID", "")).strip() == wanted:
                return template
        return None

    def upsert_mission_template(self, record):
        headers = self.mission_templates.row_values(1)
        source = dict(record or {})
        template_id = str(source.get("TemplateID", "")).strip().upper()
        if not template_id:
            template_id = self.generate_next_template_id()

        title = str(source.get("Title", "")).strip()
        if not title:
            raise ValueError("Mission title is required.")

        existing_rows = get_sheet_records("MissionTemplates")
        existing = next(
            (
                row for row in existing_rows
                if str(row.get("TemplateID", "")).strip() == template_id
            ),
            {},
        )
        payload = dict(existing)
        payload.update(source)
        payload.update({
            "TemplateID": template_id,
            "Title": title,
            "Status": str(source.get("Status", existing.get("Status", "ACTIVE")) or "ACTIVE").upper(),
            "Version": str(source.get("Version", existing.get("Version", "1.0")) or "1.0"),
            "UpdatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

        values = [payload.get(header, "") for header in headers]
        row_number = next(
            (
                index for index, row in enumerate(existing_rows, start=2)
                if str(row.get("TemplateID", "")).strip() == template_id
            ),
            None,
        )
        if row_number:
            end_cell = gspread.utils.rowcol_to_a1(row_number, len(headers))
            self.mission_templates.update(
                values=[values],
                range_name=f"A{row_number}:{end_cell}",
            )
            action = "Updated"
        else:
            self.mission_templates.append_row(values, value_input_option="RAW")
            action = "Created"

        self.clear_cache()
        return {"TemplateID": template_id, "Action": action}

    def import_mission_templates(self, records):
        aliases = {
            re.sub(r"[^a-z0-9]", "", header.lower()): header
            for header in REQUIRED_WORKSHEETS["MissionTemplates"]
        }
        headers = self.mission_templates.row_values(1)
        existing_rows = get_sheet_records("MissionTemplates")
        existing_by_id = {
            str(row.get("TemplateID", "")).strip().upper(): (index, row)
            for index, row in enumerate(existing_rows, start=2)
            if str(row.get("TemplateID", "")).strip()
        }
        highest_number = 0
        for template_id in existing_by_id:
            match = re.search(r"(\d+)$", template_id)
            if match:
                highest_number = max(highest_number, int(match.group(1)))

        created = 0
        updated = 0
        errors = []
        seen_ids = set()
        update_payloads = []
        append_payloads = []

        for row_number, raw_record in enumerate(records, start=2):
            cleaned = self._clean_record(raw_record)
            compatibility_aliases = {
                "missionid": "templateid",
                "missiontitle": "title",
                "description": "participantinstructions",
                "instructions": "participantinstructions",
                "facilitatorinstruction": "facilitatorinstructions",
                "learningobjective": "learningobjectives",
                "video": "videourl",
                "image": "imageurl",
                "pdfurl": "documenturl",
                "document": "documenturl",
                "debrief": "debriefquestions",
            }
            for old_name, new_name in compatibility_aliases.items():
                if new_name not in cleaned and old_name in cleaned:
                    cleaned[new_name] = cleaned[old_name]
            record = {
                header: cleaned.get(alias, "")
                for alias, header in aliases.items()
            }
            if not str(record.get("Title", "")).strip():
                errors.append(f"Row {row_number}: Title is required.")
                continue

            template_id = str(record.get("TemplateID", "")).strip().upper()
            if not template_id:
                highest_number += 1
                template_id = f"MT-{highest_number:04d}"
            if template_id in seen_ids:
                errors.append(
                    f"Row {row_number}: duplicate TemplateID {template_id} in import file."
                )
                continue
            seen_ids.add(template_id)

            existing_row_number, existing = existing_by_id.get(
                template_id,
                (None, {}),
            )
            payload = dict(existing)
            payload.update(record)
            payload.update({
                "TemplateID": template_id,
                "Title": str(record.get("Title", "")).strip(),
                "Status": str(record.get("Status", "ACTIVE") or "ACTIVE").upper(),
                "Version": str(record.get("Version", "1.0") or "1.0"),
                "UpdatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            values = [payload.get(header, "") for header in headers]

            if existing_row_number:
                end_cell = gspread.utils.rowcol_to_a1(
                    existing_row_number,
                    len(headers),
                )
                update_payloads.append({
                    "range": f"A{existing_row_number}:{end_cell}",
                    "values": [values],
                })
                updated += 1
            else:
                append_payloads.append(values)
                created += 1

        if update_payloads:
            self.mission_templates.batch_update(update_payloads)
        if append_payloads:
            self.mission_templates.append_rows(
                append_payloads,
                value_input_option="RAW",
            )
        if update_payloads or append_payloads:
            self.clear_cache()

        return {"Created": created, "Updated": updated, "Errors": errors}

    def get_event_missions(self, event_id, include_closed=True):
        wanted_event_id = str(event_id).strip().casefold()
        missions = [
            mission for mission in get_sheet_records("Missions")
            if str(mission.get("EventID", "")).strip().casefold()
            == wanted_event_id
        ]
        if not include_closed:
            missions = [
                mission for mission in missions
                if str(mission.get("Status", "")).upper() != "CLOSED"
            ]
        return sorted(
            missions,
            key=lambda row: (
                int(float(row.get("DisplayOrder", 9999) or 9999)),
                str(row.get("MissionID", "")),
            ),
        )

    def get_character_portrait(self, character_source):
        wanted = str(character_source or "").strip().casefold()
        if not wanted or wanted == "none":
            return ""
        records = (
            list(get_sheet_records("Missions"))
            + list(get_sheet_records("MissionTemplates"))
        )
        for record in records:
            source = str(record.get("CharacterSource", "")).strip().casefold()
            portrait = str(record.get("CharacterPortraitURL", "")).strip()
            if source == wanted and portrait:
                return portrait
        return ""

    def upsert_event_mission(self, record):
        payload = dict(record or {})
        event_id = str(payload.get("EventID", "")).strip()
        mission_id = str(payload.get("MissionID", "")).strip().upper()
        title = str(payload.get("Title", "")).strip()
        if not event_id or not mission_id or not title:
            raise ValueError("Event, Mission ID, and Title are required.")

        rows = get_sheet_records("Missions")
        existing = next(
            (
                row for row in rows
                if str(row.get("EventID", "")) == event_id
                and str(row.get("MissionID", "")).strip().upper() == mission_id
            ),
            {},
        )
        merged = dict(existing)
        merged.update(payload)
        merged.update({
            "EventID": event_id,
            "MissionID": mission_id,
            "Title": title,
            "Description": payload.get(
                "Description",
                payload.get("ParticipantInstructions", existing.get("Description", "")),
            ),
            "Status": str(payload.get("Status", existing.get("Status", "DRAFT")) or "DRAFT").upper(),
            "Version": str(payload.get("Version", existing.get("Version", "1.0")) or "1.0"),
            "UpdatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

        headers = self.missions.row_values(1)
        values = [merged.get(header, "") for header in headers]
        row_number = next(
            (
                index for index, row in enumerate(rows, start=2)
                if str(row.get("EventID", "")) == event_id
                and str(row.get("MissionID", "")).strip().upper() == mission_id
            ),
            None,
        )
        if row_number:
            end_cell = gspread.utils.rowcol_to_a1(row_number, len(headers))
            self.missions.update(
                values=[values],
                range_name=f"A{row_number}:{end_cell}",
            )
            action = "Updated"
        else:
            self.missions.append_row(values, value_input_option="RAW")
            action = "Created"

        self.clear_cache()
        return {"MissionID": mission_id, "Action": action}

    def add_template_to_event(self, template_id, event_id, mission_id=""):
        template = self.get_mission_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} was not found.")

        assigned_mission_id = str(mission_id).strip().upper() or str(template_id).strip().upper()
        record = dict(template)
        record.update({
            "EventID": str(event_id),
            "MissionID": assigned_mission_id,
            "TemplateID": str(template_id),
            "Description": template.get("ParticipantInstructions", ""),
            "Status": "DRAFT",
        })
        result = self.upsert_event_mission(record)
        result["TemplateID"] = str(template_id)
        return result

    def generate_next_event_mission_id(self, event_id, prefix="M"):
        highest = 0
        for mission in self.get_event_missions(event_id):
            match = re.fullmatch(
                rf"{re.escape(str(prefix).upper())}(\d+)",
                str(mission.get("MissionID", "")).strip().upper(),
            )
            if match:
                highest = max(highest, int(match.group(1)))
        return f"{str(prefix).upper()}{highest + 1:02d}"

    def duplicate_event_mission(self, event_id, mission_id, new_mission_id=""):
        source = self.get_mission(event_id, mission_id)
        if not source:
            raise ValueError(f"Mission {mission_id} was not found for {event_id}.")
        duplicate = copy.deepcopy(source)
        duplicate["MissionID"] = (
            str(new_mission_id).strip().upper()
            or self.generate_next_event_mission_id(event_id)
        )
        duplicate["Title"] = f"{source.get('Title', 'Mission')} (Copy)"
        duplicate["Status"] = "DRAFT"
        duplicate["DisplayOrder"] = len(self.get_event_missions(event_id)) + 1
        result = self.upsert_event_mission(duplicate)
        result["SourceMissionID"] = str(mission_id).strip().upper()
        return result

    def reorder_event_missions(self, event_id, mission_ids):
        rows = get_sheet_records("Missions")
        positions = {
            str(mission_id).strip().upper(): position
            for position, mission_id in enumerate(mission_ids, start=1)
        }
        headers = self.missions.row_values(1)
        order_column = headers.index("DisplayOrder") + 1
        updates = []
        for row_number, row in enumerate(rows, start=2):
            if str(row.get("EventID", "")) != str(event_id):
                continue
            mission_id = str(row.get("MissionID", "")).strip().upper()
            if mission_id in positions:
                cell = gspread.utils.rowcol_to_a1(row_number, order_column)
                updates.append({
                    "range": cell,
                    "values": [[positions[mission_id]]],
                })
        if updates:
            self.missions.batch_update(updates)
            self.clear_cache()
        return {"Updated": len(updates)}

    def delete_event_mission(self, event_id, mission_id):
        rows = get_sheet_records("Missions")
        row_number = next(
            (
                index for index, row in enumerate(rows, start=2)
                if str(row.get("EventID", "")) == str(event_id)
                and str(row.get("MissionID", "")).strip().upper()
                == str(mission_id).strip().upper()
            ),
            None,
        )
        if row_number is None:
            raise ValueError(f"Mission {mission_id} was not found for {event_id}.")
        self.missions.delete_rows(row_number)
        self.clear_cache()
        return {"MissionID": str(mission_id).strip().upper(), "Action": "Deleted"}

    def backfill_event_mission_editor_fields(self, event_id, mission_ids=None):
        wanted = {
            str(mission_id).strip().upper()
            for mission_id in (mission_ids or [])
        }
        updated = []
        for order, source in enumerate(
            self.get_event_missions(event_id), start=1,
        ):
            mission_id = str(source.get("MissionID", "")).strip().upper()
            if wanted and mission_id not in wanted:
                continue
            payload = dict(source)
            defaults = {
                "Module": "Mission AI",
                "Category": "Mission AI",
                "IsMandatory": "Yes",
                "DisplayOrder": order,
                "MainQuestion": source.get(
                    "ParticipantInstructions",
                    source.get("Description", ""),
                ),
                "AIRequired": source.get("AIHelpEnabled", "No"),
                "MaxAIHints": 3,
                "EvidenceRequired": (
                    "No"
                    if str(source.get("SubmissionType", "")).upper() == "NONE"
                    else "Yes"
                ),
                "MaximumUploads": 1,
                "CreditValue": source.get("Points", 0),
                "MaximumCredits": source.get("Points", 0),
                "ManualReviewRequired": "Yes",
                "AutoApprovalAllowed": "No",
                "CountdownEnabled": "Yes",
            }
            changed = False
            for key, value in defaults.items():
                if str(payload.get(key, "")).strip() == "":
                    payload[key] = value
                    changed = True
            if changed:
                self.upsert_event_mission(payload)
                updated.append(mission_id)
        return {"EventID": str(event_id), "Updated": updated}

    def launch_event_mission(self, event_id, mission_id):
        rows = get_sheet_records("Missions")
        target_row = None
        updates = []
        for index, row in enumerate(rows, start=2):
            if str(row.get("EventID", "")) != str(event_id):
                continue
            current_id = str(row.get("MissionID", "")).strip().upper()
            if current_id == str(mission_id).strip().upper():
                target_row = index
                updates.append({"range": f"F{index}", "values": [["LIVE"]]})
            elif str(row.get("Status", "")).upper() == "LIVE":
                updates.append({"range": f"F{index}", "values": [["CLOSED"]]})

        if target_row is None:
            raise ValueError(f"Mission {mission_id} was not found for this event.")
        if updates:
            self.missions.batch_update(updates)
        self.clear_cache()
        mission = self.get_mission(event_id, mission_id)

        if self.runtime.can_publish:
            self.runtime.publish_programme(
                event_id,
                self.get_event_missions(event_id),
            )

        state = self.get_event_state(event_id) or {}
        stage = {
            "StageNo": state.get("CurrentStageNo", 0),
            "StageName": mission.get("Title", "Mission"),
            "StageType": "MissionActive",
            "MissionID": mission.get("MissionID", mission_id),
            "DisplayMode": "Current Mission",
            "ParticipantMessage": mission.get(
                "ParticipantInstructions",
                mission.get("Description", ""),
            ),
            "FacilitatorInstruction": mission.get(
                "FacilitatorInstructions",
                "",
            ),
        }
        self.set_event_stage(event_id, stage)
        return mission

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
        story="",
        participant_instructions="",
        facilitator_instructions="",
        learning_objectives="",
        scoring_rule="",
        video_url="",
        image_url="",
        document_url="",
        debrief_questions="",
        template_id="",
    ):
        self.upsert_event_mission({
            "EventID": event_id,
            "MissionID": mission_id,
            "Title": title,
            "Description": description,
            "Points": points,
            "Status": "DRAFT",
            "SubmissionType": submission_type,
            "Clue": clue,
            "Answer": answer,
            "Hint1": hint1,
            "Hint2": hint2,
            "Hint3": hint3,
            "AIHelpEnabled": ai_help_enabled,
            "TemplateID": template_id,
            "Story": story,
            "ParticipantInstructions": participant_instructions or description,
            "FacilitatorInstructions": facilitator_instructions,
            "LearningObjectives": learning_objectives,
            "ScoringRule": scoring_rule,
            "VideoURL": video_url,
            "ImageURL": image_url,
            "DocumentURL": document_url,
            "DebriefQuestions": debrief_questions,
        })
        return self.launch_event_mission(event_id, mission_id)

    def get_current_mission(self, event_id, session_token=""):
        if self.runtime.is_configured and str(session_token).strip():
            runtime_state = self.runtime.get_participant_current_mission(
                session_token
            )
            if not runtime_state:
                return None
            mission = runtime_state.get("Mission")
            if not isinstance(mission, dict) or not mission:
                return None
            mission = dict(mission)
            try:
                latest = self.get_mission(
                    event_id,
                    mission.get("MissionID", ""),
                ) or {}
            except Exception:
                latest = {}
            for field in ("CharacterSource", "CharacterPortraitURL"):
                if field in latest:
                    mission[field] = latest.get(field, "")
            mission["_RuntimeStage"] = runtime_state.get("Stage", {})
            mission["_RuntimeStateVersion"] = runtime_state.get(
                "StateVersion",
                0,
            )
            return mission

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
        wanted_event_id = str(event_id).strip().casefold()
        wanted_mission_id = str(mission_id).strip().casefold()
        for mission in get_sheet_records("Missions"):
            if (
                str(mission.get("EventID", "")).strip().casefold()
                == wanted_event_id
                and str(mission.get("MissionID", "")).strip().casefold()
                == wanted_mission_id
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
        session_token="",
    ):
        record = {
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
            "SessionToken": session_token,
        }

        if self.runtime.is_configured:
            return self.runtime.save_submission(record)

        self.submissions.append_row([
            record.get(header, "")
            for header in self.submissions.row_values(1)
        ])
        self.clear_cache()
        return record

    def get_team_submission(self, event_id, mission_id, team_name):
        if self.runtime.is_configured:
            return self.runtime.get_submission(
                event_id,
                mission_id,
                "TEAM",
                team_name,
            )

        for row in get_sheet_records("Submissions"):
            if (
                str(row.get("EventID", "")) == str(event_id)
                and str(row.get("MissionID", "")) == str(mission_id)
                and str(row.get("TeamName", "")) == str(team_name)
            ):
                return row
        return None

    def get_participant_submission(
        self,
        event_id,
        mission_id,
        participant_name,
        session_token="",
    ):
        if self.runtime.is_configured:
            return self.runtime.get_submission(
                event_id,
                mission_id,
                "PARTICIPANT",
                participant_name,
                session_token=session_token,
            )

        for row in get_sheet_records("Submissions"):
            if (
                str(row.get("EventID", "")) == str(event_id)
                and str(row.get("MissionID", "")) == str(mission_id)
                and str(row.get("ParticipantName", "")).strip().lower()
                == str(participant_name).strip().lower()
            ):
                return row
        return None

    def get_event_submissions(self, event_id):
        sheet_rows = [
            row
            for row in get_sheet_records("Submissions")
            if str(row.get("EventID", "")) == str(event_id)
        ]
        if not self.runtime.can_publish:
            return sheet_rows

        try:
            runtime_rows = self.runtime.get_submissions(event_id)
        except RuntimeDatabaseError:
            return sheet_rows

        merged = {
            str(row.get("SubmissionID", "")): row
            for row in sheet_rows + runtime_rows
        }
        return list(merged.values())

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
        if self.runtime.can_publish:
            runtime_result = self.runtime.update_submission(
                submission_id=submission_id,
                score=score,
                remarks=remarks,
                judged=judged,
                status=status,
            )
            if runtime_result.get("Updated"):
                return True

        rows = get_sheet_records("Submissions")
        for index, row in enumerate(rows, start=2):
            if str(row.get("SubmissionID", "")) == str(submission_id):
                self.submissions.update(
                    values=[[
                        score,
                        status,
                        judged,
                        remarks,
                    ]],
                    range_name=f"L{index}:O{index}",
                )
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

        groups = []
        for row_index in existing_rows:
            if not groups or row_index != groups[-1][1] + 1:
                groups.append([row_index, row_index])
            else:
                groups[-1][1] = row_index
        for start_row, end_row in reversed(groups):
            self.programme_stages.delete_rows(start_row, end_row)

        headers = self.programme_stages.row_values(1)
        rows_to_append = []
        for stage in stages:
            payload = dict(stage)
            payload["EventID"] = event_id
            rows_to_append.append([
                payload.get(header, "")
                for header in headers
            ])
        if rows_to_append:
            self.programme_stages.append_rows(
                rows_to_append,
                value_input_option="RAW",
            )

        self.clear_cache()

    def build_event_programme(
        self,
        event_id,
        mission_plan,
        start_time="09:00",
        include_registration=True,
        registration_minutes=15,
        include_team_discovery=True,
        team_discovery_minutes=15,
        debrief_minutes=15,
        include_marketplace=False,
        marketplace_minutes=30,
        include_closing=True,
    ):
        if not self.get_event(event_id):
            raise ValueError(f"Event {event_id} was not found.")
        if not mission_plan:
            raise ValueError("Select at least one mission.")

        try:
            current_time = datetime.strptime(str(start_time), "%H:%M")
        except ValueError as error:
            raise ValueError("Programme start time must use HH:MM format.") from error

        templates = {
            str(row.get("TemplateID", "")).strip().upper(): row
            for row in self.get_mission_templates()
        }
        existing_rows = get_sheet_records("Missions")
        existing_map = {
            (
                str(row.get("EventID", "")),
                str(row.get("MissionID", "")).strip().upper(),
            ): (index, row)
            for index, row in enumerate(existing_rows, start=2)
        }
        mission_headers = self.missions.row_values(1)
        update_payloads = []
        append_payloads = []
        prepared_missions = []
        runtime_missions = []
        used_mission_ids = set()

        for position, item in enumerate(mission_plan, start=1):
            template_id = str(item.get("TemplateID", "")).strip().upper()
            template = templates.get(template_id)
            if not template:
                raise ValueError(f"Template {template_id} was not found.")

            mission_id = str(item.get("MissionID", "")).strip().upper()
            if not mission_id:
                mission_id = f"M{position:02d}"
            if mission_id in used_mission_ids:
                raise ValueError(f"Mission ID {mission_id} is duplicated in the programme.")
            used_mission_ids.add(mission_id)

            existing_row_number, existing = existing_map.get(
                (str(event_id), mission_id),
                (None, {}),
            )
            payload = dict(existing)
            payload.update(template)
            payload.update({
                "EventID": str(event_id),
                "MissionID": mission_id,
                "TemplateID": template_id,
                "Description": template.get("ParticipantInstructions", ""),
                "Status": "DRAFT",
                "UpdatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            values = [payload.get(header, "") for header in mission_headers]
            if existing_row_number:
                end_cell = gspread.utils.rowcol_to_a1(
                    existing_row_number,
                    len(mission_headers),
                )
                update_payloads.append({
                    "range": f"A{existing_row_number}:{end_cell}",
                    "values": [values],
                })
            else:
                append_payloads.append(values)

            runtime_missions.append(payload)

            prepared_missions.append({
                "MissionID": mission_id,
                "Template": template,
                "DurationMinutes": max(int(item.get("DurationMinutes") or 30), 1),
                "IncludeDebrief": bool(item.get("IncludeDebrief", True)),
            })

        if update_payloads:
            self.missions.batch_update(update_payloads)
        if append_payloads:
            self.missions.append_rows(
                append_payloads,
                value_input_option="RAW",
            )
        self.clear_cache()

        runtime_result = {"MissionsPublished": 0}
        if self.runtime.can_publish:
            runtime_result = self.runtime.publish_programme(
                event_id,
                runtime_missions,
            )

        stages = []

        def add_stage(
            stage_name,
            stage_type,
            duration,
            mission_id="",
            display_mode="Hybrid",
            participant_message="",
            facilitator_instruction="",
        ):
            nonlocal current_time
            duration_value = max(int(duration or 0), 0)
            stages.append({
                "StageNo": len(stages) + 1,
                "StageName": stage_name,
                "StageType": stage_type,
                "MissionID": mission_id,
                "DisplayMode": display_mode,
                "ParticipantMessage": participant_message,
                "FacilitatorInstruction": facilitator_instruction,
                "IsActive": "Yes",
                "StartTime": current_time.strftime("%H:%M"),
                "DurationMinutes": duration_value,
            })
            current_time += timedelta(minutes=duration_value)

        if include_registration:
            add_stage(
                "Registration",
                "Registration",
                registration_minutes,
                display_mode="Registration",
                participant_message="Scan the QR code, enter the join code, and register your name.",
                facilitator_instruction="Monitor registration and support participants who need help joining.",
            )

        if include_team_discovery:
            add_stage(
                "Team Discovery",
                "TeamDiscovery",
                team_discovery_minutes,
                display_mode="Registration",
                participant_message="Find your assigned team and gather together.",
                facilitator_instruction="Help participants locate their teams and prepare for the first mission.",
            )

        for prepared in prepared_missions:
            template = prepared["Template"]
            mission_id = prepared["MissionID"]
            add_stage(
                str(template.get("Title", mission_id)),
                "MissionActive",
                prepared["DurationMinutes"],
                mission_id=mission_id,
                display_mode="Current Mission",
                participant_message=str(
                    template.get("ParticipantInstructions", "")
                ),
                facilitator_instruction=str(
                    template.get("FacilitatorInstructions", "")
                ),
            )
            if prepared["IncludeDebrief"]:
                debrief_questions = str(
                    template.get("DebriefQuestions", "")
                ).strip()
                add_stage(
                    f"{template.get('Title', mission_id)} — Debrief",
                    "Debrief",
                    debrief_minutes,
                    mission_id=mission_id,
                    display_mode="Collaboration",
                    participant_message=(
                        "Reflect on the mission and prepare to share your learning."
                    ),
                    facilitator_instruction=(
                        debrief_questions
                        or "Connect the experience to workplace behaviour and application."
                    ),
                )

        if include_marketplace:
            add_stage(
                "Team Marketplace",
                "Marketplace",
                marketplace_minutes,
                display_mode="Credit Leaderboard",
                participant_message=(
                    "Review your team's available credits and purchase the "
                    "resources you need for the next phase."
                ),
                facilitator_instruction=(
                    "Open the marketplace, monitor team balances and purchases, "
                    "and close sales before the build phase begins."
                ),
            )

        if include_closing:
            add_stage(
                "Closing",
                "Closing",
                10,
                display_mode="Winner",
                participant_message="Thank you for completing the experience together.",
                facilitator_instruction="Close with key learning, commitments, and recognition.",
            )

        self.save_programme_stages(event_id, stages)
        if stages:
            self.set_event_stage(event_id, stages[0])

        return {
            "Missions": len(prepared_missions),
            "Stages": len(stages),
            "ProgrammeEndTime": current_time.strftime("%H:%M"),
            "RowsCreated": len(append_payloads),
            "RowsUpdated": len(update_payloads),
            "RuntimeMissions": runtime_result.get("MissionsPublished", 0),
        }

    def get_event_state(self, event_id):
        if self.runtime.can_publish:
            try:
                runtime_state = self.runtime.get_event_stage(event_id)
            except RuntimeDatabaseError:
                runtime_state = None
            if runtime_state:
                return runtime_state

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
        stage_payload=None,
    ):
        runtime_result = None
        runtime_stage = dict(stage_payload or {})
        runtime_stage.update({
            "StageNo": current_stage_no,
            "StageType": state,
            "StageName": stage_name,
            "MissionID": mission_id,
            "DisplayMode": display_mode,
        })
        if self.runtime.can_publish:
            if (
                str(mission_id).strip()
                and not self.runtime.has_event_mission(
                    event_id,
                    mission_id,
                )
            ):
                event_missions = self.get_event_missions(event_id)
                if not any(
                    str(row.get("MissionID", "")) == str(mission_id)
                    for row in event_missions
                ):
                    raise ValueError(
                        f"Mission {mission_id} was not found for event {event_id}."
                    )
                self.runtime.publish_programme(
                    event_id,
                    event_missions,
                )
            runtime_result = self.runtime.set_event_stage(
                event_id,
                runtime_stage,
            )

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

        sheet_updated = False
        sheet_warning = ""
        try:
            rows = get_sheet_records("EventState")
            for index, row in enumerate(rows, start=2):
                if str(row.get("EventID", "")) == str(event_id):
                    self.event_state.update(
                        values=[payload],
                        range_name=f"A{index}:G{index}",
                    )
                    sheet_updated = True
                    break

            if not sheet_updated:
                self.event_state.append_row(payload)
                sheet_updated = True
            self.clear_cache()
        except Exception as error:
            if runtime_result is None:
                raise
            sheet_warning = (
                "The live stage changed successfully, but Google Sheets "
                f"did not record the change: {error}"
            )

        return {
            "RuntimeUpdated": runtime_result is not None,
            "SheetUpdated": sheet_updated,
            "Warning": sheet_warning,
        }

    def set_event_stage(self, event_id, stage):
        return self.set_event_state(
            event_id=event_id,
            current_stage_no=stage.get("StageNo", ""),
            state=stage.get("StageType", ""),
            stage_name=stage.get("StageName", ""),
            mission_id=stage.get("MissionID", ""),
            display_mode=stage.get("DisplayMode", "Hybrid"),
            stage_payload=stage,
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
