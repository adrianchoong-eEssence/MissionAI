import streamlit as st
from streamlit_autorefresh import st_autorefresh

from branding import experience_title
from data.standard_core_v2_adapter import get_standard_database
from data.runtime_database import RuntimeDatabaseError
from engines.programme_hierarchy import friendly_type
from engines.programme_adapter import CanonicalProgrammeAdapter, ProgrammeIntegrityError
from engines.stage_timer import remaining_seconds
from engines.formula_race_checkpoints import is_formula_race_event
from screens.app_state import select_active_event
from screens.projector_broadcast import (
    DEFAULT_BROADCAST,
    render_projector_broadcast,
)
from screens.team_identity import resolve_leaderboard_rows


PROJECTOR_STYLES = """
<style>
    .stApp {
        background: #061f3d;
        color: #ffffff;
    }
    header, footer {visibility: hidden;}
    .block-container {
        padding: clamp(18px, 2.2vh, 32px) clamp(28px, 4vw, 72px);
        max-width: 1600px;
    }
    [data-testid="stSidebar"] {
        background: #061f3d;
    }
    [data-testid="stMain"] {
        color: #ffffff;
    }
    .projector-header {
        text-align: center;
        padding-top: clamp(8px, 1.4vh, 20px);
    }
    .projector-kicker {
        color: #ffffff;
        font-size: clamp(34px, 2.8vw, 46px);
        font-weight: 850;
        letter-spacing: .16em;
        line-height: 1.15;
    }
    .projector-event-title {
        color: #ffffff;
        font-size: clamp(76px, 6.6vw, 112px);
        font-weight: 950;
        line-height: 1.04;
        margin: 14px auto 0;
        max-width: 1400px;
        overflow-wrap: anywhere;
        text-wrap: balance;
    }
    .projector-event-name {
        color: #f4f8ff;
        font-size: clamp(32px, 2.8vw, 46px);
        font-weight: 650;
        line-height: 1.3;
        margin-top: 16px;
        overflow-wrap: anywhere;
    }
    .projector-mode {
        color: #e7f0ff;
        font-size: clamp(27px, 2.2vw, 36px);
        font-weight: 650;
        line-height: 1.35;
        margin-top: 18px;
    }
    .projector-brand {
        color: #dce9fb;
        font-size: clamp(19px, 1.5vw, 25px);
        font-weight: 650;
        letter-spacing: .13em;
        line-height: 1.4;
        margin-top: 16px;
    }
    .projector-brand-by {
        color: #d3e2f7;
        font-size: clamp(18px, 1.35vw, 23px);
        font-weight: 650;
        letter-spacing: .1em;
        line-height: 1.4;
        margin-top: 8px;
    }
    .projector-panel {
        color: #ffffff;
        text-align: center;
        margin: clamp(36px, 6vh, 76px) auto 0;
        max-width: 1450px;
    }
    .projector-label {
        color: #eef5ff;
        font-size: clamp(40px, 3.6vw, 58px);
        font-weight: 800;
        line-height: 1.2;
    }
    .projector-mission-title {
        color: #ffffff;
        font-size: clamp(84px, 8vw, 132px);
        font-weight: 950;
        line-height: 1.03;
        margin: 22px auto 0;
        max-width: 1450px;
        overflow-wrap: anywhere;
        text-wrap: balance;
    }
    .projector-body {
        color: #ffffff;
        font-size: clamp(38px, 3.25vw, 54px);
        font-weight: 560;
        line-height: 1.55;
        margin: 42px auto 0;
        max-width: 1280px;
        overflow-wrap: break-word;
        white-space: normal;
        text-wrap: pretty;
    }
    .projector-support {
        color: #e7f0ff;
        font-size: clamp(31px, 2.6vw, 43px);
        font-weight: 620;
        line-height: 1.45;
        margin: 44px auto 0;
        max-width: 1280px;
        overflow-wrap: break-word;
    }
    .projector-metric {
        color: #ffffff;
        font-size: clamp(112px, 11vw, 176px);
        font-weight: 950;
        line-height: 1;
        margin-top: 28px;
    }
    .projector-primary {
        color: #ffffff;
        font-size: clamp(58px, 5vw, 82px);
        font-weight: 900;
        line-height: 1.15;
        overflow-wrap: anywhere;
        text-wrap: balance;
    }
    .projector-secondary {
        color: #f0f6ff;
        font-size: clamp(36px, 3vw, 50px);
        font-weight: 650;
        line-height: 1.45;
        overflow-wrap: break-word;
    }
    .broadcast-screen {
        width:100%;
        min-height:calc(100vh - 42px);
        box-sizing:border-box;
        border-radius:24px;
        padding:clamp(42px,6vh,92px) clamp(48px,7vw,120px);
        background-color:#061326;
        background-position:center;
        background-size:cover;
        color:#ffffff;
        display:flex;
        flex-direction:column;
        justify-content:center;
        overflow:hidden;
    }
    .broadcast-presentation {
        min-height:calc(100vh - 20px);
        border-radius:0;
    }
    .broadcast-brand {
        font-size:clamp(96px,14vw,220px);
        font-weight:950;
        letter-spacing:-.06em;
        line-height:.85;
    }
    .broadcast-product {
        margin-top:24px;
        font-size:clamp(28px,3vw,50px);
        font-weight:750;
        line-height:1.25;
    }
    .broadcast-title {
        margin-top:clamp(22px,4vh,54px);
        font-size:clamp(72px,8vw,138px);
        font-weight:950;
        line-height:1.02;
        overflow-wrap:anywhere;
        text-wrap:balance;
    }
    .broadcast-subtitle, .broadcast-tagline, .broadcast-kicker {
        color:#f0f6ff;
        font-size:clamp(28px,2.7vw,46px);
        font-weight:720;
        line-height:1.35;
        overflow-wrap:break-word;
    }
    .broadcast-subtitle {margin-top:28px;}
    .broadcast-tagline {margin-top:auto;padding-top:34px;}
    .broadcast-kicker {
        color:#d8c46a;
        letter-spacing:.12em;
        text-transform:uppercase;
    }
    .broadcast-logo {
        max-width:min(34vw,480px);
        max-height:20vh;
        object-fit:contain;
        margin-top:34px;
        align-self:center;
    }
    .broadcast-story, .broadcast-experience, .broadcast-king-screen {
        display:grid;
        grid-template-columns:minmax(340px,.82fr) minmax(0,1.18fr);
        gap:clamp(42px,6vw,100px);
        align-items:center;
    }
    .broadcast-character, .broadcast-king {
        width:100%;
        height:min(76vh,850px);
        object-fit:contain;
        object-position:center bottom;
    }
    .broadcast-story-copy, .broadcast-experience-copy,
    .broadcast-king-copy {min-width:0;}
    .broadcast-message {
        margin-top:clamp(24px,4vh,48px);
        font-size:clamp(38px,3.5vw,62px);
        font-weight:600;
        line-height:1.48;
        overflow-wrap:break-word;
        text-wrap:pretty;
    }
    .broadcast-experience-image {
        width:100%;
        max-height:76vh;
        object-fit:contain;
        border-radius:24px;
    }
    .broadcast-centred {
        align-items:center;
        text-align:center;
    }
    .broadcast-countdown {
        font-size:clamp(180px,26vw,430px);
        font-weight:950;
        line-height:.88;
        font-variant-numeric:tabular-nums;
        letter-spacing:-.06em;
    }
    .broadcast-rankings {justify-content:flex-start;}
    .broadcast-ranking {
        width:min(1180px,100%);
        margin:clamp(10px,1.3vh,18px) auto 0;
        padding:clamp(16px,2vh,26px) clamp(22px,3vw,42px);
        border:2px solid rgba(255,255,255,.28);
        border-radius:20px;
        background:rgba(255,255,255,.1);
        display:flex;
        justify-content:space-between;
        gap:40px;
        font-size:clamp(30px,3vw,48px);
        font-weight:760;
        line-height:1.2;
    }
    .broadcast-custom-image {
        width:100%;
        height:calc(100vh - 90px);
        object-fit:contain;
    }
    .broadcast-blank {
        position:fixed;
        inset:0;
        z-index:999999;
        background:#000000;
    }
    @media (max-width: 1000px) {
        .broadcast-story, .broadcast-experience, .broadcast-king-screen {
            grid-template-columns:1fr;
        }
        .broadcast-character, .broadcast-king,
        .broadcast-experience-image {max-height:42vh;}
    }
    @media (max-aspect-ratio: 4/3) {
        .projector-event-title { font-size: clamp(66px, 7vw, 96px); }
        .projector-mission-title { font-size: clamp(72px, 8vw, 112px); }
        .projector-body { font-size: clamp(34px, 3.5vw, 48px); }
    }
</style>
"""


def auto_refresh(seconds=5):
    st_autorefresh(
        interval=seconds * 1000,
        key="leaderboard_display_refresh",
    )


def calculate_leaderboard(submissions):
    leaderboard = {}

    for submission in submissions:
        judged = str(submission.get("Judged", "")).lower()

        if judged not in ["yes", "true", "approved"]:
            continue

        submission_type = str(
            submission.get("SubmissionType", "")
        ).upper()
        if submission_type in {"NASI", "PIPELINE_ENTERPRISE"}:
            continue

        team = submission.get("TeamName", "Unknown Team")

        try:
            score = float(submission.get("Score") or 0)
        except Exception:
            score = 0

        leaderboard[team] = leaderboard.get(team, 0) + score

    return sorted(
        leaderboard.items(),
        key=lambda item: item[1],
        reverse=True,
    )


def display_header(event, mode):
    title = experience_title(event)
    st.markdown(
        f"""
        <div class="projector-header">
            <div class="projector-kicker">
                EXOS
            </div>
            <div class="projector-event-title">
                {title}
            </div>
            <div class="projector-event-name">
                {event.get("EventName", "")}
            </div>
            <div class="projector-mode">
                {mode}
            </div>
            <div class="projector-brand">
                eEssence Xperiential Operating System
            </div>
            <div class="projector-brand-by">
                by eEssence
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def display_registration(event, db, event_id):
    participants = db.get_participant_count(event_id)
    teams = db.get_team_count(event_id)

    st.markdown(
        f"""
        <div class="projector-panel">
            <div class="projector-primary">
                Registration Open
            </div>
            <div class="projector-metric">
                {participants}
            </div>
            <div class="projector-secondary">
                Participants Checked In
            </div>
            <div class="projector-secondary" style="margin-top:32px;">
                {teams} Teams Forming
            </div>
            <div class="projector-support">
                Scan the QR Code • Enter Join Code • Join Your Team
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def display_current_mission(mission):
    if not mission:
        st.markdown(
            """
            <div class="projector-panel">
                <div class="projector-primary">
                    Waiting for Experience Launch
                </div>
                <div class="projector-support">
                    Stand by. Your next challenge will appear shortly.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""
        <div class="projector-panel">
            <div class="projector-label">
                Current Experience
            </div>
            <div class="projector-mission-title">
                {mission.get("Title", "Experience")}
            </div>
            <div class="projector-body">
                {mission.get("Description", "")}
            </div>
            <div class="projector-support">
                Complete the mission. Submit your evidence. Support your team.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def display_competitive_leaderboard(leaderboard):
    if not leaderboard:
        st.markdown(
            """
            <div style="text-align:center; margin-top:120px;">
                <div style="font-size:60px; font-weight:900;">
                    No Approved Scores Yet
                </div>
                <div style="font-size:28px; margin-top:30px; opacity:0.75;">
                    The leaderboard will update once submissions are approved.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        """
        <div style="text-align:center; font-size:56px; font-weight:900; margin-top:50px;">
            Live Leaderboard
        </div>
        """,
        unsafe_allow_html=True,
    )

    for index, (team, score) in enumerate(leaderboard[:8], start=1):
        medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else "⭐"

        st.markdown(
            f"""
            <div style="
                margin:22px auto;
                padding:26px 40px;
                max-width:1000px;
                border-radius:28px;
                background:rgba(255,255,255,0.10);
                display:flex;
                justify-content:space-between;
                align-items:center;
                border:1px solid rgba(255,255,255,0.18);
            ">
                <div style="font-size:44px; font-weight:800;">
                    {medal} {index}. {team}
                </div>
                <div style="font-size:48px; font-weight:900;">
                    {score} pts
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def display_credit_leaderboard(wallet_status):
    wallets = wallet_status.get("Wallets", []) or []
    wallets = sorted(
        wallets,
        key=lambda row: (
            -float(row.get("EarnedCredits", 0) or 0),
            str(row.get("TeamName", "")),
        ),
    )
    if not wallet_status.get("Enabled") or not wallets:
        st.markdown(
            """
            <div style="text-align:center; margin-top:12vh;">
                <div style="font-size:clamp(38px,5vw,64px); font-weight:900;">
                    Credit Leaderboard Is Not Ready
                </div>
                <div style="font-size:clamp(20px,2.4vw,30px); margin-top:24px; opacity:0.75;">
                    Enable the Credit Wallet in the Live Event Console.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    frozen_label = " · FINAL" if wallet_status.get("EarningFrozen") else " · LIVE"
    st.markdown(
        f"""
        <div style="text-align:center; font-size:clamp(40px,5vw,62px); font-weight:900; margin-top:4vh;">
            Day 1 Credit Leaderboard{frozen_label}
        </div>
        <div style="text-align:center; font-size:clamp(18px,2vw,26px); opacity:0.72; margin-top:10px;">
            Rank is based on credits earned. Marketplace spending does not reduce the ranking.
        </div>
        """,
        unsafe_allow_html=True,
    )

    for index, wallet in enumerate(wallets[:10], start=1):
        medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else "⭐"
        earned = float(wallet.get("EarnedCredits", 0) or 0)
        balance = float(wallet.get("Balance", 0) or 0)
        earned_text = str(int(earned)) if earned.is_integer() else f"{earned:.1f}"
        balance_text = str(int(balance)) if balance.is_integer() else f"{balance:.1f}"
        st.markdown(
            f"""
            <div style="
                margin:clamp(10px,1.5vh,18px) auto;
                padding:clamp(16px,2vh,24px) clamp(20px,3vw,38px);
                max-width:1050px;
                border-radius:24px;
                background:rgba(255,255,255,0.10);
                display:grid;
                grid-template-columns:minmax(0,1fr) auto auto;
                gap:clamp(18px,3vw,42px);
                align-items:center;
                border:1px solid rgba(255,255,255,0.18);
            ">
                <div style="font-size:clamp(25px,3vw,40px); font-weight:800; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                    {medal} {index}. {wallet.get('TeamName', '')}
                </div>
                <div style="text-align:right;">
                    <div style="font-size:clamp(24px,3vw,38px); font-weight:900;">{earned_text}</div>
                    <div style="font-size:clamp(13px,1.4vw,18px); opacity:0.7;">earned</div>
                </div>
                <div style="text-align:right; min-width:100px;">
                    <div style="font-size:clamp(20px,2.5vw,32px); font-weight:800;">{balance_text}</div>
                    <div style="font-size:clamp(13px,1.4vw,18px); opacity:0.7;">available</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def display_collaborative_progress(submissions, teams_count):
    approved = [
        s for s in submissions
        if str(s.get("Judged", "")).lower() in ["yes", "true", "approved"]
    ]

    total_score = 0

    for submission in approved:
        try:
            total_score += int(submission.get("Score") or 0)
        except Exception:
            pass

    team_names = set([
        s.get("TeamName")
        for s in approved
        if s.get("TeamName")
    ])

    participation = 0

    if teams_count:
        participation = int((len(team_names) / teams_count) * 100)

    st.markdown(
        f"""
        <div style="text-align:center; margin-top:70px;">
            <div style="font-size:56px; font-weight:900;">
                Collective Progress
            </div>
            <div style="font-size:120px; font-weight:900; margin-top:35px;">
                {participation}%
            </div>
            <div style="font-size:34px; opacity:0.85;">
                Team Participation
            </div>
            <div style="font-size:48px; font-weight:800; margin-top:50px;">
                {len(approved)} Experiences Approved
            </div>
            <div style="font-size:42px; font-weight:800; margin-top:25px;">
                {total_score} Collective Points
            </div>
            <div style="font-size:30px; margin-top:60px; opacity:0.75;">
                Compete with energy. Finish with collaboration.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def display_hybrid(leaderboard, submissions, teams_count):
    col1, col2 = st.columns([1.1, 0.9])

    with col1:
        display_competitive_leaderboard(leaderboard)

    with col2:
        approved = [
            s for s in submissions
            if str(s.get("Judged", "")).lower() in ["yes", "true", "approved"]
        ]

        team_names = set([
            s.get("TeamName")
            for s in approved
            if s.get("TeamName")
        ])

        participation = 0

        if teams_count:
            participation = int((len(team_names) / teams_count) * 100)

        st.markdown(
            f"""
            <div style="
                margin-top:120px;
                padding:44px;
                border-radius:32px;
                background:rgba(255,255,255,0.10);
                border:1px solid rgba(255,255,255,0.18);
                text-align:center;
            ">
                <div style="font-size:38px; font-weight:900;">
                    Collaboration Meter
                </div>
                <div style="font-size:100px; font-weight:900; margin-top:30px;">
                    {participation}%
                </div>
                <div style="font-size:28px; opacity:0.8;">
                    Teams Contributing
                </div>
                <div style="font-size:30px; margin-top:50px; line-height:1.4;">
                    Win your missions.<br>
                    Finish together.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def display_winner(leaderboard):
    if not leaderboard:
        st.markdown(
            """
            <div style="text-align:center; margin-top:120px;">
                <div style="font-size:60px; font-weight:900;">
                    Final Results Coming Soon
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    winner, score = leaderboard[0]

    st.balloons()

    st.markdown(
        f"""
        <div style="text-align:center; margin-top:80px;">
            <div style="font-size:70px; font-weight:900;">
                🏆 Champion Team
            </div>
            <div style="font-size:110px; font-weight:900; margin-top:40px;">
                {winner}
            </div>
            <div style="font-size:54px; margin-top:25px;">
                {score} pts
            </div>
            <div style="font-size:36px; margin-top:70px; opacity:0.85;">
                Congratulations to every team.
            </div>
            <div style="font-size:32px; margin-top:20px; opacity:0.75;">
                You competed. You collaborated. You completed the mission together.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_leaderboard_display():
    st.markdown(PROJECTOR_STYLES, unsafe_allow_html=True)

    db = get_standard_database()
    events = db.get_events()

    if not events:
        st.error("No events found.")
        return

    with st.sidebar:
        st.title("EXOS Display Control")

        event = select_active_event(
            events,
            label="Active Event",
            key="live_display_event",
        )

        refresh_seconds = st.selectbox(
            "Auto Refresh",
            [2, 5, 10, 15, 30],
            index=0,
            key="live_display_refresh_seconds",
        )

        st.caption("Use browser fullscreen mode for projector display.")

    event_id = event.get("EventID")
    state = db.get_event_state(event_id) or {}
    if is_formula_race_event(event) and db.runtime.can_publish:
        try:
            checkpoint_state = db.runtime.get_formula_race_checkpoints(event_id)
        except RuntimeDatabaseError:
            checkpoint_state = {}
        if str(checkpoint_state.get("Status", "")).upper() in {"LIVE", "PAUSED", "CLOSED"}:
            auto_refresh(refresh_seconds)
            report = db.runtime.get_canonical_transaction_report(event_id)
            submissions = report.get("Submissions", [])
            balances = {str(row.get("team_id", "")): row for row in report.get("TeamBalances", [])}
            rows = []
            for team in db.get_teams(event_id):
                team_id = str(team.get("TeamID", ""))
                completed = len({str(row.get("ActivityID", "")) for row in submissions
                    if str(row.get("TeamID", "")) == team_id and str(row.get("Status", "")).upper() == "APPROVED"})
                rows.append({"Team": team.get("TeamName", team_id), "Completed": f"{completed}/4",
                    "Credits": balances.get(team_id, {}).get("available_balance", 0)})
            rows.sort(key=lambda row: (-float(row["Credits"] or 0), row["Team"]))
            st.markdown("<div class='projector-header'><div class='projector-kicker'>FORMULA R.A.C.E.</div><div class='projector-event-title'>LIVE CHECKPOINTS</div></div>",unsafe_allow_html=True)
            st.dataframe(rows,width="stretch",hide_index=True)
            pending=sum(str(row.get("Status", "")).upper()=="PENDING_REVIEW" for row in submissions)
            a,b=st.columns(2);a.metric("Pending Reviews",pending);b.metric("Current Leader",rows[0]["Team"] if rows else "—")
            return
    programme = CanonicalProgrammeAdapter.load(db, event_id)
    try:
        current_module, current_activity = programme.resolve_runtime(state)
    except ProgrammeIntegrityError as error:
        st.error(f"Projector cannot resolve the live activity: {error}")
        return
    current_stage = current_activity
    requested_mode = str(
        current_stage.get("DisplayMode", "")
        or state.get("DisplayMode", "")
    )
    allowed_modes = {
        "Registration",
        "Current Mission",
        "Credit Leaderboard",
        "Hybrid",
        "Leaderboard",
        "Collaboration",
        "Winner",
    }
    content_type = str(current_activity.get("ContentType", "Standard Activity"))
    if requested_mode in allowed_modes:
        mode = requested_mode
    elif content_type in {"Judging", "Debrief"}:
        mode = "Winner"
    elif content_type in {"Marketplace", "Sync AI"}:
        mode = "Credit Leaderboard"
    elif content_type in {"Experience Board", "Catalyst"}:
        mode = "Hybrid"
    elif current_activity.get("ActivityType") == "Registration":
        mode = "Registration"
    else:
        mode = "Leaderboard"

    with st.sidebar:
        display_mode = "Current Experience" if mode == "Current Mission" else mode
        st.success(f"Automatic view: {display_mode}")

    auto_refresh(refresh_seconds)

    submissions = db.get_submissions(event_id)
    canonical_leaderboard = []
    if db.runtime.can_publish:
        try:
            canonical_leaderboard = db.runtime.get_canonical_leaderboard(event_id)
        except RuntimeDatabaseError:
            canonical_leaderboard = []
    source_rows = (
        canonical_leaderboard if canonical_leaderboard else calculate_leaderboard(submissions)
    )
    leaderboard = resolve_leaderboard_rows(source_rows, db.get_teams(event_id))
    mission = db.get_current_mission(event_id)
    teams_count = db.get_team_count(event_id)
    broadcast_state = dict(DEFAULT_BROADCAST)
    broadcast_state.update(db.get_broadcast_state(event_id))

    wallet_status = {}
    if (
        mode == "Credit Leaderboard"
        or broadcast_state.get("Mode") in {"Scores", "Credits"}  # Scores mode maps both active and credits broadcasts for race.
        ) and db.runtime.can_publish:
        try:
            wallet_status = db.runtime.get_credit_wallet_status(event_id)
        except RuntimeDatabaseError:
            wallet_status = {}

    timer = db.get_stage_timer(
        event_id,
        current_stage.get("StageNo", ""),
        current_stage.get("DurationMinutes", 0),
    ) if current_stage else {}
    if render_projector_broadcast(
        broadcast_state,
        event=event,
        mission=mission,
        leaderboard=leaderboard,
        wallet_status=wallet_status,
        timer=timer,
    ):
        return

    display_header(event, mode)
    if current_module:
        st.markdown(
            f"""
            <div style="text-align:center;margin:8px 0 18px;">
              <div style="font-size:clamp(30px,5vw,64px);font-weight:900;">
                {current_module.get('ModuleName', '')}
              </div>
              <div style="font-size:clamp(18px,2.4vw,30px);opacity:.82;">
                {current_activity.get('StageName', '')} · {friendly_type(current_activity)}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    if current_stage:
        remaining = remaining_seconds(timer)
        if str(timer.get("Status", "")).upper() in {"RUNNING", "PAUSED"}:
            st.markdown(
                f"""
                <div style="text-align:center;font-size:clamp(46px,8vw,92px);
                    font-weight:900;margin:22px 0 8px;">
                    {remaining // 60:02d}:{remaining % 60:02d}
                </div>
                <div style="text-align:center;opacity:.72;">
                    {current_stage.get('StageName', '')} · {timer.get('Status', '')}
                </div>
                """,
                unsafe_allow_html=True,
            )

    if mode == "Registration":
        display_registration(event, db, event_id)

    elif mode == "Current Mission":
        display_current_mission(mission)

    elif mode == "Leaderboard":
        display_competitive_leaderboard(leaderboard)

    elif mode == "Credit Leaderboard":
        display_credit_leaderboard(wallet_status)

    elif mode == "Collaboration":
        display_collaborative_progress(submissions, teams_count)

    elif mode == "Winner":
        display_winner(leaderboard)

    else:
        display_hybrid(leaderboard, submissions, teams_count)
