"""Read-only Formula R.A.C.E. presentation surfaces for a 16:9 projector.

These views render canonical projections only.  They never write, never expose
an editing control, and never compute a ranking of their own: standings come
from the same `get_canonical_transaction_report` Leaderboard that Race Control
Championship reads, so the room and the facilitator can never disagree.

Layout is sized against a 16:9 stage derived from the viewport, so one screen
holds ten teams on any ordinary 16:9 display without page scrolling.
"""
from __future__ import annotations

import html
from typing import Any

import streamlit as st

from engines.formula_race_championship import AESTHETICS_RUBRIC, uses_aesthetics_rubric

PROJECTOR_VIEWS = ("credits", "criteria", "holding", "standings")
REFRESH_SECONDS = 20

_JUDGED_COMPONENTS = {"JUDGING_CRITERION", "TEAM_PHOTO"}


def _css() -> None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Inter:wght@500;700;800&display=swap');
    /* One presentation unit = 1% of the height of a 16:9 stage inside the
       viewport, so nothing is hard-coded to a pixel size. */
    :root { --u: min(1vh, 0.5625vw); }
    [data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stToolbar"],
    [data-testid="stStatusWidget"], [data-testid="stDecoration"], footer { display:none!important; }
    html, body, .stApp { overflow:hidden!important; }
    .stApp { background:linear-gradient(150deg,#050d13 0%,#0a1721 55%,#050d13 100%); color:#f5f7f8; }
    .block-container { max-width:none!important; padding:0!important; }
    [data-testid="stMainBlockContainer"] { padding:0!important; }
    .pj-stage { width:min(100vw, calc(100vh * 16 / 9)); height:min(100vh, calc(100vw * 9 / 16));
        margin:0 auto; padding:calc(4 * var(--u)) calc(5 * var(--u)); display:flex; flex-direction:column; overflow:hidden; }
    .pj-wordmark { font:800 calc(2.1 * var(--u))/1 Inter,sans-serif; letter-spacing:.34em; color:#9eabb6; text-transform:uppercase; }
    .pj-wordmark b { color:#ed3139; }
    .pj-title { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(9 * var(--u)); font-weight:800; line-height:.92;
        text-transform:uppercase; letter-spacing:.01em; color:#fff; margin:calc(.6 * var(--u)) 0 0; }
    .pj-sub { font:800 calc(2.4 * var(--u)) Inter,sans-serif; letter-spacing:.2em; text-transform:uppercase; color:#f7b733;
        margin:calc(.8 * var(--u)) 0 calc(1.4 * var(--u)); }
    .pj-state { display:inline-block; margin-bottom:calc(1.4 * var(--u)); padding:calc(.5 * var(--u)) calc(2 * var(--u));
        border-radius:999px; font:800 calc(2 * var(--u)) Inter,sans-serif; letter-spacing:.16em; text-transform:uppercase; }
    .pj-state.progress { color:#f7b733; border:calc(.28 * var(--u)) solid rgba(247,183,51,.55); }
    .pj-state.final { color:#4dd38a; border:calc(.28 * var(--u)) solid rgba(77,211,138,.6); }
    .pj-head { display:grid; gap:calc(1.6 * var(--u)); padding:0 calc(1.6 * var(--u)) calc(.5 * var(--u));
        font:800 calc(1.55 * var(--u)) Inter,sans-serif; letter-spacing:.16em; text-transform:uppercase; color:#8fa0ad; }
    .pj-head span:nth-child(n+3) { text-align:right; }
    .pj-row { display:grid; align-items:center; gap:calc(1.6 * var(--u)); padding:calc(.72 * var(--u)) calc(1.6 * var(--u));
        margin:calc(.28 * var(--u)) 0; border-radius:calc(1.2 * var(--u)); background:rgba(255,255,255,.035);
        border-left:calc(.9 * var(--u)) solid rgba(255,255,255,.09); }
    .pj-row.p1 { background:linear-gradient(90deg,rgba(247,183,51,.26),rgba(255,255,255,.03) 62%); border-left-color:#f7b733; }
    .pj-row.p2 { background:linear-gradient(90deg,rgba(197,208,216,.20),rgba(255,255,255,.03) 62%); border-left-color:#c5d0d8; }
    .pj-row.p3 { background:linear-gradient(90deg,rgba(205,127,50,.20),rgba(255,255,255,.03) 62%); border-left-color:#cd7f32; }
    .pj-rank { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(5 * var(--u)); font-weight:800; line-height:1;
        color:#fff; text-align:center; }
    .pj-row.p1 .pj-rank { color:#f7b733; font-size:calc(6 * var(--u)); }
    .pj-row.p2 .pj-rank, .pj-row.p3 .pj-rank { font-size:calc(5.5 * var(--u)); }
    .pj-team { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(4.3 * var(--u)); font-weight:800; line-height:1;
        text-transform:uppercase; color:#fff; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
    .pj-row.p1 .pj-team { font-size:calc(5 * var(--u)); }
    .pj-value { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(4.6 * var(--u)); font-weight:800; line-height:1;
        text-align:right; color:#fff; }
    .pj-value.total { color:#f7b733; }
    .pj-row.p1 .pj-value.total { font-size:calc(5.6 * var(--u)); }
    .pj-part { font:700 calc(2.3 * var(--u)) Inter,sans-serif; text-align:right; color:#9eabb6; }
    .pj-cards { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:calc(1.6 * var(--u)); flex:1; min-height:0; }
    .pj-card { border:calc(.18 * var(--u)) solid #263846; border-radius:calc(1.4 * var(--u)); padding:calc(1.6 * var(--u));
        background:rgba(255,255,255,.03); display:flex; flex-direction:column; min-height:0; }
    .pj-card h3 { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(3.9 * var(--u)); font-weight:800; line-height:.98;
        text-transform:uppercase; color:#fff; margin:0; }
    .pj-points { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(4.6 * var(--u)); font-weight:800; color:#f7b733;
        line-height:1; margin:calc(.2 * var(--u)) 0 calc(1 * var(--u)); }
    .pj-dim { margin:0 0 calc(.85 * var(--u)); padding:calc(.6 * var(--u)) calc(1 * var(--u)); border-radius:calc(.8 * var(--u));
        background:rgba(255,255,255,.045); }
    .pj-dim strong { display:block; font:800 calc(2.05 * var(--u)) Inter,sans-serif; color:#fff; letter-spacing:.02em; }
    .pj-dim strong em { float:right; font-style:normal; color:#f7b733; }
    .pj-dim span { font:600 calc(1.75 * var(--u))/1.42 Inter,sans-serif; color:#c9d3da; }
    .pj-card ul { margin:calc(.3 * var(--u)) 0 0; padding-left:calc(2.4 * var(--u)); }
    .pj-card li { font:600 calc(2.15 * var(--u))/1.6 Inter,sans-serif; color:#d8e8f0; }
    .pj-ranktable { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:calc(.55 * var(--u)); margin-top:calc(.4 * var(--u)); }
    .pj-ranktable div { padding:calc(.5 * var(--u)) calc(.8 * var(--u)); border-radius:calc(.7 * var(--u));
        background:rgba(255,255,255,.05); display:flex; justify-content:space-between; align-items:baseline;
        font:800 calc(2.05 * var(--u)) Inter,sans-serif; color:#c9d3da; }
    .pj-ranktable div b { font-family:'Barlow Condensed',Impact,sans-serif; font-size:calc(3.1 * var(--u)); color:#f7b733; }
    .pj-anchors { display:flex; gap:calc(1 * var(--u)); margin-top:auto; padding-top:calc(1 * var(--u)); flex-wrap:wrap; }
    .pj-anchors span { font:700 calc(1.6 * var(--u)) Inter,sans-serif; color:#8fa0ad; }
    .pj-note { font:700 calc(1.85 * var(--u)) Inter,sans-serif; letter-spacing:.05em; color:#9eabb6; margin-top:calc(1.2 * var(--u)); }
    .pj-hold { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; }
    .pj-hold .pj-title { font-size:calc(12 * var(--u)); }
    .pj-hold .pj-note { font-size:calc(2.6 * var(--u)); color:#c9d3da; }
    </style>
    """, unsafe_allow_html=True)


def _open_stage() -> None:
    st.markdown("<div class='pj-stage'>", unsafe_allow_html=True)


def _close_stage() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def _header(title: str, subtitle: str = "") -> None:
    st.markdown(
        f"<div class='pj-wordmark'>FORMULA <b>R.A.C.E.</b></div><div class='pj-title'>{html.escape(title)}</div>"
        + (f"<div class='pj-sub'>{html.escape(subtitle)}</div>" if subtitle else ""),
        unsafe_allow_html=True,
    )


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


def _holding_body(reason: str = "") -> None:
    st.markdown(
        "<div class='pj-hold'><div class='pj-wordmark'>FORMULA <b>R.A.C.E.</b></div>"
        "<div class='pj-title'>Championship<br>in progress</div>"
        f"<div class='pj-note'>{html.escape(reason or 'Judging in progress. Final standings will be revealed after the Drag Race.')}</div></div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------

def performance_credits(runtime, event_id: str) -> None:
    """Available wallet Credits from the canonical ledger.  NOT Championship rank."""
    _open_stage()
    _header("Performance Credits", "Available team credits")
    names = _team_names(runtime, event_id)
    leaderboard = runtime.get_canonical_transaction_report(event_id).get("Leaderboard", [])
    rows = sorted(
        ((names.get(str(row.get("TeamID", "")), str(row.get("TeamID", ""))), float(row.get("WalletBalance", 0) or 0))
         for row in leaderboard if str(row.get("TeamID", "")) in names),
        key=lambda row: (-row[1], row[0]),
    )
    if not rows:
        st.markdown("<div class='pj-note'>No teams are configured for this event.</div>", unsafe_allow_html=True)
        _close_stage()
        return
    style = "grid-template-columns:calc(7 * var(--u)) minmax(0,1fr) calc(22 * var(--u));"
    st.markdown(f"<div class='pj-head' style='{style}'><span></span><span>Team</span><span>Available credits</span></div>", unsafe_allow_html=True)
    for position, (name, credits) in enumerate(rows, start=1):
        st.markdown(
            f"<div class='pj-row' style='{style}'><div class='pj-rank'>{position}</div>"
            f"<div class='pj-team'>{html.escape(name)}</div>"
            f"<div class='pj-value'>{html.escape(_number(credits))}</div></div>",
            unsafe_allow_html=True,
        )
    st.markdown("<div class='pj-note'>Credits fund the build. They are not Championship Points.</div>", unsafe_allow_html=True)
    _close_stage()


def championship_criteria(runtime, event_id: str) -> None:
    """The configured Championship model, explained for the room.  Informational only."""
    configuration = runtime.get_formula_race_configuration(event_id)
    components = [row for row in configuration.get("ChampionshipComponents", []) if row.get("Enabled", True)]
    criteria = {str(row.get("CriterionName", "")): row for row in configuration.get("JudgingCriteria", [])}
    total = sum(float(row.get("MaximumChampionshipPoints", 0) or 0) for row in components)
    _open_stage()
    _header("The Championship", f"{_number(total)} points" if components else "")
    if not components:
        st.markdown("<div class='pj-note'>Championship Components are not configured for this event yet.</div>", unsafe_allow_html=True)
        _close_stage()
        return
    cards = []
    for component in sorted(components, key=lambda row: float(row.get("DisplayOrder", 0) or 0)):
        name = html.escape(str(component.get("DisplayName", "Component")))
        points = html.escape(_number(component.get("MaximumChampionshipPoints", 0)))
        criterion = criteria.get(str(component.get("SourceReference", "")), {})
        if str(component.get("ComponentType", "")) == "RACE_RANK":
            rank_points = dict((component.get("ScoringConfiguration", {}) or {}).get("RankPoints", {}) or {})
            ordered = sorted(((int(rank), value) for rank, value in rank_points.items() if str(rank).isdigit()))
            body = "<div class='pj-ranktable'>" + "".join(
                f"<div><span>{rank}</span><b>{html.escape(_number(value))}</b></div>" for rank, value in ordered
            ) + "</div>"
        elif uses_aesthetics_rubric(criterion):
            body = "".join(
                f"<div class='pj-dim'><strong>{html.escape(dimension)}<em>{maximum}</em></strong>"
                f"<span>{html.escape(' · '.join(bullets))}</span></div>"
                for dimension, maximum, bullets in AESTHETICS_RUBRIC
            )
        else:
            description = str(criterion.get("Description", "") or "")
            bullets = [part.strip() for part in description.replace(";", ",").split(",") if part.strip()]
            body = "<ul>" + "".join(f"<li>{html.escape(part)}</li>" for part in bullets) + "</ul>" if bullets else ""
        cards.append(f"<div class='pj-card'><h3>{name}</h3><div class='pj-points'>{points} points</div>{body}</div>")
    st.markdown("<div class='pj-cards'>" + "".join(cards) + "</div>", unsafe_allow_html=True)
    st.markdown("<div class='pj-note'>Remaining Credits are not part of Championship scoring.</div>", unsafe_allow_html=True)
    _close_stage()


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


def championship_standings(runtime, event_id: str) -> None:
    """The canonical Championship Leaderboard, revealed only once it is real."""
    configuration = runtime.get_formula_race_configuration(event_id)
    components = sorted(
        (row for row in configuration.get("ChampionshipComponents", []) if row.get("Enabled", True)),
        key=lambda row: float(row.get("DisplayOrder", 0) or 0),
    )
    names = _team_names(runtime, event_id)
    report = runtime.get_canonical_transaction_report(event_id)
    leaderboard = [row for row in report.get("Leaderboard", []) if str(row.get("TeamID", "")) in names]

    _open_stage()
    # A provisional order is never shown: an unfinished championship holds.
    if not leaderboard or not _championship_is_complete(runtime, event_id, components, set(names)):
        _holding_body()
        _close_stage()
        return

    points = {
        (str(row.get("TeamID", "")), str(row.get("ComponentID", ""))): row.get("Points", 0)
        for row in report.get("ChampionshipBreakdown", [])
    }
    maximum = sum(float(row.get("MaximumChampionshipPoints", 0) or 0) for row in components)
    _header("Final Championship Standings")
    st.markdown("<span class='pj-state final'>Final Championship Standings</span>", unsafe_allow_html=True)
    widths = "calc(7 * var(--u)) minmax(0,1fr)" + " calc(13 * var(--u))" * len(components) + " calc(18 * var(--u))"
    style = f"grid-template-columns:{widths};"
    heads = "".join(f"<span>{html.escape(str(row.get('DisplayName', 'Component')))}</span>" for row in components)
    st.markdown(
        f"<div class='pj-head' style='{style}'><span></span><span>Team</span>{heads}"
        f"<span>Points{f' / {_number(maximum)}' if maximum else ''}</span></div>",
        unsafe_allow_html=True,
    )
    for row in leaderboard:
        team_id = str(row.get("TeamID", ""))
        rank = int(float(row.get("Rank", 0) or 0))
        parts = "".join(
            f"<div class='pj-part'>{html.escape(_number(points.get((team_id, str(component.get('ComponentID', ''))), 0)))}</div>"
            for component in components
        )
        st.markdown(
            f"<div class='pj-row {'p' + str(rank) if rank in (1, 2, 3) else ''}' style='{style}'>"
            f"<div class='pj-rank'>{rank}</div><div class='pj-team'>{html.escape(names.get(team_id, team_id))}</div>"
            f"{parts}<div class='pj-value total'>{html.escape(_number(row.get('ChampionshipScore', 0)))}</div></div>",
            unsafe_allow_html=True,
        )
    _close_stage()


def championship_holding(runtime, event_id: str) -> None:
    """An explicit public holding screen while scores are entered privately."""
    _open_stage()
    _holding_body()
    _close_stage()


def show_formula_race_projector(view: str, runtime, event_id: str) -> None:
    """Render one read-only projector view.  No control ever writes from here."""
    _css()
    clean_view = str(view or "").strip().lower()
    if not str(event_id or "").strip():
        _open_stage()
        _header("Formula R.A.C.E.")
        st.markdown("<div class='pj-note'>Open this view from Race Control so it carries the event.</div>", unsafe_allow_html=True)
        _close_stage()
        return
    if clean_view == "criteria":
        championship_criteria(runtime, event_id)
        return
    if clean_view == "holding":
        championship_holding(runtime, event_id)
        return

    # Credits and standings track canonical changes without a manual rebuild.
    # st.fragment is the native periodic rerun; no JavaScript is involved.
    view_function = performance_credits if clean_view == "credits" else championship_standings

    @st.fragment(run_every=REFRESH_SECONDS)
    def _live_surface() -> None:
        view_function(runtime, event_id)

    _live_surface()
