"""Disposable R.A.C.E. proof/result ownership regression coverage."""
from pathlib import Path

from engines.formula_race_configuration import captain_result_entry_method, current_station, normalise_station


ROOT = Path(__file__).resolve().parents[1]
CAPTAIN = (ROOT / "screens/formula_race_captain.py").read_text()
ADAPTER = (ROOT / "data/formula_race_core_v2_adapter.py").read_text()
MIGRATION = (ROOT / "supabase/033_formula_race_facilitator_owned_results.sql").read_text()


def _station(method, owner="FACILITATOR"):
    return {
        "ActivityID": f"DISPOSABLE-{method}", "ShortCode": "X", "DisplayName": "Disposable station",
        "ScoringMethod": method, "ResultEntryOwner": owner, "EvidenceRequirement": "PHOTO_REQUIRED",
        "BaseCredits": 15,
    }


def test_facilitator_is_the_safe_default_owner_for_every_existing_station_method():
    for method in ("LOWEST_TIME", "HIGHEST_COUNT", "SUCCESS_COUNT", "FACILITATOR_SCORE", "NON_SCORING"):
        station = normalise_station(_station(method))
        assert station["ResultEntryOwner"] == "FACILITATOR"
        assert captain_result_entry_method(station) == ""


def test_captain_numeric_entry_requires_an_explicit_owner_and_never_applies_to_facilitator_score():
    assert captain_result_entry_method(_station("LOWEST_TIME", "CAPTAIN")) == "LOWEST_TIME"
    assert captain_result_entry_method(_station("HIGHEST_COUNT", "CAPTAIN")) == "HIGHEST_COUNT"
    assert captain_result_entry_method(_station("SUCCESS_COUNT", "CAPTAIN")) == "SUCCESS_COUNT"
    assert captain_result_entry_method(_station("FACILITATOR_SCORE", "CAPTAIN")) == ""
    assert captain_result_entry_method(_station("NON_SCORING", "CAPTAIN")) == ""


def test_proof_only_submission_advances_the_route_without_an_official_result():
    route = ["DISPOSABLE-A", "DISPOSABLE-C"]
    assert current_station(route, [{"ActivityID": "DISPOSABLE-A", "Status": "SUBMITTED"}]) == ("DISPOSABLE-C", "")
    assert "rpc_name = \"exos_v2_formula_race_submit_station\"" in ADAPTER
    assert 'payload.update({"p_result_value": result_value, "p_result_unit": str(result_unit)})' in ADAPTER


def test_captain_renderer_hides_official_result_inputs_until_explicitly_captain_owned_and_live():
    assert "result_entry_method=captain_result_entry_method(current)" in CAPTAIN
    assert 'if result_entry_method == "LOWEST_TIME"' in CAPTAIN
    assert 'elif result_entry_method in {"HIGHEST_COUNT", "SUCCESS_COUNT"}' in CAPTAIN
    assert "The station facilitator records the official result. Submit completion evidence only." in CAPTAIN
    assert CAPTAIN.index('if runtime_status!="LIVE":') < CAPTAIN.index("<div class='race-proof'>")
    assert 'result_unit=str(current.get("ResultUnit", "") or "CONFIGURED") if result_entry_method else ""' in CAPTAIN


def test_migration_separates_proof_from_facilitator_owned_official_result_and_preserves_credit_reconciliation():
    assert "depends on migrations 030 and 031" in MIGRATION
    assert "v_result_owner:=upper" in MIGRATION
    assert "v_result_owner='FACILITATOR' and p_result_value is not null" in MIGRATION
    assert "v_result_owner='CAPTAIN' and v_method in ('LOWEST_TIME','HIGHEST_COUNT','SUCCESS_COUNT') and p_result_value is null" in MIGRATION
    assert "'result_entry_owner',v_result_owner" in MIGRATION
    assert "exos_v2_formula_race_reconcile_station_ranking" in (ROOT / "data/formula_race_core_v2_adapter.py").read_text()
