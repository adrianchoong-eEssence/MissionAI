"""Large-screen, read-only Maxis live projector presentation."""
from __future__ import annotations

import html

import streamlit as st

from services.maxis_public_projector import (
    POLL_INTERVAL_SECONDS,
    PublicProjectorClient,
    PublicProjectorError,
)


def _safe(value: object) -> str:
    return html.escape(str(value or "").strip())


def _score(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{float(value):.1f}"


def _state_copy(state: str, has_score: bool) -> tuple[str, str, str]:
    if state == "HOLD":
        return "MISSION AI", "PAUSED", "STAY WITH YOUR TEAM"
    if state == "LIVE" and not has_score:
        return "MISSION AI", "IS LIVE", "ALL TEAMS START AT 0"
    if state == "LIVE":
        return "MAXIS MISSION AI", "LIVE LEADERBOARD", "● LIVE"
    if state == "ENDED":
        return "MAXIS MISSION AI", "MISSION COMPLETE", "FINAL RESULTS"
    return "MISSION AI", "GET READY", "TEAMS ARE STANDING BY"


def _rank_label(rank: int | None, has_score: bool) -> str:
    if not has_score or rank is None:
        return ""
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")


def _cards(projection: dict) -> str:
    event = projection["Event"]
    has_score = bool(event["HasAwardedScore"])
    rows = []
    for team in projection["Teams"]:
        total = max(0, int(team["Total"]))
        completed = min(max(0, int(team["Completed"])), total) if total else 0
        progress = (100 * completed / total) if total else 0
        rank = _rank_label(team["Rank"], has_score)
        rows.append(
            '<article class="mx-live-card">'
            f'<div class="mx-live-rank">{_safe(rank)}</div>'
            f'<div class="mx-live-flag">{_safe(team["Flag"])}</div>'
            '<div class="mx-live-team">'
            f'<div class="mx-live-country">{_safe(team["Country"]).upper()}</div>'
            f'<div class="mx-live-progress-copy">{completed} / {total} MISSIONS</div>'
            f'<div class="mx-live-progress"><span style="width:{progress:.2f}%"></span></div>'
            '</div>'
            f'<div class="mx-live-score">{_safe(_score(team["Score"]))}<span>PTS</span></div>'
            '</article>'
        )
    return "".join(rows)


def _inject_display_style() -> None:
    st.markdown(
        """
        <style>
        #MainMenu, header, footer, [data-testid="stSidebar"], [data-testid="collapsedControl"] {display:none !important}
        [data-testid="stAppViewContainer"], [data-testid="stMain"], .stApp {background:#03101d !important; overflow:hidden !important}
        [data-testid="stMainBlockContainer"] {max-width:none !important; padding:0 !important}
        .mx-live{box-sizing:border-box;min-height:100vh;height:100vh;overflow:hidden;padding:clamp(24px,3.2vw,58px);
          color:#fff;background:radial-gradient(circle at 12% -10%,#246779 0,#082337 40%,#03101d 78%)}
        .mx-live-eyebrow{text-align:center;color:#73f0da;font:900 clamp(14px,1.35vw,24px) Inter,sans-serif;letter-spacing:.28em}
        .mx-live-title{text-align:center;font:900 clamp(56px,6.7vw,112px)/.9 Impact,'Arial Narrow',sans-serif;letter-spacing:.02em;margin:.2rem 0 .85rem}
        .mx-live-state{width:max-content;max-width:92%;margin:0 auto clamp(18px,2.1vh,32px);padding:.55rem 1.2rem;border-radius:999px;
          border:1px solid rgba(115,240,218,.65);background:rgba(115,240,218,.10);color:#e2fffa;text-align:center;font:850 clamp(14px,1.25vw,22px) Inter,sans-serif;letter-spacing:.15em}
        .mx-live-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:clamp(12px,1.35vw,24px);max-width:1840px;margin:0 auto}
        .mx-live-card{display:grid;grid-template-columns:clamp(44px,4vw,75px) clamp(46px,4.4vw,82px) minmax(0,1fr) auto;gap:clamp(10px,1vw,20px);align-items:center;
          min-height:clamp(110px,14.5vh,160px);padding:clamp(15px,1.55vw,27px);border:1px solid rgba(255,255,255,.22);border-radius:24px;
          background:linear-gradient(115deg,rgba(25,58,82,.96),rgba(8,26,44,.96));box-shadow:0 14px 32px rgba(0,0,0,.26)}
        .mx-live-rank{text-align:center;font:900 clamp(25px,2.65vw,52px) Impact,'Arial Narrow',sans-serif;color:#ffe57d;min-height:1em}
        .mx-live-flag{font-size:clamp(38px,4vw,73px);line-height:1}.mx-live-country{font:900 clamp(27px,2.8vw,53px)/.95 Impact,'Arial Narrow',sans-serif;overflow-wrap:anywhere}
        .mx-live-progress-copy{margin-top:.32rem;font:800 clamp(11px,1vw,18px) Inter,sans-serif;letter-spacing:.13em;color:#bdd1df}
        .mx-live-progress{height:clamp(7px,.72vw,12px);margin-top:clamp(7px,.75vw,12px);border-radius:99px;background:rgba(255,255,255,.14);overflow:hidden}.mx-live-progress span{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#6ff1db,#f8db72)}
        .mx-live-score{white-space:nowrap;text-align:right;font:900 clamp(38px,4.25vw,76px)/.8 Impact,'Arial Narrow',sans-serif;color:#73f0da}.mx-live-score span{display:block;margin-top:.34rem;font:850 clamp(10px,.85vw,16px) Inter,sans-serif;letter-spacing:.14em;color:#e0f7f3}
        .mx-live-reconnect{height:100vh;display:flex;align-items:center;justify-content:center;color:#e2fffa;font:900 clamp(26px,3vw,52px) Inter,sans-serif;text-align:center}
        @media (max-width:900px){.mx-live{height:auto;min-height:100vh;overflow:visible;padding:24px 18px}.mx-live-grid{grid-template-columns:1fr}.mx-live-card{min-height:100px}}
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.fragment(run_every=f"{POLL_INTERVAL_SECONDS}s")
def _render_live_frame(client: PublicProjectorClient) -> None:
    try:
        projection = client.projection()
    except PublicProjectorError as error:
        st.markdown(f'<main class="mx-live-reconnect">{_safe(error)}</main>', unsafe_allow_html=True)
        return
    event = projection["Event"]
    eyebrow, title, state = _state_copy(event["State"], bool(event["HasAwardedScore"]))
    st.markdown(
        '<main class="mx-live">'
        f'<div class="mx-live-eyebrow">{_safe(eyebrow)}</div>'
        f'<div class="mx-live-title">{_safe(title)}</div>'
        f'<div class="mx-live-state">{_safe(state)}</div>'
        f'<section class="mx-live-grid">{_cards(projection)}</section>'
        '</main>',
        unsafe_allow_html=True,
    )


def render_maxis_live_public_projector() -> None:
    """Render the distinct public projector without controls or URL routing."""
    st.set_page_config(page_title="Maxis Mission AI — Live Leaderboard", layout="wide", initial_sidebar_state="collapsed")
    _inject_display_style()
    try:
        client = PublicProjectorClient.from_environment()
    except PublicProjectorError as error:
        st.markdown(f'<main class="mx-live-reconnect">{_safe(error)}</main>', unsafe_allow_html=True)
        return
    _render_live_frame(client)
