"""Read-only Formula R.A.C.E. presentation surfaces for a 16:9 projector.

These views render canonical projections only.  They never write, never expose
an editing control, and never compute a ranking of their own: standings come
from the same `get_canonical_transaction_report` Leaderboard that Race Control
Championship reads, so the room and the facilitator can never disagree.

Each view is emitted as ONE markdown block holding the whole slide.  Streamlit
renders every `st.markdown` call into its own container, so a stage opened in
one call and closed in another never wraps anything -- the rows become ordinary
page blocks and the document scrolls.  One block instead gives a real 16:9
stage that is centred in the viewport and sized from it.
"""
from __future__ import annotations

import html
from typing import Any

import streamlit as st

from engines.formula_race_championship import AESTHETICS_RUBRIC, uses_aesthetics_rubric

PROJECTOR_VIEWS = ("credits", "criteria", "holding", "standings")
REFRESH_SECONDS = 20

_JUDGED_COMPONENTS = {"JUDGING_CRITERION", "TEAM_PHOTO"}

# One presentation unit is 1% of the height of the 16:9 stage that fits inside
# the viewport, so every size scales with the display and none is pinned to a
# pixel.  The budget below keeps ten rows plus header and footer inside 100u.
SLIDE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Inter:wght@500;700;800&display=swap');
:root { --u: min(1vh, 0.5625vw); }
[data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stToolbar"],
[data-testid="stStatusWidget"], [data-testid="stDecoration"], [data-testid="stBottom"], footer { display:none!important; }
html, body { height:100%; margin:0; overflow:hidden!important; }
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] { height:100vh!important; overflow:hidden!important; }
.stApp { background:linear-gradient(150deg,#050d13 0%,#0a1721 55%,#050d13 100%); color:#f5f7f8; }
/* Every Streamlit wrapper is pinned to the full viewport height with no gap or
   padding, otherwise their default insets shrink the stage's parent and the
   16:9 box overhangs the viewport by a few pixels. */
.block-container, [data-testid="stMainBlockContainer"], [data-testid="stLayoutWrapper"],
[data-testid="stVerticalBlock"], [data-testid="stElementContainer"],
[data-testid="stMarkdown"], [data-testid="stMarkdownContainer"] {
    width:100%!important; height:100vh!important; max-width:none!important; min-height:0!important;
    padding:0!important; margin:0!important; gap:0!important;
    display:flex!important; align-items:center!important; justify-content:center!important;
    overflow:hidden!important; }
/* The stage is pinned to the viewport and centred with auto margins, so
   Streamlit's wrapper padding and negative margins cannot shift or shrink it. */
.pj-stage { position:fixed; top:0; right:0; bottom:0; left:0; margin:auto;
    width:min(100vw, calc(100vh * 16 / 9)); height:min(100vh, calc(100vw * 9 / 16));
    padding:calc(3.4 * var(--u)) calc(4.5 * var(--u)); display:flex; flex-direction:column; box-sizing:border-box; }
.pj-top { flex:0 0 auto; }
.pj-body { flex:1 1 auto; display:flex; flex-direction:column; justify-content:center; min-height:0; }
.pj-foot { flex:0 0 auto; }
.pj-wordmark { font:800 calc(1.9 * var(--u))/1 Inter,sans-serif; letter-spacing:.34em; color:#9eabb6; text-transform:uppercase; }
.pj-wordmark b { color:#ed3139; }
.pj-title { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(7 * var(--u)); font-weight:800; line-height:.94;
    text-transform:uppercase; letter-spacing:.01em; color:#fff; margin:calc(.4 * var(--u)) 0 0; }
.pj-sub { font:800 calc(2.1 * var(--u)) Inter,sans-serif; letter-spacing:.2em; text-transform:uppercase; color:#f7b733;
    margin:calc(.5 * var(--u)) 0 0; }
.pj-state { display:inline-block; margin-top:calc(.7 * var(--u)); padding:calc(.4 * var(--u)) calc(1.6 * var(--u));
    border-radius:999px; font:800 calc(1.75 * var(--u)) Inter,sans-serif; letter-spacing:.16em; text-transform:uppercase; }
.pj-state.final { color:#4dd38a; border:calc(.24 * var(--u)) solid rgba(77,211,138,.6); }
.pj-head { display:grid; gap:calc(1.3 * var(--u)); padding:0 calc(1.4 * var(--u)) calc(.45 * var(--u));
    font:800 calc(1.35 * var(--u)) Inter,sans-serif; letter-spacing:.16em; text-transform:uppercase; color:#8fa0ad; }
.pj-head span:nth-child(n+3) { text-align:right; }
.pj-row { display:grid; align-items:center; gap:calc(1.3 * var(--u)); padding:calc(.82 * var(--u)) calc(1.4 * var(--u));
    margin:calc(.26 * var(--u)) 0; border-radius:calc(1 * var(--u)); background:rgba(255,255,255,.035);
    border-left:calc(.75 * var(--u)) solid rgba(255,255,255,.09); }
.pj-row.p1 { background:linear-gradient(90deg,rgba(247,183,51,.26),rgba(255,255,255,.03) 62%); border-left-color:#f7b733; }
.pj-row.p2 { background:linear-gradient(90deg,rgba(197,208,216,.20),rgba(255,255,255,.03) 62%); border-left-color:#c5d0d8; }
.pj-row.p3 { background:linear-gradient(90deg,rgba(205,127,50,.20),rgba(255,255,255,.03) 62%); border-left-color:#cd7f32; }
.pj-rank { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(4 * var(--u)); font-weight:800; line-height:1;
    color:#fff; text-align:center; }
.pj-row.p1 .pj-rank { color:#f7b733; }
.pj-team { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(3.6 * var(--u)); font-weight:800; line-height:1;
    text-transform:uppercase; color:#fff; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
.pj-value { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(3.8 * var(--u)); font-weight:800; line-height:1;
    text-align:right; color:#fff; }
.pj-value.total { color:#f7b733; }
.pj-part { font:700 calc(2.1 * var(--u)) Inter,sans-serif; text-align:right; color:#9eabb6; }
.pj-cards { flex:1 1 auto; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:calc(1.4 * var(--u));
    align-items:stretch; min-height:0; margin-top:calc(1.2 * var(--u)); }
.pj-card { border:calc(.16 * var(--u)) solid #263846; border-radius:calc(1.2 * var(--u)); padding:calc(1.5 * var(--u));
    background:rgba(255,255,255,.03); display:flex; flex-direction:column; min-height:0; }
.pj-card h3 { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(3.4 * var(--u)); font-weight:800; line-height:1;
    text-transform:uppercase; color:#fff; margin:0; }
.pj-points { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(4.2 * var(--u)); font-weight:800; color:#f7b733;
    line-height:1; margin:calc(.15 * var(--u)) 0 calc(.9 * var(--u)); }
.pj-dims { display:flex; flex-direction:column; justify-content:center; gap:calc(.6 * var(--u)); flex:1; min-height:0; }
.pj-dim { padding:calc(.55 * var(--u)) calc(.9 * var(--u)); border-radius:calc(.7 * var(--u)); background:rgba(255,255,255,.045); }
.pj-dim strong { display:flex; justify-content:space-between; gap:calc(.6 * var(--u));
    font:800 calc(1.85 * var(--u)) Inter,sans-serif; color:#fff; letter-spacing:.01em; }
.pj-dim strong em { font-style:normal; color:#f7b733; }
.pj-dim span { display:block; font:600 calc(1.5 * var(--u))/1.34 Inter,sans-serif; color:#c9d3da; }
.pj-list { display:flex; flex-direction:column; justify-content:center; gap:calc(.7 * var(--u)); flex:1; min-height:0; }
.pj-list span { font:600 calc(2.1 * var(--u))/1.3 Inter,sans-serif; color:#d8e8f0; }
.pj-ranktable { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:calc(.5 * var(--u)); flex:1;
    align-content:center; min-height:0; }
.pj-ranktable div { padding:calc(.4 * var(--u)) calc(.8 * var(--u)); border-radius:calc(.6 * var(--u));
    background:rgba(255,255,255,.05); display:flex; justify-content:space-between; align-items:baseline;
    font:800 calc(1.8 * var(--u)) Inter,sans-serif; color:#c9d3da; }
.pj-ranktable div b { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(2.6 * var(--u)); color:#f7b733; }
.pj-note { font:700 calc(1.6 * var(--u)) Inter,sans-serif; letter-spacing:.05em; color:#9eabb6; margin-top:calc(1 * var(--u)); }
.pj-hold { flex:1 1 auto; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; }
.pj-hold .pj-title { font-size:calc(11 * var(--u)); margin:calc(1.4 * var(--u)) 0; }
.pj-hold .pj-note { font-size:calc(2.4 * var(--u)); color:#c9d3da; margin-top:calc(1.6 * var(--u)); }
</style>
"""


def _number(value: Any, empty: str = "0") -> str:
    if value is None or value == "":
        return empty
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else f"{number:,.1f}"


def _team_names(runtime, event_id: str) -> dict[str, str]:
    return {
        str(row.get("TeamID", "")): str(row.get("TeamIdentity") or row.get("TeamName") or row.get("TeamID", ""))
        for row in runtime.get_runtime_teams(event_id)
    }


def _top(title: str, subtitle: str = "", state: str = "") -> str:
    return (
        "<div class='pj-top'><div class='pj-wordmark'>FORMULA <b>R.A.C.E.</b></div>"
        f"<div class='pj-title'>{html.escape(title)}</div>"
        + (f"<div class='pj-sub'>{html.escape(subtitle)}</div>" if subtitle else "")
        + (f"<span class='pj-state final'>{html.escape(state)}</span>" if state else "")
        + "</div>"
    )


def _holding_slide(reason: str = "") -> str:
    return (
        "<div class='pj-hold'><div class='pj-wordmark'>FORMULA <b>R.A.C.E.</b></div>"
        "<div class='pj-title'>Championship<br>in progress</div>"
        f"<div class='pj-note'>{html.escape(reason or 'Judging in progress. Final standings will be revealed after the Drag Race.')}</div></div>"
    )


def _message_slide(title: str, note: str) -> str:
    return _top(title) + f"<div class='pj-body'><div class='pj-note'>{html.escape(note)}</div></div>"


# --------------------------------------------------------------------------
# Slides
# --------------------------------------------------------------------------

def performance_credits_slide(runtime, event_id: str) -> str:
    """Available wallet Credits from the canonical ledger.  NOT Championship rank."""
    names = _team_names(runtime, event_id)
    leaderboard = runtime.get_canonical_transaction_report(event_id).get("Leaderboard", [])
    rows = sorted(
        ((names.get(str(row.get("TeamID", "")), str(row.get("TeamID", ""))), float(row.get("WalletBalance", 0) or 0))
         for row in leaderboard if str(row.get("TeamID", "")) in names),
        key=lambda row: (-row[1], row[0]),
    )
    if not rows:
        return _message_slide("Performance Credits", "No teams are configured for this event.")
    style = "grid-template-columns:calc(6 * var(--u)) minmax(0,1fr) calc(20 * var(--u));"
    body = f"<div class='pj-head' style='{style}'><span></span><span>Team</span><span>Available credits</span></div>"
    for position, (name, credits) in enumerate(rows, start=1):
        body += (
            f"<div class='pj-row' style='{style}'><div class='pj-rank'>{position}</div>"
            f"<div class='pj-team'>{html.escape(name)}</div>"
            f"<div class='pj-value'>{html.escape(_number(credits))}</div></div>"
        )
    return (
        _top("Performance Credits", "Available team credits")
        + f"<div class='pj-body'>{body}</div>"
        + "<div class='pj-foot'><div class='pj-note'>Credits fund the build. They are not Championship Points.</div></div>"
    )


def championship_criteria_slide(runtime, event_id: str) -> str:
    """The configured Championship model, explained for the room.  Informational only."""
    configuration = runtime.get_formula_race_configuration(event_id)
    components = [row for row in configuration.get("ChampionshipComponents", []) if row.get("Enabled", True)]
    criteria = {str(row.get("CriterionName", "")): row for row in configuration.get("JudgingCriteria", [])}
    if not components:
        return _message_slide("The Championship", "Championship Components are not configured for this event yet.")
    total = sum(float(row.get("MaximumChampionshipPoints", 0) or 0) for row in components)
    cards = []
    for component in sorted(components, key=lambda row: float(row.get("DisplayOrder", 0) or 0)):
        name = html.escape(str(component.get("DisplayName", "Component")))
        points = html.escape(_number(component.get("MaximumChampionshipPoints", 0)))
        criterion = criteria.get(str(component.get("SourceReference", "")), {})
        if str(component.get("ComponentType", "")) == "RACE_RANK":
            rank_points = dict((component.get("ScoringConfiguration", {}) or {}).get("RankPoints", {}) or {})
            ordered = sorted(((int(rank), value) for rank, value in rank_points.items() if str(rank).isdigit()))
            inner = "<div class='pj-ranktable'>" + "".join(
                f"<div><span>{rank}</span><b>{html.escape(_number(value))}</b></div>" for rank, value in ordered
            ) + "</div>"
        elif uses_aesthetics_rubric(criterion):
            inner = "<div class='pj-dims'>" + "".join(
                f"<div class='pj-dim'><strong><span>{html.escape(dimension)}</span><em>{maximum}</em></strong>"
                f"<span>{html.escape(' · '.join(bullets))}</span></div>"
                for dimension, maximum, bullets in AESTHETICS_RUBRIC
            ) + "</div>"
        else:
            description = str(criterion.get("Description", "") or "")
            bullets = [part.strip() for part in description.replace(";", ",").split(",") if part.strip()]
            inner = "<div class='pj-list'>" + "".join(f"<span>{html.escape(part)}</span>" for part in bullets) + "</div>"
        cards.append(f"<div class='pj-card'><h3>{name}</h3><div class='pj-points'>{points} points</div>{inner}</div>")
    return (
        _top("The Championship", f"{_number(total)} points")
        + "<div class='pj-cards'>" + "".join(cards) + "</div>"
        + "<div class='pj-foot'><div class='pj-note'>Remaining Credits are not part of Championship scoring.</div></div>"
    )


def _championship_is_complete(runtime, event_id: str, components: list[dict[str, Any]], team_ids: set[str]) -> bool:
    """Every enabled component must have produced a real result for every team."""
    if not components or not team_ids:
        return False
    judged = {
        (str(row.get("TeamID", row.get("team_id", ""))), str(row.get("Criterion", row.get("score_dimension", ""))))
        for row in runtime.get_race_judging(event_id)
        if str(row.get("Decision", row.get("decision", "SUBMITTED"))).upper() == "SUBMITTED"
    }
    locked_teams = {
        str(row.get("TeamID", row.get("team_id", "")))
        for row in runtime.get_race_results(event_id)
        if bool(row.get("locked", row.get("Locked", False)))
        and str(row.get("checkpoint", row.get("Checkpoint", "Race Final"))) == "Race Final"
    }
    for component in components:
        component_type = str(component.get("ComponentType", ""))
        if component_type in _JUDGED_COMPONENTS:
            criterion = str(component.get("SourceReference", ""))
            if any((team_id, criterion) not in judged for team_id in team_ids):
                return False
        elif component_type == "RACE_RANK":
            if any(team_id not in locked_teams for team_id in team_ids):
                return False
    return True


def championship_standings_slide(runtime, event_id: str) -> str:
    """The canonical Championship Leaderboard, revealed only once it is real."""
    configuration = runtime.get_formula_race_configuration(event_id)
    components = sorted(
        (row for row in configuration.get("ChampionshipComponents", []) if row.get("Enabled", True)),
        key=lambda row: float(row.get("DisplayOrder", 0) or 0),
    )
    names = _team_names(runtime, event_id)
    report = runtime.get_canonical_transaction_report(event_id)
    leaderboard = [row for row in report.get("Leaderboard", []) if str(row.get("TeamID", "")) in names]

    # A provisional order is never shown: an unfinished championship holds.
    if not leaderboard or not _championship_is_complete(runtime, event_id, components, set(names)):
        return _holding_slide()

    points = {
        (str(row.get("TeamID", "")), str(row.get("ComponentID", ""))): row.get("Points", 0)
        for row in report.get("ChampionshipBreakdown", [])
    }
    maximum = sum(float(row.get("MaximumChampionshipPoints", 0) or 0) for row in components)
    widths = "calc(6 * var(--u)) minmax(0,1fr)" + " calc(11 * var(--u))" * len(components) + " calc(15 * var(--u))"
    style = f"grid-template-columns:{widths};"
    heads = "".join(f"<span>{html.escape(str(row.get('DisplayName', 'Component')))}</span>" for row in components)
    body = (
        f"<div class='pj-head' style='{style}'><span></span><span>Team</span>{heads}"
        f"<span>Points{f' / {_number(maximum)}' if maximum else ''}</span></div>"
    )
    for row in leaderboard:
        team_id = str(row.get("TeamID", ""))
        rank = int(float(row.get("Rank", 0) or 0))
        parts = "".join(
            f"<div class='pj-part'>{html.escape(_number(points.get((team_id, str(component.get('ComponentID', ''))), 0)))}</div>"
            for component in components
        )
        body += (
            f"<div class='pj-row {'p' + str(rank) if rank in (1, 2, 3) else ''}' style='{style}'>"
            f"<div class='pj-rank'>{rank}</div><div class='pj-team'>{html.escape(names.get(team_id, team_id))}</div>"
            f"{parts}<div class='pj-value total'>{html.escape(_number(row.get('ChampionshipScore', 0)))}</div></div>"
        )
    return (
        _top("Final Championship Standings", state="Final Championship Standings")
        + f"<div class='pj-body'>{body}</div>"
    )


def championship_holding_slide(runtime, event_id: str) -> str:
    """An explicit public holding screen while scores are entered privately."""
    return _holding_slide()


_SLIDES = {
    "credits": performance_credits_slide,
    "criteria": championship_criteria_slide,
    "holding": championship_holding_slide,
    "standings": championship_standings_slide,
}


def _render_slide(body: str) -> None:
    """Emit the stylesheet and the whole slide as ONE markdown block."""
    st.markdown(SLIDE_CSS + f"<div class='pj-stage'>{body}</div>", unsafe_allow_html=True)


def show_formula_race_projector(view: str, runtime, event_id: str) -> None:
    """Render one read-only projector view.  No control ever writes from here."""
    clean_view = str(view or "").strip().lower()
    if not str(event_id or "").strip():
        _render_slide(_message_slide("Formula R.A.C.E.", "Open this view from Race Control so it carries the event."))
        return
    slide = _SLIDES.get(clean_view, championship_standings_slide)
    if clean_view in {"criteria", "holding"}:
        _render_slide(slide(runtime, event_id))
        return

    # Credits and standings track canonical changes without a manual rebuild.
    # st.fragment is the native periodic rerun; no JavaScript is involved.
    @st.fragment(run_every=REFRESH_SECONDS)
    def _live_surface() -> None:
        _render_slide(slide(runtime, event_id))

    _live_surface()
