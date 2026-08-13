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
    manifest=json.loads(Path("Assets/race_teams/manifest.json").read_text())
    assert list(manifest)==EXPECTED


def test_captain_navigation_uses_explicit_selectable_sections():
    source = Path("screens/formula_race_captain.py").read_text()
    assert 'captain_section = st.radio(' in source
    assert 'key="race_captain_section"' in source
    assert 'if captain_section == "RACE Checkpoints":' in source
    assert 'if captain_section == "Wallet & Marketplace":' in source
    assert 'if captain_section == "Submissions":' in source
    assert 'st.tabs(["RACE Checkpoints","Wallet & Marketplace","Submissions"])' not in source
    assert "formula_race_purchase" in source
