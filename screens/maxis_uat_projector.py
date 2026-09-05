"""Presentation-only projector for the dedicated Maxis UAT event.

The generic Theme Park Race projection remains the data authority.  This
module deliberately consumes only its public team-progress and leaderboard
fields, so it cannot disclose evidence, selections, sessions or controls.
"""
from __future__ import annotations

import html

import streamlit as st

from engines.theme_park_race import projector_projection


MAXIS_UAT_EVENT_ID = "MAXIS-UAT-PREASSIGNED"
_COUNTRY_FLAGS = {
    "Japan": "🇯🇵",
    "South Korea": "🇰🇷",
    "France": "🇫🇷",
    "Italy": "🇮🇹",
    "Brazil": "🇧🇷",
    "Thailand": "🇹🇭",
}


def _safe(value) -> str:
    return html.escape(str(value or "").strip())


def _display_score(value) -> str:
    score = float(value or 0)
    return str(int(score)) if score.is_integer() else f"{score:.1f}"


def maxis_projector_rows(projection: dict) -> list[dict]:
    """Join canonical score and progress by TeamID for the display only."""
    leaderboard = list(projection.get("Leaderboard") or [])
    rank_by_team = {str(row.get("TeamID") or ""): index + 1 for index, row in enumerate(leaderboard)}
    score_by_team = {
        str(row.get("TeamID") or ""): row.get("Score", 0)
        for row in leaderboard
    }
    rows = []
    for team in list(projection.get("Teams") or []):
        team_id = str(team.get("TeamID") or "")
        country = str(team.get("TeamIdentity") or team.get("TeamName") or team_id)
        rows.append({
            "Rank": rank_by_team.get(team_id, len(rank_by_team) + 1),
            "Country": country,
            "Flag": _COUNTRY_FLAGS.get(country, "🏳️"),
            "Score": score_by_team.get(team_id, 0),
            "Completed": int(team.get("Completed", 0) or 0),
            "Total": int(team.get("Total", 0) or 0),
        })
    return sorted(rows, key=lambda row: (row["Rank"], row["Country"]))


def render_maxis_uat_projector(db, event_id: str) -> None:
    """Render a hall-readable, read-only leaderboard for Maxis UAT only."""
    workspace = db.runtime.theme_park_race_facilitator_workspace(event_id)
    projection = projector_projection(
        workspace, db.runtime.get_theme_park_race_configuration(event_id)
    )
    lifecycle = str(projection.get("Lifecycle") or "").upper()
    status = {
        "ACTIVE": "LIVE MISSION",
        "HELD": "MISSION PAUSED",
        "ENDED": "MISSION COMPLETE",
    }.get(lifecycle, "MISSION SETUP")
    cards = []
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for row in maxis_projector_rows(projection):
        rank_label = medals.get(row["Rank"], f"#{row['Rank']}")
        cards.append(
            '<article class="mx-projector-card">'
            f'<div class="mx-projector-rank">{rank_label}</div>'
            f'<div class="mx-projector-flag">{_safe(row["Flag"])}</div>'
            '<div class="mx-projector-team">'
            f'<div class="mx-projector-country">{_safe(row["Country"]).upper()}</div>'
            f'<div class="mx-projector-progress">{row["Completed"]} / {row["Total"]} MISSIONS</div>'
            '</div>'
            f'<div class="mx-projector-score">{_display_score(row["Score"])}<span>PTS</span></div>'
            '</article>'
        )
    st.markdown(
        """
        <style>
        .mx-projector{min-height:100vh;padding:clamp(28px,4vw,72px);box-sizing:border-box;
          background:radial-gradient(circle at 15% 0%,#1b5367 0,#071728 42%,#030c17 100%);color:#fff}
        .mx-projector-kicker{font:900 clamp(15px,1.5vw,25px) Inter,sans-serif;letter-spacing:.24em;color:#2dd4bf;text-align:center}
        .mx-projector-title{font:900 clamp(62px,8vw,138px)/.92 'Barlow Condensed',Impact,sans-serif;text-align:center;letter-spacing:.02em;margin:.25rem 0;text-transform:uppercase}
        .mx-projector-status{margin:1rem auto 2.2rem;width:max-content;max-width:90%;padding:.55rem 1.15rem;border-radius:999px;
          border:1px solid rgba(45,212,191,.68);background:rgba(45,212,191,.12);font:850 clamp(16px,1.6vw,27px) Inter,sans-serif;letter-spacing:.13em;color:#d7fffa}
        .mx-projector-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:clamp(14px,1.8vw,30px);max-width:1780px;margin:0 auto}
        .mx-projector-card{display:grid;grid-template-columns:auto auto minmax(0,1fr) auto;gap:clamp(12px,1.4vw,28px);align-items:center;
          min-height:clamp(112px,15vh,185px);padding:clamp(18px,2.2vw,34px);border-radius:26px;
          border:1px solid rgba(255,255,255,.22);background:linear-gradient(115deg,rgba(22,48,70,.94),rgba(9,25,42,.94));box-shadow:0 18px 46px rgba(0,0,0,.3)}
        .mx-projector-rank{font:900 clamp(31px,3.8vw,64px) 'Barlow Condensed',Impact,sans-serif;color:#ffe07a;min-width:clamp(42px,5vw,78px);text-align:center}
        .mx-projector-flag{font-size:clamp(40px,5vw,80px);line-height:1}.mx-projector-country{font:900 clamp(31px,3.6vw,61px)/.98 'Barlow Condensed',Impact,sans-serif;overflow-wrap:anywhere}
        .mx-projector-progress{margin-top:.35rem;font:800 clamp(13px,1.4vw,23px) Inter,sans-serif;letter-spacing:.11em;color:#9fb6c8}
        .mx-projector-score{font:900 clamp(43px,5.2vw,84px)/.85 'Barlow Condensed',Impact,sans-serif;color:#2dd4bf;text-align:right;white-space:nowrap}
        .mx-projector-score span{display:block;font:850 clamp(12px,1.2vw,20px) Inter,sans-serif;letter-spacing:.14em;color:#cfe9e6;margin-top:.35rem}
        @media (max-width:900px){.mx-projector-grid{grid-template-columns:1fr}.mx-projector{padding:28px 18px}.mx-projector-card{border-radius:18px}}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<main class="mx-projector"><div class="mx-projector-kicker">MAXIS MISSION AI</div>'
        '<div class="mx-projector-title">LIVE LEADERBOARD</div>'
        f'<div class="mx-projector-status">● {_safe(status)}</div>'
        f'<section class="mx-projector-grid">{"".join(cards)}</section></main>',
        unsafe_allow_html=True,
    )
