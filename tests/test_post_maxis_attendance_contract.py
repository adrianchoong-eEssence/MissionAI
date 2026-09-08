"""P0-A source contracts for canonical, opt-in attendance."""

from pathlib import Path

from data.standard_core_v2_adapter import StandardCoreV2Adapter


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / "supabase/042_post_maxis_p0_attendance.sql").read_text(encoding="utf-8")
ROLLBACK = (ROOT / "supabase/042_post_maxis_p0_attendance_rollback.sql").read_text(encoding="utf-8")
VERIFIER = (ROOT / "supabase/verification/exos_v2_post_maxis_attendance_verify.sql").read_text(encoding="utf-8")
CERTIFICATION = (ROOT / "supabase/certification/exos_v2_post_maxis_attendance_certification.sql").read_text(encoding="utf-8")


SERVICE_RPCS = (
    "public.exos_v2_configure_attendance(text, text)",
    "public.exos_v2_set_participant_attendance(text, uuid, text, text, text)",
    "public.exos_v2_attendance_summary(text)",
    "public.exos_v2_attendance_roster(text)",
)


def _normalised(value: str) -> str:
    return " ".join(value.lower().split())


def test_attendance_migration_is_additive_opt_in_and_does_not_rewrite_frozen_engines():
    source = _normalised(MIGRATION)

    assert "create table if not exists public.participant_attendance_v2" in source
    assert "attendance is opt-in" in source
    assert "{attendance,schemaversion}" in source
    assert "attendance is not configured for this event" in source
    assert "race4cf0ce" not in source
    assert "formula_race" not in source
    assert "delete from public.events_v2" not in source
    assert "delete from public.participants_v2" not in source
    assert "update public.participants_v2" not in source
    assert "update public.teams_v2" not in source


def test_attendance_states_audit_identity_safety_and_present_team_denominator_are_explicit():
    source = _normalised(MIGRATION)

    assert "check (attendance_state in ('preassigned', 'present', 'absent'))" in source
    assert "participant_attendance_changed" in source
    assert "pg_advisory_xact_lock" in source
    assert "presentteamsize" in source
    assert "from public.teams_v2 t" in source
    assert "left join public.participants_v2 p" in source
    assert "merged_into_participant_id is null" in source
    assert "not is_archived" in source
    assert "exos.attendance_mutation" in source


def test_attendance_acl_is_service_only_with_rls_and_a_canonical_write_guard():
    source = _normalised(MIGRATION)

    assert "alter table public.participant_attendance_v2 enable row level security" in source
    assert "create trigger exos_v2_participant_attendance_write_guard" in source
    assert "security definer" in source
    assert "set search_path = ''" in source
    for signature in SERVICE_RPCS:
        assert f"revoke all on function {signature.lower()} from public, anon, authenticated, service_role" in source
        assert f"grant execute on function {signature.lower()} to service_role" in source
    assert "grant execute on function public.exos_v2_set_participant_attendance(text, uuid, text, text, text) to anon" not in source
    assert "grant execute on function public.exos_v2_set_participant_attendance(text, uuid, text, text, text) to authenticated" not in source


def test_guarded_rollback_refuses_reinterpretation_and_never_deletes_history():
    source = _normalised(ROLLBACK)

    assert "rollback refused" in source
    assert "participant_attendance_v2" in source
    assert "attendance_configured" in source
    assert "participant_attendance_changed" in source
    for destructive in ("delete from", "truncate", "update public.events_v2"):
        assert destructive not in source


def test_verifier_checks_real_release_properties_not_just_function_presence():
    source = _normalised(VERIFIER)

    for token in (
        "security_definer", "search_path_pinned_to_empty",
        "public_execute_revoked", "anon_authenticated_execute_revoked",
        "service_role_matrix_correct", "no_unexpected_overloads",
        "attendance_rls_enabled", "canonical_write_guard_trigger_present",
        "explicit_event_opt_in_installed", "canonical_audited_mutation_installed",
        "canonical_counts_and_present_team_size_installed",
    ):
        assert token in source
    assert "insert into" not in source
    assert "update " not in source
    assert "delete from" not in source


def test_disposable_certification_is_exactly_scoped_and_protects_maxis_sentinel():
    source = _normalised(CERTIFICATION)

    assert "cert-p0a-attendance-20260908" in source
    assert "cert-p0a residue exists" in source
    assert "maxis historical sentinel changed during p0-a certification" in source
    assert "participant_attendance_changed') <> 5" in source
    assert "presentteamsize" in source
    assert "has_function_privilege('anon'" in source
    assert "delete from public.participant_attendance_v2" in source
    assert "where event_id = 'cert-p0a-attendance-20260908'" in source
    assert "delete from public.events_v2 where event_id = 'maxis-20260907-mission-ai'" not in source


class _FakeRuntime:
    is_configured = True
    can_publish = True
    url = "https://umgavcfzdaunfevaumez.supabase.co"

    def __init__(self):
        self.calls = []

    def _request(self, method, path, payload=None, query=None, admin=True, retries=4):
        self.calls.append((method, path, payload, admin))
        return {"ok": True}


def test_adapter_routes_attendance_only_to_the_service_rpc_contract():
    runtime = _FakeRuntime()
    adapter = StandardCoreV2Adapter(runtime=runtime)

    adapter.configure_attendance("EVENT", "Facilitator")
    adapter.set_participant_attendance("EVENT", "00000000-0000-0000-0000-000000000001", "present", "Facilitator", "arrived")
    adapter.get_attendance_summary("EVENT")
    adapter.get_attendance_roster("EVENT")

    assert [call[1] for call in runtime.calls] == [
        "rpc/exos_v2_configure_attendance",
        "rpc/exos_v2_set_participant_attendance",
        "rpc/exos_v2_attendance_summary",
        "rpc/exos_v2_attendance_roster",
    ]
    assert all(call[3] is True for call in runtime.calls)
    assert runtime.calls[1][2] == {
        "p_event_id": "EVENT",
        "p_participant_id": "00000000-0000-0000-0000-000000000001",
        "p_attendance_state": "PRESENT",
        "p_actor": "Facilitator",
        "p_reason": "arrived",
    }


def test_theme_park_facilitator_uses_canonical_attendance_reads_and_control_facade_only():
    source = (ROOT / "screens/theme_park_race.py").read_text(encoding="utf-8")
    control = (ROOT / "data/control_runtime.py").read_text(encoding="utf-8")

    assert "def _render_attendance_control" in source
    assert "get_attendance_summary(event_id)" in source
    assert "get_attendance_roster(event_id)" in source
    assert "control.configure_attendance(event_id, actor)" in source
    assert "control.set_participant_attendance(" in source
    assert "Participant identity and team assignment are unchanged" in source
    assert "def configure_attendance" in control
    assert "def set_participant_attendance" in control
