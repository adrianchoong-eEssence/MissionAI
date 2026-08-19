"""Operational coverage for the R.A.C.E. end-game: projector, purchase, judging, race.

Every projector surface is read-only and reuses the canonical Championship
Leaderboard; none of these tests touch a live event.
"""
from __future__ import annotations

import os
from pathlib import Path

from engines.formula_race_championship import championship_component_points, normalise_championship_component
from screens.formula_race_captain import _completed_purchase_count, _purchase_idempotency_key
from screens.formula_race_projector import PROJECTOR_VIEWS, _championship_is_complete

ROOT = Path(__file__).resolve().parents[1]
EVENT = "DISPOSABLE-ENDGAME-EVT"
TEAMS = [(f"DT-{n:02d}", f"Disposable Team {n:02d}") for n in range(1, 11)]
RANK_POINTS = {"1": 50, "2": 45, "3": 40, "4": 35, "5": 30, "6": 25, "7": 20, "8": 15, "9": 10, "10": 5}

COMPONENTS = [
    {"ComponentID": "C-AES", "DisplayOrder": 1, "DisplayName": "Aesthetics & Design", "ComponentType": "JUDGING_CRITERION",
     "SourceReference": "Aesthetics & Design", "MaximumChampionshipPoints": 40, "Enabled": True},
    {"ComponentID": "C-PHOTO", "DisplayOrder": 2, "DisplayName": "Team Photo", "ComponentType": "TEAM_PHOTO",
     "SourceReference": "Team Photo", "MaximumChampionshipPoints": 10, "Enabled": True},
    {"ComponentID": "C-DRAG", "DisplayOrder": 3, "DisplayName": "Drag Race Speed", "ComponentType": "RACE_RANK",
     "SourceReference": "", "MaximumChampionshipPoints": 50, "Enabled": True,
     "ScoringConfiguration": {"RankPoints": RANK_POINTS}},
]


def _stub_script(complete: str, view: str) -> str:
    return f'''
import json, streamlit as st
from screens.formula_race_projector import show_formula_race_projector

TEAMS = {TEAMS!r}
COMPONENTS = {COMPONENTS!r}
COMPLETE = {complete!r} == "yes"

class Runtime:
    def get_runtime_teams(self, event_id):
        return [{{"TeamID": t, "TeamName": n}} for t, n in TEAMS]

    def get_formula_race_configuration(self, event_id):
        return {{
            "ChampionshipComponents": COMPONENTS,
            "JudgingCriteria": [
                {{"CriterionName": "Aesthetics & Design", "MaximumScore": 40, "Enabled": True,
                  "Description": "Creativity, Finishing, Colour coordination, Branding, Attention to detail"}},
                {{"CriterionName": "Team Photo", "MaximumScore": 10, "Enabled": True,
                  "Description": "Team participation, Creativity, Energy, Overall presentation"}},
            ],
        }}

    def get_canonical_transaction_report(self, event_id):
        leaderboard, breakdown = [], []
        for index, (team_id, name) in enumerate(TEAMS):
            drag = {list(RANK_POINTS.values())!r}[index]
            aes = 40 - index
            photo = 10 - (index % 3)
            total = drag + aes + photo if COMPLETE else 0
            leaderboard.append({{"TeamID": team_id, "ChampionshipScore": total,
                                "WalletBalance": 80 - index * 3, "Rank": index + 1}})
            if COMPLETE:
                breakdown += [
                    {{"TeamID": team_id, "ComponentID": "C-AES", "Points": aes}},
                    {{"TeamID": team_id, "ComponentID": "C-PHOTO", "Points": photo}},
                    {{"TeamID": team_id, "ComponentID": "C-DRAG", "Points": drag}},
                ]
        return {{"Leaderboard": leaderboard, "ChampionshipBreakdown": breakdown}}

    def get_race_judging(self, event_id):
        if not COMPLETE:
            return []
        return [{{"team_id": t, "score_dimension": d, "decision": "SUBMITTED"}}
                for t, _ in TEAMS for d in ("Aesthetics & Design", "Team Photo")]

    def get_race_results(self, event_id):
        if not COMPLETE:
            return []
        return [{{"team_id": t, "locked": True, "checkpoint": "Race Final"}} for t, _ in TEAMS]

show_formula_race_projector({view!r}, Runtime(), "{EVENT}")
'''


def _render(view: str, complete: str = "no"):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string(_stub_script(complete, view), default_timeout=90)
    app.run()
    assert not app.exception, [str(e.value) for e in app.exception]
    return app, " ".join(block.value for block in app.markdown)


def _no_admin_controls(app):
    """A projector must never expose a control that can write."""
    assert not app.button
    assert not app.text_input
    assert not app.number_input
    assert not app.selectbox
    assert not app.slider
    assert not app.checkbox


# --------------------------------------------------------------------------
# Projector surfaces
# --------------------------------------------------------------------------

def test_performance_credits_projector_shows_ten_teams_and_canonical_wallets():
    app, body = _render("credits")
    assert "PERFORMANCE CREDITS" in body.upper()
    for _, name in TEAMS:
        assert name in body
    # Highest wallet first, and never presented as a Championship position.
    assert body.index("Disposable Team 01") < body.index("Disposable Team 10")
    assert "not Championship Points" in body
    _no_admin_controls(app)


def test_championship_criteria_projector_renders_the_configured_model():
    app, body = _render("criteria")
    assert "THE CHAMPIONSHIP" in body.upper()
    assert "100 points" in body
    for label, points in (("Aesthetics &amp; Design", "40 points"), ("Team Photo", "10 points"), ("Drag Race Speed", "50 points")):
        assert label in body and points in body
    for bullet in ("Creativity", "Finishing", "Colour coordination", "Branding", "Attention to detail",
                   "Team participation", "Energy", "Overall presentation"):
        assert bullet in body
    for points in RANK_POINTS.values():
        assert f"<b>{points}</b>" in body
    _no_admin_controls(app)


def test_incomplete_championship_is_never_presented_as_a_final_ranking():
    app, body = _render("standings", complete="no")
    assert "Championship in progress" in body
    assert "FINAL CHAMPIONSHIP STANDINGS" not in body.upper()
    assert "not the final classification" in body
    _no_admin_controls(app)


def test_completed_championship_shows_final_standings_with_component_columns():
    app, body = _render("standings", complete="yes")
    assert "Final Championship Standings" in body
    assert "Championship in progress" not in body
    for label in ("Aesthetics &amp; Design", "Team Photo", "Drag Race Speed"):
        assert label in body
    assert "Total / 100" in body
    # Top three are visually distinct.
    for position in ("p1", "p2", "p3"):
        assert f"pj-row {position}" in body
    _no_admin_controls(app)


def test_standings_projector_uses_the_canonical_leaderboard_order():
    _, body = _render("standings", complete="yes")
    order = [body.index(name) for _, name in TEAMS]
    assert order == sorted(order), "projector must not re-rank the canonical leaderboard"
    # Winner total is the canonical 50 + 40 + 10.
    assert "100" in body


def test_projector_views_are_declared_for_navigation():
    assert PROJECTOR_VIEWS == ("credits", "criteria", "standings")
    race_control = (ROOT / "screens" / "formula_race.py").read_text()
    for label, view in (("PERFORMANCE CREDITS", "credits"), ("CHAMPIONSHIP SCORING", "criteria"), ("CHAMPIONSHIP STANDINGS", "standings")):
        assert f'("{label}", "{view}")' in race_control
    assert 'f"?view={view}&event_id={event_id}"' in race_control
    # The dead Standard-projector link is gone, and the links are reachable from
    # both Control and Championship.
    assert "?view=projector" not in race_control
    assert race_control.count("_projector_links(s.event_id)") == 2
    entrypoint = (ROOT / "FormulaRace.py").read_text()
    assert "show_formula_race_projector" in entrypoint and "PROJECTOR_VIEWS" in entrypoint


def test_championship_completeness_requires_every_component_for_every_team():
    class Partial:
        def get_race_judging(self, event_id):
            return [{"team_id": TEAMS[0][0], "score_dimension": "Aesthetics & Design", "decision": "SUBMITTED"}]

        def get_race_results(self, event_id):
            return []

    team_ids = {team_id for team_id, _ in TEAMS}
    assert _championship_is_complete(Partial(), EVENT, COMPONENTS, team_ids) is False
    assert _championship_is_complete(Partial(), EVENT, [], team_ids) is False


# --------------------------------------------------------------------------
# Marketplace purchase
# --------------------------------------------------------------------------

def test_repeat_purchase_of_the_same_part_is_allowed():
    """CLICK 1 buys; after it lands, CLICK 2 is a distinct legitimate purchase."""
    first = _purchase_idempotency_key(EVENT, "DT-01", "ITEM-PAINT", 1, 0)
    second = _purchase_idempotency_key(EVENT, "DT-01", "ITEM-PAINT", 1, 1)
    third = _purchase_idempotency_key(EVENT, "DT-01", "ITEM-PAINT", 1, 2)
    assert first != second != third
    assert len({first, second, third}) == 3
    assert first.endswith(":1") and second.endswith(":2")


def test_double_submit_and_retry_reuse_one_key():
    """An unchanged workspace yields an unchanged key, so the RPC sees a duplicate."""
    purchases = [{"ItemID": "ITEM-PAINT", "Status": "COMPLETED"}]
    key = _purchase_idempotency_key(EVENT, "DT-01", "ITEM-PAINT", 1, _completed_purchase_count(purchases, "ITEM-PAINT"))
    again = _purchase_idempotency_key(EVENT, "DT-01", "ITEM-PAINT", 1, _completed_purchase_count(purchases, "ITEM-PAINT"))
    assert key == again


def test_purchase_key_is_scoped_per_team_and_item():
    keys = {
        _purchase_idempotency_key(EVENT, "DT-01", "ITEM-PAINT", 1, 0),
        _purchase_idempotency_key(EVENT, "DT-02", "ITEM-PAINT", 1, 0),
        _purchase_idempotency_key(EVENT, "DT-01", "ITEM-TAPE", 1, 0),
    }
    assert len(keys) == 3


def test_completed_purchase_count_ignores_other_items_and_failed_rows():
    purchases = [
        {"ItemID": "ITEM-PAINT", "Status": "COMPLETED"},
        {"ItemID": "ITEM-PAINT", "Status": "COMPLETED"},
        {"ItemID": "ITEM-TAPE", "Status": "COMPLETED"},
        {"ItemID": "ITEM-PAINT", "Status": "FAILED"},
    ]
    assert _completed_purchase_count(purchases, "ITEM-PAINT") == 2
    assert _completed_purchase_count(purchases, "ITEM-TAPE") == 1
    assert _completed_purchase_count([], "ITEM-PAINT") == 0


def test_purchase_never_writes_championship_score():
    purchase_rpc = (ROOT / "supabase" / "034_formula_race_canonical_marketplace_catalogue.sql").read_text()
    body = purchase_rpc.split("exos_v2_formula_race_purchase", 1)[1]
    assert "score_transactions_v2" not in body
    assert "credit_transactions_v2" in body


# --------------------------------------------------------------------------
# Judging
# --------------------------------------------------------------------------

def test_judging_navigation_moves_the_keyed_selectbox_with_the_cursor():
    import streamlit as st
    from screens.formula_race import _select_judging_team
    names = [name for _, name in TEAMS]
    st.session_state.clear()
    _select_judging_team(names, 0)
    assert st.session_state["judge_team"] == names[0] and st.session_state["race_judge_index"] == 0
    _select_judging_team(names, 1)
    assert st.session_state["judge_team"] == names[1]
    _select_judging_team(names, len(names))  # wraps
    assert st.session_state["judge_team"] == names[0]
    st.session_state.clear()


def test_judging_saves_advance_to_the_next_team():
    source = (ROOT / "screens" / "formula_race.py").read_text()
    block = source.split("control.save_race_judging", 1)[1].split("def drag_results", 1)[0]
    assert "_select_judging_team(names,selected_index+1)" in block


def test_judging_enforces_the_configured_maximum_and_reconciles_without_credits():
    sql = (ROOT / "supabase" / "032_formula_race_championship_components.sql").read_text()
    judging = sql.split("exos_v2_formula_race_save_judging_score", 1)[1].split("$$;", 1)[0]
    assert "Judging score is outside the configured maximum" in judging
    assert "exos_v2_formula_race_reconcile_championship" in judging
    assert "credit_transactions_v2" not in judging
    # Re-scoring one team corrects in place instead of duplicating.
    assert "on conflict(event_id,team_id,activity_id,judge_name,score_dimension) do update" in judging


# --------------------------------------------------------------------------
# Drag race and championship points
# --------------------------------------------------------------------------

def test_locked_race_ranks_award_fifty_down_to_five():
    component = normalise_championship_component(COMPONENTS[2])
    awarded = [
        championship_component_points(component, 0, 0, race_rank=rank, race_final_locked=True)
        for rank in range(1, 11)
    ]
    assert awarded == [50, 45, 40, 35, 30, 25, 20, 15, 10, 5]


def test_race_points_require_a_locked_final_result():
    component = normalise_championship_component(COMPONENTS[2])
    assert championship_component_points(component, 0, 0, race_rank=1, race_final_locked=False) == 0.0
    assert championship_component_points(component, 0, 0, race_rank=None, race_final_locked=True) == 0.0


def test_final_lock_requires_every_team_verified_and_is_tie_deterministic():
    sql = (ROOT / "supabase" / "032_formula_race_championship_components.sql").read_text()
    lock = sql.split("exos_v2_formula_race_lock_final_results", 1)[1].split("$$;", 1)[0]
    assert "Every active team requires one verified Race Final result before locking" in lock
    # Ranking metric and the deterministic tie-break.
    assert "row_number() over(order by coalesce((r.result_payload->>'time_ms')::bigint" in lock
    assert "r.team_id asc" in lock
    # A repeated lock reconciles instead of corrupting, and a partial lock is refused.
    assert "AlreadyLocked',true" in lock
    assert "Race Final has a partial lock state and requires controlled reconciliation" in lock
    assert "exos_v2_formula_race_reconcile_championship" in lock


def test_championship_reconciliation_is_idempotent_and_excludes_credits():
    sql = (ROOT / "supabase" / "032_formula_race_championship_components.sql").read_text()
    reconcile = sql.split("exos_v2_formula_race_reconcile_championship", 1)[1].split("$$;", 1)[0]
    assert "update public.score_transactions_v2 set score_delta=0" in reconcile
    assert "on conflict(event_id,idempotency_key) do update" in reconcile
    assert "credit_transactions_v2" not in reconcile
