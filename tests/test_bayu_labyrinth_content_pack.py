import json
from pathlib import Path

from scripts.build_bayu_labyrinth_sheet_requests import (
    character_portrait_reference,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "content_packs" / "bayu_beach_labyrinth_v1.json"


def load_pack():
    return json.loads(PACK_PATH.read_text(encoding="utf-8"))


def test_pack_contains_exactly_seventeen_pre_afternoon_experiences():
    pack = load_pack()
    experiences = pack["experiences"]

    assert len(experiences) == 17
    assert [item["mission_id"] for item in experiences] == [
        f"LAB{index:02d}" for index in range(1, 18)
    ]
    assert [item["source_id"] for item in experiences] == [
        "C01", "C02", "C03", "C04", "C05", "C06",
        "C11", "C12", "C13", "C14", "C15", "C16",
        "C21", "C22", "C23", "C24", "C25",
    ]


def test_approved_mechanics_and_credit_envelope_are_locked():
    experiences = load_pack()["experiences"]

    assert [item["title"] for item in experiences] == [
        "The Paris Fragment",
        "Horizon Lock",
        "The BBR Relic",
        "Seven Silent Boxes",
        "Eight-Ray Beacon",
        "Golden Signal",
        "Six Across",
        "Deepest Point",
        "Twin Needles",
        "Two Arrows, One Escape",
        "Ink Mountain Count",
        "Crown Estimate",
        "Island Portal",
        "Capacity Reached",
        "Arrow Relay",
        "Three-Layer World",
        "Twenty Seconds of Island",
    ]
    assert [item["credits"] for item in experiences] == [
        100, 90, 80, 90, 80, 90, 100, 100, 120,
        120, 110, 110, 120, 110, 120, 130, 110,
    ]
    assert sum(item["credits"] for item in experiences) == 1780
    assert [item["type"] for item in experiences] == (
        ["Observe"] * 6 + ["Think"] * 6 + ["Interact"] * 5
    )


def test_every_experience_has_only_approved_character_and_existing_image():
    approved_characters = {
        "EVA",
        "Headquarters",
        "Captain Amelia Ross",
        "Dr Marcus Hale",
        "Unknown Transmission",
    }

    for experience in load_pack()["experiences"]:
        assert experience["character"] in approved_characters
        assert experience["transmission"].strip()
        assert experience["ai_response"].strip()
        assert f"+{experience['credits']} Intelligence Credits" in experience["ai_response"]
        assert (ROOT / experience["reference_image"]).is_file()
        assert character_portrait_reference(experience["character"]).startswith(
            "supabase://exos-mission-media/characters/"
        )


def test_character_portraits_reuse_five_deterministic_storage_objects():
    references = {
        character_portrait_reference(experience["character"])
        for experience in load_pack()["experiences"]
    }

    assert references == {
        "supabase://exos-mission-media/characters/eva/portrait",
        "supabase://exos-mission-media/characters/headquarters/portrait",
        (
            "supabase://exos-mission-media/characters/"
            "captain-amelia-ross/portrait"
        ),
        "supabase://exos-mission-media/characters/dr-marcus-hale/portrait",
        (
            "supabase://exos-mission-media/characters/"
            "unknown-transmission/portrait"
        ),
    }


def test_experience_one_uses_approved_copy_and_paris_crop():
    experience = load_pack()["experiences"][0]

    assert experience["character"] == "EVA"
    assert experience["transmission"] == (
        "SIGNAL RESTORED\n\n"
        "Commander...\n\n"
        "Our archive has recovered references to an object codenamed\n"
        "\"The Paris Fragment.\"\n\n"
        "Expedition Alpha believed this object contained the first surviving "
        "clue explaining why previous expeditions disappeared.\n\n"
        "Recover visual confirmation."
    )
    assert experience["reference_image"].endswith(
        "experience-01-paris-fragment.jpg"
    )
    assert "Match Confidence: 96%" in experience["ai_response"]
