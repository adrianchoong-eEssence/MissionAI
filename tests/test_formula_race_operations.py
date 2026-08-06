from engines.formula_race import BUILD_STATUSES,JUDGING_CATEGORIES,final_standings,judging_total,validate_purchase,wallet_projection

def test_judging_total_uses_exact_categories_without_hidden_weights():
    scores={category:8 for category in JUDGING_CATEGORIES}
    assert judging_total(scores)==48

def test_wallet_reconciles_event_and_team_transactions_only():
    rows=[{"EventID":"E1","TeamID":"T1","Amount":100},{"EventID":"E1","TeamID":"T1","Amount":-35},
          {"EventID":"E1","TeamID":"T2","Amount":999},{"EventID":"E2","TeamID":"T1","Amount":999}]
    assert wallet_projection(rows,"E1","T1")["Balance"]==65

def test_marketplace_prevents_overspend_negative_stock_and_bad_quantity():
    assert validate_purchase(100,5,20,5)==(True,"")
    assert validate_purchase(99,5,20,5)[0] is False
    assert validate_purchase(100,4,20,5)[0] is False
    assert validate_purchase(100,5,20,0)[0] is False

def test_final_ranking_and_tie_break_are_deterministic():
    teams=[{"TeamID":"T2","TeamName":"Bolt"},{"TeamID":"T1","TeamName":"Apex"}]
    awards=[{"TeamID":"T1","Amount":10},{"TeamID":"T2","Amount":10}]
    rows=final_standings(teams,awards,[],[])
    assert [row["TeamName"] for row in rows]==["Apex","Bolt"]
    assert [row["Rank"] for row in rows]==[1,2]

def test_build_status_vocabulary_is_locked():
    assert BUILD_STATUSES==("Not Started","Collecting Parts","Building","Painting","Ready to Race","Completed")
