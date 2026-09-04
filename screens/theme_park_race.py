"""Shared participant, facilitator and projector surfaces for Theme Park Race.

All state is rebuilt from the Core-v2 adapter on render.  This module does not
own a participant, team, event, submission, Captain or scoring store.
"""
from __future__ import annotations

import html
import os
from datetime import datetime

import streamlit as st

from branding import COMPANY_NAME, PLATFORM_EXPANSION, PLATFORM_NAME
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


# Fixed, code-authored badge/icon content only — never interpolate
# participant or facilitator free text (mission titles, instructions,
# rejection reasons) into these.  A dynamic value with an embedded newline
# defeated Markdown's indentation handling once already (the raw team card
# incident); the fix there was to keep free text out of unsafe_allow_html
# entirely, which this module follows throughout.  Label text is unchanged
# from Sprint 1 — the visual system underneath is new, but a Captain who read
# "AWAITING REVIEW" once still reads exactly that.
_STATE_BADGES = {
    "AVAILABLE": ("tp-badge-available", "🟡", "AVAILABLE"),
    "SELECTED": ("tp-badge-progress", "🔵", "IN PROGRESS"),
    "SUBMITTED": ("tp-badge-submitted", "📨", "AWAITING REVIEW"),
    "APPROVED": ("tp-badge-approved", "✅", "COMPLETED"),
    "REJECTED": ("tp-badge-rejected", "⚠️", "RESUBMISSION REQUIRED"),
    "CLOSED": ("tp-badge-locked", "🔒", "CLOSED"),
    "TEMPORARILY_UNAVAILABLE": ("tp-badge-paused", "⏸", "PAUSED"),
}

# One recognisable identity per mission class: icon, label and an accent hue
# distinct from every other class and from every state colour, so a class is
# legible even for someone who cannot rely on colour alone.
_CLASS_STYLE = {
    "STANDARD": ("🎯", "STANDARD", "#2DD4BF"),
    "RIDE": ("🎢", "RIDE", "#FF8A3D"),
    "BONUS": ("⚡", "BONUS", "#FFC94D"),
    "SECRET": ("🔒", "SECRET", "#A78BFA"),
}


def _state_badge_html(state: str) -> str:
    css_class, icon, label = _STATE_BADGES.get(str(state or "").upper(), ("tp-badge-locked", "•", "UNAVAILABLE"))
    return f'<span class="tp-badge {css_class}">{icon} {label}</span>'


def _class_style(mission_class: str) -> tuple[str, str, str]:
    return _CLASS_STYLE.get(str(mission_class or "").upper(), _CLASS_STYLE["STANDARD"])


def _inject_mission_theme() -> None:
    """One-time, fully static CSS for the Theme Park Mission Captain surface.

    Every rule here is fixed and code-authored; nothing dynamic is ever
    interpolated into this block.

    Sprint 1 kept the default white Streamlit page and dropped one navy card
    onto it — reviewed as "just one box, boring".  This instead re-themes the
    whole page: a dark mission-control canvas, Streamlit's own chrome (header,
    toolbar, default light inputs) restyled to belong to it, and mission tiles
    built from real ``st.container(key=...)`` blocks rather than plain
    ``st.expander``/``border=True`` boxes.  Buttons, uploaders and text areas
    are still genuine Streamlit widgets underneath — only their presentation
    changes, exactly like Formula R.A.C.E.'s own separate dark theme
    (``_race_css`` in the legacy Captain shell) already does for its page;
    this module still injects nothing there and that surface injects nothing
    here.

    ``st.container(key="...")`` renders as ``st-key-{key}`` on a real DOM
    node, so a fixed, code-authored key naming scheme (never built from
    participant/facilitator text) lets plain CSS substring selectors
    (``[class*="..."]``) style every tile, and every tile of one mission
    class or lifecycle state, without knowing IDs in advance.
    """
    st.markdown(
        """
        <style>
        :root {
          --tp-bg-0:#050b14; --tp-bg-1:#0a1626; --tp-bg-2:#101f33; --tp-bg-3:#16283e;
          --tp-gold:#D9B24C; --tp-gold-deep:#B59A37;
          --tp-teal:#2DD4BF; --tp-blue:#4FA3E8; --tp-green:#3ED598;
          --tp-red:#FF5C5C; --tp-amber:#E8A23D; --tp-ink:#EAF0F8; --tp-mist:#8CA0BE;
        }
        .stApp {
          background:
            radial-gradient(circle at 15% -5%, rgba(45,212,191,.10), transparent 42%),
            radial-gradient(circle at 100% 5%, rgba(217,178,76,.12), transparent 48%),
            linear-gradient(180deg, var(--tp-bg-0) 0%, var(--tp-bg-1) 60%, var(--tp-bg-0) 100%) !important;
        }
        .stApp, .stApp p, .stApp li, .stApp label, [data-testid="stMarkdownContainer"] { color:var(--tp-ink) !important; }
        [data-testid="stCaptionContainer"] { color:var(--tp-mist) !important; }
        [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"] { display:none !important; }
        [data-testid="stMainBlockContainer"] { padding:.6rem .8rem 3rem !important; max-width:520px; }
        div[data-testid="stAlert"] { background:rgba(255,255,255,.05) !important; border:1px solid rgba(255,255,255,.14) !important; border-radius:12px !important; }
        div[data-testid="stAlert"] p { color:var(--tp-ink) !important; }
        [data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input, [data-testid="stNumberInputField"] {
          background:var(--tp-bg-2) !important; color:var(--tp-ink) !important; border:1px solid rgba(255,255,255,.16) !important; border-radius:10px !important;
        }
        [data-testid="stSelectbox"] [data-baseweb="select"] > div, [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
          background:var(--tp-bg-2) !important; border-color:rgba(255,255,255,.16) !important; color:var(--tp-ink) !important;
        }
        [data-testid="stFileUploaderDropzone"] { background:var(--tp-bg-2) !important; border:1.5px dashed var(--tp-teal) !important; border-radius:12px !important; }
        [data-testid="stFileUploaderDropzoneInstructions"] span, [data-testid="stFileUploaderDropzoneInstructions"] small { color:var(--tp-mist) !important; }
        [data-testid="stWidgetLabel"] p { color:var(--tp-ink) !important; font-weight:700 !important; }
        [data-testid="stProgress"] > div > div { background:rgba(255,255,255,.14) !important; }
        [data-testid="stProgress"] > div > div > div { background:var(--tp-gold) !important; }

        /* ---- Mission AI wordmark + Captain HUD -------------------------- */
        .mh-kicker { font:800 .7rem/1 Inter,system-ui,sans-serif; letter-spacing:.24em; text-transform:uppercase; color:var(--tp-teal); margin-bottom:.3rem; }
        .mh-team { font:800 2.7rem/.95 'Barlow Condensed',Impact,sans-serif; letter-spacing:.01em; text-transform:uppercase; color:#fff; overflow-wrap:anywhere; margin:.1rem 0 .7rem; text-shadow:0 8px 28px rgba(45,212,191,.18); }
        .mh-stats { display:flex; align-items:baseline; gap:.6rem; }
        .mh-count { font:800 3.1rem/1 'Barlow Condensed',Impact,sans-serif; color:var(--tp-gold); }
        .mh-count-label { font:800 .78rem Inter,sans-serif; letter-spacing:.08em; text-transform:uppercase; color:var(--tp-mist); }
        .mh-segments { display:flex; gap:.28rem; margin:.7rem 0 .5rem; }
        .mh-segment { flex:1; height:9px; border-radius:999px; background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.1); }
        .mh-segment.filled { background:linear-gradient(90deg,var(--tp-gold-deep),var(--tp-gold)); border-color:var(--tp-gold); }
        .mh-remaining { display:inline-block; padding:.32rem .8rem; border-radius:999px; background:rgba(45,212,191,.14); border:1px solid rgba(45,212,191,.5); color:var(--tp-teal); font:800 .78rem Inter,sans-serif; letter-spacing:.05em; }
        .mh-remaining.done { background:rgba(62,213,152,.16); border-color:var(--tp-green); color:var(--tp-green); }

        /* ---- Restrained platform brand marks (EXOS / eEssence) ----------
           One quiet line under the wordmark kicker, an order of magnitude
           smaller than .mh-team — the team stays the loudest thing on the
           page. Never repeated per-tile; see the sign-off block and footer
           below for the only other two places brand identity appears. */
        .mh-brand-line { display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; margin:-.05rem 0 .55rem; }
        .mh-brand-powered { font:800 .56rem Inter,system-ui,sans-serif; letter-spacing:.12em; text-transform:uppercase; color:var(--tp-mist); opacity:.7; }
        .mh-brand-exos { color:var(--tp-gold); font-weight:800; }
        .mh-brand-by { font:600 .56rem Inter,system-ui,sans-serif; letter-spacing:.04em; color:var(--tp-mist); opacity:.5; font-style:italic; }
        .mh-alert-kicker { font:800 .62rem Inter,system-ui,sans-serif; letter-spacing:.16em; text-transform:uppercase; color:rgba(255,255,255,.68); margin-bottom:.2rem; }

        /* ---- Status badges (fixed enum content only) -------------------- */
        .tp-badge { display:inline-flex; align-items:center; gap:.32rem; padding:.34rem .7rem; border-radius:999px; font:800 .72rem Inter,system-ui,sans-serif; letter-spacing:.03em; text-transform:uppercase; border:1.5px solid transparent; white-space:nowrap; }
        .tp-badge-available { background:rgba(217,178,76,.16); color:var(--tp-gold); border-color:var(--tp-gold); }
        .tp-badge-progress  { background:rgba(45,212,191,.14); color:var(--tp-teal); border-color:var(--tp-teal); }
        .tp-badge-submitted { background:rgba(140,160,190,.14); color:var(--tp-mist); border-color:rgba(140,160,190,.5); }
        .tp-badge-approved  { background:rgba(62,213,152,.14); color:var(--tp-green); border-color:var(--tp-green); }
        .tp-badge-rejected  { background:rgba(255,92,92,.16); color:#FF8A8A; border-color:var(--tp-red); }
        .tp-badge-locked    { background:rgba(140,160,190,.1); color:var(--tp-mist); border-color:rgba(140,160,190,.35); }
        .tp-badge-paused    { background:rgba(232,162,61,.16); color:var(--tp-amber); border-color:var(--tp-amber); }
        .tp-points { display:inline-flex; align-items:center; gap:.25rem; padding:.2rem .55rem; border-radius:999px; background:rgba(217,178,76,.12); color:var(--tp-gold); font:800 .68rem Inter,sans-serif; letter-spacing:.03em; }

        /* ---- Mission tiles: real st.container(key="tile-...") blocks ----
           The accent strip and class label colour are set via small
           inline-styled elements the tile itself renders (colour comes only
           from the fixed _CLASS_STYLE lookup, keyed by the closed
           MissionClass enum — never participant/facilitator text), not via
           a CSS custom property on the container, which Python cannot set
           directly on an st.container(key=...) wrapper.  The strip sits in
           normal flow with negative margins bleeding to the padded edges,
           not position:absolute — an absolutely positioned full-height bar
           here once overlapped the title on any tile tall enough to need
           one (a RIDE tile's evidence form), since its height tracked the
           tile's total content rather than a single line. */
        div[class*="st-key-tile-"] { background:linear-gradient(165deg,var(--tp-bg-3) 0%,var(--tp-bg-2) 100%); border:1px solid rgba(255,255,255,.1); border-radius:16px; padding:1.05rem 1.05rem .9rem; margin-bottom:.75rem; overflow:hidden; }
        div[class*="-tilestate-available-"] { box-shadow:0 0 0 1px rgba(217,178,76,.5), 0 10px 28px rgba(217,178,76,.12); }
        div[class*="-tilestate-rejected-"] { box-shadow:0 0 0 1px rgba(255,92,92,.55), 0 10px 28px rgba(255,92,92,.14); }
        div[class*="-tilestate-selected-"] { box-shadow:0 0 0 1px rgba(45,212,191,.4); }
        div[class*="-tilestate-submitted-"], div[class*="-tilestate-approved-"] { opacity:.82; }
        .mh-tile-accent-bar { height:4px; border-radius:4px; margin:-1.05rem -1.05rem .8rem; }
        .mh-tile-class { display:flex; align-items:center; gap:.4rem; font:800 .68rem Inter,sans-serif; letter-spacing:.1em; text-transform:uppercase; margin-bottom:.25rem; }
        .mh-tile-class-icon { font-size:1.05rem; }
        .mh-tile-title { font:800 1.3rem/1.18 'Barlow Condensed',Impact,sans-serif; letter-spacing:.01em; color:#fff; margin:.05rem 0 .5rem; overflow-wrap:anywhere; }
        .mh-tile-meta { color:var(--tp-mist); font:700 .68rem Inter,sans-serif; letter-spacing:.04em; text-transform:uppercase; margin:.4rem 0 .1rem; }
        div[class*="st-key-board-disabled"] { opacity:.55; filter:grayscale(.25); }
        .mh-secret-banner { background:linear-gradient(120deg,rgba(167,139,250,.32),rgba(8,20,38,.92)); border:1px solid var(--tp-purple,#A78BFA); border-radius:12px; padding:.7rem 1rem; margin-bottom:.6rem; color:#fff; }
        .mh-secret-banner-title { font:800 .84rem Inter,sans-serif; letter-spacing:.03em; text-transform:uppercase; }
        .mh-rejected-banner { background:rgba(255,92,92,.14); border:1.5px solid var(--tp-red); border-radius:12px; padding:.8rem 1rem; margin:.5rem 0; color:#FFD6D6; }
        .mh-rejected-title { font:800 .95rem Inter,system-ui,sans-serif; letter-spacing:.04em; text-transform:uppercase; margin-bottom:.15rem; color:#fff; }

        /* ---- Paused / Ended full-width banners --------------------------- */
        .mh-paused-banner { background:linear-gradient(120deg,rgba(232,162,61,.22),rgba(8,20,38,.94)); border:1px solid var(--tp-amber); border-radius:16px; padding:1.6rem 1.1rem; margin:.5rem 0 .8rem; color:#fff; text-align:center; }
        .mh-paused-title { font:800 1.6rem/1.15 'Barlow Condensed',Impact,sans-serif; letter-spacing:.02em; text-transform:uppercase; margin-bottom:.4rem; }
        .mh-complete-banner { background:linear-gradient(120deg,rgba(62,213,152,.24),rgba(8,20,38,.94)); border:1px solid var(--tp-green); border-radius:16px; padding:1.6rem 1.1rem; margin:.5rem 0 .8rem; color:#fff; text-align:center; }
        .mh-complete-title { font:800 1.7rem/1.15 'Barlow Condensed',Impact,sans-serif; letter-spacing:.02em; text-transform:uppercase; margin-bottom:.2rem; }

        /* ---- Brand sign-off (ENDED, screenshot-worthy) and persistent
           footer. Two distinct, restrained blocks — never both on the same
           screen, so eEssence/EXOS is never repeated back-to-back. */
        .mh-sign-off { margin-top:1.3rem; padding-top:1.1rem; border-top:1px solid rgba(255,255,255,.18); }
        .mh-sign-off-name { font:800 .78rem Inter,system-ui,sans-serif; letter-spacing:.22em; text-transform:uppercase; opacity:.9; }
        .mh-sign-off-line { font:600 .7rem Inter,system-ui,sans-serif; letter-spacing:.04em; opacity:.75; margin-top:.2rem; }
        .mh-sign-off-line strong { font-weight:800; }
        .mh-footer { text-align:center; margin:2.2rem 0 .4rem; padding-top:1rem; border-top:1px solid rgba(255,255,255,.08); }
        .mh-footer-line { font:600 .6rem Inter,system-ui,sans-serif; letter-spacing:.08em; color:var(--tp-mist); opacity:.5; }
        .mh-footer-line strong { opacity:.85; letter-spacing:.12em; }

        /* ---- Buttons / uploader, Theme Park's own colour ----------------- */
        div.stButton>button, div[data-testid="stFormSubmitButton"]>button { min-height:48px; border-radius:10px; font-weight:800; letter-spacing:.01em; }
        div.stButton>button[kind="primary"] { background:var(--tp-gold-deep); border-color:var(--tp-gold-deep); color:#0a1626; }
        div.stButton>button[kind="primary"]:hover { background:var(--tp-gold); border-color:var(--tp-gold); color:#0a1626; }
        div.stButton>button[kind="primary"]:disabled { background:rgba(140,160,190,.25); border-color:rgba(140,160,190,.25); color:var(--tp-mist); opacity:1; }
        div.stButton>button[kind="secondary"] { background:var(--tp-bg-2); border-color:rgba(255,255,255,.18); color:var(--tp-ink); }
        /* The file uploader's own "Browse files" control is a different
           internal Streamlit component (stBaseButton, not st.button), so
           the div.stButton rule above never reaches it. */
        [data-testid="stBaseButton-secondary"] { background:var(--tp-bg-3) !important; border-color:rgba(255,255,255,.22) !important; color:var(--tp-ink) !important; }

        @media (max-width:600px) {
          .mh-team { font-size:2.15rem; }
          .mh-count { font-size:2.5rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


_MAX_PROGRESS_SEGMENTS = 12


def _segmented_progress_html(completed: int, total: int) -> str:
    """A per-mission segment strip, not a plain bar — the Captain can count
    completed vs. remaining missions at a glance instead of reading numbers.
    Every value here is an int derived from canonical Progress counts, never
    participant/facilitator text, so building this HTML carries no escaping
    risk.  Beyond ``_MAX_PROGRESS_SEGMENTS`` missions the per-mission strip
    stops being scannable, so it falls back to one proportional segment.
    """
    if total <= 0:
        return ""
    if total > _MAX_PROGRESS_SEGMENTS:
        fraction = min(completed / total, 1.0)
        return f'<div class="mh-segments"><div class="mh-segment filled" style="flex:{fraction:.4f} 0 0"></div><div class="mh-segment" style="flex:{1 - fraction:.4f} 0 0"></div></div>'
    segments = "".join(
        f'<div class="mh-segment{" filled" if position < completed else ""}"></div>'
        for position in range(total)
    )
    return f'<div class="mh-segments">{segments}</div>'


def _render_mission_header(workspace) -> None:
    """The mission HUD: identity, progress and what's left, at a glance.

    Team identity is the loudest element on the page; Captain status is
    rendered separately (by ``_render_captain_authority``) as secondary
    information underneath, never competing with it.  Unlike Sprint 1's
    boxed navy card, this sits directly on the page's own dark canvas —
    a HUD overlay, not a floating panel — so the first viewport reads as one
    continuous mission surface rather than "a box on a white page".
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
    done = remaining == 0 and total > 0
    remaining_label = "ALL MISSIONS DONE" if done else f"{remaining} MISSION{'S' if remaining != 1 else ''} REMAINING"
    st.markdown(
        '<div class="mh-kicker">MISSION AI</div>'
        '<div class="mh-brand-line">'
        f'<span class="mh-brand-powered">POWERED BY <span class="mh-brand-exos">{html.escape(PLATFORM_NAME)}™</span></span>'
        f'<span class="mh-brand-by">by {html.escape(COMPANY_NAME)}</span>'
        '</div>'
        f'<div class="mh-team">{safe_team}</div>'
        '<div class="mh-stats">'
        f'<span class="mh-count">{completed}/{total}</span>'
        '<span class="mh-count-label">MISSIONS<br/>COMPLETE</span>'
        '</div>'
        f'{_segmented_progress_html(completed, total)}'
        f'<span class="mh-remaining{" done" if done else ""}">{remaining_label}</span>',
        unsafe_allow_html=True,
    )


def _render_brand_footer() -> None:
    """A subtle, persistent platform signature — one line, always the same,
    never a banner. The ENDED screen gets its own dedicated sign-off instead
    of this (see ``_render_ended_participant_screen``), so EXOS/eEssence is
    never repeated twice on the same screen."""
    st.markdown(
        '<div class="mh-footer">'
        f'<div class="mh-footer-line"><strong>{html.escape(PLATFORM_NAME)}™</strong></div>'
        f'<div class="mh-footer-line">{html.escape(PLATFORM_EXPANSION)}</div>'
        f'<div class="mh-footer-line">An {html.escape(COMPANY_NAME)} Experience</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_paused_banner() -> None:
    st.markdown(
        '<div class="mh-paused-banner">'
        '<div class="mh-paused-title">⏸ Mission AI Paused</div>'
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


def _render_ended_participant_screen(workspace) -> None:
    """Render the terminal, celebratory state from canonical progress, no writes.

    Built as a screenshot-worthy sign-off: a participant who captures this
    screen naturally carries Mission AI, EXOS and eEssence branding with it.
    Team identity and the completion count still come from this same call —
    a second ``_render_mission_header`` call would duplicate both.
    """
    team = str(workspace.get("TeamIdentity") or workspace.get("TeamID") or "Your Team").strip()
    safe_team = html.escape(team)
    progress = workspace.get("Progress", {}) or {}
    completed = int(progress.get("Completed", 0) or 0)
    total = int(progress.get("Total", 0) or 0)
    st.markdown(
        '<div class="mh-complete-banner">'
        '<div class="mh-complete-title">🎉 Mission Complete</div>'
        '<div class="mh-kicker" style="margin-top:.9rem;">TEAM</div>'
        f'<div class="mh-team">{safe_team}</div>'
        f'<div class="mh-count">{completed}/{total}</div>'
        '<div class="mh-count-label">MISSIONS COMPLETED</div>'
        '<div style="margin-top:1.1rem;">Thank you for participating.</div>'
        '<div style="opacity:.82;margin-top:.15rem;">Please wait for your facilitator to announce the winning team.</div>'
        '<div class="mh-sign-off">'
        '<div class="mh-sign-off-name">MISSION AI</div>'
        f'<div class="mh-sign-off-line">Powered by <strong>{html.escape(PLATFORM_NAME)}™</strong></div>'
        f'<div class="mh-sign-off-line">An {html.escape(COMPANY_NAME)} Experience</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


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
        st.error(_participant_runtime_error(error))
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
                    st.error(_participant_runtime_error(error))
                    return
                except Exception as error:
                    _submit_trace(activity_id, RPC_COMPLETED=False, ERROR_CLASS=type(error).__name__)
                    st.error(f"Submission failed unexpectedly. You can try again: {error}")
                    return
        finally:
            st.session_state[submitting_key] = False
        if str(workspace.get("StrategyMode", "")).upper() == "OPEN_MISSION_BOARD":
            st.success(f"📨 Evidence received. Sent to {PLATFORM_NAME} — awaiting facilitator review.")
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


# Display-only labels for two closed enums the ride form exposes to the
# Captain. The selectbox's underlying returned value is still the exact
# canonical enum string passed everywhere below (payloads, comparisons) —
# only the on-screen text changes, via st.selectbox(format_func=...).
_RIDE_PATHWAY_LABELS = {
    "GROUND_CONTROL": "Ground Control (some ride, some support)",
    "FULL_TEAM": "Full Team (everyone rides)",
    "FACILITATOR_VERIFIED": "Facilitator Verified",
}
_RIDE_ATTEMPT_LABELS = {
    "COMPLETED": "Completed",
    "ABORTED_BY_ATTRACTION": "Aborted by Attraction",
    "TEAM_WITHDREW": "Team Withdrew",
    "ATTEMPTED": "Attempted",
}


def _participant_runtime_error(error: Exception) -> str:
    """Translate expected server rejections without weakening their authority."""
    text = str(error or "").casefold()
    if "maximum concurrent mission selections" in text:
        return "Your team already has the maximum number of active missions. Submit or complete one before choosing another."
    if "mission is not available" in text or "mission is unavailable" in text or "secret mission is locked" in text:
        return "This mission is unavailable right now. Choose another mission or check with your facilitator."
    if "captain" in text or "participant session is invalid" in text:
        if "claim is not open" in text:
            return "Mission Captain selection is not open for this event yet."
        return "Only your Mission Captain on their active device can do this. Ask them to restore Mission Captain access if needed."
    if "evidence" in text or "numeric result" in text or "ride completion requires" in text:
        return "Your evidence is incomplete or does not match this mission. Check the mission card and try again."
    if "not active" in text:
        return "The mission is not active yet. Please wait for your facilitator."
    return f"Mission AI could not complete that action. Please try again or check with your facilitator. ({error})"


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
    pathway = st.selectbox(
        "Evidence pathway", pathway_options,
        format_func=lambda value: _RIDE_PATHWAY_LABELS.get(value, value),
        key=f"theme_race_ride_path_{activity_id}",
    )
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
        format_func=lambda value: _RIDE_ATTEMPT_LABELS.get(value, value),
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
                    st.error(_participant_runtime_error(error))
                    return
                except Exception as error:
                    _submit_trace(activity_id, RPC_COMPLETED=False, ERROR_CLASS=type(error).__name__)
                    st.error(f"Submission failed unexpectedly. You can try again: {error}")
                    return
        finally:
            st.session_state[submitting_key] = False
        st.success("📨 Ride outcome recorded.")
        st.rerun()


# Lower-case, hyphen-safe tokens only — used solely to build a
# st.container(key=...) string, never rendered as text.
_STATE_TOKENS = {
    "AVAILABLE": "available", "SELECTED": "selected", "SUBMITTED": "submitted",
    "APPROVED": "approved", "REJECTED": "rejected", "CLOSED": "locked",
    "TEMPORARILY_UNAVAILABLE": "paused",
}


def _render_mission_card(db, workspace, mission, captain_active, interactive=True):
    """One mission tile: class identity, title, state badge, points, action.

    A Secret Mission is never locked by the time it reaches this board (the
    engine excludes a still-locked Secret Mission entirely).  The Maxis UAT
    config releases its Secret cards from the start, so the participant sees a
    visible surprise card rather than waiting for a facilitator release.

    ``interactive=False`` is the HELD/paused presentation: the tile still
    shows what it is and its current state, but renders no button and no
    evidence form at all, so a paused Mission can never reach the select or
    submit RPCs regardless of Captain authority — a stricter guarantee than
    gating on ``captain_active`` alone.
    """
    activity_id = mission.get("ActivityID", "")
    state = str(mission.get("MissionState", "LOCKED")).upper()
    mission_class = str(mission.get("MissionClass", "STANDARD")).upper()
    icon, class_label, accent = _class_style(mission_class)
    state_token = _STATE_TOKENS.get(state, "locked")
    class_token = mission_class.lower() if mission_class in _CLASS_STYLE else "standard"
    tile_key = f"tile-tileclass-{class_token}-tilestate-{state_token}-{activity_id}"

    with st.container(key=tile_key, border=False):
        if mission_class == "SECRET":
            st.markdown(
                '<div class="mh-secret-banner">'
                f'<div class="mh-alert-kicker">🛰️ {html.escape(PLATFORM_NAME)} Alert</div>'
                '<div class="mh-secret-banner-title">🕵️ Secret Mission Unlocked · Live Now</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        st.markdown(
            f'<div class="mh-tile-accent-bar" style="background:{accent}"></div>'
            f'<div class="mh-tile-class" style="color:{accent}"><span class="mh-tile-class-icon">{icon}</span>{class_label}</div>'
            f'<div class="mh-tile-title">{html.escape(str(mission.get("DisplayName") or "Mission"))}</div>',
            unsafe_allow_html=True,
        )

        badge_html = _state_badge_html(state)
        try:
            points = int((mission.get("Scoring", {}) or {}).get("Maximum") or 0)
        except (TypeError, ValueError):
            points = 0
        if points > 0:
            badge_html += f' <span class="tp-points">⚡ UP TO {points} PTS</span>'
        st.markdown(badge_html, unsafe_allow_html=True)

        meta = " · ".join(
            part for part in (
                str(mission.get("Zone", "") or "").strip(),
                str(mission.get("LocationDescription", "") or "").strip(),
            ) if part
        )
        if meta:
            st.markdown(f'<div class="mh-tile-meta">{html.escape(meta)}</div>', unsafe_allow_html=True)

        if not interactive:
            st.caption("Paused — resumes when your facilitator restarts the mission.")
            return

        if state == "AVAILABLE":
            # Instructions reveal only once the mission is selected/in
            # progress — an available tile stays scannable, not a brief.
            if mission.get("SafetyNote"):
                st.warning(f"⚠️ {mission['SafetyNote']}")
            # Always constructed regardless of captain_active: it is
            # re-derived from a live session join on every independent
            # rerun and is not guaranteed identical between the render
            # that shows this button and the one that processes its
            # click.  Gating construction on it can silently drop a click
            # with no error — see _render_evidence_form for the full case.
            if st.button(
                "🎯 Accept Mission", type="primary", width="stretch",
                key=f"theme_race_board_select_{activity_id}", disabled=not captain_active,
            ):
                if not captain_active:
                    st.caption("Only the Mission Captain can accept a mission.")
                    return
                try:
                    db.runtime.select_theme_park_race_mission(st.session_state.get("participant_session_token", ""), activity_id)
                except RuntimeDatabaseError as error:
                    st.error(_participant_runtime_error(error))
                    return
                # A toast, not a permanent banner: it survives the rerun below
                # (Streamlit queues it for the next script run) and fades on
                # its own, so this one EXOS mention never becomes clutter.
                st.toast(f"Mission accepted — {PLATFORM_NAME} has activated your next challenge.", icon="🛰️")
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
                    '<div class="mh-rejected-banner">'
                    '<div class="mh-rejected-title">⚠️ Resubmission Required</div>'
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
                # SELECTED reveals the brief for the first time (text
                # reduction: an AVAILABLE tile never showed it).  REJECTED
                # suppresses it again — the rejection banner above already
                # carries the facilitator's specific feedback, and repeating
                # the same generic brief the Captain already attempted once
                # only adds clutter to the card's densest state.
                _render_evidence_form(
                    db, workspace, mission, captain_active,
                    show_title=False, show_instruction=state != "REJECTED",
                )
        elif state == "TEMPORARILY_UNAVAILABLE":
            st.caption("Paused for now — choose another mission. No penalty.")
        elif state == "CLOSED":
            st.caption("Closed.")
        elif state == "SUBMITTED":
            st.caption("Sent to EXOS. Awaiting facilitator review.")
        elif state == "APPROVED":
            st.caption("Mission locked in.")


def _render_open_mission_board(db, workspace, captain_active, interactive=True):
    """Render only this team's canonical available/selected board state."""
    board = workspace.get("MissionBoard", [])
    if not board:
        st.info("No mission is currently available.")
        return
    st.markdown('<div class="mh-kicker" style="margin-top:.4rem;">MISSION BOARD</div>', unsafe_allow_html=True)
    if interactive:
        for mission in board:
            _render_mission_card(db, workspace, mission, captain_active, interactive=True)
    else:
        with st.container(key="board-disabled", border=False):
            for mission in board:
                _render_mission_card(db, workspace, mission, captain_active, interactive=False)


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

    if lifecycle == "HELD":
        # The board recedes (dimmed, no buttons or forms at all) rather than
        # vanishing — the Captain can still see what's in progress while
        # paused, but interactive=False means no click here can ever reach
        # select/submit, regardless of Captain authority.
        if strategy_mode == "OPEN_MISSION_BOARD":
            _render_open_mission_board(db, workspace, captain_active, interactive=False)
        _render_brand_footer()
        return

    if lifecycle != "ACTIVE":
        return
    if strategy_mode == "OPEN_MISSION_BOARD":
        _render_open_mission_board(db, workspace, captain_active)
        _render_brand_footer()
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
    _render_brand_footer()


_AVAILABILITY_LABELS = {
    "AVAILABLE": "Available",
    "TEMPORARILY_UNAVAILABLE": "Temporarily Unavailable",
    "CLOSED": "Closed",
}
_SECRET_STATE_LABELS = {"LOCKED": "Locked", "RELEASED": "Released"}


def _human_timestamp(value) -> str:
    """Best-effort human rendering of a canonical ISO-8601 timestamp.

    Presentation only -- the raw value is still shown verbatim as a secondary
    diagnostic caption everywhere the existing code already surfaced it (the
    OPEN_MISSION_BOARD stale-revision context), so nothing canonical is lost.
    """
    text = str(value or "").strip()
    if not text:
        return "Just now"
    try:
        cleaned = text[:-1] + "+00:00" if text.endswith("Z") else text
        return datetime.fromisoformat(cleaned).strftime("%b %d, %I:%M %p").replace(" 0", " ")
    except ValueError:
        return text


def _facilitator_status(lifecycle: str, runtime_phase: str) -> tuple[str, str, str]:
    """Presentation label for the exact canonical fields the control
    branching below already switches on -- never a new lifecycle source."""
    if lifecycle == "ENDED" or runtime_phase == "CLOSED":
        return ("ended", "■", "ENDED")
    if runtime_phase == "HELD":
        return ("paused", "⏸", "PAUSED")
    if runtime_phase == "ACTIVE":
        return ("live", "●", "LIVE")
    if runtime_phase == "READY":
        return ("ready", "◇", "READY")
    return ("unknown", "?", "UNAVAILABLE")


def _inject_facilitator_theme() -> None:
    """Static CSS for the Facilitator Mission Control surface.

    Same dark, gold-accented Mission AI visual language as the participant
    HUD (``_inject_mission_theme``), but built for laptop/tablet operator
    scanning rather than a narrow mobile card feed -- a wider canvas, denser
    layout. Its own class namespace (``mc-*``) and its own injector: the two
    surfaces never render on the same page, and keeping them independent
    means a future change to one can never silently reach the other.
    """
    st.markdown(
        """
        <style>
        :root {
          --mc-bg-0:#050b14; --mc-bg-1:#0a1626; --mc-bg-2:#101f33; --mc-bg-3:#16283e;
          --mc-gold:#D9B24C; --mc-gold-deep:#B59A37;
          --mc-teal:#2DD4BF; --mc-blue:#4FA3E8; --mc-green:#3ED598;
          --mc-red:#FF5C5C; --mc-amber:#E8A23D; --mc-ink:#EAF0F8; --mc-mist:#8CA0BE;
        }
        .stApp {
          background:
            radial-gradient(circle at 10% -10%, rgba(45,212,191,.08), transparent 42%),
            radial-gradient(circle at 100% 0%, rgba(217,178,76,.10), transparent 48%),
            linear-gradient(180deg, var(--mc-bg-0) 0%, var(--mc-bg-1) 55%, var(--mc-bg-0) 100%) !important;
        }
        .stApp, .stApp p, .stApp li, .stApp label, [data-testid="stMarkdownContainer"] { color:var(--mc-ink) !important; }
        [data-testid="stCaptionContainer"] { color:var(--mc-mist) !important; }
        [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"] { display:none !important; }
        [data-testid="stMainBlockContainer"] { padding:.8rem 1.2rem 3rem !important; max-width:900px; }
        div[data-testid="stAlert"] { background:rgba(255,255,255,.05) !important; border:1px solid rgba(255,255,255,.14) !important; border-radius:12px !important; }
        div[data-testid="stAlert"] p { color:var(--mc-ink) !important; }
        [data-testid="stTextInput"] input, [data-testid="stNumberInputField"] {
          background:var(--mc-bg-2) !important; color:var(--mc-ink) !important; border:1px solid rgba(255,255,255,.16) !important; border-radius:10px !important;
        }
        [data-testid="stSelectbox"] [data-baseweb="select"] > div {
          background:var(--mc-bg-2) !important; border-color:rgba(255,255,255,.16) !important; color:var(--mc-ink) !important;
        }
        [data-testid="stWidgetLabel"] p { color:var(--mc-ink) !important; font-weight:700 !important; }
        [data-testid="stMetric"] { background:var(--mc-bg-2); border:1px solid rgba(255,255,255,.1); border-radius:12px; padding:.6rem .8rem; }
        [data-testid="stMetric"] label p, [data-testid="stMetricLabel"] p { color:var(--mc-mist) !important; font-size:.68rem !important; letter-spacing:.06em; text-transform:uppercase; }
        [data-testid="stMetricValue"] { color:var(--mc-ink) !important; }
        [data-testid="stExpander"] { background:var(--mc-bg-2) !important; border:1px solid rgba(255,255,255,.12) !important; border-radius:14px !important; }
        /* Streamlit's own generated class sets an explicit light
           background-color on an OPEN summary header (its expanded-state
           highlight) -- overriding only `color` left that light background
           in place, making the header unreadable. background-color must be
           forced here too, not just inherited from the expander wrapper. */
        [data-testid="stExpander"] summary { background-color:var(--mc-bg-2) !important; color:var(--mc-ink) !important; font-weight:700; }
        [data-testid="stExpander"] summary:hover { background-color:var(--mc-bg-3) !important; }
        [data-testid="stExpander"] summary p { color:var(--mc-ink) !important; }
        div.stButton>button, div[data-testid="stFormSubmitButton"]>button { min-height:46px; border-radius:10px; font-weight:800; }
        div.stButton>button[kind="primary"] { background:var(--mc-gold-deep); border-color:var(--mc-gold-deep); color:#0a1626; }
        div.stButton>button[kind="primary"]:hover { background:var(--mc-gold); border-color:var(--mc-gold); color:#0a1626; }
        div.stButton>button[kind="primary"]:disabled { background:rgba(140,160,190,.25); border-color:rgba(140,160,190,.25); color:var(--mc-mist); opacity:1; }
        div.stButton>button[kind="secondary"] { background:var(--mc-bg-2); border-color:rgba(255,255,255,.2); color:var(--mc-ink); }
        div[class*="st-key-mc-danger-"] button { background:rgba(255,92,92,.14) !important; border:1.5px solid var(--mc-red) !important; color:#FFD6D6 !important; }
        div[class*="st-key-mc-danger-"] button:hover { background:rgba(255,92,92,.26) !important; }
        div[class*="st-key-mc-danger-"] button:disabled { background:rgba(140,160,190,.15) !important; border-color:rgba(140,160,190,.3) !important; color:var(--mc-mist) !important; }

        .mc-kicker { font:800 .7rem/1 Inter,system-ui,sans-serif; letter-spacing:.24em; text-transform:uppercase; color:var(--mc-teal); margin-bottom:.2rem; }
        .mc-title { font:800 1.9rem/1.05 'Barlow Condensed',Impact,sans-serif; letter-spacing:.01em; text-transform:uppercase; color:#fff; margin:0 0 .35rem; }
        .mc-brand-line { display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; }
        .mc-brand-powered { font:800 .56rem Inter,system-ui,sans-serif; letter-spacing:.12em; text-transform:uppercase; color:var(--mc-mist); opacity:.7; }
        .mc-brand-exos { color:var(--mc-gold); font-weight:800; }
        .mc-brand-by { font:600 .56rem Inter,system-ui,sans-serif; color:var(--mc-mist); opacity:.5; font-style:italic; }

        .mc-identity-kicker { font:800 .6rem Inter,sans-serif; letter-spacing:.16em; text-transform:uppercase; color:var(--mc-mist); opacity:.75; margin-bottom:.15rem; text-align:right; }
        .mc-identity-confirmed { font:700 .74rem Inter,sans-serif; color:var(--mc-green); text-align:right; margin-top:.2rem; }

        .mc-status-card { border-radius:16px; padding:1rem 1.2rem; margin:.6rem 0 1rem; border:1px solid rgba(255,255,255,.12); }
        .mc-status-label { font:800 .66rem Inter,sans-serif; letter-spacing:.18em; text-transform:uppercase; opacity:.7; margin-bottom:.25rem; }
        .mc-status-value { font:800 1.9rem/1 'Barlow Condensed',Impact,sans-serif; letter-spacing:.02em; }
        .mc-status-ready { background:linear-gradient(120deg,rgba(79,163,232,.2),rgba(8,20,38,.92)); border-color:var(--mc-blue); }
        .mc-status-ready .mc-status-value { color:var(--mc-blue); }
        .mc-status-live { background:linear-gradient(120deg,rgba(62,213,152,.22),rgba(8,20,38,.92)); border-color:var(--mc-green); }
        .mc-status-live .mc-status-value { color:var(--mc-green); }
        .mc-status-paused { background:linear-gradient(120deg,rgba(232,162,61,.24),rgba(8,20,38,.92)); border-color:var(--mc-amber); }
        .mc-status-paused .mc-status-value { color:var(--mc-amber); }
        .mc-status-ended { background:linear-gradient(120deg,rgba(255,92,92,.2),rgba(8,20,38,.92)); border-color:var(--mc-red); }
        .mc-status-ended .mc-status-value { color:#FF8A8A; }
        .mc-status-unknown { background:rgba(140,160,190,.1); border-color:rgba(140,160,190,.35); }
        .mc-status-unknown .mc-status-value { color:var(--mc-mist); }

        .mc-workload-card { border-radius:14px; padding:.85rem 1.1rem; margin:.3rem 0 1rem; border:1px solid rgba(255,255,255,.1); }
        .mc-workload-clear { background:rgba(62,213,152,.06); color:var(--mc-mist); }
        .mc-workload-alert { background:rgba(217,178,76,.14); border:1.5px solid var(--mc-gold); }
        .mc-workload-line { font:800 .92rem Inter,sans-serif; letter-spacing:.02em; }
        .mc-workload-alert .mc-workload-line { color:var(--mc-gold); }

        .mc-section-title { font:800 .78rem Inter,sans-serif; letter-spacing:.14em; text-transform:uppercase; color:var(--mc-teal); margin:1.6rem 0 .6rem; }

        .mc-team-card { background:linear-gradient(165deg,var(--mc-bg-3) 0%,var(--mc-bg-2) 100%); border:1px solid rgba(255,255,255,.1); border-left:4px solid rgba(255,255,255,.15); border-radius:12px; padding:.85rem 1rem; margin-bottom:.65rem; }
        .mc-team-card-alert { border-left-color:var(--mc-amber); box-shadow:0 0 0 1px rgba(232,162,61,.35); }
        .mc-team-name { font:800 1.15rem/1.1 'Barlow Condensed',Impact,sans-serif; letter-spacing:.01em; text-transform:uppercase; color:#fff; }
        .mc-team-meta { font:600 .72rem Inter,sans-serif; color:var(--mc-mist); margin:.15rem 0 .55rem; }
        .mc-team-progress-row { display:flex; align-items:center; gap:.6rem; }
        .mc-team-progress-bar { flex:1; height:8px; border-radius:999px; background:rgba(255,255,255,.12); overflow:hidden; }
        .mc-team-progress-fill { height:100%; background:linear-gradient(90deg,var(--mc-gold-deep),var(--mc-gold)); }
        .mc-team-progress-count { font:800 .74rem Inter,sans-serif; letter-spacing:.03em; color:var(--mc-ink); white-space:nowrap; }
        .mc-team-status-line { font:800 .68rem Inter,sans-serif; letter-spacing:.05em; text-transform:uppercase; margin-top:.4rem; }
        .mc-team-status-pending { color:var(--mc-gold); }
        .mc-team-status-rejected { color:#FF8A8A; }

        .mc-review-kicker { font:800 .68rem Inter,sans-serif; letter-spacing:.16em; text-transform:uppercase; color:var(--mc-amber); margin-bottom:.3rem; }
        .mc-review-team { font:800 1.3rem/1.15 'Barlow Condensed',Impact,sans-serif; text-transform:uppercase; color:#fff; margin-bottom:.3rem; }
        .mc-review-row { font:700 .78rem Inter,sans-serif; color:var(--mc-mist); margin:.1rem 0; }
        .mc-review-row strong { color:var(--mc-ink); font-weight:800; }

        .mc-mission-summary-row { display:flex; justify-content:space-between; gap:.6rem; font:700 .78rem Inter,sans-serif; padding:.35rem 0; border-bottom:1px solid rgba(255,255,255,.08); }
        .mc-mission-summary-label { color:var(--mc-mist); letter-spacing:.06em; text-transform:uppercase; font-size:.68rem; }
        .mc-mission-summary-value { color:var(--mc-ink); font-weight:800; text-align:right; }

        .mc-alert-banner { background:linear-gradient(120deg,rgba(167,139,250,.28),rgba(8,20,38,.92)); border:1px solid #A78BFA; border-radius:12px; padding:.75rem 1rem; margin:.7rem 0; color:#fff; }
        .mc-alert-kicker { font:800 .62rem Inter,sans-serif; letter-spacing:.16em; text-transform:uppercase; color:rgba(255,255,255,.68); margin-bottom:.15rem; }
        .mc-alert-title { font:800 .92rem Inter,sans-serif; letter-spacing:.03em; text-transform:uppercase; }

        @media (max-width:640px) {
          [data-testid="stMainBlockContainer"] { padding:.6rem .7rem 2.5rem !important; }
          .mc-title { font-size:1.5rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_facilitator_team_card(row) -> None:
    """One team's scan-in-two-seconds status: identity, progress, workload.

    Deliberately omits the current/selected mission activity ids the old
    dataframe row exposed -- they are internal identifiers, not something a
    facilitator scanning for action needs, and dropping them is itself part
    of the wording cleanup (no raw ids where a human summary already covers
    it: progress count, pending review, resubmission required)."""
    team = html.escape(str(row.get("TeamIdentity", row.get("TeamID", "Team"))))
    captain = html.escape(str(row.get("CaptainName") or "Not selected"))
    registered = int(row.get("RegisteredParticipants", 0) or 0)
    completed = int(row.get("Completed", 0) or 0)
    total = int(row.get("Total", 0) or 0)
    fraction = min(completed / total, 1.0) if total else 0.0
    pending = int(row.get("PendingReview", 0) or 0)
    rejected = int(row.get("Rejected", 0) or 0)
    status_lines = ""
    if pending:
        status_lines += f'<div class="mc-team-status-line mc-team-status-pending">{pending} AWAITING REVIEW</div>'
    if rejected:
        status_lines += f'<div class="mc-team-status-line mc-team-status-rejected">RESUBMISSION REQUIRED · {rejected}</div>'
    st.markdown(
        f'<div class="mc-team-card{" mc-team-card-alert" if (pending or rejected) else ""}">'
        f'<div class="mc-team-name">{team}</div>'
        f'<div class="mc-team-meta">Captain: {captain} · {registered} registered</div>'
        '<div class="mc-team-progress-row">'
        f'<div class="mc-team-progress-bar"><div class="mc-team-progress-fill" style="width:{fraction * 100:.0f}%"></div></div>'
        f'<div class="mc-team-progress-count">{completed}/{total} COMPLETE</div>'
        '</div>'
        f'{status_lines}'
        '</div>',
        unsafe_allow_html=True,
    )


def render_theme_park_race_facilitator(db, control, event_id):
    """Facilitator lifecycle, Captain, review, progress, scoring and controls."""
    try:
        workspace = db.runtime.theme_park_race_facilitator_workspace(event_id)
    except RuntimeDatabaseError as error:
        st.error(str(error))
        return
    _inject_facilitator_theme()

    phase = str(workspace.get("TeamFormationPhase", "")).upper()
    runtime_phase = str(workspace.get("RuntimePhase", "READY")).upper()
    lifecycle = str(workspace.get("Lifecycle", "")).upper()
    strategy_mode = str(workspace.get("StrategyMode", "")).upper()

    header_col, identity_col = st.columns([3, 2])
    with header_col:
        st.markdown(
            '<div class="mc-kicker">MISSION AI</div>'
            '<div class="mc-title">Mission Control</div>'
            '<div class="mc-brand-line">'
            f'<span class="mc-brand-powered">POWERED BY <span class="mc-brand-exos">{html.escape(PLATFORM_NAME)}™</span></span>'
            f'<span class="mc-brand-by">by {html.escape(COMPANY_NAME)}</span>'
            '</div>',
            unsafe_allow_html=True,
        )
    with identity_col:
        st.markdown('<div class="mc-identity-kicker">Facilitator</div>', unsafe_allow_html=True)
        # Label text unchanged ("Facilitator identity") -- only its visual
        # weight is reduced (collapsed label + a small kicker in its place).
        # The audited actor requirement itself is untouched: same widget,
        # same key, same value used in every control call below.
        actor = st.text_input(
            "Facilitator identity", key=f"theme_race_actor_{event_id}",
            label_visibility="collapsed", placeholder="Enter your name",
        )
        if actor.strip():
            st.markdown(f'<div class="mc-identity-confirmed">✓ {html.escape(actor.strip())}</div>', unsafe_allow_html=True)

    status_token, status_icon, status_label = _facilitator_status(lifecycle, runtime_phase)
    st.markdown(
        f'<div class="mc-status-card mc-status-{status_token}">'
        '<div class="mc-status-label">Mission Status</div>'
        f'<div class="mc-status-value">{status_icon} {status_label}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    metrics = st.columns(4)
    metrics[0].metric("Registered", workspace.get("RegistrationCount", 0))
    metrics[1].metric("Teams", workspace.get("TeamCount", 0))
    metrics[2].metric("Captains", f"{workspace.get('CaptainCount', 0)}/{workspace.get('TeamCount', 0)}")
    metrics[3].metric("Missions", workspace.get("MissionCount", 0))

    # The facilitator's actual workload, not a seventh equal metric box --
    # this is the one number that should pull the eye when it is non-zero.
    pending_total = int(workspace.get("PendingReviewCount", 0) or 0)
    rejected_total = sum(int(row.get("Rejected", 0) or 0) for row in workspace.get("Teams", []))
    if pending_total or rejected_total:
        lines = []
        if pending_total:
            lines.append(f'<div class="mc-workload-line">⚠ {pending_total} PENDING REVIEW{"S" if pending_total != 1 else ""}</div>')
        if rejected_total:
            lines.append(f'<div class="mc-workload-line">↻ {rejected_total} RESUBMISSION{"S" if rejected_total != 1 else ""} REQUIRED</div>')
        st.markdown(f'<div class="mc-workload-card mc-workload-alert">{"".join(lines)}</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="mc-workload-card mc-workload-clear"><div class="mc-workload-line">✓ No reviews pending</div></div>',
            unsafe_allow_html=True,
        )

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
            st.caption("Submissions are closed. Final results are preserved.")
        elif phase != "ACTIVE":
            st.caption("Mission start unlocks after every team has an effective Captain.")
        elif runtime_phase == "READY":
            if st.button("▶ Start Mission", type="primary", width="stretch", disabled=not actor, key=f"theme_race_start_{event_id}"):
                control.set_theme_park_race_runtime_phase(event_id, "ACTIVE", actor); st.rerun()
        elif runtime_phase == "HELD":
            resume, close = st.columns(2)
            with resume:
                if st.button("▶ Resume Mission", type="primary", width="stretch", disabled=not actor, key=f"theme_race_resume_{event_id}"):
                    control.set_theme_park_race_runtime_phase(event_id, "ACTIVE", actor); st.rerun()
            with close, st.container(key="mc-danger-end"):
                if st.button("■ End Mission", width="stretch", disabled=not actor, key=f"theme_race_end_{event_id}"):
                    control.set_theme_park_race_runtime_phase(event_id, "CLOSED", actor); st.rerun()
        elif runtime_phase == "ACTIVE":
            pause, close = st.columns(2)
            with pause:
                if st.button("⏸ Hold Mission", width="stretch", disabled=not actor, key=f"theme_race_hold_{event_id}"):
                    control.set_theme_park_race_runtime_phase(event_id, "HELD", actor); st.rerun()
            with close, st.container(key="mc-danger-end"):
                if st.button("■ End Mission", width="stretch", disabled=not actor, key=f"theme_race_end_{event_id}"):
                    control.set_theme_park_race_runtime_phase(event_id, "CLOSED", actor); st.rerun()
        else:
            st.warning("Mission runtime state is unavailable.")

    if lifecycle != "ENDED" and strategy_mode == "OPEN_MISSION_BOARD":
        st.markdown('<div class="mc-section-title">Mission Board Control</div>', unsafe_allow_html=True)
        operations = {row.get("ActivityID", ""): row for row in workspace.get("MissionOperations", [])}
        if operations:
            # Confirmation is read back from the freshly reloaded canonical
            # workspace above, not from the values just clicked -- so this
            # never claims success the backend has not actually confirmed.
            notice_activity_id = st.session_state.pop(f"theme_race_board_notice_{event_id}", None)
            if notice_activity_id and notice_activity_id in operations:
                notice_row = operations[notice_activity_id]
                if (str(notice_row.get("MissionClass", "")).upper() == "SECRET"
                        and str(notice_row.get("SecretState", "")).upper() == "RELEASED"):
                    st.markdown(
                        '<div class="mc-alert-banner">'
                        f'<div class="mc-alert-kicker">🛰️ {html.escape(PLATFORM_NAME)} Alert</div>'
                        '<div class="mc-alert-title">🔓 Secret Mission Released</div>'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    availability = str(notice_row.get("OperationalStatus", "")).upper()
                    st.success(
                        f"Mission Updated — {notice_row.get('DisplayName', notice_activity_id)} is now "
                        f"{_AVAILABILITY_LABELS.get(availability, availability)}."
                    )

            activity_id = st.selectbox(
                "Mission", list(operations),
                format_func=lambda key: f"{operations[key].get('DisplayName', key)} · {operations[key].get('MissionClass', 'STANDARD')}",
                key=f"theme_race_board_operation_mission_{event_id}",
            )
            operation = operations[activity_id]
            mission_class = str(operation.get("MissionClass", "STANDARD")).upper()
            current_availability = str(operation.get("OperationalStatus", "AVAILABLE")).upper()
            current_secret_state = str(operation.get("SecretState", "LOCKED")).upper()

            # The current canonical state, read-only, before any control
            # below can change it.
            summary_rows = [
                ("Mission", operation.get("DisplayName", activity_id)),
                ("Type", mission_class),
                ("Availability", _AVAILABILITY_LABELS.get(current_availability, current_availability)),
            ]
            if mission_class == "SECRET":
                summary_rows.append(("Secret State", _SECRET_STATE_LABELS.get(current_secret_state, current_secret_state)))
            st.markdown(
                "".join(
                    '<div class="mc-mission-summary-row">'
                    f'<span class="mc-mission-summary-label">{html.escape(str(label))}</span>'
                    f'<span class="mc-mission-summary-value">{html.escape(str(value))}</span>'
                    '</div>'
                    for label, value in summary_rows
                ),
                unsafe_allow_html=True,
            )

            operational_status = st.selectbox(
                "Availability", ["AVAILABLE", "TEMPORARILY_UNAVAILABLE", "CLOSED"],
                index=["AVAILABLE", "TEMPORARILY_UNAVAILABLE", "CLOSED"].index(current_availability),
                format_func=lambda value: _AVAILABILITY_LABELS.get(value, value),
                key=f"theme_race_board_status_{event_id}",
            )
            secret_state = "RELEASED"
            if mission_class == "SECRET":
                secret_state = st.selectbox(
                    "Secret mission state", ["LOCKED", "RELEASED"],
                    index=["LOCKED", "RELEASED"].index(current_secret_state),
                    format_func=lambda value: _SECRET_STATE_LABELS.get(value, value),
                    key=f"theme_race_board_secret_{event_id}",
                )
            if st.button("Apply Mission Board Control", type="primary", disabled=not actor, key=f"theme_race_board_apply_{event_id}"):
                control.set_theme_park_race_mission_operation(event_id, activity_id, operational_status, secret_state, actor)
                st.session_state[f"theme_race_board_notice_{event_id}"] = activity_id
                st.rerun()

    st.markdown('<div class="mc-section-title">Team Status</div>', unsafe_allow_html=True)
    teams = workspace.get("Teams", [])
    if not teams:
        st.caption("No teams yet.")
    for row in teams:
        _render_facilitator_team_card(row)

    if lifecycle != "ENDED" and phase in {"CAPTAIN_SELECTION", "ACTIVE"}:
        with st.expander("Facilitator Captain transfer"):
            transfer_teams = {row.get("TeamID", ""): row for row in workspace.get("Teams", [])}
            if transfer_teams:
                team_id = st.selectbox("Team", list(transfer_teams), format_func=lambda key: transfer_teams[key].get("TeamIdentity", key), key=f"theme_race_transfer_team_{event_id}")
                members = [row for row in db.runtime.get_theme_park_race_players(event_id) if row.get("TeamID") == team_id]
                choices = {row.get("ParticipantID", ""): row for row in members}
                if choices:
                    participant_id = st.selectbox("New Captain", list(choices), format_func=lambda key: choices[key].get("Name", key), key=f"theme_race_transfer_participant_{event_id}")
                    reason = st.text_input("Transfer reason", key=f"theme_race_transfer_reason_{event_id}")
                    if st.button("Transfer Captain", disabled=not actor or not reason.strip(), key=f"theme_race_transfer_{event_id}"):
                        control.transfer_team_formation_captain(event_id, team_id, participant_id, actor, reason)
                        st.success("Captain transfer recorded. The new Captain must recover Captain authority on their device.")
                        st.rerun()

    st.markdown("#### Review Queue")
    _render_review_notice(event_id)
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
    mission_classes = {
        str(row.get("ActivityID", "")): str(row.get("MissionClass") or "STANDARD").upper()
        for row in workspace.get("MissionOperations", [])
    }
    for submission in queue:
        submission_id = submission.get("SubmissionID", "")
        team_id = str(submission.get("TeamID", ""))
        activity_id = str(submission.get("ActivityID", ""))
        team_label = team_names.get(team_id) or str(submission.get("TeamName") or team_id or "Team")
        mission_label = mission_names.get(activity_id) or activity_id or "Mission"
        mission_class = mission_classes.get(activity_id, "STANDARD")
        # A pending review is the facilitator's work: never hide it behind a
        # collapsed panel they have to discover -- expanded=True, and the
        # first thing inside is the structured REVIEW REQUIRED summary.
        with st.expander(f"{team_label} · {mission_label} · SUBMITTED", expanded=True):
            st.markdown(
                '<div class="mc-review-kicker">⚠ Review Required</div>'
                f'<div class="mc-review-team">Team {html.escape(team_label)}</div>'
                f'<div class="mc-review-row">Mission: <strong>{html.escape(mission_label)}</strong></div>'
                f'<div class="mc-review-row">Type: <strong>{html.escape(mission_class)}</strong></div>'
                f'<div class="mc-review-row">Submitted: <strong>{html.escape(_human_timestamp(submission.get("SubmittedAt")))}</strong></div>',
                unsafe_allow_html=True,
            )
            if submission.get("Remarks"):
                st.markdown("**Text evidence**")
                st.write(submission["Remarks"])
            photo = get_photo_url(submission.get("ImageURL", ""), submission.get("DriveFileID", ""))
            if photo:
                st.image(photo, width="stretch")
            if submission.get("RideAttemptStatus"):
                pathway = submission.get("RideEvidencePathway") or ""
                attempt = submission.get("RideAttemptStatus") or ""
                st.caption(
                    f"Ride pathway: {_RIDE_PATHWAY_LABELS.get(pathway, pathway) or '—'} · "
                    f"Attempt: {_RIDE_ATTEMPT_LABELS.get(attempt, attempt)} · "
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
                    "✓ Approve", type="primary", width="stretch",
                    disabled=not actor, key=f"theme_race_approve_{submission_id}",
                ):
                    _queue_review_notice(event_id, submit_theme_park_race_review(
                        control, strategy_mode, submission,
                        decision="APPROVE", score=score, actor=actor, notes=notes,
                    ))
                    st.rerun()
            with reject:
                st.caption("Return this mission for resubmission. Scores 0. A reason is required.")
                # Requiring the reason keeps this deliberate and guarantees the
                # 039 contract receives one; it can never approve or carry a
                # score. Visually differentiated (red) as the terminal-feeling
                # decision, same disabled/click semantics as before.
                with st.container(key=f"mc-danger-reject-{submission_id}"):
                    if st.button(
                        "↻ Return for Resubmission", width="stretch",
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
