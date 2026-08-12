from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_participant_displays_approved_submission_score_not_static_credit_seed():
    source = (ROOT / "screens/participant.py").read_text()
    existing = source.split("def render_existing_submission", 1)[1].split(
        "def save_structured_submission", 1
    )[0]
    programme = source.split("def render_programme_activity", 1)[1].split(
        "def render_mission_ai_briefing", 1
    )[0]

    assert 'st.metric("Approved score", f"{_credit_number(approved_score)} pts")' in existing
    assert 'existing_submission.get("Score", "")' in existing
    assert 'contract.get("Type") == "NON_SCORING"' in existing
    assert 'Completed / Approved · Non-scoring' in existing
    assert 'st.metric("Credits", details["Credits"])' not in programme
    assert 'details.get("ScoringMode", "")' in programme
    assert "Competitive score is finalised after facilitator review." in programme


def test_standard_approval_uses_score_ledger_only_and_is_idempotent():
    sql = (ROOT / "supabase/025_standard_programme_runtime.sql").read_text()

    assert "insert into public.score_transactions_v2" in sql
    assert "on conflict(event_id,idempotency_key) do update" in sql
    assert "insert into public.credit_transactions_v2" not in sql
