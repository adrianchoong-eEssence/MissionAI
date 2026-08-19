"""Operational coverage for the R.A.C.E. end-game: projector, purchase, judging, race.

Every projector surface is read-only and reuses the canonical Championship
Leaderboard; none of these tests touch a live event.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from engines.formula_race_championship import (
    AESTHETICS_RUBRIC, AESTHETICS_RUBRIC_TOTAL, SCORING_ANCHORS, aesthetics_total,
    championship_component_points, normalise_championship_component, uses_aesthetics_rubric,
)
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
    """No provisional order reaches the room while scores are being entered."""
    app, body = _render("standings", complete="no")
    assert "in progress" in body
    assert "Final standings will be revealed after the Drag Race" in body
    assert "FINAL CHAMPIONSHIP STANDINGS" not in body.upper()
    for _, name in TEAMS:
        assert name not in body, "an unfinished championship must not leak team positions"
    assert "class='pj-row" not in body
    _no_admin_controls(app)


def test_explicit_holding_view_never_shows_scores():
    app, body = _render("holding", complete="yes")
    assert "in progress" in body
    for _, name in TEAMS:
        assert name not in body
    _no_admin_controls(app)


def test_completed_championship_shows_final_standings_with_component_columns():
    app, body = _render("standings", complete="yes")
    assert "Final Championship Standings" in body
    assert "Judging in progress" not in body
    for label in ("Aesthetics &amp; Design", "Team Photo", "Drag Race Speed"):
        assert label in body
    assert "Points / 100" in body
    # Top three are visually prominent.
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
    assert PROJECTOR_VIEWS == ("credits", "criteria", "holding", "standings")
    race_control = (ROOT / "screens" / "formula_race.py").read_text()
    for label, view in (("PERFORMANCE CREDITS", "credits"), ("CHAMPIONSHIP SCORING", "criteria"),
                        ("CHAMPIONSHIP IN PROGRESS", "holding"), ("CHAMPIONSHIP STANDINGS", "standings")):
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


def test_every_projector_view_is_a_sixteen_by_nine_presentation_stage():
    for view in PROJECTOR_VIEWS:
        app, body = _render(view, complete="yes")
        assert "--u: min(1vh, 0.5625vw)" in body, f"{view} is not sized against a 16:9 stage"
        assert "calc(100vh * 16 / 9)" in body and "calc(100vw * 9 / 16)" in body
        assert "class='pj-stage'" in body
        # No dashboard chrome and no page scrolling.
        assert 'data-testid="stSidebar"], [data-testid="stToolbar"]' in body
        assert "overflow:hidden!important" in body
        # Typography scales with the stage; nothing is pinned to a pixel size.
        assert not re.search(r"font(?:-size)?\s*:\s*[^;]*\b\d+px", body.split("</style>")[0]), f"{view} pins a pixel font size"
        _no_admin_controls(app)


def test_credits_and_standings_refresh_without_javascript():
    from screens import formula_race_projector as projector
    source = (ROOT / "screens" / "formula_race_projector.py").read_text()
    assert "@st.fragment(run_every=REFRESH_SECONDS)" in source
    assert 0 < projector.REFRESH_SECONDS <= 60
    assert "<script" not in source and "components.html" not in source


def test_projector_module_never_writes():
    source = (ROOT / "screens" / "formula_race_projector.py").read_text()
    for mutation in ("save_", "_rpc(", "formula_race_purchase", "review_race_checkpoint",
                     "lock_race_results", "st.button", "st.form"):
        assert mutation not in source, f"projector must not reach {mutation}"


# --------------------------------------------------------------------------
# Aesthetics rubric — operator assistance, one canonical score
# --------------------------------------------------------------------------

def test_four_aesthetics_dimensions_total_exactly_forty():
    assert len(AESTHETICS_RUBRIC) == 4
    assert [maximum for _, maximum, _ in AESTHETICS_RUBRIC] == [10, 10, 10, 10]
    assert AESTHETICS_RUBRIC_TOTAL == 40
    assert [name for name, _, _ in AESTHETICS_RUBRIC] == [
        "Craftsmanship & Finish", "Creative Design", "Visual Impact & Branding", "Design Integration",
    ]


def test_aesthetics_total_is_the_sum_and_each_dimension_is_capped_at_ten():
    perfect = {name: 10 for name, _, _ in AESTHETICS_RUBRIC}
    assert aesthetics_total(perfect) == 40
    assert aesthetics_total({name: 99 for name, _, _ in AESTHETICS_RUBRIC}) == 40, "a dimension cannot exceed 10"
    assert aesthetics_total({name: -5 for name, _, _ in AESTHETICS_RUBRIC}) == 0
    assert aesthetics_total({"Craftsmanship & Finish": 9, "Creative Design": 7,
                             "Visual Impact & Branding": 6, "Design Integration": 8}) == 30
    assert aesthetics_total({}) == 0


def test_rubric_is_offered_only_for_the_configured_forty_point_criterion():
    assert uses_aesthetics_rubric({"CriterionName": "Aesthetics & Design", "MaximumScore": 40}) is True
    assert uses_aesthetics_rubric({"CriterionName": "Team Photo", "MaximumScore": 10}) is False
    assert uses_aesthetics_rubric({"CriterionName": "Aesthetics & Design", "MaximumScore": 20}) is False


def test_canonical_submission_receives_only_the_summed_forty():
    """The four inputs are operator assistance; one canonical score is saved."""
    source = (ROOT / "screens" / "formula_race.py").read_text()
    block = source.split("def judging(", 1)[1].split("def drag_results", 1)[0]
    assert "score = aesthetics_total(sub_scores)" in block
    assert "scores[criterion_name]=score" in block
    # One save per configured criterion, unchanged contract.
    assert "control.save_race_judging(s.event_id,selected.id,scores,reason,actor)" in block
    assert "ChampionshipComponents" not in block.split("st.button(\"Submit score\"", 1)[-1]
    adapter = (ROOT / "data" / "formula_race_core_v2_adapter.py").read_text()
    judging_save = adapter.split("def save_formula_race_judging", 1)[1].split("def formula_race_submit_team_photo", 1)[0]
    assert "exos_v2_formula_race_save_judging_score" in judging_save
    assert "p_score" in judging_save and "sub_score" not in judging_save


def test_scoring_anchors_are_visible_to_the_judge():
    assert [band for band, _ in SCORING_ANCHORS] == ["9–10", "7–8", "5–6", "3–4", "1–2"]
    block = (ROOT / "screens" / "formula_race.py").read_text().split("def judging(", 1)[1]
    assert "SCORING_ANCHORS" in block


def test_component_maxima_remain_forty_ten_fifty_of_one_hundred():
    maxima = {row["DisplayName"]: row["MaximumChampionshipPoints"] for row in COMPONENTS}
    assert maxima == {"Aesthetics & Design": 40, "Team Photo": 10, "Drag Race Speed": 50}
    assert sum(maxima.values()) == 100


def test_criteria_projector_explains_forty_ten_and_fifty():
    _, body = _render("criteria")
    assert "100 points" in body
    for points in ("40 points", "10 points", "50 points"):
        assert points in body
    for dimension, maximum, _ in AESTHETICS_RUBRIC:
        assert html.escape(dimension) in body
    for bullet in ("Clean construction", "Originality", "Colour coordination", "Cohesive overall design"):
        assert bullet in body
    for bullet in ("Team participation", "Energy", "Overall presentation"):
        assert bullet in body
    for points in RANK_POINTS.values():
        assert f"<b>{points}</b>" in body


# --------------------------------------------------------------------------
# Marketplace purchase
# --------------------------------------------------------------------------

def test_captain_parts_depot_no_longer_requests_item_imagery():
    captain = (ROOT / "screens" / "formula_race_captain.py").read_text()
    depot = captain.split('if captain_section == "Wallet & Marketplace"', 1)[1].split('if captain_section == "Build"', 1)[0]
    assert "st.image" not in depot
    assert 'item.get("ImageReference"' not in depot
    assert "get_formula_race_station_reference_image_url" not in depot
    # Name, price, owned quantity and the buy control remain.
    assert "ItemName" in depot and "CreditCost" in depot
    assert "already owns" in depot
    assert "formula_race_purchase" in depot


def test_marketplace_configuration_and_prices_are_untouched_by_the_captain():
    captain = (ROOT / "screens" / "formula_race_captain.py").read_text()
    assert "save_formula_race_configuration" not in captain
    assert "CreditCost=" not in captain

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


def test_judging_screen_renders_four_ten_point_inputs_and_submits_one_forty():
    """Render the real judging screen and prove the canonical payload."""
    from streamlit.testing.v1 import AppTest
    script = f'''
import streamlit as st
from types import SimpleNamespace
from screens.formula_race import judging

TEAMS = {TEAMS!r}
COMPONENTS = {COMPONENTS!r}
saved = {{}}

class Control:
    runtime = SimpleNamespace(get_formula_race_team_photo_url=lambda ref: "")
    def save_race_judging(self, event_id, team_id, scores, reason, actor):
        saved.update({{"team_id": team_id, "scores": dict(scores), "actor": actor, "reason": reason}})
        st.session_state["saved_payload"] = saved

snapshot = SimpleNamespace(
    event_id="{EVENT}",
    teams=[SimpleNamespace(id=t, name=n) for t, n in TEAMS],
    operations={{"Configuration": {{
        "JudgingCriteria": [
            {{"CriterionName": "Aesthetics & Design", "MaximumScore": 40, "Enabled": True}},
            {{"CriterionName": "Team Photo", "MaximumScore": 10, "Enabled": True}},
        ],
        "ChampionshipComponents": COMPONENTS,
    }}, "TeamPhotos": [], "BuildStatus": []}},
)
judging(snapshot, Control())
'''
    app = AppTest.from_string(script, default_timeout=90)
    app.run()
    assert not app.exception, [str(e.value) for e in app.exception]

    labels = [widget.label for widget in app.number_input]
    assert labels == [f"{dimension} /{maximum}" for dimension, maximum, _ in AESTHETICS_RUBRIC]
    for widget in app.number_input:
        assert widget.max == 10, "an Aesthetics dimension cannot exceed 10"
    # Team Photo keeps its own /10 slider; Aesthetics no longer uses one.
    assert [slider.label for slider in app.slider] == ["Team Photo"]
    assert app.slider[0].max == 10

    for widget, value in zip(app.number_input, (9, 8, 7, 6)):
        widget.set_value(value)
    app.slider[0].set_value(9)
    app.text_input(key="race_control_operator").set_value("Disposable Judge")
    app.text_input(key="race_judge_reason").set_value("Disposable UAT")
    app.run()
    app.button[2].click().run()  # Submit score, after the two navigation buttons

    payload = app.session_state["saved_payload"]["scores"]
    assert payload == {"Aesthetics & Design": 30, "Team Photo": 9}
    assert payload["Aesthetics & Design"] == 9 + 8 + 7 + 6 <= AESTHETICS_RUBRIC_TOTAL
    assert set(payload) == {"Aesthetics & Design", "Team Photo"}, "no sub-score is ever submitted"
