from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / "supabase/018_formula_race_live_activation.sql").read_text()
CONFIG = (ROOT / "supabase/seeds/formula_race_evt0006_live_config.sql").read_text()
CAPTAIN = (ROOT / "screens/formula_race_captain.py").read_text()


def test_live_operations_are_event_and_team_scoped():
    assert "foreign key(event_id,team_id)" in MIGRATION
    assert "runtime_marketplace_purchase_idempotency_uidx" in MIGRATION
    assert "where event_id=a.event_id and team_id=a.team_id" in MIGRATION
    assert "p_idempotency_key" in MIGRATION


def test_reset_is_confirmed_audited_and_preserves_configuration():
    assert "p_event_name_confirmation" in MIGRATION
    assert "formula_race_reset_audit" in MIGRATION
    assert "update runtime_marketplace_items set stock_quantity=initial_stock_quantity" in MIGRATION
    assert "delete from runtime_events" not in MIGRATION
    assert "delete from runtime_teams" not in MIGRATION
    assert "delete from formula_race_team_access" not in MIGRATION


def test_evt0006_configuration_uses_only_approved_structure():
    assert CONFIG.count("('EVT-0006','RACE-D") == 15
    for stage in (
        "Briefing", "R.A.C.E. Credit Challenge 1", "R.A.C.E. Credit Challenge 4",
        "Facilitator Review", "Credit Awards", "Spend Credits",
        "Marketplace / Material Collection", "Formula Car Build",
        "Painting / Design", "Team Photo", "Drag Push Race", "Judging",
        "Final Championship",
    ):
        assert stage in CONFIG
    assert '"CreditValue":null' in CONFIG
    assert '"MarketplacePrices":null' in CONFIG


def test_marketplace_is_editable_but_closed_until_values_are_approved():
    for material in (
        "Wooden Chassis Board", "Metal Axle Rods", "Wheelbarrow Tyres",
        "Cardboard Sheets or Boxes", "Bolts, Nuts and Washers",
        "Tape and Fasteners", "Spray Paint",
    ):
        assert material in CONFIG
    assert CONFIG.count("0,0,0,false,") == 7


def test_captain_surface_uses_server_workspace_purchase_and_logout():
    assert "formula_race_captain_workspace" in CAPTAIN
    assert "formula_race_purchase" in CAPTAIN
    assert "formula_race_captain_logout" in CAPTAIN
