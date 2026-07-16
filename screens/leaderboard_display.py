import streamlit as st
from streamlit_autorefresh import st_autorefresh

from data.google_sheets import GoogleSheetsDB
from data.runtime_database import RuntimeDatabaseError
from screens.app_state import select_active_event


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
    st.markdown(
        f"""
        <div style="text-align:center; padding-top:20px;">
            <div style="font-size:32px; letter-spacing:4px; font-weight:700;">
                EXOS
            </div>
            <div style="font-size:72px; font-weight:900; margin-top:10px;">
                Mission AI
            </div>
            <div style="font-size:28px; margin-top:8px; opacity:0.85;">
                {event.get("EventName", "")}
            </div>
            <div style="font-size:22px; margin-top:14px; opacity:0.7;">
                {mode}
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
        <div style="text-align:center; margin-top:80px;">
            <div style="font-size:56px; font-weight:800;">
                Registration Open
            </div>
            <div style="font-size:120px; font-weight:900; margin-top:40px;">
                {participants}
            </div>
            <div style="font-size:34px;">
                Participants Checked In
            </div>
            <div style="font-size:36px; margin-top:40px;">
                {teams} Teams Forming
            </div>
            <div style="font-size:26px; margin-top:60px; opacity:0.75;">
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
            <div style="text-align:center; margin-top:120px;">
                <div style="font-size:64px; font-weight:900;">
                    Waiting for Mission Launch
                </div>
                <div style="font-size:28px; margin-top:30px; opacity:0.75;">
                    Stand by. Your next challenge will appear shortly.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""
        <div style="text-align:center; margin-top:70px;">
            <div style="font-size:42px; opacity:0.8;">
                Current Mission
            </div>
            <div style="font-size:82px; font-weight:900; margin-top:20px;">
                {mission.get("Title", "Mission")}
            </div>
            <div style="font-size:34px; max-width:1100px; margin:45px auto 0 auto; line-height:1.4;">
                {mission.get("Description", "")}
            </div>
            <div style="font-size:28px; margin-top:50px; opacity:0.8;">
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
                {len(approved)} Missions Approved
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
    st.markdown(
        """
        <style>
            .stApp {
                background: radial-gradient(circle at top, #1f2937 0%, #0f172a 45%, #020617 100%);
                color: white;
            }
            header {visibility: hidden;}
            footer {visibility: hidden;}
            .block-container {
                padding-top: 2rem;
                padding-bottom: 2rem;
                max-width: 1400px;
            }
            [data-testid="stSidebar"] {
                background: #0f172a;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    db = GoogleSheetsDB()
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

        mode = st.selectbox(
            "Display Mode",
            [
                "Registration",
                "Current Mission",
                "Credit Leaderboard",
                "Hybrid",
                "Leaderboard",
                "Collaboration",
                "Winner",
            ],
            index=3,
            key="live_display_mode",
        )

        refresh_seconds = st.selectbox(
            "Auto Refresh",
            [5, 10, 15, 30],
            index=1,
            key="live_display_refresh_seconds",
        )

        st.caption("Use browser fullscreen mode for projector display.")

    event_id = event.get("EventID")

    auto_refresh(refresh_seconds)

    submissions = db.get_submissions(event_id)
    leaderboard = calculate_leaderboard(submissions)
    mission = db.get_current_mission(event_id)
    teams_count = db.get_team_count(event_id)

    wallet_status = {}
    if mode == "Credit Leaderboard" and db.runtime.can_publish:
        try:
            wallet_status = db.runtime.get_credit_wallet_status(event_id)
        except RuntimeDatabaseError:
            wallet_status = {}

    display_header(event, mode)

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
