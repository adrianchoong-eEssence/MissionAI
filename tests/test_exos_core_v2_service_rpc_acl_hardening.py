from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDENING = (
    ROOT / "supabase/040a_exos_core_v2_service_rpc_acl_hardening.sql"
).read_text(encoding="utf-8")
CORE = (ROOT / "supabase/020_exos_core_v2_schema.sql").read_text(encoding="utf-8")
TEAM_ACCESS = (
    ROOT / "supabase/022_exos_core_v2_team_access.sql"
).read_text(encoding="utf-8")

SERVICE_ONLY = (
    "public.exos_v2_publish_event(text,text,text,jsonb,public.exos_v2_scoring_mode,text)",
    "public.exos_v2_admin_recover_identity(text,uuid,text,text,text)",
    "public.exos_v2_admin_merge_participants(text,uuid,uuid,text,text)",
    "public.exos_v2_ledger_score(text,text,uuid,numeric,text,public.exos_v2_scoring_mode,text)",
    "public.exos_v2_ledger_credit(text,text,uuid,text,integer,text,text)",
    "public.exos_v2_set_team_access_pin(text,text,text,text)",
)


def normalized(source):
    return " ".join(source.lower().split())


def test_source_contract_classifies_all_six_as_service_only():
    source = normalized(CORE + "\n" + TEAM_ACCESS)

    for signature in SERVICE_ONLY:
        assert f"grant execute on function {signature} to service_role;" in source
        assert f"grant execute on function {signature} to anon" not in source


def test_040a_enforces_service_role_only_on_exact_signatures():
    source = normalized(HARDENING)

    for signature in SERVICE_ONLY:
        assert (
            f"revoke execute on function {signature} "
            "from public, anon, authenticated;"
        ) in source
        assert f"grant execute on function {signature} to service_role;" in source


def test_040a_is_acl_only_and_does_not_touch_participant_rpcs():
    lowered = HARDENING.lower()

    assert "create or replace function" not in lowered
    assert "alter function" not in lowered
    assert "create trigger" not in lowered
    assert "drop trigger" not in lowered
    assert "insert into" not in lowered
    assert "update " not in lowered
    assert "delete from" not in lowered
    assert "truncate" not in lowered

    for participant_rpc in (
        "exos_v2_join_event_v2",
        "exos_v2_restore_join",
        "exos_v2_recover_participant_access",
        "exos_v2_team_access_login",
        "exos_v2_restore_team_access",
        "exos_v2_standard_participant_state",
        "exos_v2_standard_submit",
        "exos_v2_team_formation_register_random",
        "exos_v2_team_formation_claim_preassigned",
        "exos_v2_recover_team_formation_participant",
        "exos_v2_claim_team_formation_captain",
        "exos_v2_recover_team_formation_captain",
        "exos_v2_theme_park_race_submit",
        "exos_v2_theme_park_race_board_select",
        "exos_v2_theme_park_race_board_record_ride_outcome",
        "exos_v2_theme_park_race_board_submit",
    ):
        assert participant_rpc not in lowered
