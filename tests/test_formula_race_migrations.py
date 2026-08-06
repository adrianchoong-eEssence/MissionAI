from pathlib import Path

ROOT=Path("supabase")
M15=(ROOT/"015_formula_race_preassigned_identity.sql").read_text()
M16=(ROOT/"016_formula_race_captain_sessions.sql").read_text()
M17=(ROOT/"017_formula_race_operations.sql").read_text()
VERIFY=(ROOT/"formula_race_migrations_verify.sql").read_text()

def test_every_formula_migration_has_a_rollback():
    for number,name in ((15,"formula_race_preassigned_identity"),(16,"formula_race_captain_sessions"),(17,"formula_race_operations")):
        assert (ROOT/f"{number:03d}_{name}_rollback.sql").is_file()

def test_all_team_entities_use_composite_event_team_foreign_keys():
    assert "unique (event_id, team_id)" in (ROOT/"runtime_schema.sql").read_text()
    assert M16.count("foreign key(event_id,team_id) references public.runtime_teams(event_id,team_id)")==1
    assert M17.count("foreign key(event_id,team_id) references public.runtime_teams(event_id,team_id)")==3

def test_indexes_cover_sessions_current_rows_and_history():
    for name in ("formula_race_team_access_session_uidx","formula_race_team_access_event_connected_idx"):
        assert name in M16
    for name in ("formula_race_build_event_team_created_idx","formula_race_judging_one_current",
                 "formula_race_judging_history_idx","formula_race_results_one_current","formula_race_results_history_idx"):
        assert name in M17

def test_constraints_cover_status_scores_results_and_audit_identity():
    for status in ("Not Started","Collecting Parts","Building","Painting","Ready to Race","Completed"):
        assert status in M17
    for fragment in ("total_score>=0 and total_score<=60","finish_time_ms>=0","penalty_ms>=0",
                     "bonus_credits>=0","length(trim(reason))>0","length(trim(created_by))>0"):
        assert fragment in M17
    assert "length(trim(updated_by))>0" in M16

def test_rls_and_privilege_boundaries_are_explicit():
    for table in ("formula_race_team_access",):
        assert f"alter table public.{table} enable row level security" in M16
    for table in ("formula_race_build_status","formula_race_judging","formula_race_results","formula_race_event_config"):
        assert f"alter table public.{table} enable row level security" in M17
    assert "revoke all on table public.formula_race_team_access from anon,authenticated" in M16
    assert "to service_role" in M16 and "to service_role" in M17

def test_every_mutation_is_event_and_team_scoped():
    for function in ("exos_set_formula_race_build_status","exos_save_formula_race_judging","exos_save_formula_race_result"):
        body=M17.split(f"public.{function}",1)[1]
        assert "p_event_id" in body and "p_team_id" in body
        assert "event_id=trim(p_event_id) and team_id=trim(p_team_id)" in body
    assert "event_id=e.event_id and team_id=trim(p_team_id)" in M16

def test_rollbacks_are_data_guarded():
    assert "Rollback blocked" in (ROOT/"016_formula_race_captain_sessions_rollback.sql").read_text()
    rollback=(ROOT/"017_formula_race_operations_rollback.sql").read_text()
    assert "Rollback blocked" in rollback and "select count(*)" in rollback

def test_post_deployment_verifier_checks_catalog_security_and_isolation():
    for fragment in ("relrowsecurity","role_table_grants","Expected four composite team foreign keys",
                     "SECURITY DEFINER","Missing required index"):
        assert fragment in VERIFY

def test_legacy_individual_join_is_not_required_by_verifier():
    assert "exos_join_preassigned_event" not in VERIFY
    assert "insert into public.runtime_participants" not in M15
