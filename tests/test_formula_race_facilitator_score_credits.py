from pathlib import Path

from engines.formula_race_configuration import performance_credits, validate_stations


def _facilitator_score_station(per_score_point=1):
    return {
        "ActivityID": "RESULT",
        "ShortCode": "R",
        "DisplayName": "Any facilitator-scored station",
        "ScoringMethod": "FACILITATOR_SCORE",
        "BaseCredits": 15,
        "PerformanceCredits": {"PerScorePoint": per_score_point},
    }


def test_facilitator_score_performance_credits_are_generic_and_add_to_base_award():
    station = _facilitator_score_station()

    assert 15 + performance_credits(station, {"OfficialResult": 0}) == 15
    assert 15 + performance_credits(station, {"OfficialResult": 5}) == 20
    assert 15 + performance_credits(station, {"OfficialResult": 10}) == 25
    assert performance_credits(_facilitator_score_station(2), {"OfficialResult": 5}) == 10


def test_facilitator_score_mapping_rejects_negative_credit_rates_without_changing_other_methods():
    assert validate_stations([_facilitator_score_station(-1)]) == [
        "R: Credits per score point cannot be negative."
    ]
    rank_station = {
        "ActivityID": "A", "ShortCode": "A", "DisplayName": "Ranked",
        "ScoringMethod": "LOWEST_TIME", "PerformanceCredits": {"RankCredits": {"1": 8}},
    }
    success_station = {
        "ActivityID": "E", "ShortCode": "E", "DisplayName": "Counted",
        "ScoringMethod": "SUCCESS_COUNT", "PerformanceCredits": {"PerSuccess": 2},
    }
    assert performance_credits(rank_station, {"Rank": 1, "OfficialResult": 999}) == 8
    assert performance_credits(success_station, {"OfficialResult": 5}) == 10


def test_migration_031_reconciles_one_performance_ledger_row_for_score_corrections():
    sql = Path("supabase/031_formula_race_facilitator_score_performance_credits.sql").read_text()

    assert "depends on migration 030 being installed" in sql
    assert "'FACILITATOR_SCORE'" in sql
    assert "'PerScorePoint'" in sql
    assert "floor(greatest(v_row.official_result,0)" in sql
    assert "'race-station-performance|'||trim(p_activity_id)||'|'||v_row.team_id" in sql
    assert "on conflict(event_id,idempotency_key) do update set amount=excluded.amount" in sql
    assert "elsif v_method='FACILITATOR_SCORE' then" in sql
    assert "delete from public.credit_transactions_v2" in sql
    assert "v_method<>'FACILITATOR_SCORE' and (v_team_count=0 or v_verified_count<>v_team_count)" in sql
