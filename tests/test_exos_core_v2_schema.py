import os
import re

from pathlib import Path
from shutil import which

import pytest

ROOT = Path("supabase")
SUPPORT = ROOT / "verification"
MIGRATION = (ROOT / "020_exos_core_v2_schema.sql").read_text()
TEAM_ACCESS_PATCH = (ROOT / "022_exos_core_v2_team_access.sql").read_text()
ROLLBACK = (ROOT / "020_exos_core_v2_schema_rollback.sql").read_text()
PRECHECK = (SUPPORT / "exos_core_v2_preflight.sql").read_text()
POSTCHECK = (SUPPORT / "exos_core_v2_postflight.sql").read_text()
ROLLBACK_VERIFY = (SUPPORT / "exos_core_v2_rollback_verify.sql").read_text()


REQUIRED_TABLES = [
    "events_v2",
    "programmes_v2",
    "modules_v2",
    "activities_v2",
    "teams_v2",
    "participants_v2",
    "participant_sessions_v2",
    "activity_runtime_v2",
    "submissions_v2",
    "submission_evidence_v2",
    "reviews_v2",
    "score_transactions_v2",
    "credit_transactions_v2",
    "marketplace_items_v2",
    "marketplace_transactions_v2",
    "build_status_v2",
    "judging_scores_v2",
    "race_results_v2",
    "projector_state_v2",
    "location_checkpoints_v2",
    "location_evidence_v2",
    "ai_jobs_v2",
    "ai_results_v2",
    "audit_log_v2",
]


def test_core_v2_requires_v2_tables():
    lowered = MIGRATION.lower()
    for table in REQUIRED_TABLES:
        assert f"create table if not exists public.{table}".lower() in lowered


def test_core_v2_identity_contracts_present():
    lowered = MIGRATION.lower()
    for name in (
        "exos_v2_publish_event",
        "exos_v2_join_event_v2",
        "exos_v2_restore_join",
        "exos_v2_admin_recover_identity",
        "exos_v2_admin_merge_participants",
        "exos_v2_ledger_score",
        "exos_v2_ledger_credit",
    ):
        assert f"create or replace function public.{name}".lower() in lowered
    assert "revoke all on function public.exos_v2_join_event_v2" in MIGRATION
    assert "grant execute on function public.exos_v2_join_event_v2" in MIGRATION


def test_core_v2_scoring_mode_controls():
    lowered = MIGRATION.lower()
    assert "create type if not exists public.exos_v2_scoring_mode" not in lowered
    for mode in ("team_competitive", "enterprise", "non_scoring"):
        assert f"'{mode.upper()}'" in MIGRATION


def test_core_v2_event_team_isolation():
    lowered = MIGRATION.lower()
    for fragment in (
        "event_id text not null references public.events_v2(event_id)",
        "team_id text not null references public.teams_v2(team_id)",
        "event_id text not null references public.events_v2(event_id)",
        "alter table public.teams_v2 enable row level security",
    ):
        assert fragment in lowered


def test_core_v2_indexes_and_security():
    lowered = MIGRATION.lower()
    assert "create index if not exists teams_v2_event_idx" in lowered
    assert "create index if not exists participant_sessions_v2_event_idx" in lowered
    assert "create index if not exists submissions_v2_event_idx" in lowered
    assert "alter table public.score_transactions_v2 enable row level security" in lowered
    assert "revoke all on table public.events_v2 from anon, authenticated" in MIGRATION


def test_core_v2_rollback_is_guarded_and_does_not_drop_data():
    lowered = ROLLBACK.lower()
    assert "rollback blocked" in lowered
    assert "select count(*) into v_rows from public.score_transactions_v2" in lowered
    assert "drop table if exists public.events_v2" in lowered
    assert "drop function if exists public.exos_v2_join_event_v2" in lowered


def test_core_v2_schema_verification_exists():
    for path in (PRECHECK, POSTCHECK, ROLLBACK_VERIFY):
        assert len(path) > 10
    assert "required_extensions" in PRECHECK
    assert "orphan_submission" in POSTCHECK
    assert "rollback guard" in ROLLBACK_VERIFY.lower() or "v2_rollback_guard_present" in ROLLBACK_VERIFY


def test_core_v2_schema_has_postgres_safe_type_creation():
    lowered = MIGRATION.lower()
    assert re.search(r"create\s+type\s+if\s+not\s+exists\s+public\.exos_v2_", lowered) is None
    assert re.search(r"create\s+policy\s+if\s+not\s+exists", lowered) is None


def test_core_v2_sql_artifacts_do_not_contain_bad_dollar_quotes():
    bad_patterns = [
        re.compile(r"\$\*.*\$\*"),
        re.compile(r"\*\$\$"),
        re.compile(r"`"),
    ]

    for path in (
        Path("supabase/020_exos_core_v2_schema.sql"),
        Path("supabase/021_exos_core_v2_pgcrypto_fix.sql"),
        Path("supabase/022_exos_core_v2_team_access.sql"),
    ):
        text = path.read_text().lower()
        for pattern in bad_patterns:
            assert pattern.search(text) is None, (
                f"found malformed SQL artifact in {path}: pattern {pattern.pattern}"
            )


def test_core_v2_sql_no_wrapper_or_unqualified_pgcrypto_calls():
    files = (
        Path("supabase/020_exos_core_v2_schema.sql"),
        Path("supabase/021_exos_core_v2_pgcrypto_fix.sql"),
    )
    disallowed_wrappers = re.compile(r"create\s+or\s+replace\s+function\s+extensions\.(?:digest|gen_random_uuid|crypt|gen_salt)\s*\(", re.IGNORECASE)
    disallowed_public_calls = re.compile(r"\bpublic\.(?:digest|gen_random_uuid|crypt|gen_salt)\s*\(", re.IGNORECASE)
    unqualified_calls = re.compile(r"(?<![\w\.])(?:digest|gen_random_uuid|crypt|gen_salt)\s*\(", re.IGNORECASE)

    for path in files:
        text = path.read_text()
        assert disallowed_wrappers.search(text) is None, (
            f"{path}: wrapper/proxy function definition detected for pgcrypto call"
        )
        assert disallowed_public_calls.search(text) is None, (
            f"{path}: public-schema pgcrypto call detected"
        )
        cleaned = re.sub(
            r"(--.*?$|/\*.*?\*/|'[^']*'|\"[^\"]*\")",
            "",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        for match in unqualified_calls.finditer(cleaned):
            token = match.group(0).lower()
            raise AssertionError(f"{path}: unqualified pgcrypto call detected: {token} at {match.start()}")


def test_core_v2_team_access_contract_present():
    lowered = TEAM_ACCESS_PATCH.lower()
    for table in ("team_access_credentials_v2", "team_access_sessions_v2"):
        assert f"create table if not exists public.{table}" in lowered
    for rpc in (
        "exos_v2_set_team_access_pin",
        "exos_v2_team_access_login",
        "exos_v2_restore_team_access",
    ):
        assert f"create or replace function public.{rpc}" in lowered
        assert f"grant execute on function public.{rpc}" in TEAM_ACCESS_PATCH
    assert "formula_race" not in lowered


def test_core_v2_join_event_v2_session_insert_sql_shape():
    pattern = re.compile(
        r"create or replace function public\.exos_v2_join_event_v2[\s\S]*?"
        r"insert into public\.participant_sessions_v2[\s\S]*?"
        r"on conflict \(event_id, idempotency_key\) do update[\s\S]*?"
        r"set[\s\S]*?is_active = true\s*\n\s*returning \* into v_session;",
        re.IGNORECASE,
    )
    assert pattern.search(MIGRATION) is not None
    assert ") returning * into v_session" not in MIGRATION


def test_core_v2_schema_enum_creation_is_guarded():
    for enum_name in (
        "exos_v2_activity_type",
        "exos_v2_scoring_mode",
        "exos_v2_submission_status",
        "exos_v2_review_decision",
        "exos_v2_build_status",
    ):
        assert f"select 1 from pg_type t" in MIGRATION
        assert f"create type public.{enum_name}" in MIGRATION


@pytest.mark.skipif(not os.getenv("POSTGRES_TEST_DSN") or not which("psql"), reason="POSTGRES_TEST_DSN/psql not available")
def test_core_v2_schema_executes_clean_on_local_postgres():
    import subprocess

    dsn = os.environ["POSTGRES_TEST_DSN"]
    proc = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(Path("supabase/020_exos_core_v2_schema.sql"))],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(f"Migration execution failed: {proc.stderr}")
