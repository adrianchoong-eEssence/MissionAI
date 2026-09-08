"""Large-screen AIA Tech public projector. No controls, identity, or evidence."""
from __future__ import annotations

import html
import streamlit as st

from services.aia_public_projector import AIAPublicProjectorClient, POLL_INTERVAL_SECONDS, PublicProjectorError


def _safe(value: object) -> str:
    return html.escape(str(value or "").strip())


@st.fragment(run_every=f"{POLL_INTERVAL_SECONDS}s")
def _frame(client: AIAPublicProjectorClient) -> None:
    try:
        projection = client.projection()
    except PublicProjectorError as error:
        st.markdown(f'<main class="aia-reconnect">{_safe(error)}</main>', unsafe_allow_html=True)
        return
    event = projection["Event"]
    cards = "".join(
        '<article class="aia-card">'
        f'<div class="aia-rank">{_safe("#" + str(team["Rank"]) if event["HasAwardedScore"] and team["Rank"] else "")}</div>'
        f'<div><div class="aia-team">{_safe(team["Country"]).upper()}</div><div class="aia-progress">{team["Completed"]} / {team["Total"]} COMPLETED</div></div>'
        f'<div class="aia-score">{int(team["Score"])}<small>PTS</small></div></article>'
        for team in projection["Teams"])
    state = "PAUSED" if event["State"] == "HOLD" else event["State"]
    st.markdown('<main class="aia-live"><div class="aia-kicker">AIA TECH</div><h1>MISSION AI</h1>'
                f'<div class="aia-state">LIVE LEADERBOARD · {_safe(state)}</div><section>{cards}</section></main>', unsafe_allow_html=True)


def render_aia_live_public_projector() -> None:
    st.set_page_config(page_title="AIA Tech — Mission AI", layout="wide", initial_sidebar_state="collapsed")
    st.markdown("""<style>#MainMenu,header,footer,[data-testid=stSidebar]{display:none!important}.stApp{background:#051526}.block-container{padding:0!important}.aia-live,.aia-reconnect{min-height:100vh;box-sizing:border-box;padding:clamp(28px,4vw,70px);color:#fff;background:radial-gradient(circle at 12% 0,#176b83,#051526 62%);font-family:Inter,sans-serif}.aia-kicker{text-align:center;color:#70edd8;font-weight:900;letter-spacing:.3em;font-size:clamp(15px,1.5vw,26px)}h1{text-align:center;font-size:clamp(66px,8vw,148px);line-height:.9;margin:.3rem 0;font-weight:950}.aia-state{margin:1.6rem auto 2rem;text-align:center;font-weight:800;letter-spacing:.14em;color:#dffaf5}section{max-width:1800px;margin:auto;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.aia-card{display:grid;grid-template-columns:72px 1fr auto;align-items:center;gap:18px;padding:22px 26px;border:1px solid #ffffff33;border-radius:20px;background:#0c2a44}.aia-rank,.aia-score{font-size:clamp(28px,3.5vw,68px);font-weight:950;color:#ffdb75}.aia-team{font-size:clamp(25px,2.5vw,46px);font-weight:900}.aia-progress{margin-top:7px;color:#bad3e3;font-size:14px;font-weight:800;letter-spacing:.12em}.aia-score{color:#70edd8;text-align:right}.aia-score small{display:block;font-size:12px;letter-spacing:.14em}@media(max-width:900px){section{grid-template-columns:1fr}.aia-live{padding:28px 18px}}</style>""", unsafe_allow_html=True)
    try:
        client = AIAPublicProjectorClient.from_environment()
    except PublicProjectorError as error:
        st.markdown(f'<main class="aia-reconnect">{_safe(error)}</main>', unsafe_allow_html=True)
        return
    _frame(client)
