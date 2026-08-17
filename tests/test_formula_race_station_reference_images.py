import io
from types import SimpleNamespace

from PIL import Image

from data.mission_media import (
    REFERENCE_PREFIX,
    delete_formula_race_station_reference,
    get_formula_race_station_reference_url,
    upload_formula_race_station_reference,
)


def _valid_png_upload():
    payload = io.BytesIO()
    Image.new("RGB", (8, 6), "red").save(payload, format="PNG")
    return SimpleNamespace(
        name="station-reference.png",
        type="image/png",
        getvalue=payload.getvalue,
    )


def test_station_reference_uses_private_event_and_station_scope_and_never_cross_deletes():
    class Runtime:
        def __init__(self):
            self.uploads, self.deleted = [], []

        def upload_mission_media(self, **kwargs):
            self.uploads.append(kwargs)

        def create_mission_media_url(self, storage_path, expires_in):
            return f"https://private.example.test/sign/{storage_path}?expires={expires_in}"

        def delete_mission_media(self, paths):
            self.deleted.append(paths)
            return paths

    runtime = Runtime()
    reference = upload_formula_race_station_reference(
        runtime, _valid_png_upload(), "EVENT / ONE", "STATION / A",
    )

    assert reference.startswith(REFERENCE_PREFIX + "formula-race/stations/EVENT-ONE/STATION-A/reference/")
    assert runtime.uploads[0]["storage_path"] == reference[len(REFERENCE_PREFIX):]
    assert get_formula_race_station_reference_url(runtime, reference).startswith("https://private.example.test/sign/")
    assert delete_formula_race_station_reference(runtime, "EVENT / ONE", "STATION / OTHER", reference) == []
    assert runtime.deleted == []
    assert delete_formula_race_station_reference(runtime, "EVENT / ONE", "STATION / A", reference)
    assert runtime.deleted == [[reference[len(REFERENCE_PREFIX):]]]


def test_station_reference_assets_are_kept_separate_from_evidence_and_marketplace_media():
    source = open("data/mission_media.py").read()
    captain = open("screens/formula_race_captain.py").read()
    setup = open("screens/formula_race.py").read()

    assert 'RACE_STATION_REFERENCE_ROOT = "formula-race/stations"' in source
    assert '"Station reference image (facilitator instruction only)"' in setup
    assert '"Private event/station image. This is not Captain proof or participant evidence."' in setup
    assert 'storage_reference="supabase://exos-submissions/"+storage_path' in captain
    assert 'delete_formula_race_station_reference' in source
