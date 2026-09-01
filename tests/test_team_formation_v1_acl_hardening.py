from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDENING = (
    ROOT / "supabase/036a_team_formation_v1_acl_hardening.sql"
).read_text(encoding="utf-8")
MIGRATION = (
    ROOT / "supabase/036_exos_core_v2_team_formation_v1.sql"
).read_text(encoding="utf-8")

SERVICE_ONLY = (
    "public.exos_v2_configure_team_formation(text,text,jsonb,jsonb,text)",
    "public.exos_v2_open_team_formation(text,text)",
    "public.exos_v2_lock_team_formation(text,text)",
    "public.exos_v2_open_team_captain_selection(text,text)",
    "public.exos_v2_activate_team_formation(text,text)",
    "public.exos_v2_transfer_team_formation_captain(text,text,uuid,text,text)",
)
INTERNAL = (
    "public.exos_v2_team_formation_credential_hash(text)",
    "public.exos_v2_team_formation_participant_write_guard()",
    "public.exos_v2_team_formation_team_write_guard()",
    "public.exos_v2_team_formation_captain_session_guard()",
)
PARTICIPANT = (
    "public.exos_v2_team_formation_register_random(text,text,text,text)",
    "public.exos_v2_team_formation_claim_preassigned(text,text,text)",
    "public.exos_v2_recover_team_formation_participant(text,text,text)",
    "public.exos_v2_claim_team_formation_captain(uuid,text)",
    "public.exos_v2_recover_team_formation_captain(text,text,text)",
)


def normalized(source):
    return " ".join(source.lower().split())


def test_036_function_classification_matches_committed_role_contract():
    source = normalized(MIGRATION)

    for signature in SERVICE_ONLY:
        assert f"grant execute on function {signature} to service_role;" in source
        assert f"grant execute on function {signature} to anon" not in source
    for signature in PARTICIPANT:
        assert (
            f"grant execute on function {signature} "
            "to anon, authenticated, service_role;"
        ) in source


def test_036a_enforces_exact_function_role_matrix():
    source = normalized(HARDENING)

    for signature in SERVICE_ONLY + INTERNAL:
        assert (
            f"revoke all on function {signature} "
            "from public, anon, authenticated, service_role;"
        ) in source
        assert f"grant execute on function {signature} to service_role;" in source
        assert f"grant execute on function {signature} to anon" not in source

    for signature in PARTICIPANT:
        assert (
            f"revoke all on function {signature} "
            "from public, anon, authenticated, service_role;"
        ) in source
        assert (
            f"grant execute on function {signature} "
            "to anon, authenticated, service_role;"
        ) in source


def test_036a_is_acl_only_and_covers_every_036_function():
    source = normalized(HARDENING)
    lowered = HARDENING.lower()

    assert "create or replace function" not in lowered
    assert "alter function" not in lowered
    assert "create trigger" not in lowered
    assert "drop trigger" not in lowered
    assert "insert into" not in lowered
    assert "update " not in lowered
    assert "delete from" not in lowered
    assert "truncate" not in lowered

    expected = set(SERVICE_ONLY + INTERNAL + PARTICIPANT)
    covered = {
        signature
        for signature in expected
        if f"revoke all on function {signature} " in source
    }
    assert covered == expected
