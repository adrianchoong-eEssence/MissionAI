from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_exos_shell_locks_navigation_sidebar_open():
    source = (ROOT / "MissionAI.py").read_text()

    assert 'initial_sidebar_state="expanded"' in source
    assert "apply_branding(lock_sidebar=True)" in source


def test_locked_sidebar_css_overrides_persisted_collapsed_state():
    source = (ROOT / "branding.py").read_text()

    assert '[data-testid="stSidebar"][aria-expanded="false"]' in source
    assert "transform:translateX(0) !important" in source
    assert '[data-testid="stSidebarCollapseButton"]' in source
    assert '[data-testid="stExpandSidebarButton"]' in source
    assert "pointer-events:none !important" in source


def test_participant_and_facilitator_do_not_force_admin_navigation():
    participant = (ROOT / "Participant.py").read_text()
    facilitator = (ROOT / "Facilitator.py").read_text()

    assert "lock_sidebar=True" not in participant
    assert "lock_sidebar=True" not in facilitator
