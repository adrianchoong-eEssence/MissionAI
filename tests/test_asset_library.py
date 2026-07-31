from pathlib import Path
from unittest.mock import patch

import pytest

from data.google_sheets import GoogleSheetsDB, REQUIRED_WORKSHEETS
from data.mission_media import upload_library_asset


class UploadedImage:
    name = "portrait.png"
    type = "image/png"

    @staticmethod
    def getvalue():
        return b"asset-bytes"


class Runtime:
    def __init__(self):
        self.paths = []

    def upload_mission_media(self, storage_path, media_bytes, content_type):
        self.paths.append(storage_path)


class Worksheet:
    def __init__(self, headers, records=None):
        self.headers = headers
        self.records = list(records or [])
        self.deleted = []
        self.batch_updates = []

    def row_values(self, row):
        return list(self.headers)

    def append_row(self, values, value_input_option=None):
        self.records.append(dict(zip(self.headers, values)))

    def update(self, values, range_name):
        pass

    def delete_rows(self, row):
        self.deleted.append(row)

    def batch_update(self, updates):
        self.batch_updates.extend(updates)


def test_asset_catalog_has_required_reuse_metadata():
    assert REQUIRED_WORKSHEETS["Assets"] == [
        "AssetID",
        "Category",
        "Name",
        "MediaReference",
        "FileName",
        "ContentType",
        "CreatedAt",
        "UpdatedAt",
    ]


def test_replacing_library_asset_reuses_deterministic_storage_object():
    runtime = Runtime()
    with patch(
        "data.mission_media.get_runtime_database",
        return_value=runtime,
    ):
        first = upload_library_asset(UploadedImage(), "ASSET-001")
        second = upload_library_asset(
            UploadedImage(),
            "ASSET-001",
            current_reference=first,
        )

    assert first == second
    assert first == (
        "supabase://exos-mission-media/assets/asset-001/file"
    )
    assert runtime.paths == [
        "assets/asset-001/file",
        "assets/asset-001/file",
    ]


def test_existing_character_and_mission_image_references_are_catalogued_once():
    db = GoogleSheetsDB.__new__(GoogleSheetsDB)
    db.assets = Worksheet(REQUIRED_WORKSHEETS["Assets"])
    db.clear_cache = lambda: None
    records = {
        "Assets": [],
        "Missions": [
            {
                "MissionID": "LAB01",
                "Title": "The Paris Fragment",
                "CharacterSource": "EVA",
                "CharacterPortraitURL": (
                    "supabase://exos-mission-media/characters/eva/portrait"
                ),
                "ReferenceImageURL": "static/bayu/paris.jpg",
            },
            {
                "MissionID": "LAB02",
                "Title": "Horizon Lock",
                "CharacterSource": "EVA",
                "CharacterPortraitURL": (
                    "supabase://exos-mission-media/characters/eva/portrait"
                ),
                "ReferenceImageURL": "static/bayu/horizon.jpg",
            },
        ],
        "MissionTemplates": [],
    }

    with patch(
        "data.google_sheets.get_sheet_records",
        side_effect=lambda name: records[name],
    ):
        result = db.ensure_existing_assets_catalogue()

    assert result == {"Added": 3}
    assert len(db.assets.records) == 3
    assert {
        row["Category"] for row in db.assets.records
    } == {"Characters", "Mission Images"}


def test_empty_catalogue_initialises_without_error():
    db = GoogleSheetsDB.__new__(GoogleSheetsDB)
    db.assets = Worksheet(REQUIRED_WORKSHEETS["Assets"])
    db.clear_cache = lambda: None

    with patch(
        "data.google_sheets.get_sheet_records",
        side_effect=lambda name: [],
    ):
        result = db.ensure_existing_assets_catalogue()

    assert result == {"Added": 0}
    assert db.assets.records == []


def test_former_catalogued_spelling_remains_compatible():
    db = GoogleSheetsDB.__new__(GoogleSheetsDB)
    with patch.object(
        db,
        "ensure_existing_assets_catalogue",
        return_value={"Added": 2},
    ) as initialise:
        result = db.ensure_existing_assets_catalogued()

    assert result == {"Added": 2}
    initialise.assert_called_once_with()


def test_asset_delete_is_blocked_while_experience_uses_reference():
    reference = "supabase://exos-mission-media/assets/asset-001/file"
    db = GoogleSheetsDB.__new__(GoogleSheetsDB)
    db.assets = Worksheet(
        REQUIRED_WORKSHEETS["Assets"],
        [{
            "AssetID": "ASSET-001",
            "Category": "Characters",
            "Name": "EVA",
            "MediaReference": reference,
        }],
    )
    records = {
        "Assets": db.assets.records,
        "Missions": [{
            "MissionID": "LAB01",
            "CharacterPortraitURL": reference,
        }],
        "MissionTemplates": [],
    }

    with patch(
        "data.google_sheets.get_sheet_records",
        side_effect=lambda name: records[name],
    ):
        with pytest.raises(ValueError, match="still used by LAB01"):
            db.delete_asset("ASSET-001")

    assert db.assets.deleted == []


def test_replacing_legacy_asset_reference_relinks_existing_experiences():
    db = GoogleSheetsDB.__new__(GoogleSheetsDB)
    db.missions = Worksheet(REQUIRED_WORKSHEETS["Missions"])
    db.mission_templates = Worksheet(REQUIRED_WORKSHEETS["MissionTemplates"])
    records = {
        "Missions": [{
            "MissionID": "LAB01",
            "ReferenceImageURL": "static/bayu/paris.jpg",
        }],
        "MissionTemplates": [],
    }

    with patch(
        "data.google_sheets.get_sheet_records",
        side_effect=lambda name: records[name],
    ):
        updated = db._replace_asset_reference(
            "static/bayu/paris.jpg",
            "supabase://exos-mission-media/assets/img-bayu-01/file",
        )

    assert updated == 1
    assert db.missions.batch_updates == [{
        "range": "BL2",
        "values": [[
            "supabase://exos-mission-media/assets/img-bayu-01/file"
        ]],
    }]


def test_experience_studio_uses_visual_reference_image_editor():
    source = (
        Path(__file__).resolve().parents[1]
        / "screens"
        / "mission_setup.py"
    ).read_text(encoding="utf-8")

    assert '"Select Character"' in source
    assert '"Select Mission Image"' not in source
    assert '"Choose Image"' in source
    assert "Asset Library · Mission Images" in source
    assert '"Selected" if asset_id == current_asset_id else "Choose"' in source
    assert "st.session_state[state_key] = selected_reference" in source
    assert '"Upload New Image"' in source
    assert '"Replace Image"' in source
    assert '"Crop Image"' in source
    assert '"Remove Image"' in source
    assert "Character Portrait Upload" not in source
