"""UAT participant experience for Mission AI Theme Park Race.

Presentation-only wrapper around the frozen canonical Theme Park Race engine.
It does not own or mutate team, Captain, mission, submission, review or score
state. All authority remains in the existing Core v2 RPC path.
"""
from __future__ import annotations

import html

import streamlit as st

from data.runtime_database import RuntimeDatabaseError
from screens.theme_park_race import (
    _LIFECYCLE_COPY,
    _inject_mission_theme,
    _render_brand_footer,
    _render_captain_authority,
    _render_ended_participant_screen,
    _render_evidence_form,
    _render_mission_header,
    _render_open_mission_board,
    _render_paused_banner,
    _route_rows,
    _workspace,
)


def _safe(value) -> str:
    return html.escape(str(value or "").strip())


def _member_name(member: dict) -> str:
    return str(
        member.get("Name")
        or member.get("ParticipantName")
        or member.get("DisplayName")
        or member.get("ParticipantID")
        or "Team member"
    ).strip()


def _render_team_experience(workspace: dict) -> None:
    """Make team belonging visible to every participant before gameplay."""
    team = str(workspace.get("TeamIdentity") or workspace.get("TeamID") or "Your Team").strip()
    captain_name = str(workspace.get("CaptainName") or "").strip()
    members = list(workspace.get("TeamMembers") or [])
    participant_id = str(st.session_state.get("participant_id") or "").strip()

    st.markdown(
        """
        <style>
        .mx-team-shell{margin:.65rem 0 1rem;padding:1rem;border-radius:18px;
          background:linear-gradient(145deg,rgba(22,40,62,.96),rgba(10,22,38,.96));
          border:1px solid rgba(217,178,76,.35);box-shadow:0 12px 34px rgba(0,0,0,.22)}
        .mx-eyebrow{font:800 .62rem Inter,sans-serif;letter-spacing:.18em;text-transform:uppercase;color:#2DD4BF}
        .mx-team-name{font:800 1.65rem/1.05 'Barlow Condensed',Impact,sans-serif;text-transform:uppercase;color:#fff;margin:.2rem 0 .35rem}
        .mx-team-count{font:700 .72rem Inter,sans-serif;color:#8CA0BE;margin-bottom:.75rem}
        .mx-captain{padding:.6rem .75rem;border-radius:12px;background:rgba(217,178,76,.10);border:1px solid rgba(217,178,76,.35);margin:.55rem 0 .75rem}
        .mx-captain-label{font:800 .58rem Inter,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#D9B24C}
        .mx-captain-name{font:800 .9rem Inter,sans-serif;color:#fff;margin-top:.1rem}
        .mx-member{display:flex;align-items:center;gap:.65rem;padding:.55rem .15rem;border-top:1px solid rgba(255,255,255,.07)}
        .mx-avatar{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(45,212,191,.12);border:1px solid rgba(45,212,191,.35);color:#2DD4BF;font:800 .68rem Inter,sans-serif;flex:0 0 auto}
        .mx-member-name{font:700 .78rem Inter,sans-serif;color:#EAF0F8;min-width:0;overflow-wrap:anywhere}
        .mx-you{margin-left:auto;font:800 .55rem Inter,sans-serif;letter-spacing:.1em;text-transform:uppercase;color:#2DD4BF}
        .mx-crown{margin-left:auto;color:#D9B24C;font-size:.8rem}
        .mx-rule{margin:.7rem 0 .1rem;padding:.65rem .75rem;border-radius:12px;background:rgba(45,212,191,.08);border:1px solid rgba(45,212,191,.22);font:700 .72rem/1.4 Inter,sans-serif;color:#CFE9E6}
        </style>
        """,
        unsafe_allow_html=True,
    )

    rows = []
    for member in members:
        name = _member_name(member)
        member_id = str(member.get("ParticipantID") or "").strip()
        initials = "".join(part[:1] for part in name.split()[:2]).upper() or "•"
        is_you = bool(participant_id and member_id == participant_id)
        is_captain = bool(captain_name and name.casefold() == captain_name.casefold())
        marker = '<span class="mx-you">YOU</span>' if is_you else ('<span class="mx-crown">★ CAPTAIN</span>' if is_captain else "")
        rows.append(
            '<div class="mx-member">'
            f'<div class="mx-avatar">{_safe(initials)}</div>'
            f'<div class="mx-member-name">{_safe(name)}</div>{marker}</div>'
        )

    captain_block = (
        f'<div class="mx-captain"><div class="mx-captain-label">Mission Captain</div><div class="mx-captain-name">★ {_safe(captain_name)}</div></div>'
        if captain_name
        else '<div class="mx-captain"><div class="mx-captain-label">Mission Captain</div><div class="mx-captain-name">Not selected yet</div></div>'
    )
    count_copy = f"{len(members)} team member{'s' if len(members) != 1 else ''}" if members else "Team roster loading"
    st.markdown(
        '<div class="mx-team-shell">'
        '<div class="mx-eyebrow">MY TEAM</div>'
        f'<div class="mx-team-name">{_safe(team)}</div>'
        f'<div class="mx-team-count">{_safe(count_copy)}</div>'
        f'{captain_block}'
        f'{"".join(rows)}'
        '<div class="mx-rule">Everyone can follow the Mission Board and team progress. Only your Mission Captain can submit results and evidence.</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_maxis_theme_park_participant(db, enrollment_credential="", device_id=""):
    """Shared participant view with Captain authority layered on top."""
    _inject_mission_theme()
    session_token = st.session_state.get("participant_session_token", "")
    try:
        workspace = _workspace(db, session_token)
    except RuntimeDatabaseError as error:
        st.warning("Mission AI is reconnecting.")
        st.caption(str(error))
        if st.button("Retry", width="stretch", key="theme_race_workspace_retry"):
            st.rerun()
        return

    lifecycle = workspace.get("Lifecycle", "REGISTRATION")
    strategy_mode = str(workspace.get("StrategyMode", "CONFIGURED_TEAM_ROUTE")).upper()

    if lifecycle == "ENDED":
        _render_ended_participant_screen(workspace)
        return

    if lifecycle in {"ACTIVE", "HELD"}:
        _render_mission_header(workspace)
    else:
        title, message = _LIFECYCLE_COPY.get(lifecycle, ("Mission AI", "Waiting for your facilitator."))
        st.markdown('<div class="mh-kicker">MISSION AI · TEAM EXPERIENCE</div>', unsafe_allow_html=True)
        st.subheader(title)
        st.info(message)

    # The roster is a shared team fact, visible to every authenticated member.
    # It is deliberately rendered before Captain controls and gameplay.
    if workspace.get("TeamID") or workspace.get("TeamIdentity"):
        _render_team_experience(workspace)

    if strategy_mode != "OPEN_MISSION_BOARD":
        st.caption(f"Team route progress: {workspace.get('Progress', {}).get('Completed', 0)} / {workspace.get('Progress', {}).get('Total', 0)}")
        route_rows = _route_rows(workspace)
        if route_rows:
            st.dataframe(route_rows, hide_index=True, width="stretch")

    if lifecycle == "HELD":
        _render_paused_banner()

    captain_active = _render_captain_authority(db, workspace, enrollment_credential, device_id)

    if lifecycle == "HELD":
        if strategy_mode == "OPEN_MISSION_BOARD":
            _render_open_mission_board(db, workspace, captain_active, interactive=False)
        _render_brand_footer()
        return

    if lifecycle != "ACTIVE":
        _render_brand_footer()
        return

    if strategy_mode == "OPEN_MISSION_BOARD":
        if not captain_active:
            st.caption("Follow the missions with your team. Your Mission Captain controls selection and submission.")
        _render_open_mission_board(db, workspace, captain_active)
        _render_brand_footer()
        return

    mission = workspace.get("CurrentMission")
    if not mission:
        st.success("🎉 Your team has completed every mission on this route.")
        _render_brand_footer()
        return
    if not captain_active:
        st.caption("Mission details are visible to the whole team. Only the Mission Captain can submit.")
        st.subheader(mission.get("DisplayName") or "Current mission")
        st.write(mission.get("ParticipantInstruction", ""))
        _render_brand_footer()
        return
    _render_evidence_form(db, workspace, mission)
    _render_brand_footer()
