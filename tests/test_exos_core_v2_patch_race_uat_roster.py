import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "exos_core_v2_patch_race_uat_roster.py"

spec = importlib.util.spec_from_file_location("exos_core_v2_patch_race_uat_roster", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)  # type: ignore[arg-type]


def test_team_index_accepts_canonical_race_uat_team_id() -> None:
    assert (
        module._team_index("CORE-V2-RACE-UAT-T01-4CF0CEAF5F", "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F")
        == 1
    )


def test_team_index_rejects_wrong_event_suffix() -> None:
    assert (
        module._team_index("CORE-V2-RACE-UAT-T01-DEADBEEF01", "CORE-V2-RACE-UAT-EVT-4CF0CEAF5F")
        is None
    )
