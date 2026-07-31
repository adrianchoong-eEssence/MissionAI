import io
import json

from PIL import Image

from screens.mission_setup import (
    assign_reference_crop,
    assign_reference_image,
    crop_reference_image,
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


def test_crop_saves_only_original_asset_id_and_coordinates():
    class DB:
        def upsert_event_mission(self, payload):
            self.payload = payload
            return payload

    db = DB()
    mission = {"EventID": "EVT-0004", "MissionID": "LAB01", "ReferenceImageURL": "original"}
    coords = {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.4}

    assign_reference_crop(db, mission, "MISSION-IMAGES-001", coords)

    assert db.payload["OriginalAssetID"] == "MISSION-IMAGES-001"
    assert json.loads(db.payload["CropCoordinates"]) == coords
    assert db.payload["ReferenceImageURL"] == "original"
