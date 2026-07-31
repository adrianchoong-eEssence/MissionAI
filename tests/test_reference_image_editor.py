import io
import json
from unittest.mock import patch

from PIL import Image

from screens.mission_setup import (
    assign_reference_crop,
    cropped_reference_image,
    assign_reference_image,
    crop_reference_image,
    reference_crop_coordinates,
)


def _png(width=200, height=100):
    image = Image.new("RGB", (width, height), "#cc3300")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_crop_reference_image_uses_requested_box():
    cropped = crop_reference_image(_png(), (50, 10, 150, 90))
    result = Image.open(io.BytesIO(cropped))

    assert result.size == (100, 80)
    assert result.format == "PNG"


def test_crop_reference_image_clamps_box_to_source_bounds():
    cropped = crop_reference_image(_png(40, 30), (-20, -10, 100, 100))
    result = Image.open(io.BytesIO(cropped))

    assert result.size == (40, 30)


def test_uploaded_asset_reference_is_assigned_without_mutating_other_fields():
    class DB:
        payload = None

        def upsert_event_mission(self, payload):
            self.payload = payload
            return {"Action": "Updated", "MissionID": payload["MissionID"]}

    db = DB()
    mission = {
        "EventID": "EVT-0004",
        "MissionID": "LAB01",
        "Title": "The Paris Fragment",
        "CreditValue": "100",
        "ReferenceImageURL": "old-reference",
    }

    result = assign_reference_image(db, mission, "new-library-reference")

    assert result == {"Action": "Updated", "MissionID": "LAB01"}
    assert db.payload["ReferenceImageURL"] == "new-library-reference"
    assert db.payload["Title"] == "The Paris Fragment"
    assert db.payload["CreditValue"] == "100"
    assert mission["ReferenceImageURL"] == "old-reference"


def test_crop_saves_explicit_non_destructive_metadata():
    class DB:
        def upsert_event_mission(self, payload):
            self.payload = payload
            return payload

    db = DB()
    mission = {"EventID": "EVT-0004", "MissionID": "LAB01", "ReferenceImageURL": "original"}
    coords = {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.4}

    assign_reference_crop(
        db, mission, "MISSION-IMAGES-001", coords, zoom=180, rotation=0,
    )

    assert db.payload["OriginalImageID"] == "MISSION-IMAGES-001"
    assert db.payload["CropX"] == 0.1
    assert db.payload["CropY"] == 0.2
    assert db.payload["CropWidth"] == 0.5
    assert db.payload["CropHeight"] == 0.4
    assert db.payload["Zoom"] == 180
    assert db.payload["Rotation"] == 0
    assert db.payload["ReferenceImageURL"] == "original"


def test_saved_crop_coordinates_reopen_and_invalid_values_are_rejected():
    saved = '{"x":0.1,"y":0.2,"width":0.5,"height":0.4}'

    assert reference_crop_coordinates(saved) == {
        "x": 0.1, "y": 0.2, "width": 0.5, "height": 0.4,
    }
    assert reference_crop_coordinates('{"x":0.8,"y":0,"width":0.5,"height":1}') is None
    assert reference_crop_coordinates({
        "CropX": "0.1", "CropY": "0.2",
        "CropWidth": "0.5", "CropHeight": "0.4",
    }) == {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.4}


def test_participant_crop_is_rendered_from_original_asset_bytes():
    with patch(
        "screens.mission_setup._reference_image_bytes",
        return_value=_png(200, 100),
    ):
        cropped = cropped_reference_image(
            "original-reference",
            '{"x":0.25,"y":0.1,"width":0.5,"height":0.8}',
        )

    assert Image.open(io.BytesIO(cropped)).size == (100, 80)


def test_no_crop_metadata_uses_full_image_fallback():
    assert cropped_reference_image("original-reference", {}) is None


def test_two_experiences_share_original_but_render_different_persisted_crops():
    source = Image.new("RGB", (200, 100), "#cc3300")
    source.paste("#0033cc", (100, 0, 200, 100))
    source_output = io.BytesIO()
    source.save(source_output, format="PNG")
    original_bytes = source_output.getvalue()
    original_before = bytes(original_bytes)
    asset_id = "MISSION-IMAGE-SHARED"
    reference = "supabase://exos-mission-media/assets/shared/file"

    class DB:
        records = {}

        def upsert_event_mission(self, payload):
            self.records[payload["MissionID"]] = dict(payload)
            return payload

    db = DB()
    first = {"EventID": "EVT-UAT", "MissionID": "EXP-01", "ReferenceImageURL": reference}
    second = {"EventID": "EVT-UAT", "MissionID": "EXP-02", "ReferenceImageURL": reference}
    assign_reference_crop(
        db, first, asset_id,
        {"x": 0.0, "y": 0.0, "width": 0.5, "height": 1.0},
        zoom=200,
    )
    assign_reference_crop(
        db, second, asset_id,
        {"x": 0.5, "y": 0.0, "width": 0.5, "height": 1.0},
        zoom=200,
    )

    # Simulate refresh/reopen by reading fresh record copies.
    refreshed_first = dict(db.records["EXP-01"])
    refreshed_second = dict(db.records["EXP-02"])
    with patch(
        "screens.mission_setup._reference_image_bytes",
        return_value=original_bytes,
    ):
        first_clue = cropped_reference_image(reference, refreshed_first)
        second_clue = cropped_reference_image(reference, refreshed_second)

    assert refreshed_first["OriginalImageID"] == asset_id
    assert refreshed_second["OriginalImageID"] == asset_id
    assert refreshed_first["ReferenceImageURL"] == reference
    assert refreshed_second["ReferenceImageURL"] == reference
    assert first_clue != second_clue
    assert Image.open(io.BytesIO(first_clue)).size == (100, 100)
    assert Image.open(io.BytesIO(second_clue)).size == (100, 100)
    assert original_bytes == original_before
