from engines.formula_race_configuration import (
    configuration_lock_reasons, current_station, generate_balanced_routes,
    normalise_result, performance_credits, rank_verified_results, validate_marketplace_items,
    validate_routes, validate_stations,
)


def test_variable_station_routes_are_balanced_and_manual_routes_validate():
    teams, stations = ["T1", "T2", "T3", "T4", "T5"], ["A", "B", "C"]
    routes = generate_balanced_routes(teams, stations)
    assert [route[0] for route in routes.values()] == ["A", "B", "C", "A", "B"]
    assert not validate_routes(routes, teams, stations)
    routes["T1"] = ["A", "B"]
    assert validate_routes(routes, teams, stations)


def test_submission_gates_progress_without_waiting_for_verification_or_refresh():
    route = ["C", "A", "T"]
    assert current_station(route, []) == ("C", "A")
    assert current_station(route, [{"ActivityID": "C", "Status": "SUBMITTED"}]) == ("A", "T")
    assert current_station(route, [{"ActivityID": "C", "Status": "UNDER REVIEW"}]) == ("A", "T")


def test_scoring_contract_normalises_time_and_uses_deterministic_shared_ranks():
    assert normalise_result("LOWEST_TIME", None, minutes=1, seconds=2, precision_ms=3) == 62003
    ranked = rank_verified_results([
        {"TeamID": "B", "Verified": True, "OfficialResult": 9},
        {"TeamID": "A", "Verified": True, "OfficialResult": 9},
        {"TeamID": "C", "Verified": True, "OfficialResult": 11},
    ], "LOWEST_TIME")
    assert [(row["TeamID"], row["Rank"]) for row in ranked] == [("A", 1), ("B", 1), ("C", 3)]
    assert performance_credits({"PerformanceCredits": {"RankCredits": {"1": 20}}}, ranked[0]) == 20


def test_configuration_validation_and_live_safety_contracts_are_generic():
    assert validate_stations([{ "ActivityID": "S1", "ShortCode": "X", "DisplayName": "Any station", "BaseCredits": 0}]) == []
    assert validate_marketplace_items([{ "ItemName": "Blueprint", "Category": "KNOWLEDGE", "CreditCost": 5, "KnowledgeContent": "https://example.test"}]) == []
    locks = configuration_lock_reasons(submissions=1, purchases=1, judging_scores=1)
    assert all(locks.values())
