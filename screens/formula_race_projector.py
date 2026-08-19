"""Read-only Formula R.A.C.E. projector surfaces.

These views render canonical projections only.  They never write, never expose
an editing control, and never compute a ranking of their own: standings come
from the same `get_canonical_transaction_report` Leaderboard that Race Control
Championship reads, so the room and the facilitator can never disagree.
"""
from __future__ import annotations

import html
from typing import Any

import streamlit as st

PROJECTOR_VIEWS = ("credits", "criteria", "standings")

_JUDGED_COMPONENTS = {"JUDGING_CRITERION", "TEAM_PHOTO"}


def _css() -> None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Inter:wght@500;700;800&display=swap');
    [data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stToolbar"] { display:none!important; }
    .stApp { background:linear-gradient(150deg,#050d13 0%,#0a1721 55%,#050d13 100%); color:#f5f7f8; }
    .block-container { max-width:1680px; padding:1.1rem 2.2rem 1.6rem; }
    .pj-wordmark { font:800 1.5rem/1 Inter,sans-serif; letter-spacing:.34em; color:#9eabb6; text-transform:uppercase; }
    .pj-wordmark b { color:#ed3139; }
    .pj-title { font-family:'Barlow Condensed',Impact,sans-serif; font-size:4.6rem; font-weight:800; line-height:.9;
        text-transform:uppercase; letter-spacing:.02em; color:#fff; margin:.1rem 0 .1rem; }
    .pj-sub { font:800 1.05rem Inter,sans-serif; letter-spacing:.22em; text-transform:uppercase; color:#f7b733; margin-bottom:.9rem; }
    .pj-state { display:inline-block; padding:.3rem .9rem; border-radius:999px; font:800 .95rem Inter,sans-serif;
        letter-spacing:.16em; text-transform:uppercase; }
    .pj-state.progress { color:#f7b733; border:2px solid rgba(247,183,51,.55); }
    .pj-state.final { color:#4dd38a; border:2px solid rgba(77,211,138,.6); }
    .pj-row { display:grid; align-items:center; gap:1rem; padding:.5rem .9rem; margin:.32rem 0; border-radius:10px;
        background:rgba(255,255,255,.035); border-left:6px solid rgba(255,255,255,.09); }
    .pj-row.p1 { background:linear-gradient(90deg,rgba(247,183,51,.24),rgba(255,255,255,.03) 62%); border-left-color:#f7b733; }
    .pj-row.p2 { background:linear-gradient(90deg,rgba(197,208,216,.20),rgba(255,255,255,.03) 62%); border-left-color:#c5d0d8; }
    .pj-row.p3 { background:linear-gradient(90deg,rgba(205,127,50,.20),rgba(255,255,255,.03) 62%); border-left-color:#cd7f32; }
    .pj-rank { font-family:'Barlow Condensed',Impact,sans-serif; font-size:2.9rem; font-weight:800; line-height:1; color:#fff; text-align:center; }
    .pj-row.p1 .pj-rank { color:#f7b733; }
    .pj-team { font-family:'Barlow Condensed',Impact,sans-serif; font-size:2.5rem; font-weight:800; line-height:1;
        text-transform:uppercase; color:#fff; overflow-wrap:anywhere; }
    .pj-value { font-family:'Barlow Condensed',Impact,sans-serif; font-size:2.5rem; font-weight:800; line-height:1; text-align:right; color:#fff; }
    .pj-value.total { color:#f7b733; }
    .pj-part { font:700 1.4rem Inter,sans-serif; text-align:right; color:#c9d3da; }
    .pj-head { display:grid; gap:1rem; padding:0 .9rem .3rem; font:800 .82rem Inter,sans-serif;
        letter-spacing:.16em; text-transform:uppercase; color:#8fa0ad; }
    .pj-head span:not(:first-child):not(:nth-child(2)) { text-align:right; }
    .pj-card { border:1px solid #263846; border-radius:14px; padding:1rem 1.2rem; background:rgba(255,255,255,.03); height:100%; }
    .pj-card h3 { font-family:'Barlow Condensed',Impact,sans-serif; font-size:2.5rem; font-weight:800; line-height:.95;
        text-transform:uppercase; color:#fff; margin:0; }
    .pj-points { font-family:'Barlow Condensed',Impact,sans-serif; font-size:2.9rem; font-weight:800; color:#f7b733; line-height:1; margin:.1rem 0 .5rem; }
    .pj-card ul { margin:0; padding-left:1.1rem; }
    .pj-card li { font:600 1.15rem/1.62 Inter,sans-serif; color:#d8e8f0; }
    .pj-ranktable { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:.4rem; margin-top:.3rem; }
    .pj-ranktable div { padding:.34rem .2rem; border-radius:8px; background:rgba(255,255,255,.05); text-align:center;
        font:800 1.15rem Inter,sans-serif; color:#f5f7f8; }
    .pj-ranktable div b { display:block; color:#f7b733; font-size:1.5rem; }
    .pj-note { font:700 1rem Inter,sans-serif; letter-spacing:.06em; color:#9eabb6; margin-top:.7rem; }
    </style>
    """, unsafe_allow_html=True)


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


def performance_credits(runtime, event_id: str) -> None:
    """Wallet Credits from the canonical ledger.  Explicitly NOT Championship rank."""
    _header("Performance Credits", "Team wallet · canonical credit ledger")
    names = _team_names(runtime, event_id)
    leaderboard = runtime.get_canonical_transaction_report(event_id).get("Leaderboard", [])
    rows = sorted(
        ((names.get(str(row.get("TeamID", "")), str(row.get("TeamID", ""))), float(row.get("WalletBalance", 0) or 0))
         for row in leaderboard if str(row.get("TeamID", "")) in names),
        key=lambda row: (-row[1], row[0]),
    )
    if not rows:
        st.markdown("<div class='pj-note'>No teams are configured for this event.</div>", unsafe_allow_html=True)
        return
    style = "grid-template-columns:6rem minmax(0,1fr) 12rem;"
    st.markdown(f"<div class='pj-head' style='{style}'><span></span><span>Team</span><span>Credits</span></div>", unsafe_allow_html=True)
    for position, (name, credits) in enumerate(rows, start=1):
        st.markdown(
            f"<div class='pj-row' style='{style}'><div class='pj-rank'>{position}</div>"
            f"<div class='pj-team'>{html.escape(name)}</div>"
            f"<div class='pj-value'>{html.escape(_number(credits))}</div></div>",
            unsafe_allow_html=True,
        )
    st.markdown("<div class='pj-note'>Credits fund the build. They are not Championship Points.</div>", unsafe_allow_html=True)


def championship_criteria(runtime, event_id: str) -> None:
    """The configured Championship model, rendered for the room.  Informational only."""
    configuration = runtime.get_formula_race_configuration(event_id)
    components = [row for row in configuration.get("ChampionshipComponents", []) if row.get("Enabled", True)]
    criteria = {str(row.get("CriterionName", "")): row for row in configuration.get("JudgingCriteria", [])}
    total = sum(float(row.get("MaximumChampionshipPoints", 0) or 0) for row in components)
    _header("The Championship", f"{_number(total)} points" if components else "")
    if not components:
        st.markdown(
            "<div class='pj-note'>Championship Components are not configured for this event yet.</div>",
            unsafe_allow_html=True,
        )
        return
    ordered = sorted(components, key=lambda row: float(row.get("DisplayOrder", 0) or 0))
    for column, component in zip(st.columns(len(ordered)), ordered):
        with column:
            name = str(component.get("DisplayName", "Component"))
            points = _number(component.get("MaximumChampionshipPoints", 0))
            body = ""
            if str(component.get("ComponentType", "")) == "RACE_RANK":
                rank_points = dict((component.get("ScoringConfiguration", {}) or {}).get("RankPoints", {}) or {})
                cells = "".join(
                    f"<div>{rank}<b>{html.escape(_number(rank_points.get(str(rank), 0)))}</b></div>"
                    for rank in range(1, len(rank_points) + 1) if str(rank) in rank_points
                )
                body = f"<div class='pj-ranktable'>{cells}</div>" if cells else ""
            else:
                description = str(criteria.get(str(component.get("SourceReference", "")), {}).get("Description", "") or "")
                bullets = [part.strip() for part in description.replace(";", ",").split(",") if part.strip()]
                if bullets:
                    body = "<ul>" + "".join(f"<li>{html.escape(part)}</li>" for part in bullets) + "</ul>"
            st.markdown(
                f"<div class='pj-card'><h3>{html.escape(name)}</h3><div class='pj-points'>{html.escape(points)} points</div>{body}</div>",
                unsafe_allow_html=True,
            )
    st.markdown("<div class='pj-note'>Remaining Credits are not part of Championship scoring.</div>", unsafe_allow_html=True)


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
    """The canonical Championship Leaderboard, rendered for a projector."""
    configuration = runtime.get_formula_race_configuration(event_id)
    components = sorted(
        (row for row in configuration.get("ChampionshipComponents", []) if row.get("Enabled", True)),
        key=lambda row: float(row.get("DisplayOrder", 0) or 0),
    )
    names = _team_names(runtime, event_id)
    report = runtime.get_canonical_transaction_report(event_id)
    leaderboard = [row for row in report.get("Leaderboard", []) if str(row.get("TeamID", "")) in names]
    points = {}
    for row in report.get("ChampionshipBreakdown", []):
        points[(str(row.get("TeamID", "")), str(row.get("ComponentID", "")))] = row.get("Points", 0)

    complete = _championship_is_complete(runtime, event_id, components, set(names))
    _header("Final Championship Standings" if complete else "Championship Standings")
    state = "final" if complete else "progress"
    label = "Final Championship Standings" if complete else "Championship in progress"
    st.markdown(f"<span class='pj-state {state}'>{html.escape(label)}</span>", unsafe_allow_html=True)
    if not leaderboard:
        st.markdown("<div class='pj-note'>No teams are configured for this event.</div>", unsafe_allow_html=True)
        return

    maximum = sum(float(row.get("MaximumChampionshipPoints", 0) or 0) for row in components)
    widths = "6rem minmax(0,1fr)" + " 9rem" * len(components) + " 11rem"
    style = f"grid-template-columns:{widths};"
    heads = "".join(f"<span>{html.escape(str(row.get('DisplayName', 'Component')))}</span>" for row in components)
    st.markdown(
        f"<div class='pj-head' style='{style}'><span></span><span>Team</span>{heads}"
        f"<span>Total{f' / {_number(maximum)}' if maximum else ''}</span></div>",
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
    if not complete:
        st.markdown(
            "<div class='pj-note'>Scores update as judging and the final race are confirmed. "
            "This is not the final classification.</div>",
            unsafe_allow_html=True,
        )


def show_formula_race_projector(view: str, runtime, event_id: str) -> None:
    """Render one read-only projector view.  No control ever writes from here."""
    _css()
    clean_view = str(view or "").strip().lower()
    if not str(event_id or "").strip():
        _header("Formula R.A.C.E.")
        st.markdown("<div class='pj-note'>Open this view from Race Control so it carries the event.</div>", unsafe_allow_html=True)
        return
    if clean_view == "credits":
        performance_credits(runtime, event_id)
    elif clean_view == "criteria":
        championship_criteria(runtime, event_id)
    else:
        championship_standings(runtime, event_id)
