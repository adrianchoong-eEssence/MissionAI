from datetime import datetime, timedelta, timezone
from pathlib import Path

from engines.live_location import derive_team_locations, location_status


ROOT = Path(__file__).resolve().parents[1]


def test_status_is_deterministic_and_team_centroid_never_hides_separation():
    now = datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc)
    assert location_status(now - timedelta(seconds=90), consent_enabled=True, now=now, stale_after_seconds=90) == "CURRENT"
    assert location_status(now - timedelta(seconds=91), consent_enabled=True, now=now, stale_after_seconds=90) == "STALE"
    assert location_status(now, consent_enabled=False, now=now, stale_after_seconds=90) == "UNAVAILABLE"
    rows = [
        {"TeamID": "GT-01", "Status": "CURRENT", "Latitude": 5.4141, "Longitude": 100.3288},
        {"TeamID": "GT-01", "Status": "CURRENT", "Latitude": 5.4142, "Longitude": 100.3289},
        {"TeamID": "GT-02", "Status": "CURRENT", "Latitude": 5.0, "Longitude": 100.0},
        {"TeamID": "GT-02", "Status": "CURRENT", "Latitude": 6.0, "Longitude": 101.0},
        {"TeamID": "GT-03", "Status": "STALE", "Latitude": 5.4, "Longitude": 100.3},
    ]
    teams = {row["TeamID"]: row for row in derive_team_locations(rows, separation_threshold_meters=250)}
    assert teams["GT-01"]["Status"] == "CURRENT" and teams["GT-01"]["Location"] is not None
    assert teams["GT-02"]["Status"] == "SEPARATED" and teams["GT-02"]["Location"] is None
    assert teams["GT-03"]["Status"] == "UNAVAILABLE" and teams["GT-03"]["Location"] is None


def test_core_migration_is_additive_scoped_rls_protected_and_uses_canonical_operations():
    migration = (ROOT / "supabase" / "048_exos_core_v2_live_location_announcements_v1.sql").read_text()
    for table in ("event_location_configurations_v2", "participant_location_consents_v2", "participant_location_updates_v2", "event_announcements_v2"):
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" in migration
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in migration
    assert "p_session_token" in migration and "p_event_id" in migration
    assert "SET search_path = ''" in migration
    assert "ALL + URGENT announcements require explicit confirmation" in migration
    assert "idempotency_key" in migration and "Idempotent" in migration
    assert "UNIQUE (event_id, idempotency_key)" in migration
    assert "Live location consent is required" in migration
    assert "NOT v_config.enabled OR now() < v_config.tracking_starts_at" in migration
    assert "LIVE_LOCATION_UPDATED" in migration
    assert "AwardsMissionScore" not in migration
    assert "projector" not in migration.casefold()
    assert "GRANT EXECUTE" in migration and "TO anon, authenticated" in migration


def test_participant_and_mission_control_surfaces_use_only_the_adapter_and_in_app_polling():
    participant = (ROOT / "services" / "live_location_participant.py").read_text()
    component = (ROOT / "components" / "live_location" / "index.html").read_text()
    watcher = (ROOT / "services" / "maxis_live_state.py").read_text()
    control = (ROOT / "screens" / "live_location_operations.py").read_text()
    adapter = (ROOT / "data" / "standard_core_v2_adapter.py").read_text()
    kai = (ROOT / "services" / "kai_location_operations.py").read_text()
    assert "ENABLE LIVE LOCATION" in participant and "LOCATION UNAVAILABLE" in participant
    assert "ACKNOWLEDGE" in participant and "get_participant_announcements" in participant
    assert "background tracking is not guaranteed" in component
    assert "Location permission was denied" in component and "LOCATION UNAVAILABLE" in component
    assert "get_participant_announcements(session_token)" in watcher
    assert "ALL + URGENT announcement" in control and "get_live_location_operator_map" in control
    assert "exos_v2_submit_live_location" in adapter and "exos_v2_send_event_announcement" in adapter
    assert "idempotency_key" in adapter and "uuid.uuid4" in control
    assert "runtime.send_event_announcement(event_id, **payload)" in kai


def test_aia_integration_is_explicit_and_never_uses_gps_for_score():
    aia = (ROOT / "screens" / "aia_random_registration.py").read_text()
    config = (ROOT / "supabase" / "049_aia_tech_live_location_v1_configuration.sql").read_text()
    assert "render_live_location_participant" in aia and "render_participant_announcements" in aia
    assert "AIA-TECH-20261023-UAT" in config
    assert "'INDIVIDUAL'" in config and "AwardsMissionScore', false" in config
    assert "OWNER_WINDOW_REQUIRED" in config


def test_250_location_plan_is_explicitly_unexecuted_and_requires_real_mobile_uat():
    source = (ROOT / "scripts" / "exos_location_announcements_250_plan.py").read_text()
    assert "NOT_EXECUTED" in source
    assert "same-time second event isolation" in source
    assert "no background-tracking PASS claim" in source
    assert "real browser/mobile runners" in source


def test_operational_documentation_sets_privacy_and_retention_contracts_without_global_event_state():
    doc = (ROOT / "docs" / "EXOS_LIVE_LOCATION_ANNOUNCEMENTS_V1.md").read_text()
    assert "15 to 30 seconds" in doc and "90 seconds" in doc and "24 hours" in doc
    assert "background tracking is not guaranteed" in doc
    assert "does not create a global current-event context" in doc
    assert "does not award a score" in doc


def test_window_visibility_guard_keeps_retained_points_unavailable_outside_tracking_time():
    guard = (ROOT / "supabase" / "050_exos_live_location_window_visibility_guard.sql").read_text()
    assert "CREATE OR REPLACE FUNCTION public.exos_v2_live_location_operator_map" in guard
    assert "NOT v_config.enabled OR now() < v_config.tracking_starts_at" in guard
    assert "TO service_role" in guard and "FROM PUBLIC, anon, authenticated" in guard


def test_location_history_is_bounded_and_checkpoint_path_has_no_score_mutation():
    migration = (ROOT / "supabase" / "048_exos_core_v2_live_location_announcements_v1.sql").read_text()
    assert "LIMIT greatest(1, least(coalesce(p_limit, 20), 100))" in migration
    checkpoint = migration.split("CREATE OR REPLACE FUNCTION public.exos_v2_live_location_checkpoint_proximity", 1)[1]
    checkpoint = checkpoint.split("CREATE OR REPLACE FUNCTION public.exos_v2_cleanup_live_location", 1)[0]
    assert "score" not in checkpoint.casefold()
