"""Large-screen ENCA projector showing the active stage and cumulative score."""
from __future__ import annotations

import html

import streamlit as st

from services.enca_public_projector import (
    POLL_INTERVAL_SECONDS,
    EncaPublicProjectorClient,
    EncaPublicProjectorError,
)


def _safe(value: object) -> str:
    return html.escape(str(value or "").strip())


def _score(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{float(value):.1f}"


def _style() -> None:
    st.markdown("""<style>
    #MainMenu,header,footer,[data-testid=stSidebar],[data-testid=collapsedControl]{display:none!important}
    .stApp{background:#061928}.block-container{max-width:none!important;padding:0!important}
    .enca-projector{min-height:100vh;box-sizing:border-box;padding:clamp(28px,4vw,70px);color:#fff;background:radial-gradient(circle at 15% 0,#704923,#061928 60%);font-family:Inter,sans-serif}
    .enca-kicker,.enca-state{text-align:center;letter-spacing:.22em;font-weight:900;color:#ffe27b}.enca-title{text-align:center;font:950 clamp(48px,7vw,120px)/.92 Impact,sans-serif;margin:.35rem 0}.enca-stage{text-align:center;font:900 clamp(18px,2vw,36px) Inter,sans-serif;margin:1.3rem 0 2rem}.enca-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;max-width:1800px;margin:auto}.enca-card{display:grid;grid-template-columns:80px 1fr auto;gap:18px;align-items:center;background:#172e40;border:1px solid #ffffff33;border-radius:20px;padding:24px}.enca-rank,.enca-score{font:950 clamp(30px,3.6vw,70px) Impact,sans-serif;color:#ffe27b}.enca-team{font:900 clamp(25px,2.6vw,50px) Impact,sans-serif}.enca-score{color:#73efd9;text-align:right}.enca-score small{display:block;font:800 12px Inter,sans-serif;letter-spacing:.14em}.enca-reconnect{height:100vh;display:flex;align-items:center;justify-content:center;color:#e7fff8;font:900 clamp(24px,3vw,50px) Inter,sans-serif}@media(max-width:900px){.enca-grid{grid-template-columns:1fr}.enca-projector{padding:28px 18px}}
    </style>""", unsafe_allow_html=True)


@st.fragment(run_every=f"{POLL_INTERVAL_SECONDS}s")
def _frame(client: EncaPublicProjectorClient) -> None:
    try:
        projection = client.projection()
    except EncaPublicProjectorError as error:
        st.markdown(f'<main class="enca-reconnect">{_safe(error)}</main>', unsafe_allow_html=True)
        return
    event = projection["Event"]
    cards = "".join(
        '<article class="enca-card">'
        f'<div class="enca-rank">#{team["Rank"]}</div><div><div class="enca-team">{_safe(team["Flag"])} {_safe(team["Country"]).upper()}</div></div>'
        f'<div class="enca-score">{_safe(_score(team["Score"]))}<small>TOTAL PTS</small></div></article>'
        for team in projection["Teams"]
    )
    current = _safe(event["CurrentStage"] or "AWAITING NEXT STAGE")
    st.markdown(
        '<main class="enca-projector"><div class="enca-kicker">ENCA GROUP · GEORGE TOWN · PENANG</div>'
        '<div class="enca-title">TEAM CHALLENGE</div>'
        f'<div class="enca-stage">CURRENT STAGE · {current}</div><div class="enca-state">{_safe(event["State"])}</div>'
        f'<section class="enca-grid">{cards}</section></main>', unsafe_allow_html=True,
    )


def render_enca_public_projector(event_id: str) -> None:
    st.set_page_config(page_title="ENCA Team Challenge", layout="wide", initial_sidebar_state="collapsed")
    _style()
    try:
        client = EncaPublicProjectorClient.from_environment(event_id)
    except EncaPublicProjectorError as error:
        st.markdown(f'<main class="enca-reconnect">{_safe(error)}</main>', unsafe_allow_html=True)
        return
    _frame(client)
