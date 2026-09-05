"""UAT participant experience for Mission AI Theme Park Race.

Presentation-only wrapper around the frozen canonical Theme Park Race engine.
It does not own or mutate team, Captain, mission, submission, review or score
state. All authority remains in the existing Core v2 RPC path.
"""
from __future__ import annotations

import html
import json
import os
import urllib.error
import urllib.request

import streamlit as st

from data.runtime_database import RuntimeDatabaseError
from screens.participant import restore_participant_identity
from screens.theme_park_race import (
    _LIFECYCLE_COPY,
    _inject_mission_theme,
    _render_brand_footer,
    _render_captain_claim,
    _render_ended_participant_screen,
    _render_evidence_form,
    _render_mission_header,
    _render_mission_card,
    _render_paused_banner,
    _route_rows,
    _workspace,
)
from services.personal_key_credentials import derive_personal_key_credential
from services.maxis_team_formation_gate import country_roster_is_available


_ASSISTANT_MODEL = "gpt-5.6-luna"
_ASSISTANT_QUICK_PROMPTS = (
    "Explain the missions simply",
    "What evidence do we need?",
    "Which missions are worth most?",
    "What should our team do next?",
)
_COUNTRY_FLAGS = {
    "Japan": "🇯🇵", "South Korea": "🇰🇷", "France": "🇫🇷",
    "Italy": "🇮🇹", "Brazil": "🇧🇷", "Thailand": "🇹🇭",
}


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


def _render_individual_pass(workspace: dict) -> None:
    """Give every participant an unmistakable personal login identity.

    Never render the session token, device identifier, enrollment credential,
    API key or any other authentication secret. This is a human-facing event
    pass only, rebuilt from canonical participant/team workspace data.
    """
    name = str(st.session_state.get("participant_name") or "Participant").strip()
    team = str(workspace.get("TeamIdentity") or workspace.get("TeamID") or "Team pending").strip()
    is_captain = bool(workspace.get("IsCaptain"))
    role = "MISSION CAPTAIN" if is_captain else "TEAM MEMBER"
    lifecycle = str(workspace.get("Lifecycle") or "").upper()
    status = "MISSION LIVE" if lifecycle == "ACTIVE" else ("MISSION PAUSED" if lifecycle == "HELD" else "SIGNED IN")

    st.markdown(
        """
        <style>
        .mx-pass{margin:.45rem 0 .75rem;padding:.8rem .9rem;border-radius:14px;
          background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.12)}
        .mx-pass-kicker{font:800 .57rem Inter,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:#8CA0BE}
        .mx-pass-name{font:800 1.05rem/1.15 Inter,sans-serif;color:#fff;margin:.2rem 0 .45rem;overflow-wrap:anywhere}
        .mx-pass-grid{display:grid;grid-template-columns:1fr 1fr;gap:.45rem}
        .mx-pass-cell{padding:.45rem .55rem;border-radius:10px;background:rgba(10,22,38,.55)}
        .mx-pass-label{font:800 .52rem Inter,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:#8CA0BE}
        .mx-pass-value{font:800 .72rem Inter,sans-serif;color:#EAF0F8;margin-top:.08rem;overflow-wrap:anywhere}
        .mx-pass-role{color:#D9B24C}.mx-pass-live{color:#2DD4BF}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="mx-pass">'
        '<div class="mx-pass-kicker">SIGNED IN AS</div>'
        f'<div class="mx-pass-name">{_safe(name)}</div>'
        '<div class="mx-pass-grid">'
        '<div class="mx-pass-cell"><div class="mx-pass-label">Country</div>'
        f'<div class="mx-pass-value">{_safe(team)}</div></div>'
        '<div class="mx-pass-cell"><div class="mx-pass-label">Role</div>'
        f'<div class="mx-pass-value mx-pass-role">{_safe(role)}</div></div>'
        '<div class="mx-pass-cell"><div class="mx-pass-label">Access</div>'
        '<div class="mx-pass-value">INDIVIDUAL</div></div>'
        '<div class="mx-pass-cell"><div class="mx-pass-label">Status</div>'
        f'<div class="mx-pass-value mx-pass-live">{_safe(status)}</div></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )


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
        '<div class="mx-eyebrow">YOUR COUNTRY TEAM</div>'
        f'<div class="mx-team-name">{_safe(team)}</div>'
        f'<div class="mx-team-count">{_safe(count_copy)}</div>'
        f'{captain_block}'
        f'{"".join(rows)}'
        '<div class="mx-rule">Everyone can follow the Mission Board and team progress. Only your Mission Captain can submit results and evidence.</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_briefing() -> None:
    st.markdown("### Mission briefing")
    st.info(
        "Not every mission is required. Choose the missions that best fit your team, "
        "maximise your approved points, and return by the facilitator's announced deadline."
    )
    st.caption("Everyone can follow the board and progress. Only the Mission Captain can accept missions and submit evidence.")


def _render_canonical_team_progress(db, workspace: dict) -> None:
    """Show score and completed missions from the canonical ledger/progress views."""
    team_id = str(workspace.get("TeamID") or "")
    score = 0.0
    try:
        leaderboard = db.runtime.get_canonical_leaderboard(workspace.get("EventID", ""))
        score = next((float(row.get("Score", 0) or 0) for row in leaderboard
                      if str(row.get("TeamID") or "") == team_id), 0.0)
    except (AttributeError, RuntimeDatabaseError):
        # Board availability must not depend on the optional display read.
        score = 0.0
    progress = dict(workspace.get("Progress") or {})
    completed = int(progress.get("Completed", 0) or 0)
    total = int(progress.get("Total", 0) or 0)
    country = str(workspace.get("TeamIdentity") or workspace.get("TeamID") or "Your country")
    score_copy = str(int(score)) if score.is_integer() else f"{score:.1f}"
    st.markdown(
        """
        <style>
        .mx-progress{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:.65rem;align-items:center;margin:.6rem 0 1rem;padding:.75rem .85rem;border-radius:15px;background:linear-gradient(115deg,rgba(45,212,191,.13),rgba(11,27,44,.95));border:1px solid rgba(45,212,191,.42)}
        .mx-progress-flag{font-size:2rem}.mx-progress-country{font:900 .68rem Inter,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#fff}.mx-progress-copy{font:800 .61rem Inter,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#9fb6c8;margin-top:.18rem}.mx-progress-score{text-align:right;font:900 1.85rem/.9 'Barlow Condensed',Impact,sans-serif;color:#ffe07a}.mx-progress-score span{display:block;font:800 .54rem Inter,sans-serif;letter-spacing:.12em;color:#d6deea;margin-top:.2rem}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="mx-progress">'
        f'<div class="mx-progress-flag">{_safe(_COUNTRY_FLAGS.get(country, "🏳️"))}</div>'
        f'<div><div class="mx-progress-country">{_safe(country)}</div><div class="mx-progress-copy">{completed} / {total} missions completed</div></div>'
        f'<div class="mx-progress-score">{_safe(score_copy)}<span>TOTAL SCORE</span></div></div>',
        unsafe_allow_html=True,
    )


def _render_maxis_open_board(db, workspace: dict, captain_active: bool, *, interactive: bool = True) -> None:
    """Group the existing canonical board without changing its authority rules."""
    board = list(workspace.get("MissionBoard") or [])
    if not board:
        st.info("No mission is currently available.")
        return
    categories = (
        ("🎢 RIDES", {"RIDE"}),
        ("🎯 TASKS", {"STANDARD", "BONUS"}),
        ("🕵️ SECRET MISSIONS", {"SECRET"}),
    )
    for title, classes in categories:
        missions = [mission for mission in board if str(mission.get("MissionClass", "STANDARD")).upper() in classes]
        # Approved missions remain visible as a shared team record, but never
        # compete with active choices for attention or look actionable again.
        missions.sort(key=lambda mission: str(mission.get("MissionState", "")).upper() == "APPROVED")
        if not missions:
            continue
        st.markdown(f"### {title}")
        for mission in missions:
            _render_mission_card(db, workspace, mission, captain_active, interactive=interactive)


def _render_maxis_captain_authority(db, workspace: dict, device_id: str) -> bool:
    """Keep Captain ownership canonical while using a Personal Key for recovery."""
    if not workspace.get("IsCaptain"):
        if workspace.get("Lifecycle") == "CAPTAIN_SELECTION":
            _render_captain_claim(db, workspace, device_id)
        else:
            st.info("Only the Mission Captain can submit evidence for this country team.")
        return False

    st.caption("🧭 You are the Mission Captain")
    if workspace.get("CaptainSessionActive", False):
        return True

    st.warning("Mission Captain access needs to be restored on this device before you can submit.")
    with st.form("maxis_captain_recovery", clear_on_submit=True):
        key = st.text_input("PERSONAL KEY", type="password", autocomplete="off")
        submitted = st.form_submit_button("Restore Mission Captain Access", type="primary", width="stretch")
    if not submitted:
        return False
    try:
        credential = derive_personal_key_credential("MAXIS-UAT-PREASSIGNED", key)
        identity = db.runtime.recover_team_formation_captain("MXKEY7", credential, device_id)
    except (RuntimeDatabaseError, ValueError):
        st.error("That Personal Key was not recognised. Check the code beside your name and try again.")
        return False
    finally:
        # Neither the raw Personal Key nor its opaque derivative is retained
        # by this screen after the single recovery call.
        st.session_state.pop("maxis_captain_recovery-PERSONAL KEY", None)
    if not identity or str(identity.get("ParticipantID", "")) != str(workspace.get("ParticipantID", "")):
        st.error("Mission Captain access could not be restored on this device. Please contact the facilitator.")
        return False
    # Captain recovery also revives the canonical participant session on this
    # device.  Persist its returned token before rerunning, otherwise the next
    # workspace read would use the deliberately invalidated older session.
    restore_participant_identity(identity)
    st.success("Mission Captain access restored.")
    st.rerun()


def _assistant_context(workspace: dict) -> dict:
    """Build the only context Mission AI is allowed to answer from."""
    missions = []
    for mission in list(workspace.get("MissionBoard") or []):
        missions.append({
            "name": mission.get("DisplayName") or "Mission",
            "class": mission.get("MissionClass") or "STANDARD",
            "state": mission.get("MissionState") or "",
            "zone": mission.get("Zone") or "",
            "location": mission.get("LocationDescription") or "",
            "instruction": mission.get("ParticipantInstruction") or "",
            "safety": mission.get("SafetyNote") or "",
            "points": (mission.get("Scoring") or {}).get("Maximum") or 0,
            "evidence": mission.get("Evidence") or {},
            "ride_participation": mission.get("RideParticipation") or {},
            "required_riders": mission.get("RideRequiredParticipantCount") or 0,
        })
    progress = workspace.get("Progress") or {}
    return {
        "event": workspace.get("EventName") or "Mission AI",
        "team": workspace.get("TeamIdentity") or workspace.get("TeamID") or "",
        "role": "Mission Captain" if workspace.get("IsCaptain") else "Team Member",
        "captain": workspace.get("CaptainName") or "Not selected",
        "lifecycle": workspace.get("Lifecycle") or "",
        "progress": {
            "completed": progress.get("Completed", 0),
            "total": progress.get("Total", 0),
        },
        "missions": missions,
        "event_rule": "Teams do not need to complete every mission. Maximise points and return by the facilitator's announced deadline.",
    }


def _deterministic_assistant_answer(question: str, context: dict) -> str:
    """Useful fail-open answer when OPENAI_API_KEY is unavailable."""
    q = question.casefold()
    missions = list(context.get("missions") or [])
    if "worth" in q or "point" in q or "highest" in q:
        ranked = sorted(missions, key=lambda row: float(row.get("points") or 0), reverse=True)
        if ranked:
            return "Highest-value visible missions: " + "; ".join(
                f"{row['name']} — {int(row.get('points') or 0)} pts" for row in ranked[:4]
            ) + ". You do not need to complete everything."
    if "evidence" in q or "submit" in q:
        active = [row for row in missions if str(row.get("state", "")).upper() in {"SELECTED", "REJECTED"}]
        rows = active or missions[:3]
        if rows:
            parts = []
            for row in rows:
                evidence = row.get("evidence") or {}
                needs = []
                if (evidence.get("Text") or {}).get("Required"):
                    needs.append((evidence.get("Text") or {}).get("Label") or "text response")
                if (evidence.get("Photo") or {}).get("Required"):
                    needs.append((evidence.get("Photo") or {}).get("Label") or "photo")
                if (evidence.get("NumericResult") or {}).get("Required"):
                    needs.append((evidence.get("NumericResult") or {}).get("Label") or "numeric result")
                parts.append(f"{row['name']}: {', '.join(needs) if needs else 'follow the mission card'}")
            return "Evidence needed — " + "; ".join(parts) + "."
    if "next" in q or "should" in q:
        available = [row for row in missions if str(row.get("state", "")).upper() == "AVAILABLE"]
        if available:
            best = max(available, key=lambda row: float(row.get("points") or 0))
            return f"A strong next option is {best['name']} for up to {int(best.get('points') or 0)} points. Choose based on queue, distance and your team's confidence, and return by the announced deadline."
    if "explain" in q or "simple" in q or "mission" in q:
        selected = [row for row in missions if str(row.get("state", "")).upper() in {"SELECTED", "REJECTED"}]
        rows = selected or missions[:4]
        if rows:
            return "In simple terms: " + " ".join(
                f"{row['name']}: {row.get('instruction') or 'follow the mission card.'}" for row in rows
            )
    return "I can explain any visible mission, tell you what evidence is required, compare points, or suggest what your team could attempt next."


def _call_mission_ai(question: str, context: dict) -> str:
    api_key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return _deterministic_assistant_answer(question, context)

    instructions = (
        "You are Mission AI, an in-event guide for a corporate team challenge. "
        "Answer ONLY from the supplied canonical event context. Never invent park rules, mission rules, scores, deadlines, locations or evidence requirements. "
        "Never claim to approve, submit, score, select a Captain, release a Secret Mission, or change EXOS state. "
        "Use very simple action language suitable for someone walking around a theme park. Keep answers under 120 words. "
        "If the answer is not in the context, say: 'Check with your facilitator.'"
    )
    payload = json.dumps({
        "model": _ASSISTANT_MODEL,
        "instructions": instructions,
        "input": f"EVENT CONTEXT:\n{json.dumps(context, ensure_ascii=False)}\n\nPARTICIPANT QUESTION:\n{question}",
        "max_output_tokens": 250,
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return _deterministic_assistant_answer(question, context)

    if body.get("output_text"):
        return str(body["output_text"]).strip()
    chunks = []
    for item in body.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                chunks.append(str(content["text"]))
    return "\n".join(chunks).strip() or _deterministic_assistant_answer(question, context)


def _render_mission_ai_assistant(workspace: dict) -> None:
    """Read-only, event-grounded participant assistant."""
    st.markdown(
        """
        <style>
        .mx-ai-shell{margin:1rem 0;padding:.9rem;border-radius:16px;background:linear-gradient(145deg,rgba(45,212,191,.10),rgba(10,22,38,.96));border:1px solid rgba(45,212,191,.38)}
        .mx-ai-title{font:800 1rem Inter,sans-serif;color:#fff}.mx-ai-sub{font:600 .68rem/1.4 Inter,sans-serif;color:#8CA0BE;margin-top:.15rem}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="mx-ai-shell"><div class="mx-ai-title">✨ Ask Mission AI</div>'
        '<div class="mx-ai-sub">Ask about your visible missions, evidence, points or what your team could do next. Mission AI cannot change scores or event rules.</div></div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(2)
    pending_question = ""
    for index, prompt in enumerate(_ASSISTANT_QUICK_PROMPTS):
        with cols[index % 2]:
            if st.button(prompt, width="stretch", key=f"mx_ai_quick_{index}"):
                pending_question = prompt

    typed = st.text_input(
        "Ask Mission AI",
        key="mx_ai_question",
        placeholder="e.g. Explain Acorn Adventure simply",
        label_visibility="collapsed",
    )
    if st.button("Ask ✨", type="primary", width="stretch", key="mx_ai_ask"):
        pending_question = typed.strip()

    if pending_question:
        with st.spinner("Mission AI is checking your event…"):
            answer = _call_mission_ai(pending_question, _assistant_context(workspace))
        st.session_state["mx_ai_last_question"] = pending_question
        st.session_state["mx_ai_last_answer"] = answer

    if st.session_state.get("mx_ai_last_answer"):
        st.caption(st.session_state.get("mx_ai_last_question", ""))
        st.info(st.session_state["mx_ai_last_answer"])


def render_maxis_theme_park_participant(db, enrollment_credential="", device_id="", workspace=None):
    """Shared participant view with Captain authority layered on top."""
    _inject_mission_theme()
    if workspace is None:
        session_token = st.session_state.get("participant_session_token", "")
        try:
            workspace = _workspace(db, session_token)
        except RuntimeDatabaseError:
            st.warning("Mission AI is reconnecting.")
            st.caption("Your team state could not be refreshed yet. Please retry.")
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
        _render_canonical_team_progress(db, workspace)
    else:
        title, message = _LIFECYCLE_COPY.get(lifecycle, ("Mission AI", "Waiting for your facilitator."))
        st.markdown('<div class="mh-kicker">MISSION AI · TEAM EXPERIENCE</div>', unsafe_allow_html=True)
        st.subheader(title)
        st.info(message)

    # Team details are withheld until canonical Team Formation has passed the
    # country-only registration stage.  This keeps the initial reveal free of
    # roster, Captain and mission-board disclosure.
    _render_individual_pass(workspace)

    if country_roster_is_available(workspace) and (workspace.get("TeamID") or workspace.get("TeamIdentity")):
        _render_team_experience(workspace)

    # The strategic rule is a live-game rule, not only a pre-launch briefing.
    # Keep it visible when the board is ACTIVE (and while it is HELD) so teams
    # can make informed choices without relying on a facilitator reminder.
    if lifecycle in {"READY", "ACTIVE", "HELD"}:
        _render_briefing()

    if strategy_mode != "OPEN_MISSION_BOARD":
        st.caption(f"Team route progress: {workspace.get('Progress', {}).get('Completed', 0)} / {workspace.get('Progress', {}).get('Total', 0)}")
        route_rows = _route_rows(workspace)
        if route_rows:
            st.dataframe(route_rows, hide_index=True, width="stretch")

    if lifecycle == "HELD":
        _render_paused_banner()

    del enrollment_credential
    captain_active = _render_maxis_captain_authority(db, workspace, device_id)

    # The assistant is read-only and remains useful to every team member.
    # It is shown during READY/ACTIVE/HELD but not after terminal END.
    if lifecycle in {"READY", "ACTIVE", "HELD"}:
        _render_mission_ai_assistant(workspace)

    if lifecycle == "HELD":
        if strategy_mode == "OPEN_MISSION_BOARD":
            _render_maxis_open_board(db, workspace, captain_active, interactive=False)
        _render_brand_footer()
        return

    if lifecycle != "ACTIVE":
        _render_brand_footer()
        return

    if strategy_mode == "OPEN_MISSION_BOARD":
        if not captain_active:
            st.caption("Follow the missions with your team. Your Mission Captain controls selection and submission.")
        _render_maxis_open_board(db, workspace, captain_active)
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
