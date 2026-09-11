"""Large-screen public projector for a fixed EventID Hunt deployment."""
from __future__ import annotations

import html

import streamlit as st

from services.hunt_public_projector import HuntPublicProjectorClient, HuntPublicProjectorError, POLL_INTERVAL_SECONDS


def _safe(value: object) -> str:
    return html.escape(str(value or "").strip())


def _score(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{float(value):.1f}"


def _style() -> None:
    st.markdown("""<style>
    #MainMenu,header,footer,[data-testid=stSidebar],[data-testid=collapsedControl]{display:none!important}
    .stApp{background:#061928}.block-container{max-width:none!important;padding:0!important}
    .hunt-projector{min-height:100vh;box-sizing:border-box;padding:clamp(28px,4vw,70px);color:#fff;background:radial-gradient(circle at 15% 0,#246b72,#061928 60%);font-family:Inter,sans-serif}
    .hunt-kicker,.hunt-state{text-align:center;letter-spacing:.22em;font-weight:900;color:#76eed7}.hunt-title{text-align:center;font:950 clamp(52px,7vw,130px)/.92 Impact,sans-serif;margin:.35rem 0}.hunt-state{color:#e8fff9;margin-bottom:2rem}.hunt-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;max-width:1800px;margin:auto}.hunt-card{display:grid;grid-template-columns:80px 1fr auto;gap:18px;align-items:center;background:#0b2a42;border:1px solid #ffffff33;border-radius:20px;padding:24px}.hunt-rank,.hunt-score{font:950 clamp(30px,3.6vw,70px) Impact,sans-serif;color:#ffe27b}.hunt-team{font:900 clamp(25px,2.6vw,50px) Impact,sans-serif}.hunt-progress{font-size:14px;font-weight:800;letter-spacing:.13em;color:#bfd3e1;margin-top:7px}.hunt-score{color:#73efd9;text-align:right}.hunt-score small{display:block;font:800 12px Inter,sans-serif;letter-spacing:.14em}.hunt-reconnect{height:100vh;display:flex;align-items:center;justify-content:center;color:#e7fff8;font:900 clamp(24px,3vw,50px) Inter,sans-serif}
    @media(max-width:900px){.hunt-grid{grid-template-columns:1fr}.hunt-projector{padding:28px 18px}}
    </style>""", unsafe_allow_html=True)


@st.fragment(run_every=f"{POLL_INTERVAL_SECONDS}s")
def _frame(client: HuntPublicProjectorClient) -> None:
    try:
        projection = client.projection()
    except HuntPublicProjectorError as error:
        st.markdown(f'<main class="hunt-reconnect">{_safe(error)}</main>', unsafe_allow_html=True)
        return
    event = projection["Event"]
    cards = "".join(
        '<article class="hunt-card">'
        f'<div class="hunt-rank">#{team["Rank"]}</div><div><div class="hunt-team">{_safe(team["TeamName"]).upper()}</div>'
        f'<div class="hunt-progress">{team["Completed"]} / {team["Total"]} COMPLETED</div></div>'
        f'<div class="hunt-score">{_safe(_score(team["Score"]))}<small>PTS</small></div></article>'
        for team in projection["Teams"]
    )
    state = "RETURN TO BASE" if event["State"] == "RETURN_NOW" else ("CLOSED" if event["State"] == "CLOSED" else event["State"])
    st.markdown('<main class="hunt-projector"><div class="hunt-kicker">GEORGE TOWN</div><div class="hunt-title">MISSION AI WALK HUNT</div>'
                f'<div class="hunt-state">LIVE LEADERBOARD · {_safe(state)}</div><section class="hunt-grid">{cards}</section></main>', unsafe_allow_html=True)


def render_hunt_public_projector(event_id: str) -> None:
    st.set_page_config(page_title="George Town — Mission AI Walk Hunt", layout="wide", initial_sidebar_state="collapsed")
    _style()
    try:
        client = HuntPublicProjectorClient.from_environment(event_id)
    except HuntPublicProjectorError as error:
        st.markdown(f'<main class="hunt-reconnect">{_safe(error)}</main>', unsafe_allow_html=True)
        return
    _frame(client)
