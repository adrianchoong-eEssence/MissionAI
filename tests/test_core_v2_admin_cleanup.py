from pathlib import Path

import pytest

from screens.programme_builder import _source_stages_for
from engines.programme_hierarchy import canonical_event_programme
from scripts.exos_core_v2_prepare_aia_weekend import agile_programme
from scripts.exos_core_v2_staging_cleanup import (
    DELETE_ALLOWLIST,
    DELETE_ORDER,
    KEEP_EVENT_IDS,
    require_staging,
)


ROOT = Path(__file__).resolve().parents[1]


def test_real_aia_candidate_tuple_resolves_without_integer_dict_key():
    upper = {"EventID": "AIA-WE-260810081110-UPPER", "EventName": "AIA Upper South"}
    lower = {"EventID": "AIA-WE-260810081110-LOWER", "EventName": "AIA Lower South"}
    upper_stages = [{"StageName": f"Stage {index}"} for index in range(1, 8)]
    lower_stages = [{"StageName": f"Stage {index}"} for index in range(1, 8)]
    candidates = [(upper, upper_stages), (lower, lower_stages)]
    assert _source_stages_for(candidates, upper["EventID"]) == upper_stages
    assert _source_stages_for(candidates, lower["EventID"]) == lower_stages


@pytest.mark.parametrize("event_id", [
    "AIA-WE-260810081110-UPPER",
    "AIA-WE-260810081110-LOWER",
])
def test_real_aia_seven_stage_shape_has_every_builder_render_key(event_id):
    stages = [module["Activities"][0] for module in agile_programme(event_id)]
    modules = canonical_event_programme(stages, event_id)
    assert [module["ModuleName"] for module in modules] == [
        "Launch App / Country Assignment", "Pipeline", "Helium Stick",
        "Key Punch", "Lunch / Break", "Catalyst Challenge", "NASI",
    ]
    assert len(modules) == 7
    for module in modules:
        assert {
            "ModuleName", "Day", "DurationMinutes", "ActivityCount",
            "Activities", "StartTime",
        } <= set(module)
        assert len(module["Activities"]) == 1


def test_cleanup_allow_lists_are_explicit_disjoint_and_complete_for_audit():
    assert set(KEEP_EVENT_IDS) == {
        "AIA-WE-260810081110-UPPER",
        "AIA-WE-260810081110-LOWER",
        "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F",
    }
    assert len(DELETE_ALLOWLIST) == 9
    assert set(KEEP_EVENT_IDS).isdisjoint(DELETE_ALLOWLIST)


def test_cleanup_order_is_child_first():
    assert DELETE_ORDER.index("submission_evidence_v2") < DELETE_ORDER.index("submissions_v2")
    assert DELETE_ORDER.index("submissions_v2") < DELETE_ORDER.index("participants_v2")
    assert DELETE_ORDER.index("team_access_sessions_v2") < DELETE_ORDER.index("team_access_credentials_v2")
    assert DELETE_ORDER.index("activities_v2") < DELETE_ORDER.index("modules_v2")
    assert DELETE_ORDER.index("modules_v2") < DELETE_ORDER.index("programmes_v2")
    assert DELETE_ORDER[-1] == "events_v2"


def test_cleanup_requires_staging_and_refuses_production(monkeypatch):
    runtime = type("Runtime", (), {
        "url": "https://staging-example.supabase.co",
        "can_publish": True,
    })()
    monkeypatch.delenv("EXOS_ENV", raising=False)
    with pytest.raises(RuntimeError, match="EXOS_ENV"):
        require_staging(runtime)
    monkeypatch.setenv("EXOS_ENV", "staging")
    runtime.url = "https://bqsbkdfzqyiodivhyxnq.supabase.co"
    with pytest.raises(RuntimeError, match="non-staging"):
        require_staging(runtime)


def test_cleanup_is_dry_run_by_default_and_requires_execute_flag():
    source = (ROOT / "scripts/exos_core_v2_staging_cleanup.py").read_text()
    assert 'parser.add_argument("--execute", action="store_true"' in source
    assert 'report["DryRun"] = not args.execute' in source
    assert 'execute(runtime, report) if args.execute else' in source


def test_event_home_has_explicit_current_archived_and_all_views():
    source = (ROOT / "screens/events_home.py").read_text()
    assert '["Current", "Archived / Inactive", "All"]' in source
    assert 'db.get_events(include_archived=True)' in source


def test_programme_builder_has_no_duplicate_start_blank_widget_key():
    source = (ROOT / "screens/programme_builder.py").read_text()
    assert source.count('key=f"start_blank_{event_id}"') == 1
    assert 'key=f"manual_start_blank_{event_id}"' in source
