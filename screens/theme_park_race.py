"""Shared participant, facilitator and projector surfaces for Theme Park Race.

All state is rebuilt from the Core-v2 adapter on render.  This module does not
own a participant, team, event, submission, Captain or scoring store.
"""
from __future__ import annotations

import html
import os
from datetime import datetime

import streamlit as st

from data.google_drive import get_photo_url, upload_photo
from data.runtime_database import RuntimeDatabaseError
from engines.theme_park_race import projector_projection
from data.upload_safety import upload_error_message


def _submit_trace_enabled() -> bool:
    return str(os.getenv("EXOS_ENV", "")).strip().lower() == "staging"


def _submit_trace(activity_id: str, **fields) -> None:
    """TEMPORARY diagnostic for the P0 board-submit investigation.

    Staging only.  Never logs a session token, device id, credential, photo
    URL, or participant name/PII — only booleans, enum-like states, and
    exception class names.
    """
    if not _submit_trace_enabled():
        return
    rendered = " | ".join(f"{key}={value}" for key, value in fields.items())
    print(f"TPR_SUBMIT_TRACE | activity_id={activity_id} | {rendered}")


_LIFECYCLE_COPY = {
    "REGISTRATION": ("Registration", "Register to receive your team assignment."),
    "TEAM_FORMATION": ("Team Formation", "Registration is open. Your team assignment is on its way."),
    "FORMATION_LOCKED": ("Teams Locked", "Team formation has closed. Your team is now final."),
    "CAPTAIN_SELECTION": ("Captain Selection", "Your team must choose one Mission Captain before missions can start."),
    "READY": ("Get Ready", "Teams and Captains are set. Your facilitator will start the mission shortly."),
    "ACTIVE": ("Mission Active", "Complete your team's missions."),
    "HELD": ("Mission AI Paused", "Please wait for your facilitator."),
    "ENDED": ("Mission Complete 🎉", "Thank you for participating."),
}


# Fixed, code-authored badge content only — never interpolate participant or
# facilitator free text (mission titles, instructions, rejection reasons)
# into these.  A dynamic value with an embedded newline defeated Markdown's
# indentation handling once already (the raw team card incident); the fix
# there was to keep free text out of unsafe_allow_html entirely, which this
# module follows throughout.
_STATE_BADGES = {
    "AVAILABLE": ("tp-badge-available", "🟡", "AVAILABLE"),
    "SELECTED": ("tp-badge-progress", "🔵", "IN PROGRESS"),
    "SUBMITTED": ("tp-badge-submitted", "📨", "AWAITING REVIEW"),
    "APPROVED": ("tp-badge-approved", "✅", "COMPLETED"),
    "REJECTED": ("tp-badge-rejected", "⚠️", "RESUBMISSION REQUIRED"),
    "CLOSED": ("tp-badge-locked", "🔒", "CLOSED"),
    "TEMPORARILY_UNAVAILABLE": ("tp-badge-paused", "⏸", "PAUSED"),
}


def _state_badge_html(state: str) -> str:
    css_class, icon, label = _STATE_BADGES.get(str(state or "").upper(), ("tp-badge-locked", "•", "UNAVAILABLE"))
    return f'<span class="tp-badge {css_class}">{icon} {label}</span>'


def _inject_mission_theme() -> None:
    """One-time, fully static CSS for the Theme Park Mission Captain surface.

    Every rule here is fixed and code-authored; nothing dynamic is ever
    interpolated into this block.  EXOS Navy/Gold anchor the brand; a teal
    accent gives Theme Park Mission its own identity next to Formula
    R.A.C.E.'s red, distinct from it rather than copying it.
    """
    st.markdown(
        """
        <style>
        :root {
          --tp-navy:#082D58; --tp-navy-deep:#051D3B; --tp-gold:#B59A37;
          --tp-teal:#0E9C8B; --tp-blue:#2E6DB4; --tp-green:#1E8E5A;
          --tp-red:#C4342F; --tp-amber:#B8790A; --tp-mist:#5B7089;
        }
        .tp-header { background:linear-gradient(135deg,var(--tp-navy) 0%,var(--tp-navy-deep) 100%); border:1px solid rgba(181,154,55,.45); border-radius:16px; padding:1.1rem 1.25rem; margin-bottom:1rem; color:#fff; }
        .tp-header-kicker { font:800 .68rem/1 Inter,system-ui,sans-serif; letter-spacing:.16em; text-transform:uppercase; color:var(--tp-gold); margin-bottom:.2rem; }
        .tp-header-team { font:800 2rem/1.08 'Barlow Condensed',Impact,sans-serif; letter-spacing:.01em; text-transform:uppercase; color:#fff; overflow-wrap:anywhere; margin:0; }
        .tp-header-stats { display:flex; align-items:baseline; gap:.55rem; margin-top:.6rem; }
        .tp-header-count { font:800 2.5rem/1 'Barlow Condensed',Impact,sans-serif; color:var(--tp-gold); }
        .tp-header-count-label { font:800 .74rem Inter,sans-serif; letter-spacing:.07em; text-transform:uppercase; color:#e8edf3; }
        .tp-header-remaining { margin-top:.5rem; display:inline-block; padding:.3rem .7rem; border-radius:999px; background:rgba(181,154,55,.2); border:1px solid rgba(181,154,55,.55); color:var(--tp-gold); font:800 .76rem Inter,sans-serif; letter-spacing:.04em; }
        .tp-progress-track { background:rgba(255,255,255,.2); border-radius:999px; height:8px; margin:.65rem 0 .1rem; overflow:hidden; }
        .tp-progress-fill { background:var(--tp-gold); height:100%; border-radius:999px; }
        .tp-badge { display:inline-flex; align-items:center; gap:.32rem; padding:.34rem .7rem; border-radius:999px; font:800 .74rem Inter,system-ui,sans-serif; letter-spacing:.03em; text-transform:uppercase; border:1.5px solid transparent; white-space:nowrap; }
        .tp-badge-available { background:#FFF3D6; color:#6B4400; border-color:#D99B12; }
        .tp-badge-progress  { background:#DFF5F2; color:#08463E; border-color:var(--tp-teal); }
        .tp-badge-submitted { background:#E4EEFB; color:#173C6B; border-color:var(--tp-blue); }
        .tp-badge-approved  { background:#E1F5E7; color:#0F4A29; border-color:var(--tp-green); }
        .tp-badge-rejected  { background:#FBE4E3; color:#6B0F0C; border-color:var(--tp-red); }
        .tp-badge-locked    { background:#EAEEF3; color:#33414F; border-color:#B8C3D0; }
        .tp-badge-paused    { background:#FCE7CC; color:#5E3600; border-color:var(--tp-amber); }
        .tp-card-meta { color:var(--tp-mist); font:700 .72rem Inter,sans-serif; letter-spacing:.04em; text-transform:uppercase; margin-bottom:.1rem; }
        .tp-points { display:inline-flex; align-items:center; gap:.25rem; padding:.2rem .55rem; border-radius:999px; background:rgba(181,154,55,.16); color:#6B4400; font:800 .7rem Inter,sans-serif; letter-spacing:.03em; }
        .tp-secret-banner { background:linear-gradient(120deg,rgba(181,154,55,.28),rgba(8,45,88,.94)); border:1px solid var(--tp-gold); border-radius:12px; padding:.75rem 1rem; margin-bottom:.6rem; color:#fff; font:800 .88rem Inter,sans-serif; letter-spacing:.03em; text-transform:uppercase; }
        .tp-paused-banner { background:linear-gradient(120deg,rgba(184,121,10,.24),rgba(8,45,88,.92)); border:1px solid var(--tp-amber); border-radius:14px; padding:1.4rem 1.1rem; margin:.4rem 0 .6rem; color:#fff; text-align:center; }
        .tp-paused-banner-title { font:800 1.5rem/1.15 'Barlow Condensed',Impact,sans-serif; letter-spacing:.02em; text-transform:uppercase; margin-bottom:.35rem; }
        .tp-rejected-banner { background:#FBE4E3; border:2px solid var(--tp-red); border-radius:12px; padding:.85rem 1rem; margin:.4rem 0 .5rem; color:#5A0D0A; }
        .tp-rejected-title { font:800 1rem Inter,system-ui,sans-serif; letter-spacing:.04em; text-transform:uppercase; margin-bottom:.15rem; }
        div.stButton>button, div[data-testid="stFormSubmitButton"]>button { min-height:48px; border-radius:10px; font-weight:800; letter-spacing:.01em; }
        /* Theme Park's own primary-action colour, on top of Streamlit's default
           red. Injected only by _inject_mission_theme(), which only the Theme
           Park participant surface calls, so it never reaches the legacy
           Captain shell's page — that surface injects its own, separate CSS
           and is a different entrypoint entirely. */
        div.stButton>button[kind="primary"] { background:var(--tp-navy); border-color:var(--tp-navy); color:#fff; }
        div.stButton>button[kind="primary"]:hover { background:var(--tp-navy-deep); border-color:var(--tp-navy-deep); color:#fff; }
        div.stButton>button[kind="primary"]:disabled { background:#C3CCD6; border-color:#C3CCD6; color:#5B7089; opacity:1; }
        div[data-testid="stFileUploader"] { border:1.5px dashed var(--tp-teal); border-radius:10px; padding:.5rem; }
        @media (max-width:600px) {
          .tp-header-team { font-size:1.65rem; }
          .tp-header-count { font-size:2.05rem; }
          .block-container { padding-left:.6rem !important; padding-right:.6rem !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_mission_header(workspace) -> None:
    """Persistent Team/progress dashboard. Every value is canonical and live.

    Team identity is the loudest element on the page; Captain status is
    rendered separately (by ``_render_captain_authority``) as secondary
    information underneath, never competing with it.
    """
    team = str(workspace.get("TeamIdentity") or workspace.get("TeamID") or "Your Team").strip()
    # Team identity is facilitator-configured free text, not a closed enum —
    # escape it before it enters raw HTML.  A dynamic value with an embedded
    # newline once defeated Markdown's own indentation handling this exact
    # way (the raw team card incident); html.escape is the actual fix, not
    # just avoiding textwrap.dedent.  The visual upper-case treatment is CSS
    # (text-transform), not a Python .upper() — the underlying text a screen
    # reader or a test sees stays exactly what the facilitator configured.
    safe_team = html.escape(team)
    progress = workspace.get("Progress", {}) or {}
    completed = int(progress.get("Completed", 0) or 0)
    total = int(progress.get("Total", 0) or 0)
    remaining = max(total - completed, 0)
    fraction = min(completed / total, 1.0) if total > 0 else 0.0
    remaining_label = "ALL MISSIONS DONE" if remaining == 0 and total > 0 else f"{remaining} TO GO"
    # Everything below is ONE markdown call inside a single .tp-header wrapper.
    # The kicker/team/stats/remaining pieces were previously written as four
    # separate st.markdown calls with no enclosing card, so the navy/gold
    # background never actually rendered and their white/near-white text sat
    # directly on the page background instead — invisible, not just low
    # contrast.  A native st.progress() bar also can't live inside a single
    # HTML string, so the indicator here is a plain width-percentage div —
    # `fraction` is always a float derived from Progress counts, never
    # participant/facilitator text, so it carries no escaping risk.
    st.markdown(
        '<div class="tp-header">'
        '<div class="tp-header-kicker">MISSION CAPTAIN</div>'
        f'<div class="tp-header-team">TEAM {safe_team}</div>'
        '<div class="tp-header-stats">'
        f'<span class="tp-header-count">{completed}/{total}</span>'
        '<span class="tp-header-count-label">MISSIONS<br/>COMPLETED</span>'
        '</div>'
        f'<div class="tp-progress-track"><div class="tp-progress-fill" style="width:{fraction * 100:.0f}%;"></div></div>'
        f'<span class="tp-header-remaining">{remaining_label}</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_paused_banner() -> None:
    st.markdown(
        '<div class="tp-paused-banner">'
        '<div class="tp-paused-banner-title">⏸ Mission AI Paused</div>'
        '<div>Please wait for your facilitator.</div>'
        '</div>',
        unsafe_allow_html=True,
    )


OPEN_MISSION_BOARD = "OPEN_MISSION_BOARD"
_STALE_REVISION_NOTICE = (
    "This submission changed after this page was loaded, so nothing was reviewed. "
    "The board has been refreshed — review the current revision."
)


def _workspace(db, session_token):
    return db.runtime.theme_park_race_participant_workspace(session_token)


def submit_theme_park_race_review(control, strategy_mode, submission, *, decision, score, actor, notes):
    """Route one facilitator decision to the canonical contract for this mode.

    OPEN_MISSION_BOARD reviews go to the installed 039 board contract carrying
    the exact revision the facilitator was shown, so a submission that changed
    in the meantime is refused rather than silently reviewed.  Every other
    engine and strategy keeps its existing review contract untouched.
    """
    submission_id = str(submission.get("SubmissionID", ""))
    approved = str(decision).upper() in {"APPROVE", "APPROVED"}
    if str(strategy_mode or "").upper() != OPEN_MISSION_BOARD:
        control.review_submission(
            submission_id, score if approved else 0, notes,
            status="APPROVED" if approved else "REJECTED",
        )
        return {"Reviewed": True}
    submitted_at = str(submission.get("SubmittedAt", "") or "")
    if not submitted_at:
        return {"Reviewed": False, "Level": "warning", "Message": _STALE_REVISION_NOTICE}
    mapped = "APPROVE" if approved else "REJECT"
    try:
        control.review_theme_park_race_board_submission(
            submission_id, submitted_at, mapped,
            score=score if approved else 0, actor=actor, reason=notes,
            idempotency_key=f"theme-park-race-board-review|{submission_id}|{submitted_at}|{mapped}",
        )
    except RuntimeDatabaseError as error:
        if "revision is stale" in str(error).casefold():
            return {"Reviewed": False, "Level": "warning", "Message": _STALE_REVISION_NOTICE}
        return {"Reviewed": False, "Level": "error", "Message": str(error)}
    return {"Reviewed": True}


def _queue_review_notice(event_id, outcome):
    if outcome.get("Message"):
        st.session_state[f"theme_race_review_notice_{event_id}"] = outcome


def _render_review_notice(event_id):
    outcome = st.session_state.pop(f"theme_race_review_notice_{event_id}", None) or {}
    if not outcome.get("Message"):
        return
    if str(outcome.get("Level", "warning")) == "error":
        st.error(outcome["Message"])
    else:
        st.warning(outcome["Message"])


def _mission_status(workspace, activity_id):
    row = (workspace.get("Progress", {}).get("SubmissionsByActivity", {}) or {}).get(activity_id, {})
    return str(row.get("Status", "AVAILABLE" if activity_id == workspace.get("Progress", {}).get("CurrentActivityID") else "LOCKED")).upper()


def _route_rows(workspace):
    current = str(workspace.get("Progress", {}).get("CurrentActivityID", ""))
    submitted = workspace.get("Progress", {}).get("SubmissionsByActivity", {}) or {}
    rows = []
    for position, activity_id in enumerate(workspace.get("Route", []) or [], 1):
        status = str((submitted.get(activity_id) or {}).get("Status", "")).upper()
        if not status:
            status = "CURRENT" if activity_id == current else "LOCKED"
        rows.append({"#": position, "Mission ID": activity_id, "Status": status})
    return rows


def _render_ended_participant_screen(workspace):
    """Render the terminal, celebratory state from canonical progress, no writes."""
    st.success("MISSION COMPLETE 🎉")
    _render_mission_header(workspace)
    st.write("Thank you for participating.")
    st.info("Please wait for your facilitator to announce the winning team.")


def _restore_captain_recovery(identity):
    """Keep only canonical identity values after the recovery RPC returns."""
    for source, target in (
        ("ParticipantID", "participant_id"),
        ("EventID", "participant_event_id"),
        ("TeamID", "participant_team_id"),
        ("Team", "participant_team"),
        ("Name", "participant_name"),
        ("SessionToken", "participant_session_token"),
    ):
        if identity.get(source) not in (None, ""):
            st.session_state[target] = identity[source]


def _render_captain_claim(db, workspace, device_id):
    """Offer the canonical Team Formation Captain claim to an eligible member.

    The seat, not the browser, decides what is shown: eligibility comes from the
    canonical workspace, and the claim itself is settled server-side by
    ``exos_v2_claim_team_formation_captain`` under the participant's own
    session.  No PIN, no Formula R.A.C.E. captain shell, no service role.
    """
    event_id = workspace.get("EventID", "")
    if not workspace.get("CanClaimCaptain"):
        captain_name = str(workspace.get("CaptainName", "") or "").strip()
        # Safe, public team fact only — never the Captain's session or device.
        st.info(
            f"Captain already selected: {captain_name}." if captain_name
            else "Captain already selected for this team."
        )
        return

    st.write("Your team doesn't have a Mission Captain yet.")
    if not st.button(
        "Become Mission Captain", type="primary", width="stretch",
        key=f"theme_race_claim_{event_id}",
    ):
        return

    session_token = st.session_state.get("participant_session_token", "")
    if not session_token:
        st.error("Your participant session is reconnecting. Try again in a moment.")
        return
    try:
        result = db.runtime.claim_team_formation_captain(session_token, device_id)
    except RuntimeDatabaseError as error:
        st.error(str(error))
        return

    if result.get("Claimed"):
        st.success("You are now this team's Mission Captain.")
        st.rerun()
    elif result.get("RecoveryRequired"):
        st.warning(
            "Mission Captain access is already active on a different device. "
            "Recover it on that device, or ask your facilitator to transfer it."
        )
    elif result.get("CaptainAlreadyClaimed"):
        st.info("Mission Captain already selected for this team.")
        st.rerun()
    else:
        st.info("Captain selection is not open for this team right now.")


def _render_captain_authority(db, workspace, enrollment_credential, device_id):
    event_id = workspace.get("EventID", "")
    if not workspace.get("IsCaptain"):
        if workspace.get("Lifecycle") == "CAPTAIN_SELECTION":
            _render_captain_claim(db, workspace, device_id)
        else:
            st.info("Only the Mission Captain can submit evidence for this team.")
        return False

    st.caption("🧭 You are the Mission Captain")
    if not workspace.get("CaptainSessionActive", False):
        st.warning("Mission Captain access needs to be restored on this device before you can submit.")
        if st.button("Restore Mission Captain Access", type="primary", width="stretch", key=f"theme_race_recover_captain_{event_id}"):
            if not enrollment_credential:
                st.error("Secure registration is still loading. Try again in a moment.")
                return False
            identity = db.runtime.recover_team_formation_captain(
                st.session_state.get("participant_join_code", ""), enrollment_credential, device_id,
            )
            _restore_captain_recovery(identity)
            st.success("Mission Captain access restored.")
            st.rerun()
        return False
    return True


def _render_evidence_form(db, workspace, mission, captain_active=True, show_title=True, show_instruction=True):
    """Render this mission's evidence form and, on submit, call board_submit.

    The Submit button is constructed on EVERY render where this mission is
    SELECTED/REJECTED, regardless of ``captain_active``.  ``captain_active``
    is re-derived on every independent script rerun from a live join across
    ``participant_sessions_v2`` and ``team_access_sessions_v2`` by device id —
    it is not guaranteed identical between the rerun that displays this button
    and the very next rerun that processes its click.  If that gate is instead
    used to decide whether ``st.button(...)`` is even *called*, a click can be
    silently and permanently lost with no exception: Streamlit only honours a
    widget's click for the run in which that exact widget (by key) is
    constructed, and a conditional branch skipped ahead of it drops the click
    with nothing to show for it.  Authorization is instead re-checked, fresh,
    at the moment the already-fired click is handled below.

    ``show_title`` is False when the caller (the mission board card) has
    already rendered the mission's name; the Configured Route caller has no
    such card and still needs its own title here.

    ``show_instruction`` is False for a REJECTED resubmission: the rejection
    banner above this form already carries the facilitator's specific
    feedback, and repeating the same generic brief the Captain already saw
    (and already attempted) only adds clutter to the card's densest state.
    The safety note is never suppressed — it is not the redundant text this
    is guarding against, and it can matter on every attempt.
    """
    evidence = mission.get("Evidence", {}) or {}
    text_config = evidence.get("Text", {}) or {}
    photo_config = evidence.get("Photo", {}) or {}
    numeric_config = evidence.get("NumericResult", {}) or {}
    activity_id = mission["ActivityID"]
    submitting_key = f"theme_race_submitting_{activity_id}"
    if show_title:
        st.subheader(mission.get("DisplayName") or "Current mission")
    if show_instruction and mission.get("ParticipantInstruction"):
        st.write(mission["ParticipantInstruction"])
    if mission.get("SafetyNote"):
        st.warning(f"⚠️ {mission['SafetyNote']}")

    text = ""
    if text_config.get("Required"):
        text = st.text_area(text_config.get("Label") or "Team response", key=f"theme_race_text_{activity_id}")
    elif photo_config.get("Required") or numeric_config.get("Required"):
        text = st.text_area("Optional team note", key=f"theme_race_text_{activity_id}")

    uploaded_photo = None
    if photo_config.get("Required"):
        uploaded_photo = st.file_uploader(
            photo_config.get("Label") or "Private team photo", type=["jpg", "jpeg", "png"],
            key=f"theme_race_photo_{activity_id}",
        )
        if uploaded_photo is not None:
            st.image(uploaded_photo, width="stretch")

    numeric = ""
    if numeric_config.get("Required"):
        numeric = st.text_input(
            numeric_config.get("Label") or "Result", key=f"theme_race_numeric_{activity_id}",
        )

    already_submitting = bool(st.session_state.get(submitting_key))
    authorized = captain_active and not already_submitting
    is_resubmission = str(mission.get("MissionState", "")).upper() == "REJECTED"
    submit_label = "🔁 Update & Resubmit" if is_resubmission else "✅ Submit Evidence"
    if not captain_active:
        st.caption("Only the Mission Captain can submit for this team.")
    elif already_submitting:
        st.info("Submitting… please wait.")
    if st.button(
        submit_label, type="primary", width="stretch",
        key=f"theme_race_submit_{activity_id}", disabled=not authorized,
    ):
        _submit_trace(
            activity_id, CLICK_RECEIVED=True, MISSION_STATE=mission.get("MissionState", ""),
            STRATEGY_MODE=workspace.get("StrategyMode", ""),
            HAS_TEXT=bool(text.strip()), HAS_PHOTO=uploaded_photo is not None,
        )
        # The disabled state above should already prevent this, but a stale
        # rerun must never be able to fire a second RPC while one is in flight,
        # nor act on a click captured before authorization was re-confirmed.
        if not authorized:
            return
        if text_config.get("Required") and not text.strip():
            st.warning("Enter the required text evidence.")
            return
        if photo_config.get("Required") and uploaded_photo is None:
            st.warning("Upload the required private photo evidence.")
            return
        if numeric_config.get("Required"):
            try:
                number = float(numeric)
            except (TypeError, ValueError):
                st.warning("Enter a numeric result.")
                return
            minimum, maximum = numeric_config.get("Minimum"), numeric_config.get("Maximum")
            if minimum is not None and number < float(minimum):
                st.warning("Result is below the configured minimum.")
                return
            if maximum is not None and number > float(maximum):
                st.warning("Result is above the configured maximum.")
                return

        # session_state[submitting_key] is cleared in `finally` on every path —
        # success, a known RuntimeDatabaseError/ValueError, or anything
        # unexpected — so it can never survive as a stuck "pending" flag.
        st.session_state[submitting_key] = True
        try:
            with st.spinner("Submitting mission evidence…"):
                uploaded = {}
                if uploaded_photo is not None:
                    _submit_trace(activity_id, UPLOAD_STARTED=True)
                    try:
                        uploaded = upload_photo(
                            event_id=workspace["EventID"], mission_id=activity_id,
                            team_name=st.session_state.get("participant_team", workspace["TeamID"]),
                            participant_name=st.session_state.get("participant_name", ""),
                            uploaded_file=uploaded_photo,
                        )
                        _submit_trace(activity_id, UPLOAD_COMPLETED=True)
                    except (RuntimeDatabaseError, ValueError) as error:
                        _submit_trace(activity_id, UPLOAD_COMPLETED=False, ERROR_CLASS=type(error).__name__)
                        st.error(upload_error_message("Photo upload", saved=False, retry=True, error=error))
                        return
                    except Exception as error:
                        # Never let an unexpected upload failure look like a hang.
                        _submit_trace(activity_id, UPLOAD_COMPLETED=False, ERROR_CLASS=type(error).__name__)
                        st.error(f"Photo upload failed unexpectedly. You can try again: {error}")
                        return
                payload = {
                    "TeamName": st.session_state.get("participant_team", workspace["TeamID"]),
                    "ParticipantName": st.session_state.get("participant_name", ""),
                    "SubmissionType": "THEME_PARK_RACE",
                    "Remarks": text.strip(),
                    "Metric1": numeric.strip(),
                    "ImageURL": uploaded.get("url", ""),
                    "DriveFileID": uploaded.get("file_id", ""),
                    "SubmittedAtClient": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                }
                try:
                    _submit_trace(activity_id, RPC_STARTED=True)
                    db.runtime.save_theme_park_race_submission(
                        st.session_state.get("participant_session_token", ""), activity_id, payload,
                        strategy_mode=workspace.get("StrategyMode", ""),
                    )
                    _submit_trace(activity_id, RPC_COMPLETED=True)
                except RuntimeDatabaseError as error:
                    _submit_trace(activity_id, RPC_COMPLETED=False, ERROR_CLASS=type(error).__name__)
                    st.error(str(error))
                    return
                except Exception as error:
                    _submit_trace(activity_id, RPC_COMPLETED=False, ERROR_CLASS=type(error).__name__)
                    st.error(f"Submission failed unexpectedly. You can try again: {error}")
                    return
        finally:
            st.session_state[submitting_key] = False
        if str(workspace.get("StrategyMode", "")).upper() == "OPEN_MISSION_BOARD":
            st.success("📨 Submitted! Awaiting facilitator review.")
        else:
            st.success("Mission evidence submitted. The next route mission is now available unless this evidence is later rejected.")
        st.rerun()


def _upload_board_photo(workspace, mission_id, suffix, uploaded_photo):
    if uploaded_photo is None:
        return {}
    return upload_photo(
        event_id=workspace["EventID"], mission_id=f"{mission_id}-{suffix}",
        team_name=st.session_state.get("participant_team", workspace["TeamID"]),
        participant_name=st.session_state.get("participant_name", ""), uploaded_file=uploaded_photo,
    )


def _render_ride_evidence_form(db, workspace, mission, captain_active=True, show_title=True):
    """Ride proof UI. Server-side board RPC repeats all Captain/team checks.

    See ``_render_evidence_form`` for why the submit button is always
    constructed here regardless of ``captain_active``.
    """
    activity_id = mission["ActivityID"]
    submitting_key = f"theme_race_ride_submitting_{activity_id}"
    evidence = mission.get("Evidence", {}) or {}
    required = mission.get("RideRequiredParticipantCount", 0)
    members = {row.get("ParticipantID", ""): row.get("Name", row.get("ParticipantID", "")) for row in workspace.get("TeamMembers", [])}
    if show_title:
        st.subheader(mission.get("DisplayName") or "Ride mission")
    st.write(f"Required riders: {required} of {len(members)} current team members.")
    st.caption("An attraction exterior photo is not queue-entry proof. Follow attraction staff instructions and never capture evidence where park rules prohibit it.")
    pathway_options = mission.get("RideParticipation", {}).get("EvidencePathways") or []
    pathway = st.selectbox("Evidence pathway", pathway_options, key=f"theme_race_ride_path_{activity_id}")
    riders = st.multiselect(
        "Team members who entered the official queue", list(members),
        format_func=lambda key: members.get(key, key), key=f"theme_race_ride_riders_{activity_id}",
    )
    remaining = [member_id for member_id in members if member_id not in riders]
    ground_control = []
    if pathway == "GROUND_CONTROL":
        ground_control = st.multiselect(
            "Ground Control team members", remaining,
            format_func=lambda key: members.get(key, key), key=f"theme_race_ground_control_{activity_id}",
        )
    remarks = st.text_area(evidence.get("Text", {}).get("Label") or "Team note", key=f"theme_race_ride_text_{activity_id}")
    attempt = st.selectbox(
        "Ride attempt outcome", ["COMPLETED", "ABORTED_BY_ATTRACTION", "TEAM_WITHDREW", "ATTEMPTED"],
        key=f"theme_race_ride_attempt_{activity_id}",
    )
    queue_photo = post_photo = None
    facilitator_request = ""
    if attempt == "COMPLETED" and pathway in {"GROUND_CONTROL", "FULL_TEAM"}:
        queue_photo = st.file_uploader("Private official queue-entry evidence", type=["jpg", "jpeg", "png"], key=f"theme_race_queue_{activity_id}")
        post_photo = st.file_uploader("Private configured post-ride verification", type=["jpg", "jpeg", "png"], key=f"theme_race_postride_{activity_id}")
    elif attempt == "COMPLETED" and pathway == "FACILITATOR_VERIFIED":
        facilitator_request = st.text_input("Facilitator verification request", key=f"theme_race_ride_verify_{activity_id}")

    already_submitting = bool(st.session_state.get(submitting_key))
    authorized = captain_active and not already_submitting
    if not captain_active:
        st.caption("Only the Mission Captain can submit for this team.")
    elif already_submitting:
        st.info("Submitting… please wait.")
    if st.button(
        "Record Outcome" if attempt != "COMPLETED" else "✅ Submit Ride Evidence",
        type="primary", width="stretch", key=f"theme_race_ride_submit_{activity_id}",
        disabled=not authorized,
    ):
        _submit_trace(
            activity_id, CLICK_RECEIVED=True, MISSION_STATE=mission.get("MissionState", ""),
            STRATEGY_MODE=workspace.get("StrategyMode", ""),
            HAS_TEXT=bool(remarks.strip()),
            HAS_PHOTO=queue_photo is not None or post_photo is not None,
        )
        if not authorized:
            return
        if evidence.get("Text", {}).get("Required") and not remarks.strip():
            st.warning("Enter the required text evidence.")
            return
        if attempt == "COMPLETED" and len(riders) < int(required or 0):
            st.warning(f"At least {required} canonical team riders are required.")
            return
        if attempt == "COMPLETED" and pathway in {"GROUND_CONTROL", "FULL_TEAM"} and (queue_photo is None or post_photo is None):
            st.warning("Queue-entry and post-ride evidence are both required for this evidence pathway.")
            return

        st.session_state[submitting_key] = True
        try:
            with st.spinner("Submitting ride evidence…"):
                try:
                    _submit_trace(activity_id, UPLOAD_STARTED=queue_photo is not None or post_photo is not None)
                    queue = _upload_board_photo(workspace, activity_id, "QUEUE", queue_photo)
                    post = _upload_board_photo(workspace, activity_id, "POST", post_photo)
                    _submit_trace(activity_id, UPLOAD_COMPLETED=True)
                except (RuntimeDatabaseError, ValueError) as error:
                    _submit_trace(activity_id, UPLOAD_COMPLETED=False, ERROR_CLASS=type(error).__name__)
                    st.error(upload_error_message("Ride evidence upload", saved=False, retry=True, error=error))
                    return
                except Exception as error:
                    _submit_trace(activity_id, UPLOAD_COMPLETED=False, ERROR_CLASS=type(error).__name__)
                    st.error(f"Ride evidence upload failed unexpectedly. You can try again: {error}")
                    return
                payload = {
                    "TeamName": st.session_state.get("participant_team", workspace["TeamID"]),
                    "ParticipantName": st.session_state.get("participant_name", ""),
                    "SubmissionType": "THEME_PARK_RACE_RIDE",
                    "Remarks": remarks.strip(), "RideEvidencePathway": pathway,
                    "RideAttemptStatus": attempt, "RiderParticipantIDs": riders,
                    "GroundControlParticipantIDs": ground_control,
                    "QueueEntryEvidence": queue.get("url", ""), "PostRideEvidence": post.get("url", ""),
                    "FacilitatorVerificationRequest": facilitator_request.strip(),
                }
                try:
                    _submit_trace(activity_id, RPC_STARTED=True)
                    if attempt == "COMPLETED":
                        db.runtime.save_theme_park_race_submission(
                            st.session_state.get("participant_session_token", ""), activity_id, payload,
                            strategy_mode=workspace.get("StrategyMode", ""),
                        )
                    else:
                        db.runtime.record_theme_park_race_ride_outcome(
                            st.session_state.get("participant_session_token", ""), activity_id, attempt, payload,
                        )
                    _submit_trace(activity_id, RPC_COMPLETED=True)
                except RuntimeDatabaseError as error:
                    _submit_trace(activity_id, RPC_COMPLETED=False, ERROR_CLASS=type(error).__name__)
                    st.error(str(error))
                    return
                except Exception as error:
                    _submit_trace(activity_id, RPC_COMPLETED=False, ERROR_CLASS=type(error).__name__)
                    st.error(f"Submission failed unexpectedly. You can try again: {error}")
                    return
        finally:
            st.session_state[submitting_key] = False
        st.success("📨 Ride outcome recorded.")
        st.rerun()


_MISSION_CLASS_LABEL = {
    "STANDARD": "🎯 STANDARD MISSION",
    "RIDE": "🎢 RIDE MISSION",
    "BONUS": "⭐ BONUS MISSION",
    "SECRET": "🔓 SECRET MISSION",
}


def _render_mission_card(db, workspace, mission, captain_active):
    """One scannable mission card: title, type, state badge, points, action.

    A Secret Mission is never locked by the time it reaches this board (the
    engine excludes a still-locked Secret Mission from MissionBoard entirely),
    so any Secret Mission rendered here has just been released — it always
    gets the reveal banner, never facilitator/UAT release mechanics.
    """
    activity_id = mission.get("ActivityID", "")
    state = str(mission.get("MissionState", "LOCKED")).upper()
    mission_class = str(mission.get("MissionClass", "STANDARD")).upper()
    with st.container(border=True):
        if mission_class == "SECRET":
            st.markdown('<div class="tp-secret-banner">🔓 Secret Mission Unlocked</div>', unsafe_allow_html=True)
        st.caption(_MISSION_CLASS_LABEL.get(mission_class, "🎯 MISSION"))
        st.markdown(f"#### {mission.get('DisplayName') or 'Mission'}")

        badge_html = _state_badge_html(state)
        try:
            points = int((mission.get("Scoring", {}) or {}).get("Maximum") or 0)
        except (TypeError, ValueError):
            points = 0
        if points > 0:
            badge_html += f' <span class="tp-points">🏅 UP TO {points} PTS</span>'
        st.markdown(badge_html, unsafe_allow_html=True)

        meta = " · ".join(
            part for part in (
                str(mission.get("Zone", "") or "").strip(),
                str(mission.get("LocationDescription", "") or "").strip(),
            ) if part
        )
        if meta:
            st.markdown(f'<div class="tp-card-meta">{html.escape(meta)}</div>', unsafe_allow_html=True)

        if state == "AVAILABLE":
            st.write(mission.get("ParticipantInstruction", ""))
            if mission.get("SafetyNote"):
                st.warning(f"⚠️ {mission['SafetyNote']}")
            # Always constructed regardless of captain_active: it is
            # re-derived from a live session join on every independent
            # rerun and is not guaranteed identical between the render
            # that shows this button and the one that processes its
            # click.  Gating construction on it can silently drop a click
            # with no error — see _render_evidence_form for the full case.
            if st.button(
                "🎯 Select Mission", type="primary", width="stretch",
                key=f"theme_race_board_select_{activity_id}", disabled=not captain_active,
            ):
                if not captain_active:
                    st.caption("Only the Mission Captain can select a mission.")
                    return
                try:
                    db.runtime.select_theme_park_race_mission(st.session_state.get("participant_session_token", ""), activity_id)
                except RuntimeDatabaseError as error:
                    st.error(str(error))
                    return
                st.rerun()
        elif state in {"SELECTED", "REJECTED"}:
            if state == "REJECTED":
                # The same evidence form below is otherwise identical to a
                # never-submitted SELECTED mission; without this banner a
                # Captain cannot tell "returned for resubmission" from
                # "not yet attempted".  Fixed banner text only — the
                # facilitator's own reason is written via native st.write,
                # never interpolated into this HTML.
                st.markdown(
                    '<div class="tp-rejected-banner">'
                    '<div class="tp-rejected-title">⚠️ Resubmission Required</div>'
                    '<div>Your submission was reviewed and returned.</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                reason = str(mission.get("RejectionReason", "") or "").strip()
                if reason:
                    st.markdown("**Facilitator feedback:**")
                    st.write(reason)
            if mission_class == "RIDE":
                _render_ride_evidence_form(db, workspace, mission, captain_active, show_title=False)
            else:
                _render_evidence_form(
                    db, workspace, mission, captain_active,
                    show_title=False, show_instruction=state != "REJECTED",
                )
        elif state == "TEMPORARILY_UNAVAILABLE":
            st.write("This mission is paused for now. Choose another available mission — no penalty.")
        elif state == "CLOSED":
            st.write("This mission is closed.")
        elif state == "SUBMITTED":
            st.write("EXOS has received your submission.")
        elif state == "APPROVED":
            st.write("Nicely done — this mission is locked in.")


def _render_open_mission_board(db, workspace, captain_active):
    """Render only this team's canonical available/selected board state."""
    board = workspace.get("MissionBoard", [])
    if not board:
        st.info("No mission is currently available.")
        return
    st.markdown("### 🗺️ Mission Board")
    for mission in board:
        _render_mission_card(db, workspace, mission, captain_active)


def render_theme_park_race_participant(db, enrollment_credential="", device_id=""):
    """Participant/Captain surface driven solely by the canonical workspace."""
    _inject_mission_theme()
    session_token = st.session_state.get("participant_session_token", "")
    try:
        workspace = _workspace(db, session_token)
    except RuntimeDatabaseError as error:
        # A failed workspace read otherwise removes the whole surface, including
        # Captain selection, with no way back short of a full page reload.
        st.warning("Mission AI is reconnecting.")
        st.caption(str(error))
        if st.button("Retry", width="stretch", key="theme_race_workspace_retry"):
            st.rerun()
        return
    lifecycle = workspace.get("Lifecycle", "REGISTRATION")
    strategy_mode = str(workspace.get("StrategyMode", "CONFIGURED_TEAM_ROUTE")).upper()

    # An ended Mission is terminal on every reconnect.  Do this before Captain
    # authority rendering so an old browser cannot expose recovery, selection,
    # or evidence controls after the canonical End control has completed.
    if lifecycle == "ENDED":
        _render_ended_participant_screen(workspace)
        return

    if lifecycle in {"ACTIVE", "HELD"}:
        # The persistent dashboard replaces the generic lifecycle banner once
        # there is a team and a mission board worth glancing at; earlier
        # lifecycle states (registration, Captain selection, ...) have no
        # progress yet, so they keep the plain title/message form below.
        _render_mission_header(workspace)
    else:
        title, message = _LIFECYCLE_COPY.get(lifecycle, ("Mission AI", "Waiting for your facilitator."))
        team_identity = str(workspace.get("TeamIdentity", "") or "").strip()
        st.subheader(title)
        if team_identity:
            st.caption(f"Team {team_identity}")
        st.info(message)

    if strategy_mode != "OPEN_MISSION_BOARD":
        st.caption(f"Team route progress: {workspace.get('Progress', {}).get('Completed', 0)} / {workspace.get('Progress', {}).get('Total', 0)}")
        route_rows = _route_rows(workspace)
        if route_rows:
            st.dataframe(route_rows, hide_index=True, width="stretch")

    if lifecycle == "HELD":
        _render_paused_banner()

    captain_active = _render_captain_authority(db, workspace, enrollment_credential, device_id)
    if lifecycle != "ACTIVE":
        return
    if strategy_mode == "OPEN_MISSION_BOARD":
        _render_open_mission_board(db, workspace, captain_active)
        return
    mission = workspace.get("CurrentMission")
    if not mission:
        st.success("🎉 Your team has completed every mission on this route.")
        return
    if not captain_active:
        st.caption("Mission details are visible to the whole team. Only the Mission Captain can submit.")
        st.subheader(mission.get("DisplayName") or "Current mission")
        st.write(mission.get("ParticipantInstruction", ""))
        return
    _render_evidence_form(db, workspace, mission)


def render_theme_park_race_facilitator(db, control, event_id):
    """Facilitator lifecycle, Captain, review, progress, scoring and controls."""
    try:
        workspace = db.runtime.theme_park_race_facilitator_workspace(event_id)
    except RuntimeDatabaseError as error:
        st.error(str(error))
        return
    st.subheader("Theme Park Race Control")
    metrics = st.columns(6)
    metrics[0].metric("Lifecycle", workspace.get("Lifecycle", "—"))
    metrics[1].metric("Registered", workspace.get("RegistrationCount", 0))
    metrics[2].metric("Teams", workspace.get("TeamCount", 0))
    metrics[3].metric("Captains", f"{workspace.get('CaptainCount', 0)}/{workspace.get('TeamCount', 0)}")
    metrics[4].metric("Missions", workspace.get("MissionCount", 0))
    metrics[5].metric("Pending reviews", workspace.get("PendingReviewCount", 0))

    actor = st.text_input("Facilitator identity", key=f"theme_race_actor_{event_id}")
    phase = str(workspace.get("TeamFormationPhase", "")).upper()
    runtime_phase = str(workspace.get("RuntimePhase", "READY")).upper()
    lifecycle = str(workspace.get("Lifecycle", "")).upper()
    lifecycle_col, mission_col = st.columns(2)
    with lifecycle_col:
        if lifecycle == "ENDED":
            st.caption(f"Team Formation status: {phase or '—'}")
        elif phase == "DRAFT":
            if st.button("Open registration", type="primary", disabled=not actor, key=f"theme_race_open_{event_id}"):
                control.open_team_formation(event_id, actor); st.rerun()
        elif phase == "REGISTRATION_OPEN":
            if st.button("Lock team formation", type="primary", disabled=not actor, key=f"theme_race_lock_{event_id}"):
                control.lock_team_formation(event_id, actor); st.rerun()
        elif phase == "FORMATION_LOCKED":
            if st.button("Open Captain selection", type="primary", disabled=not actor, key=f"theme_race_captains_{event_id}"):
                control.open_team_captain_selection(event_id, actor); st.rerun()
        elif phase == "CAPTAIN_SELECTION":
            if st.button("Activate teams", type="primary", disabled=not actor, key=f"theme_race_activate_teams_{event_id}"):
                control.activate_team_formation(event_id, actor); st.rerun()
        else:
            st.success("Team Formation is active.")
    with mission_col:
        if lifecycle == "ENDED" or runtime_phase == "CLOSED":
            st.error("MISSION ENDED")
            st.info("Submissions are closed. Final results are preserved.")
        elif phase != "ACTIVE":
            st.caption("Mission start unlocks after every team has an effective Captain.")
        elif runtime_phase == "READY":
            if st.button("Start Mission", type="primary", disabled=not actor, key=f"theme_race_start_{event_id}"):
                control.set_theme_park_race_runtime_phase(event_id, "ACTIVE", actor); st.rerun()
        elif runtime_phase == "HELD":
            resume, close = st.columns(2)
            if resume.button("Resume Mission", type="primary", disabled=not actor, key=f"theme_race_resume_{event_id}"):
                control.set_theme_park_race_runtime_phase(event_id, "ACTIVE", actor); st.rerun()
            if close.button("End Mission", disabled=not actor, key=f"theme_race_end_{event_id}"):
                control.set_theme_park_race_runtime_phase(event_id, "CLOSED", actor); st.rerun()
        elif runtime_phase == "ACTIVE":
            pause, close = st.columns(2)
            if pause.button("Hold Mission", disabled=not actor, key=f"theme_race_hold_{event_id}"):
                control.set_theme_park_race_runtime_phase(event_id, "HELD", actor); st.rerun()
            if close.button("End Mission", disabled=not actor, key=f"theme_race_end_{event_id}"):
                control.set_theme_park_race_runtime_phase(event_id, "CLOSED", actor); st.rerun()
        else:
            st.warning("Mission runtime state is unavailable.")

    if lifecycle != "ENDED" and str(workspace.get("StrategyMode", "")).upper() == "OPEN_MISSION_BOARD":
        with st.expander("Mission Board control", expanded=True):
            operations = {row.get("ActivityID", ""): row for row in workspace.get("MissionOperations", [])}
            if operations:
                activity_id = st.selectbox(
                    "Mission", list(operations),
                    format_func=lambda key: f"{operations[key].get('DisplayName', key)} · {operations[key].get('MissionClass', 'STANDARD')}",
                    key=f"theme_race_board_operation_mission_{event_id}",
                )
                operation = operations[activity_id]
                operational_status = st.selectbox(
                    "Operational status", ["AVAILABLE", "TEMPORARILY_UNAVAILABLE", "CLOSED"],
                    index=["AVAILABLE", "TEMPORARILY_UNAVAILABLE", "CLOSED"].index(str(operation.get("OperationalStatus", "AVAILABLE")).upper()),
                    key=f"theme_race_board_status_{event_id}",
                )
                secret_state = "RELEASED"
                if str(operation.get("MissionClass", "")).upper() == "SECRET":
                    secret_state = st.selectbox(
                        "Secret mission state", ["LOCKED", "RELEASED"],
                        index=["LOCKED", "RELEASED"].index(str(operation.get("SecretState", "LOCKED")).upper()),
                        key=f"theme_race_board_secret_{event_id}",
                    )
                if st.button("Apply mission board control", disabled=not actor, key=f"theme_race_board_apply_{event_id}"):
                    control.set_theme_park_race_mission_operation(event_id, activity_id, operational_status, secret_state, actor)
                    st.rerun()

    st.markdown("#### Team progress and Captain status")
    rows = [{
        "Team": row.get("TeamIdentity", row.get("TeamID")),
        "Registered": row.get("RegisteredParticipants", 0),
        "Captain": row.get("CaptainName") or "Not selected",
        "Progress": f"{row.get('Completed', 0)}/{row.get('Total', 0)}",
        "Current mission": row.get("CurrentActivityID") or "Complete",
        "Selected missions": ", ".join(row.get("SelectedMissionActivityIDs", [])) or "—",
        "Pending review": row.get("PendingReview", 0),
        "Rejected": row.get("Rejected", 0),
    } for row in workspace.get("Teams", [])]
    st.dataframe(rows, hide_index=True, width="stretch")

    if lifecycle != "ENDED" and phase in {"CAPTAIN_SELECTION", "ACTIVE"}:
        with st.expander("Facilitator Captain transfer"):
            teams = {row.get("TeamID", ""): row for row in workspace.get("Teams", [])}
            if teams:
                team_id = st.selectbox("Team", list(teams), format_func=lambda key: teams[key].get("TeamIdentity", key), key=f"theme_race_transfer_team_{event_id}")
                members = [row for row in db.runtime.get_theme_park_race_players(event_id) if row.get("TeamID") == team_id]
                choices = {row.get("ParticipantID", ""): row for row in members}
                if choices:
                    participant_id = st.selectbox("New Captain", list(choices), format_func=lambda key: choices[key].get("Name", key), key=f"theme_race_transfer_participant_{event_id}")
                    reason = st.text_input("Transfer reason", key=f"theme_race_transfer_reason_{event_id}")
                    if st.button("Transfer Captain", disabled=not actor or not reason.strip(), key=f"theme_race_transfer_{event_id}"):
                        control.transfer_team_formation_captain(event_id, team_id, participant_id, actor, reason)
                        st.success("Captain transfer recorded. The new Captain must recover Captain authority on their device.")
                        st.rerun()

    st.markdown("#### Submission review")
    _render_review_notice(event_id)
    strategy_mode = str(workspace.get("StrategyMode", "")).upper()
    queue = workspace.get("ReviewQueue", [])
    if not queue:
        st.caption("No submissions are awaiting review.")
    # Canonical display names, so a pending review identifies its team and
    # mission instead of raw team/activity identifiers.
    team_names = {
        str(row.get("TeamID", "")): str(row.get("TeamIdentity") or row.get("TeamID", ""))
        for row in workspace.get("Teams", [])
    }
    mission_names = {
        str(row.get("ActivityID", "")): str(row.get("DisplayName") or row.get("ActivityID", ""))
        for row in workspace.get("MissionOperations", [])
    }
    for submission in queue:
        submission_id = submission.get("SubmissionID", "")
        team_id = str(submission.get("TeamID", ""))
        activity_id = str(submission.get("ActivityID", ""))
        team_label = team_names.get(team_id) or str(submission.get("TeamName") or team_id or "Team")
        mission_label = mission_names.get(activity_id) or activity_id or "Mission"
        # A pending review is the facilitator's work: never hide it behind a
        # collapsed panel they have to discover.
        with st.expander(f"{team_label} · {mission_label} · SUBMITTED", expanded=True):
            st.caption(f"Team {team_label} · Mission {mission_label}")
            if submission.get("Remarks"):
                st.markdown("**Text evidence**")
                st.write(submission["Remarks"])
            photo = get_photo_url(submission.get("ImageURL", ""), submission.get("DriveFileID", ""))
            if photo:
                st.image(photo, width="stretch")
            if submission.get("RideAttemptStatus"):
                st.caption(
                    f"Ride pathway: {submission.get('RideEvidencePathway') or '—'} · "
                    f"Attempt: {submission.get('RideAttemptStatus')} · "
                    f"Canonical riders declared: {len(submission.get('RiderParticipantIDs', []))} / "
                    f"{submission.get('RequiredRideParticipants') or '—'} required from "
                    f"{submission.get('CanonicalTeamMemberCount') or '—'} members"
                )
                if submission.get("GroundControlParticipantIDs"):
                    st.caption(f"Ground Control declared: {len(submission.get('GroundControlParticipantIDs', []))}")
                queue_photo = get_photo_url(submission.get("QueueEntryEvidence", ""), "")
                if queue_photo:
                    st.image(queue_photo, caption="Private queue-entry evidence", width="stretch")
                post_ride_photo = get_photo_url(submission.get("PostRideEvidence", ""), "")
                if post_ride_photo:
                    st.image(post_ride_photo, caption="Private post-ride verification", width="stretch")
                if submission.get("FacilitatorVerificationRequest"):
                    st.write(submission["FacilitatorVerificationRequest"])
            score = st.number_input(
                "Score (applied on approve only)",
                value=float(submission.get("Score") or 0),
                key=f"theme_race_score_{submission_id}",
            )
            notes = st.text_input("Facilitator reason / notes", key=f"theme_race_notes_{submission_id}")
            if strategy_mode == OPEN_MISSION_BOARD:
                st.caption(f"Reviewing revision submitted at {submission.get('SubmittedAt') or 'unknown'}.")
            # Both decisions are dead without a facilitator identity, so say so
            # here rather than leaving a silently greyed pair of buttons.
            if not actor:
                st.warning("Enter your facilitator identity above to approve or reject.")
            st.divider()

            approve, reject = st.columns(2)
            with approve:
                st.caption("Approve and award the score above.")
                if st.button(
                    "✅ Approve", type="primary", width="stretch",
                    disabled=not actor, key=f"theme_race_approve_{submission_id}",
                ):
                    _queue_review_notice(event_id, submit_theme_park_race_review(
                        control, strategy_mode, submission,
                        decision="APPROVE", score=score, actor=actor, notes=notes,
                    ))
                    st.rerun()
            with reject:
                st.caption("Reject and reopen the mission. Scores 0. A reason is required.")
                # Requiring the reason keeps Reject deliberate and guarantees the
                # 039 contract receives one; it can never approve or carry a score.
                if st.button(
                    "❌ Reject — request resubmission", width="stretch",
                    disabled=not actor or not notes.strip(),
                    key=f"theme_race_reject_{submission_id}",
                ):
                    _queue_review_notice(event_id, submit_theme_park_race_review(
                        control, strategy_mode, submission,
                        decision="REJECT", score=0, actor=actor, notes=notes,
                    ))
                    st.rerun()


def render_theme_park_race_projector(db, event_id):
    """Display-only live projection; no lifecycle, review or score mutations."""
    workspace = db.runtime.theme_park_race_facilitator_workspace(event_id)
    event = db.get_event(event_id) or {}
    projection = projector_projection(workspace, db.runtime.get_theme_park_race_configuration(event_id))
    ended = str(projection.get("Lifecycle", "")).upper() == "ENDED"
    projector_title = "MISSION ENDED" if ended else "LIVE MISSION"
    st.markdown(
        f"<div class='projector-header'><div class='projector-kicker'>THEME PARK RACE</div><div class='projector-event-title'>{projector_title}</div></div>",
        unsafe_allow_html=True,
    )
    st.caption(f"{event.get('EventName', '')} · {projection.get('Lifecycle', '')} · {projection.get('PendingReviewCount', 0)} pending review")
    if ended:
        st.info("Mission ended. Final team progress and scoring are preserved.")
    open_board = str(projection.get("StrategyMode", "")).upper() == "OPEN_MISSION_BOARD"
    st.dataframe([(
        {
            "Team": row.get("TeamIdentity", row.get("TeamID")),
            "Approved missions": f"{row.get('Completed', 0)}/{row.get('Total', 0)}",
            "Pending review": row.get("PendingReview", 0),
            "Captain": "Ready" if row.get("CaptainSelected") else "Selecting",
        } if open_board else {
            "Team": row.get("TeamIdentity", row.get("TeamID")),
            "Mission progress": f"{row.get('Completed', 0)}/{row.get('Total', 0)}",
            "Current mission": row.get("CurrentActivityID") or "Complete",
            "Pending review": row.get("PendingReview", 0),
            "Captain": "Ready" if row.get("CaptainSelected") else "Selecting",
        }
    ) for row in projection.get("Teams", [])], hide_index=True, width="stretch")
    if open_board:
        aggregate = projection.get("MissionAggregate", [])
        if aggregate:
            st.markdown("### Mission board status")
            st.dataframe([{
                "Mission": row.get("DisplayName", row.get("ActivityID", "")),
                "Class": row.get("MissionClass", "STANDARD"),
                "Operational status": row.get("OperationalStatus", "AVAILABLE"),
            } for row in aggregate], hide_index=True, width="stretch")
        for mission in projection.get("ReleasedSecretMissionAnnouncements", []):
            st.info(f"Secret mission released: {mission}")
    if projection.get("ShowOverallScoring"):
        leaderboard = projection.get("Leaderboard", [])
        if leaderboard:
            st.markdown("### Overall scoring")
            st.dataframe([{
                "Rank": position,
                "Team": row.get("TeamName", row.get("TeamID", "Team")),
                "Score": row.get("Score", 0),
            } for position, row in enumerate(leaderboard, 1)], hide_index=True, width="stretch")
