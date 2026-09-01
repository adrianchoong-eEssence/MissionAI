from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDENING = (
    ROOT / "supabase/026a_standard_participant_access_acl_hardening.sql"
).read_text(encoding="utf-8")
RECOVERY = (
    ROOT / "supabase/026_standard_participant_access_recovery.sql"
).read_text(encoding="utf-8")


def test_026a_closes_only_direct_participant_access_to_identity_helper():
    normalized = " ".join(HARDENING.lower().split())

    assert normalized.count(
        "revoke execute on function "
        "public.exos_v2_identity_payload(text,uuid) "
        "from public, anon, authenticated;"
    ) == 1
    assert normalized.count(
        "grant execute on function "
        "public.exos_v2_identity_payload(text,uuid) to service_role;"
    ) == 1


def test_026a_is_acl_only_and_preserves_participant_wrapper_grants():
    lowered = HARDENING.lower()

    assert "create or replace function" not in lowered
    assert "alter function" not in lowered
    assert "insert into" not in lowered
    assert "update " not in lowered
    assert "delete from" not in lowered
    assert "truncate" not in lowered
    assert "exos_v2_restore_join" not in lowered
    assert "exos_v2_recover_participant_access" not in lowered

    normalized_recovery = " ".join(RECOVERY.lower().split())
    assert (
        "grant execute on function "
        "public.exos_v2_restore_join(text, text, text) "
        "to anon, authenticated;"
    ) in normalized_recovery
    assert (
        "grant execute on function "
        "public.exos_v2_recover_participant_access(text, text, text) "
        "to anon, authenticated;"
    ) in normalized_recovery
