#!/usr/bin/env python3
"""Back up and audit one EXOS Google Sheets event before safe clean-up.

The default mode is read-only. It exports every worksheet, creates machine and
human audit reports, and records only deletion candidates that are safe enough
to review. Production changes require both --apply and --confirm-event-id.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

import gspread
from google.oauth2.service_account import Credentials


DEFAULT_SPREADSHEET_ID = "1XWCW9UVj_1cxA32ItsE8-nAr9q0NEgOhhD5e3C64Hvw"
DEFAULT_EVENT_ID = "EVT-0001"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
)

EXPECTED_HEADERS = {
    "Events": [
        "EventID",
        "Client",
        "Department",
        "EventName",
        "EventDate",
        "Venue",
        "Facilitator",
        "Status",
        "ProgrammeType",
        "JoinCode",
        "NextTeamIndex",
        "NumberOfTeams",
        "Notes",
    ],
    "Participants": [
        "EventID",
        "Name",
        "Team",
        "Points",
        "Status",
        "ParticipantID",
        "TeamID",
        "JoinedAt",
        "LastSeenAt",
    ],
    "Teams": [
        "EventID",
        "TeamID",
        "TeamName",
        "Members",
        "Facilitator",
        "Score",
        "Status",
    ],
    "Missions": [
        "EventID",
        "MissionID",
        "Title",
        "Description",
        "Points",
        "Status",
        "SubmissionType",
        "Clue",
        "Answer",
        "Hint1",
        "Hint2",
        "Hint3",
        "AIHelpEnabled",
        "TemplateID",
        "Story",
        "ParticipantInstructions",
        "FacilitatorInstructions",
        "LearningObjectives",
        "ScoringRule",
        "VideoURL",
        "ImageURL",
        "DocumentURL",
        "DebriefQuestions",
        "Version",
        "UpdatedAt",
    ],
    "Submissions": [
        "SubmissionID",
        "EventID",
        "MissionID",
        "TeamName",
        "ParticipantName",
        "ImageURL",
        "DriveFileID",
        "SubmissionType",
        "Metric1",
        "Metric2",
        "Metric3",
        "Score",
        "Status",
        "Judged",
        "Remarks",
        "SubmittedAt",
    ],
    "ProgrammeStages": [
        "EventID",
        "StageNo",
        "StageName",
        "StageType",
        "MissionID",
        "DisplayMode",
        "ParticipantMessage",
        "FacilitatorInstruction",
        "IsActive",
        "StartTime",
        "DurationMinutes",
    ],
    "EventState": [
        "EventID",
        "CurrentStageNo",
        "State",
        "StageName",
        "MissionID",
        "DisplayMode",
        "LastUpdated",
    ],
}


@dataclass
class SheetSnapshot:
    title: str
    sheet_id: int
    row_count: int
    column_count: int
    values: list[list[str]]
    formulas: list[list[str]]
    merges: list[dict[str, Any]]

    @property
    def headers(self) -> list[str]:
        return [str(value).strip() for value in (self.values[0] if self.values else [])]

    @property
    def last_populated_row(self) -> int:
        last_row = 0
        for index, row in enumerate(self.values, start=1):
            if any(str(value).strip() for value in row):
                last_row = index
        return last_row

    @property
    def last_populated_column(self) -> int:
        last_column = 0
        for row in self.values:
            for index, value in enumerate(row, start=1):
                if str(value).strip():
                    last_column = max(last_column, index)
        return last_column

    def records(self) -> list[dict[str, Any]]:
        if not self.headers:
            return []
        output = []
        for row_number, row in enumerate(self.values[1:], start=2):
            padded = list(row) + [""] * max(0, len(self.headers) - len(row))
            output.append(
                {
                    "_row_number": row_number,
                    "_values": padded[: len(self.headers)],
                    **dict(zip(self.headers, padded[: len(self.headers)])),
                }
            )
        return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up and audit the first AIA EXOS project.",
    )
    parser.add_argument("--spreadsheet-id", default=DEFAULT_SPREADSHEET_ID)
    parser.add_argument("--event-id", default=DEFAULT_EVENT_ID)
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--output-root", default="backups")
    parser.add_argument("--backup-name", default="")
    parser.add_argument("--drive-backup-id", default="")
    parser.add_argument("--drive-backup-url", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-event-id", default="")
    parser.add_argument(
        "--review-report",
        default="",
        help="Path to the exact dry-run JSON being approved for --apply.",
    )
    return parser.parse_args()


def status_code(error: Exception) -> int | None:
    response = getattr(error, "response", None)
    code = getattr(response, "status_code", None)
    if code is not None:
        try:
            return int(code)
        except (TypeError, ValueError):
            return None
    match = re.search(r"\[(\d{3})\]", str(error))
    return int(match.group(1)) if match else None


def with_retry(
    operation: Callable[[], Any],
    *,
    attempts: int = 6,
    base_delay: float = 0.6,
    max_delay: float = 8.0,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except gspread.exceptions.APIError as error:
            last_error = error
            if status_code(error) not in RETRYABLE_STATUS_CODES:
                raise
        except (TimeoutError, ConnectionError) as error:
            last_error = error

        if attempt < attempts - 1:
            delay = min(max_delay, base_delay * (2**attempt))
            time.sleep(delay + random.uniform(0, delay * 0.25))
    if last_error:
        raise last_error
    raise RuntimeError("Google Sheets request failed without an exception.")


def authorise(credentials_path: Path) -> gspread.Client:
    credentials = Credentials.from_service_account_file(
        str(credentials_path),
        scopes=SCOPES,
    )
    return gspread.authorize(credentials)


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "sheet"


def normalise(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def row_signature(row: dict[str, Any], ignored: Iterable[str] = ()) -> tuple[str, ...]:
    ignored_fields = set(ignored) | {"_row_number", "_values"}
    return tuple(
        normalise(row.get(key, ""))
        for key in sorted(key for key in row if key not in ignored_fields)
    )


def parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        pass
    for timestamp_format in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(candidate, timestamp_format)
        except ValueError:
            continue
    return None


def valid_media_reference(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text.startswith("supabase://"):
        return True
    parsed = urlparse(text)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def trim_matrix(matrix: list[list[Any]]) -> list[list[str]]:
    rows = [[str(value) for value in row] for row in matrix]
    while rows and not any(value.strip() for value in rows[-1]):
        rows.pop()
    last_column = 0
    for row in rows:
        for column, value in enumerate(row, start=1):
            if value.strip():
                last_column = max(last_column, column)
    return [row[:last_column] for row in rows] if last_column else []


def fetch_snapshots(workbook: gspread.Spreadsheet) -> tuple[dict[str, SheetSnapshot], dict]:
    metadata = with_retry(workbook.fetch_sheet_metadata)
    sheet_metadata = metadata.get("sheets", [])
    titles = [
        sheet.get("properties", {}).get("title", "")
        for sheet in sheet_metadata
        if sheet.get("properties", {}).get("title")
    ]
    ranges = [f"'{title.replace(chr(39), chr(39) * 2)}'" for title in titles]

    displayed = with_retry(
        lambda: workbook.values_batch_get(
            ranges,
            params={"valueRenderOption": "FORMATTED_VALUE"},
        )
    )
    formulas = with_retry(
        lambda: workbook.values_batch_get(
            ranges,
            params={"valueRenderOption": "FORMULA"},
        )
    )
    displayed_by_range = {
        item.get("range", ""): item.get("values", [])
        for item in displayed.get("valueRanges", [])
    }
    formulas_by_range = {
        item.get("range", ""): item.get("values", [])
        for item in formulas.get("valueRanges", [])
    }

    snapshots: dict[str, SheetSnapshot] = {}
    for sheet in sheet_metadata:
        properties = sheet.get("properties", {})
        title = properties.get("title", "")
        quoted_title = f"'{title.replace(chr(39), chr(39) * 2)}'"
        value_key = next(
            (
                key
                for key in displayed_by_range
                if key == quoted_title or key.startswith(f"{quoted_title}!")
                or key == title or key.startswith(f"{title}!")
            ),
            "",
        )
        formula_key = next(
            (
                key
                for key in formulas_by_range
                if key == quoted_title or key.startswith(f"{quoted_title}!")
                or key == title or key.startswith(f"{title}!")
            ),
            "",
        )
        grid = properties.get("gridProperties", {})
        snapshots[title] = SheetSnapshot(
            title=title,
            sheet_id=int(properties.get("sheetId", 0)),
            row_count=int(grid.get("rowCount", 0)),
            column_count=int(grid.get("columnCount", 0)),
            values=trim_matrix(displayed_by_range.get(value_key, [])),
            formulas=trim_matrix(formulas_by_range.get(formula_key, [])),
            merges=list(sheet.get("merges", [])),
        )
    return snapshots, metadata


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_snapshots(
    backup_dir: Path,
    snapshots: dict[str, SheetSnapshot],
    metadata: dict,
    *,
    spreadsheet_id: str,
    event_id: str,
    drive_backup_id: str,
    drive_backup_url: str,
) -> dict[str, Any]:
    csv_dir = backup_dir / "csv"
    json_dir = backup_dir / "json"
    formula_dir = backup_dir / "formulas"
    csv_dir.mkdir(parents=True, exist_ok=False)
    json_dir.mkdir(parents=True, exist_ok=False)
    formula_dir.mkdir(parents=True, exist_ok=False)

    files = []
    for title, snapshot in snapshots.items():
        file_stem = safe_filename(title)
        csv_path = csv_dir / f"{file_stem}.csv"
        json_path = json_dir / f"{file_stem}.json"
        formula_path = formula_dir / f"{file_stem}.formulas.json"

        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            csv.writer(handle).writerows(snapshot.values)
        json_path.write_text(
            json.dumps(
                {
                    "sheet": title,
                    "sheet_id": snapshot.sheet_id,
                    "values": snapshot.values,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        formula_path.write_text(
            json.dumps(
                {
                    "sheet": title,
                    "sheet_id": snapshot.sheet_id,
                    "formulas": snapshot.formulas,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        for path in (csv_path, json_path, formula_path):
            files.append(
                {
                    "path": str(path.relative_to(backup_dir)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )

    metadata_path = backup_dir / "spreadsheet_metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    files.append(
        {
            "path": metadata_path.name,
            "bytes": metadata_path.stat().st_size,
            "sha256": sha256(metadata_path),
        }
    )

    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "source_spreadsheet_id": spreadsheet_id,
        "target_event_id": event_id,
        "drive_backup_id": drive_backup_id,
        "drive_backup_url": drive_backup_url,
        "worksheet_count": len(snapshots),
        "worksheets": {
            title: {
                "sheet_id": snapshot.sheet_id,
                "grid_rows": snapshot.row_count,
                "grid_columns": snapshot.column_count,
                "exported_rows": len(snapshot.values),
                "exported_columns": max(
                    (len(row) for row in snapshot.values),
                    default=0,
                ),
                "headers": snapshot.headers,
            }
            for title, snapshot in snapshots.items()
        },
        "files": files,
        "restore_ready": bool(files and snapshots),
    }
    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (backup_dir / "RESTORE.md").write_text(
        "\n".join(
            [
                "# EXOS Workbook Restore",
                "",
                "Preferred rollback: open the Drive backup and replace the source",
                "workbook only after confirming the backup title and timestamp.",
                "",
                "Row-level rollback: import the matching CSV or JSON export into a",
                "temporary workbook, compare the target EventID, then restore only",
                "the affected rows. Never overwrite unrelated event rows.",
                "",
                f"Source spreadsheet: {spreadsheet_id}",
                f"Drive backup: {drive_backup_url or drive_backup_id or 'not recorded'}",
                f"Target event: {event_id}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def rows_for_event(snapshot: SheetSnapshot | None, event_id: str) -> list[dict[str, Any]]:
    if snapshot is None or "EventID" not in snapshot.headers:
        return []
    return [
        row
        for row in snapshot.records()
        if str(row.get("EventID", "")).strip() == event_id
    ]


def duplicates_by(
    rows: list[dict[str, Any]],
    fields: Iterable[str],
    *,
    ignore_blank: bool = True,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    field_list = list(fields)
    for row in rows:
        key = tuple(normalise(row.get(field, "")) for field in field_list)
        if ignore_blank and not any(key):
            continue
        grouped[key].append(row)
    return [
        {
            "fields": field_list,
            "key": list(key),
            "rows": [row["_row_number"] for row in matches],
        }
        for key, matches in grouped.items()
        if len(matches) > 1
    ]


def exact_duplicate_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not any(str(value).strip() for value in row.get("_values", [])):
            continue
        grouped[tuple(str(value) for value in row.get("_values", []))].append(row)
    return [
        {
            "rows": [row["_row_number"] for row in matches],
            "keep_row": matches[0]["_row_number"],
            "safe_delete_rows": [
                row["_row_number"]
                for row in matches[1:]
            ],
        }
        for matches in grouped.values()
        if len(matches) > 1
    ]


def blank_rows(snapshot: SheetSnapshot) -> list[int]:
    return [
        row_number
        for row_number, row in enumerate(snapshot.values[1:], start=2)
        if not any(str(value).strip() for value in row)
    ]


def formula_cells(snapshot: SheetSnapshot) -> list[dict[str, Any]]:
    cells = []
    for row_number, row in enumerate(snapshot.formulas, start=1):
        for column_number, value in enumerate(row, start=1):
            if str(value).startswith("="):
                cells.append(
                    {
                        "row": row_number,
                        "column": column_number,
                        "formula": value,
                    }
                )
    return cells


def inspect_sheet_structure(snapshot: SheetSnapshot) -> dict[str, Any]:
    expected = EXPECTED_HEADERS.get(snapshot.title)
    missing_headers = []
    unexpected_headers = []
    header_order_matches = None
    if expected is not None:
        missing_headers = [header for header in expected if header not in snapshot.headers]
        unexpected_headers = [header for header in snapshot.headers if header not in expected]
        header_order_matches = snapshot.headers == expected
    last_row = snapshot.last_populated_row
    last_column = snapshot.last_populated_column
    return {
        "grid_rows": snapshot.row_count,
        "grid_columns": snapshot.column_count,
        "last_populated_row": last_row,
        "last_populated_column": last_column,
        "trailing_blank_rows": max(0, snapshot.row_count - last_row),
        "trailing_blank_columns": max(0, snapshot.column_count - last_column),
        "blank_rows_within_export": blank_rows(snapshot),
        "merged_ranges": snapshot.merges,
        "formula_cells": formula_cells(snapshot),
        "headers": snapshot.headers,
        "missing_expected_headers": missing_headers,
        "unexpected_headers": unexpected_headers,
        "header_order_matches_expected": header_order_matches,
    }


def build_audit(
    snapshots: dict[str, SheetSnapshot],
    *,
    event_id: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    events = snapshots.get("Events")
    event_matches = rows_for_event(events, event_id)
    if len(event_matches) != 1:
        raise RuntimeError(
            f"Expected exactly one Events row for {event_id}; found {len(event_matches)}."
        )
    event = event_matches[0]

    teams = rows_for_event(snapshots.get("Teams"), event_id)
    participants = rows_for_event(snapshots.get("Participants"), event_id)
    missions = rows_for_event(snapshots.get("Missions"), event_id)
    submissions = rows_for_event(snapshots.get("Submissions"), event_id)
    stages = rows_for_event(snapshots.get("ProgrammeStages"), event_id)
    event_state = rows_for_event(snapshots.get("EventState"), event_id)

    team_names = {
        normalise(team.get("TeamName", ""))
        for team in teams
        if normalise(team.get("TeamName", ""))
    }
    team_ids = {
        normalise(team.get("TeamID", ""))
        for team in teams
        if normalise(team.get("TeamID", ""))
    }
    mission_ids = {
        normalise(mission.get("MissionID", ""))
        for mission in missions
        if normalise(mission.get("MissionID", ""))
    }
    participant_names = {
        normalise(participant.get("Name", ""))
        for participant in participants
        if normalise(participant.get("Name", ""))
    }

    participant_exact = exact_duplicate_groups(participants)
    participant_id_duplicates = duplicates_by(participants, ["ParticipantID"])
    participant_name_duplicates = duplicates_by(participants, ["Name"])
    participant_normalised_name_duplicates = participant_name_duplicates
    participant_multi_team = []
    names_to_teams: dict[str, set[str]] = defaultdict(set)
    names_to_rows: dict[str, list[int]] = defaultdict(list)
    for participant in participants:
        name = normalise(participant.get("Name", ""))
        team = normalise(participant.get("Team", ""))
        if name:
            if team:
                names_to_teams[name].add(team)
            names_to_rows[name].append(participant["_row_number"])
    for name, assigned_teams in names_to_teams.items():
        if len(assigned_teams) > 1:
            participant_multi_team.append(
                {
                    "normalised_name": name,
                    "teams": sorted(assigned_teams),
                    "rows": names_to_rows[name],
                }
            )

    timestamp_clusters = []
    timed_participants = []
    malformed_participant_timestamps = []
    for participant in participants:
        for field in ("JoinedAt", "LastSeenAt"):
            value = participant.get(field, "")
            if str(value).strip() and parse_timestamp(value) is None:
                malformed_participant_timestamps.append(
                    {
                        "row": participant["_row_number"],
                        "field": field,
                        "value": value,
                    }
                )
        joined_at = parse_timestamp(participant.get("JoinedAt", ""))
        if joined_at:
            timed_participants.append((joined_at, participant))
    timed_participants.sort(key=lambda item: item[0])
    for index, (joined_at, participant) in enumerate(timed_participants):
        matches = [participant]
        cursor = index + 1
        while cursor < len(timed_participants):
            next_time, next_participant = timed_participants[cursor]
            if abs((next_time - joined_at).total_seconds()) > 5:
                break
            matches.append(next_participant)
            cursor += 1
        if len(matches) > 1:
            key = tuple(sorted(row["_row_number"] for row in matches))
            if not any(tuple(group["rows"]) == key for group in timestamp_clusters):
                timestamp_clusters.append(
                    {
                        "rows": list(key),
                        "start": joined_at.isoformat(),
                        "window_seconds": 5,
                    }
                )

    participant_no_team = [
        row["_row_number"]
        for row in participants
        if not normalise(row.get("Team", "")) and not normalise(row.get("TeamID", ""))
    ]
    participant_invalid_team = [
        {
            "row": row["_row_number"],
            "team": row.get("Team", ""),
            "team_id": row.get("TeamID", ""),
        }
        for row in participants
        if (
            normalise(row.get("Team", ""))
            and normalise(row.get("Team", "")) not in team_names
        )
        or (
            normalise(row.get("TeamID", ""))
            and normalise(row.get("TeamID", "")) not in team_ids
        )
    ]
    participant_blank_names = [
        row["_row_number"] for row in participants if not normalise(row.get("Name", ""))
    ]
    participant_partial = [
        {
            "row": row["_row_number"],
            "missing": [
                field
                for field in ("EventID", "Name", "Team", "Status")
                if not normalise(row.get(field, ""))
            ],
            "legacy_identity_missing": [
                field
                for field in ("ParticipantID", "TeamID", "JoinedAt", "LastSeenAt")
                if not normalise(row.get(field, ""))
            ],
        }
        for row in participants
        if any(
            not normalise(row.get(field, ""))
            for field in (
                "EventID",
                "Name",
                "Team",
                "Status",
                "ParticipantID",
                "TeamID",
                "JoinedAt",
                "LastSeenAt",
            )
        )
    ]

    team_exact = exact_duplicate_groups(teams)
    team_id_duplicates = duplicates_by(teams, ["TeamID"])
    team_name_duplicates = duplicates_by(teams, ["TeamName"])
    team_indexes = []
    invalid_team_indexes = []
    for row in teams:
        match = re.fullmatch(r"TEAM-(\d+)", str(row.get("TeamID", "")).strip())
        if not match:
            invalid_team_indexes.append(
                {"row": row["_row_number"], "team_id": row.get("TeamID", "")}
            )
        else:
            team_indexes.append(int(match.group(1)))
    expected_team_count = int(float(event.get("NumberOfTeams", 0) or 0))
    missing_team_indexes = [
        index
        for index in range(1, expected_team_count + 1)
        if index not in set(team_indexes)
    ]
    participant_counts = Counter(
        str(row.get("Team", "")).strip()
        for row in participants
        if str(row.get("Team", "")).strip()
    )

    submission_exact = exact_duplicate_groups(submissions)
    submission_id_duplicates = duplicates_by(submissions, ["SubmissionID"])
    submission_semantic_duplicates = duplicates_by(
        submissions,
        [
            "EventID",
            "MissionID",
            "TeamName",
            "ParticipantName",
            "ImageURL",
            "DriveFileID",
            "SubmissionType",
            "Metric1",
            "Metric2",
            "Metric3",
            "Score",
            "Status",
            "Judged",
            "Remarks",
            "SubmittedAt",
        ],
    )
    submission_no_participant = [
        row["_row_number"]
        for row in submissions
        if not normalise(row.get("ParticipantName", ""))
    ]
    submission_unknown_participant = [
        {
            "row": row["_row_number"],
            "participant": row.get("ParticipantName", ""),
        }
        for row in submissions
        if normalise(row.get("ParticipantName", ""))
        not in participant_names | {"facilitator"}
    ]
    submission_no_team = [
        row["_row_number"]
        for row in submissions
        if not normalise(row.get("TeamName", ""))
    ]
    submission_invalid_team = [
        {
            "row": row["_row_number"],
            "team": row.get("TeamName", ""),
        }
        for row in submissions
        if normalise(row.get("TeamName", ""))
        not in team_names | {"enterprise"}
    ]
    submission_invalid_mission = [
        {
            "row": row["_row_number"],
            "mission_id": row.get("MissionID", ""),
        }
        for row in submissions
        if normalise(row.get("MissionID", "")) not in mission_ids
    ]
    submission_empty = [
        row["_row_number"]
        for row in submissions
        if not any(
            normalise(row.get(field, ""))
            for field in (
                "MissionID",
                "TeamName",
                "ParticipantName",
                "ImageURL",
                "DriveFileID",
                "SubmissionType",
                "Metric1",
                "Metric2",
                "Metric3",
                "Score",
                "Remarks",
            )
        )
    ]
    submission_incomplete_uploads = [
        row["_row_number"]
        for row in submissions
        if normalise(row.get("SubmissionType", "")) in {"photo", "image", "catalyst"}
        and not (
            valid_media_reference(row.get("ImageURL", ""))
            or str(row.get("DriveFileID", "")).strip()
        )
    ]
    photo_duplicates = duplicates_by(
        [
            row
            for row in submissions
            if str(row.get("ImageURL", "")).strip()
            or str(row.get("DriveFileID", "")).strip()
        ],
        ["ImageURL", "DriveFileID"],
    )
    invalid_media_urls = [
        {
            "row": row["_row_number"],
            "image_url": row.get("ImageURL", ""),
        }
        for row in submissions
        if str(row.get("ImageURL", "")).strip()
        and not valid_media_reference(row.get("ImageURL", ""))
    ]

    mission_exact = exact_duplicate_groups(missions)
    mission_id_duplicates = duplicates_by(missions, ["MissionID"])
    stage_exact = exact_duplicate_groups(stages)
    stage_number_duplicates = duplicates_by(stages, ["StageNo"])
    invalid_stage_missions = [
        {
            "row": row["_row_number"],
            "stage_no": row.get("StageNo", ""),
            "mission_id": row.get("MissionID", ""),
        }
        for row in stages
        if normalise(row.get("MissionID", ""))
        and normalise(row.get("MissionID", "")) not in mission_ids
        and normalise(row.get("MissionID", "")) != "ref01"
    ]
    invalid_active_stage_references = []
    for state in event_state:
        current_stage_no = normalise(state.get("CurrentStageNo", ""))
        matching_stage = next(
            (
                stage
                for stage in stages
                if normalise(stage.get("StageNo", "")) == current_stage_no
            ),
            None,
        )
        if current_stage_no and matching_stage is None:
            invalid_active_stage_references.append(
                {
                    "row": state["_row_number"],
                    "current_stage_no": state.get("CurrentStageNo", ""),
                }
            )

    sheet_structures = {
        title: inspect_sheet_structure(snapshot)
        for title, snapshot in snapshots.items()
    }
    associated_tabs = sorted(
        title
        for title, snapshot in snapshots.items()
        if rows_for_event(snapshot, event_id)
    )

    safe_delete_rows: dict[str, list[int]] = defaultdict(list)
    for sheet_title, groups in (
        ("Participants", participant_exact),
        ("Teams", team_exact),
        ("Submissions", submission_exact),
        ("Missions", mission_exact),
        ("ProgrammeStages", stage_exact),
    ):
        for group in groups:
            safe_delete_rows[sheet_title].extend(group["safe_delete_rows"])
    for row_number in submission_empty:
        safe_delete_rows["Submissions"].append(row_number)
    safe_delete_rows = {
        title: sorted(set(rows))
        for title, rows in safe_delete_rows.items()
        if rows
    }

    manual_review = {
        "participant_id_duplicates": participant_id_duplicates,
        "participant_name_duplicates": participant_name_duplicates,
        "participant_multiple_teams": participant_multi_team,
        "participant_invalid_team": participant_invalid_team,
        "participant_no_team": participant_no_team,
        "participant_blank_names": participant_blank_names,
        "participant_partial_or_legacy_rows": participant_partial,
        "participant_malformed_timestamps": malformed_participant_timestamps,
        "participant_registration_clusters": timestamp_clusters,
        "team_id_duplicates": team_id_duplicates,
        "team_name_duplicates": team_name_duplicates,
        "invalid_team_indexes": invalid_team_indexes,
        "missing_team_indexes": missing_team_indexes,
        "submission_id_duplicates": submission_id_duplicates,
        "submission_semantic_duplicates": submission_semantic_duplicates,
        "submission_no_participant": submission_no_participant,
        "submission_unknown_participant": submission_unknown_participant,
        "submission_no_team": submission_no_team,
        "submission_invalid_team": submission_invalid_team,
        "submission_invalid_mission": submission_invalid_mission,
        "submission_incomplete_uploads": submission_incomplete_uploads,
        "duplicate_photo_references": photo_duplicates,
        "invalid_media_urls": invalid_media_urls,
        "mission_id_duplicates": mission_id_duplicates,
        "stage_number_duplicates": stage_number_duplicates,
        "invalid_stage_missions": invalid_stage_missions,
        "invalid_active_stage_references": invalid_active_stage_references,
    }

    total_safe_deletes = sum(len(rows) for rows in safe_delete_rows.values())
    manual_review_count = sum(
        len(items)
        for items in manual_review.values()
        if isinstance(items, list)
    )
    event_sheet_counts = {
        title: len(rows_for_event(snapshot, event_id))
        for title, snapshot in snapshots.items()
        if "EventID" in snapshot.headers
    }
    audit = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "mode": "DRY_RUN",
        "source_spreadsheet_id": manifest["source_spreadsheet_id"],
        "event": {
            "EventID": event_id,
            "EventName": event.get("EventName", ""),
            "EventDate": event.get("EventDate", ""),
            "Client": event.get("Client", ""),
            "Department": event.get("Department", ""),
            "Venue": event.get("Venue", ""),
            "JoinCode": event.get("JoinCode", ""),
            "NumberOfTeams": expected_team_count,
            "Status": event.get("Status", ""),
            "participant_count": len(participants),
            "submission_count": len(submissions),
            "mission_count": len(missions),
            "programme_stage_count": len(stages),
            "team_count": len(teams),
            "associated_tabs": associated_tabs,
            "associated_google_drive_folders": "NOT_VERIFIED_FROM_WORKBOOK",
        },
        "sheet_event_row_counts": event_sheet_counts,
        "sheet_structures": sheet_structures,
        "participants": {
            "rows_inspected": len(participants),
            "valid_core_rows": len(participants)
            - len(participant_blank_names)
            - len(participant_no_team)
            - len(participant_invalid_team),
            "exact_duplicate_groups": participant_exact,
            "duplicate_participant_ids": participant_id_duplicates,
            "duplicate_display_names": participant_name_duplicates,
            "duplicate_normalised_display_names": participant_normalised_name_duplicates,
            "created_within_five_seconds": timestamp_clusters,
            "multiple_team_assignments": participant_multi_team,
            "no_team": participant_no_team,
            "invalid_team_assignments": participant_invalid_team,
            "blank_names": participant_blank_names,
            "blank_event_ids": [],
            "partial_or_legacy_rows": participant_partial,
            "malformed_timestamps": malformed_participant_timestamps,
            "team_distribution": dict(sorted(participant_counts.items())),
        },
        "teams": {
            "rows_inspected": len(teams),
            "exact_duplicate_groups": team_exact,
            "duplicate_team_ids": team_id_duplicates,
            "duplicate_team_names": team_name_duplicates,
            "invalid_team_indexes": invalid_team_indexes,
            "missing_team_indexes": missing_team_indexes,
            "configured_team_count": expected_team_count,
            "actual_team_count": len(teams),
            "participant_distribution": dict(sorted(participant_counts.items())),
        },
        "submissions": {
            "rows_inspected": len(submissions),
            "exact_duplicate_groups": submission_exact,
            "duplicate_submission_ids": submission_id_duplicates,
            "semantic_duplicate_groups": submission_semantic_duplicates,
            "no_participant": submission_no_participant,
            "unknown_participant": submission_unknown_participant,
            "no_team": submission_no_team,
            "invalid_team": submission_invalid_team,
            "invalid_mission": submission_invalid_mission,
            "empty_submissions": submission_empty,
            "incomplete_uploads": submission_incomplete_uploads,
            "duplicate_photo_references": photo_duplicates,
            "invalid_media_urls": invalid_media_urls,
            "approved_count": sum(
                normalise(row.get("Status", "")) == "approved"
                for row in submissions
            ),
        },
        "missions_and_stages": {
            "mission_rows_inspected": len(missions),
            "mission_exact_duplicate_groups": mission_exact,
            "duplicate_mission_ids": mission_id_duplicates,
            "stage_rows_inspected": len(stages),
            "stage_exact_duplicate_groups": stage_exact,
            "duplicate_stage_numbers": stage_number_duplicates,
            "invalid_stage_missions": invalid_stage_missions,
            "event_state_rows": event_state,
            "invalid_active_stage_references": invalid_active_stage_references,
        },
        "safe_automatic_cleanup": {
            "rows_by_sheet": safe_delete_rows,
            "total_rows": total_safe_deletes,
        },
        "manual_review": manual_review,
        "manual_review_item_count": manual_review_count,
        "preserve": {
            "participants_with_scores": [
                row["_row_number"]
                for row in participants
                if str(row.get("Points", "")).strip()
                not in {"", "0", "0.0"}
            ],
            "approved_submission_rows": [
                row["_row_number"]
                for row in submissions
                if normalise(row.get("Status", "")) == "approved"
            ],
            "photo_submission_rows": [
                row["_row_number"]
                for row in submissions
                if str(row.get("ImageURL", "")).strip()
                or str(row.get("DriveFileID", "")).strip()
            ],
            "all_nonduplicate_rows": True,
        },
        "estimated_after_cleanup": {
            title: count - len(safe_delete_rows.get(title, []))
            for title, count in event_sheet_counts.items()
        },
        "estimated_processing_reduction": {
            "row_deletions": total_safe_deletes,
            "participant_count_read_change": (
                "Application protection replaces full Participants records "
                "with a cached EventID-column count."
            ),
            "estimated_full_record_fields_avoided_per_count": max(
                0,
                len(snapshots.get("Participants", SheetSnapshot("", 0, 0, 0, [], [], [])).headers)
                - 1,
            ),
        },
        "backup": manifest,
        "limitations": [
            "Google Drive folder ownership cannot be inferred from worksheet rows.",
            "Rows belonging to the wrong event cannot be inferred without an external participant roster.",
            "Display-name matches are never treated as identity proof.",
            "Hidden-row and full-sheet formatting inspection is limited to exported metadata.",
        ],
    }
    return audit


def human_report(audit: dict[str, Any]) -> str:
    event = audit["event"]
    participants = audit["participants"]
    submissions = audit["submissions"]
    teams = audit["teams"]
    missions = audit["missions_and_stages"]
    safe = audit["safe_automatic_cleanup"]
    structures = audit["sheet_structures"]

    structure_rows = []
    for title in sorted(structures):
        structure = structures[title]
        structure_rows.append(
            f"| {title} | {structure['last_populated_row']} | "
            f"{structure['trailing_blank_rows']} | "
            f"{len(structure['blank_rows_within_export'])} | "
            f"{len(structure['formula_cells'])} | "
            f"{len(structure['merged_ranges'])} |"
        )
    safe_rows = [
        f"- `{title}`: rows {', '.join(map(str, rows))}"
        for title, rows in safe["rows_by_sheet"].items()
    ] or ["- None"]

    return "\n".join(
        [
            "# EXOS AIA First Project Dry-Run Audit",
            "",
            f"Generated: {audit['generated_at']}",
            f"Mode: **{audit['mode']} — production data was not modified**",
            "",
            "## Event identified",
            "",
            f"- Event ID: `{event['EventID']}`",
            f"- Event name: {event['EventName']}",
            f"- Client / department: {event['Client']} / {event['Department']}",
            f"- Date: {event['EventDate']}",
            f"- Venue: {event['Venue']}",
            f"- Join code: `{event['JoinCode']}`",
            f"- Status: {event['Status']}",
            f"- Teams: {event['team_count']} (configured {event['NumberOfTeams']})",
            f"- Participants: {event['participant_count']}",
            f"- Submissions: {event['submission_count']}",
            f"- Mission rows: {event['mission_count']}",
            f"- Programme stages: {event['programme_stage_count']}",
            f"- Associated tabs: {', '.join(event['associated_tabs'])}",
            "- Associated Google Drive folders: not verifiable from workbook data",
            "",
            "## Backup",
            "",
            f"- Drive backup: {audit['backup'].get('drive_backup_url') or audit['backup'].get('drive_backup_id') or 'not recorded'}",
            f"- Local worksheet exports: {audit['backup']['worksheet_count']} tabs",
            f"- Restore manifest ready: {audit['backup']['restore_ready']}",
            "",
            "## Participants",
            "",
            f"- Rows inspected: {participants['rows_inspected']}",
            f"- Valid core rows: {participants['valid_core_rows']}",
            f"- Exact duplicate groups: {len(participants['exact_duplicate_groups'])}",
            f"- Duplicate participant IDs: {len(participants['duplicate_participant_ids'])}",
            f"- Duplicate names requiring review: {len(participants['duplicate_display_names'])}",
            f"- Multiple-team identities requiring review: {len(participants['multiple_team_assignments'])}",
            f"- No-team rows: {len(participants['no_team'])}",
            f"- Invalid-team rows: {len(participants['invalid_team_assignments'])}",
            f"- Blank-name rows: {len(participants['blank_names'])}",
            f"- Partial/legacy rows: {len(participants['partial_or_legacy_rows'])}",
            f"- Malformed timestamps: {len(participants['malformed_timestamps'])}",
            f"- Team distribution: {json.dumps(participants['team_distribution'], ensure_ascii=False)}",
            "",
            "## Teams",
            "",
            f"- Rows inspected: {teams['rows_inspected']}",
            f"- Exact duplicate groups: {len(teams['exact_duplicate_groups'])}",
            f"- Duplicate IDs: {len(teams['duplicate_team_ids'])}",
            f"- Invalid indexes: {len(teams['invalid_team_indexes'])}",
            f"- Missing indexes: {teams['missing_team_indexes']}",
            "",
            "## Submissions",
            "",
            f"- Rows inspected: {submissions['rows_inspected']}",
            f"- Approved rows: {submissions['approved_count']}",
            f"- Exact duplicate groups: {len(submissions['exact_duplicate_groups'])}",
            f"- Semantic duplicate groups requiring review: {len(submissions['semantic_duplicate_groups'])}",
            f"- Empty rows: {len(submissions['empty_submissions'])}",
            f"- Orphan/unknown participants: {len(submissions['unknown_participant'])}",
            f"- Invalid teams: {len(submissions['invalid_team'])}",
            f"- Invalid missions: {len(submissions['invalid_mission'])}",
            f"- Incomplete uploads: {len(submissions['incomplete_uploads'])}",
            f"- Duplicate photo references: {len(submissions['duplicate_photo_references'])}",
            f"- Invalid media URLs: {len(submissions['invalid_media_urls'])}",
            "",
            "## Missions and programme stages",
            "",
            f"- Mission rows: {missions['mission_rows_inspected']}",
            f"- Duplicate mission IDs requiring review: {len(missions['duplicate_mission_ids'])}",
            f"- Exact duplicate mission groups: {len(missions['mission_exact_duplicate_groups'])}",
            f"- Programme stages: {missions['stage_rows_inspected']}",
            f"- Duplicate stage numbers: {len(missions['duplicate_stage_numbers'])}",
            f"- Invalid stage mission references: {len(missions['invalid_stage_missions'])}",
            f"- Invalid active-stage references: {len(missions['invalid_active_stage_references'])}",
            "",
            "## Safe automatic clean-up candidates",
            "",
            f"Total rows: {safe['total_rows']}",
            *safe_rows,
            "",
            "No rows have been deleted. Similar display names, different IDs,",
            "approved work, scored work, and uncertain records remain preserved.",
            "",
            "## Sheet structure",
            "",
            "| Sheet | Last populated row | Trailing blank rows | Internal blank rows | Formula cells | Merges |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            *structure_rows,
            "",
            "## Review gate",
            "",
            "Production clean-up may proceed only after this report and the",
            "`manual_review.json` file have been reviewed and explicitly approved.",
            "",
        ]
    )


def apply_safe_cleanup(
    workbook: gspread.Spreadsheet,
    audit: dict[str, Any],
    *,
    event_id: str,
    confirm_event_id: str,
    review_report: Path,
    backup_dir: Path,
) -> list[dict[str, Any]]:
    if confirm_event_id != event_id:
        raise RuntimeError("--confirm-event-id must exactly match --event-id.")
    if not review_report.exists():
        raise RuntimeError("--review-report must point to the reviewed dry-run JSON.")
    reviewed = json.loads(review_report.read_text(encoding="utf-8"))
    if reviewed.get("mode") != "DRY_RUN":
        raise RuntimeError("The reviewed report is not a dry-run report.")
    if reviewed.get("event", {}).get("EventID") != event_id:
        raise RuntimeError("The reviewed report belongs to another event.")
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("Backup manifest is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("restore_ready"):
        raise RuntimeError("Backup manifest is not restore-ready.")

    approved_rows = reviewed.get("safe_automatic_cleanup", {}).get("rows_by_sheet", {})
    current_rows = audit.get("safe_automatic_cleanup", {}).get("rows_by_sheet", {})
    if approved_rows != current_rows:
        raise RuntimeError(
            "Production data changed after the reviewed dry run. Run a new audit."
        )

    worksheets = {worksheet.title: worksheet for worksheet in workbook.worksheets()}
    audit_log = []
    for sheet_title, row_numbers in sorted(current_rows.items()):
        worksheet = worksheets.get(sheet_title)
        if worksheet is None:
            raise RuntimeError(f"Worksheet {sheet_title} no longer exists.")
        for row_number in sorted(set(row_numbers), reverse=True):
            before = with_retry(lambda rn=row_number: worksheet.row_values(rn))
            if event_id not in {str(value).strip() for value in before}:
                raise RuntimeError(
                    f"Refusing to delete {sheet_title} row {row_number}: "
                    f"target EventID is not present."
                )
            with_retry(lambda rn=row_number: worksheet.delete_rows(rn))
            audit_log.append(
                {
                    "timestamp": datetime.now().astimezone().isoformat(),
                    "sheet": sheet_title,
                    "row": row_number,
                    "action": "DELETE_SAFE_DUPLICATE_OR_EMPTY",
                    "event_id": event_id,
                    "before": before,
                }
            )
    return audit_log


def main() -> int:
    args = parse_args()
    credentials_path = Path(args.credentials).expanduser().resolve()
    if not credentials_path.exists():
        raise FileNotFoundError(f"Credentials file not found: {credentials_path}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = (
        args.backup_name.strip()
        or f"EXOS_AIA_FIRST_PROJECT_BACKUP_{timestamp}"
    )
    backup_dir = Path(args.output_root).expanduser().resolve() / backup_name
    if backup_dir.exists():
        raise FileExistsError(
            f"Backup directory already exists and will not be overwritten: {backup_dir}"
        )
    backup_dir.mkdir(parents=True, exist_ok=False)

    client = authorise(credentials_path)
    workbook = with_retry(lambda: client.open_by_key(args.spreadsheet_id))
    snapshots, metadata = fetch_snapshots(workbook)
    manifest = export_snapshots(
        backup_dir,
        snapshots,
        metadata,
        spreadsheet_id=args.spreadsheet_id,
        event_id=args.event_id,
        drive_backup_id=args.drive_backup_id,
        drive_backup_url=args.drive_backup_url,
    )
    audit = build_audit(
        snapshots,
        event_id=args.event_id,
        manifest=manifest,
    )

    audit_path = backup_dir / "dry_run_audit.json"
    manual_review_path = backup_dir / "manual_review.json"
    report_path = backup_dir / "dry_run_report.md"
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manual_review_path.write_text(
        json.dumps(audit["manual_review"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path.write_text(human_report(audit), encoding="utf-8")

    audit_log = []
    if args.apply:
        review_report = Path(args.review_report).expanduser().resolve()
        audit_log = apply_safe_cleanup(
            workbook,
            audit,
            event_id=args.event_id,
            confirm_event_id=args.confirm_event_id,
            review_report=review_report,
            backup_dir=backup_dir,
        )
        (backup_dir / "cleanup_audit_log.json").write_text(
            json.dumps(audit_log, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    result = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "event_id": args.event_id,
        "backup_dir": str(backup_dir),
        "drive_backup_url": args.drive_backup_url,
        "dry_run_report": str(report_path),
        "machine_report": str(audit_path),
        "manual_review_report": str(manual_review_path),
        "safe_cleanup_candidates": audit["safe_automatic_cleanup"]["total_rows"],
        "records_changed": len(audit_log),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
