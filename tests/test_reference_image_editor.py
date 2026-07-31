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
