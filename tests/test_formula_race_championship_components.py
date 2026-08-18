from pathlib import Path

from engines.formula_race_championship import (
    championship_component_points, normalise_championship_components,
    validate_championship_components,
)


CRITERIA = [
    {"CriterionName": "Aesthetic", "MaximumScore": 40, "Enabled": True},
    {"CriterionName": "Photo", "MaximumScore": 10, "Enabled": True},
]


def test_generic_components_support_independent_maximums_and_normalisation():
    components = normalise_championship_components([
        {"ComponentID": "DESIGN", "DisplayName": "Design", "ComponentType": "JUDGING_CRITERION", "MaximumChampionshipPoints": 40, "SourceReference": "Aesthetic"},
        {"ComponentID": "PHOTO", "DisplayName": "Photo", "ComponentType": "TEAM_PHOTO", "MaximumChampionshipPoints": 10, "SourceReference": "Photo"},
        {"ComponentID": "RACE", "DisplayName": "Race", "ComponentType": "RACE_RANK", "MaximumChampionshipPoints": 50, "ScoringConfiguration": {"RankPoints": {str(rank): 50 - rank for rank in range(1, 11)}}},
    ])
    assert not validate_championship_components(components, CRITERIA, 10)
    assert championship_component_points(components[0], 40, 40) == 40
    assert championship_component_points(components[0], 5, 10) == 20
    assert championship_component_points(components[1], 10, 10, team_photo_submitted=False) == 0
    assert championship_component_points(components[1], 10, 10, team_photo_submitted=True) == 10
    assert championship_component_points(components[2], 0, 0, race_rank=1, race_final_locked=False) == 0
    assert championship_component_points(components[2], 0, 0, race_rank=1, race_final_locked=True) == 49


def test_ten_team_championship_calculation_is_deterministic_with_explicit_race_tie_break():
    component = normalise_championship_components([
        {"ComponentID": "RACE", "DisplayName": "Race", "ComponentType": "RACE_RANK", "MaximumChampionshipPoints": 50, "ScoringConfiguration": {"RankPoints": {str(rank): 50 - rank for rank in range(1, 11)}}}
    ])[0]
    teams = [{"TeamIdentity": f"Team {rank}", "RaceRank": rank} for rank in range(1, 11)]
    rows = [{**team, "Total": championship_component_points(component, 0, 0, race_rank=team["RaceRank"], race_final_locked=True)} for team in teams]
    rows.sort(key=lambda row: (-row["Total"], row["RaceRank"], row["TeamIdentity"]))
    assert [row["TeamIdentity"] for row in rows] == [f"Team {rank}" for rank in range(1, 11)]


def test_championship_migration_is_race_scoped_and_reconciles_without_wallet_credits():
    sql = Path("supabase/032_formula_race_championship_components.sql").read_text()
    assert "Depends on 020, 030 and 031" in sql
    assert "race_championship_team_photos_v2" in sql
    assert "correction_of uuid" in sql
    assert "v_score_recorded>=v_photo_submitted" in sql
    assert "exos_v2_formula_race_reconcile_championship" in sql
    assert "RACE_RANK" in sql and "TEAM_PHOTO" in sql and "JUDGING_CRITERION" in sql
    assert "race-championship-component|" in sql
    assert "on conflict(event_id,idempotency_key) do update set score_delta=excluded.score_delta" in sql
    assert "credit_transactions_v2" not in sql
    assert "marketplace_transactions_v2" not in sql
    assert "exos_v2_formula_race_lock_final_results" in sql


def test_captain_and_race_control_expose_dedicated_private_team_photo_workflows():
    captain = Path("screens/formula_race_captain.py").read_text()
    control = Path("screens/formula_race.py").read_text()
    adapter = Path("data/formula_race_core_v2_adapter.py").read_text()
    assert '"Upload Team Photo"' in captain and '"SUBMIT TEAM PHOTO"' in captain
    assert "team-photos/{event_id}/{team_id}" in captain
    assert "formula_race_submit_team_photo" in captain
    assert "get_formula_race_team_photo_url" in control
    assert 'st.subheader("Championship Components")' in control
    assert '"SAVE CHAMPIONSHIP COMPONENTS"' in control
    assert '"Championship subtotal"' in control
    assert "formula_race_submit_team_photo" in adapter
