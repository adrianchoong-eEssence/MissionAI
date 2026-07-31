import io

from PIL import Image

from screens.mission_setup import assign_reference_image, crop_reference_image


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
