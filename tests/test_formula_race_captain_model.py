from pathlib import Path
from screens.event_manager import FORMULA_RACE_TEAMS

EXPECTED=["Sandstorm","Bolt","Zenith","Scuderia Best","Apex Velocity","Velocity",
          "Fast & Curious","Lakas","Drift Club","Papaya Crew"]
SQL=Path("supabase/016_formula_race_captain_sessions.sql").read_text()

def test_exact_fixed_team_roster():
    assert FORMULA_RACE_TEAMS==EXPECTED and len(set(FORMULA_RACE_TEAMS))==10

def test_captain_login_is_pin_scoped_and_never_allocates_teams():
    function=SQL.split("public.exos_formula_race_captain_login",1)[1]
    for required in ("event_id=e.event_id and team_id=trim(p_team_id)","crypt(trim(p_pin)",
                     "active_device_id<>trim(p_device_id)","Incorrect team PIN"):
        assert required in function
    for forbidden in ("insert into public.runtime_teams","order by count(","runtime_participants"):
        assert forbidden not in function

def test_team_asset_slots_cover_roster():
    import json
    manifest=json.loads(Path("assets/race_teams/manifest.json").read_text())
    assert list(manifest)==EXPECTED
