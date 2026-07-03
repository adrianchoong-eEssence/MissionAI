import streamlit as st
from datetime import date
import random

st.set_page_config(
    page_title="Mission AI Studio",
    page_icon="🚀",
    layout="wide"
)

if "page" not in st.session_state:
    st.session_state["page"] = "studio"

if "current_stage_index" not in st.session_state:
    st.session_state["current_stage_index"] = 0

if "stages" not in st.session_state:
    st.session_state["stages"] = [
        "Registration",
        "Team Formation",
        "Mission Briefing",
        "Mission 1",
        "Lunch Break",
        "Mission 2",
        "Debrief",
        "Closing"
    ]

if "participants" not in st.session_state:
    st.session_state["participants"] = []

if "teams_revealed" not in st.session_state:
    st.session_state["teams_revealed"] = False

if "team_assignments" not in st.session_state:
    st.session_state["team_assignments"] = {}

if "current_participant" not in st.session_state:
    st.session_state["current_participant"] = ""

if "team_identities" not in st.session_state:
    st.session_state["team_identities"] = [
        {"emoji": "🐯", "name": "TIGER"},
        {"emoji": "🐼", "name": "PANDA"},
        {"emoji": "🦅", "name": "EAGLE"},
        {"emoji": "🦊", "name": "FOX"},
        {"emoji": "🐺", "name": "WOLF"},
        {"emoji": "🦁", "name": "LION"},
        {"emoji": "🐬", "name": "DOLPHIN"},
        {"emoji": "🐘", "name": "ELEPHANT"},
        {"emoji": "🦉", "name": "OWL"},
        {"emoji": "🐸", "name": "FROG"},
    ]


def go_to(page_name):
    st.session_state["page"] = page_name
    st.rerun()


def get_current_stage():
    return st.session_state["stages"][st.session_state["current_stage_index"]]


def next_stage():
    if st.session_state["current_stage_index"] < len(st.session_state["stages"]) - 1:
        st.session_state["current_stage_index"] += 1
    st.rerun()


def previous_stage():
    if st.session_state["current_stage_index"] > 0:
        st.session_state["current_stage_index"] -= 1
    st.rerun()


def get_number_of_teams():
    mission = st.session_state.get("mission")
    if mission and mission.get("number_of_teams"):
        return int(mission["number_of_teams"])
    return 7


def get_active_team_identities():
    requested_teams = get_number_of_teams()
    identities = st.session_state["team_identities"]

    if requested_teams <= len(identities):
        return identities[:requested_teams]

    extra = []
    for i in range(len(identities) + 1, requested_teams + 1):
        extra.append({"emoji": "⭐", "name": f"TEAM {i}"})

    return identities + extra


def reveal_teams():
    participants = st.session_state["participants"]
    active_teams = get_active_team_identities()

    assignments = {}
    shuffled = participants.copy()
    random.shuffle(shuffled)

    # Smart Shuffle v0.0.7:
    # Assign participants evenly across the selected number of teams.
    # Example: 70 pax / 7 teams = 10 each.
    # Example: 73 pax / 7 teams = first 3 teams get 11, others get 10.
    for index, participant in enumerate(shuffled):
        team = active_teams[index % len(active_teams)]
        assignments[participant] = team

    st.session_state["team_assignments"] = assignments
    st.session_state["teams_revealed"] = True

    if "Team Formation" in st.session_state["stages"]:
        st.session_state["current_stage_index"] = st.session_state["stages"].index("Team Formation")

    st.rerun()


def reset_teams():
    st.session_state["teams_revealed"] = False
    st.session_state["team_assignments"] = {}
    st.rerun()


def show_stage_timeline():
    st.write("### Mission Timeline")
    current_index = st.session_state["current_stage_index"]

    for i, stage in enumerate(st.session_state["stages"]):
        if i < current_index:
            st.write(f"✅ {stage}")
        elif i == current_index:
            st.write(f"🟢 **{stage}**")
        else:
            st.write(f"⬜ {stage}")


def show_team_assignments():
    assignments = st.session_state["team_assignments"]

    if not assignments:
        st.info("Teams have not been revealed yet.")
        return

    st.write("### Team Assignments")

    grouped = {}
    for participant, team in assignments.items():
        label = f'{team["emoji"]} {team["name"]}'
        grouped.setdefault(label, []).append(participant)

    for label, members in grouped.items():
        with st.expander(f"{label} — {len(members)} pax", expanded=True):
            for member in sorted(members):
                st.write("✅", member)


def show_studio():
    st.title("🚀 Mission AI Studio")
    st.subheader("eEssence Experiential Learning OS")

    st.info("This is Adrian's cockpit. Use this screen to prepare and manage the programme.")

    st.divider()

    current_stage = get_current_stage()
    col_status_1, col_status_2, col_status_3 = st.columns(3)
    col_status_1.metric("Current Stage", current_stage)
    col_status_2.metric("Participants Joined", len(st.session_state["participants"]))
    col_status_3.metric("Teams", get_number_of_teams())

    st.subheader("Participants")
    if len(st.session_state["participants"]) == 0:
        st.info("No participants joined yet.")
    else:
        for p in st.session_state["participants"]:
            team = st.session_state["team_assignments"].get(p)
            if team:
                st.write(f'✅ {p} → {team["emoji"]} {team["name"]}')
            else:
                st.write("✅", p)

    st.divider()

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("⬅️ Previous Stage", use_container_width=True):
            previous_stage()

    with col_b:
        if st.button("➡️ Next Stage", use_container_width=True):
            next_stage()

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🚀 Create / Open Mission", use_container_width=True):
            go_to("mission_setup")

        if st.button("📂 Projects", use_container_width=True):
            st.info("Projects module coming soon.")

        if st.button("🎲 Smart Shuffle", use_container_width=True):
            st.info("Use Mission Remote → Smart Shuffle + Reveal Teams.")

    with col2:
        if st.button("📺 Mission Control Display", use_container_width=True):
            go_to("mission_control")

        if st.button("📱 Participant Companion", use_container_width=True):
            go_to("participant")

        if st.button("🎛️ Mission Remote", use_container_width=True):
            go_to("remote")

    st.divider()
    show_team_assignments()

    st.divider()
    show_stage_timeline()

    st.divider()
    st.caption("Mission AI Studio v0.0.7 — Smart Shuffle")
    st.caption("Powered by eEssence")


def show_mission_setup():
    st.title("🛰️ Create / Open Mission")
    st.caption("Prepare today's programme before launching Mission Control.")

    if st.button("← Back to Studio"):
        go_to("studio")

    st.divider()

    with st.form("mission_setup_form"):
        col1, col2 = st.columns(2)

        with col1:
            project_name = st.text_input("Project Name", "70 Pax Pilot Programme")
            client_name = st.text_input("Client Name")
            programme_name = st.text_input("Programme Name")
            venue = st.text_input("Venue")

        with col2:
            programme_date = st.date_input("Programme Date", date.today())
            expected_pax = st.number_input("Expected Participants", min_value=1, value=70)
            actual_pax = st.number_input("Actual Participants", min_value=1, value=70)
            number_of_teams = st.number_input("Number of Teams", min_value=1, value=7)

        project_type = st.selectbox(
            "Project Type",
            [
                "Indoor Team Building",
                "Outdoor Hunt",
                "Road Rally / Motor Hunt",
                "AI Mission",
                "Custom"
            ]
        )

        submitted = st.form_submit_button("Save Mission Plan")

    if submitted:
        st.session_state["mission"] = {
            "project_name": project_name,
            "client_name": client_name,
            "programme_name": programme_name,
            "venue": venue,
            "programme_date": str(programme_date),
            "expected_pax": expected_pax,
            "actual_pax": actual_pax,
            "number_of_teams": number_of_teams,
            "project_type": project_type
        }

        st.success("✅ Mission Plan Saved")

        average_team_size = actual_pax / number_of_teams

        st.write("### Mission Summary")
        st.write(f"**Project:** {project_name}")
        st.write(f"**Client:** {client_name}")
        st.write(f"**Programme:** {programme_name}")
        st.write(f"**Venue:** {venue}")
        st.write(f"**Date:** {programme_date}")
        st.write(f"**Expected Pax:** {expected_pax}")
        st.write(f"**Actual Pax:** {actual_pax}")
        st.write(f"**Teams:** {number_of_teams}")
        st.write(f"**Project Type:** {project_type}")

        st.write("### Team Size Check")
        st.write(f"Average team size: **{average_team_size:.1f} pax per team**")

        if average_team_size < 6:
            st.warning("⚠️ Team size may be too small.")
        elif average_team_size > 15:
            st.warning("⚠️ Team size may be too large.")
        else:
            st.success("✅ Team size looks workable.")


def show_mission_control():
    st.title("📺 Mission Control Display")
    st.caption("This is the projector screen for the whole room.")

    if st.button("← Back to Studio"):
        go_to("studio")

    st.divider()

    mission = st.session_state.get("mission", None)
    current_stage = get_current_stage()

    if mission is None:
        st.warning("No mission has been created yet.")
        st.write("Go to **Create / Open Mission** first.")
        return

    st.header(mission["project_name"])
    st.subheader(mission["client_name"])

    st.divider()

    col1, col2, col3 = st.columns(3)
    col1.metric("Current Stage", current_stage)
    col2.metric("Participants Joined", len(st.session_state["participants"]))
    col3.metric("Teams Revealed", "YES" if st.session_state["teams_revealed"] else "NO")

    st.divider()

    if current_stage == "Registration":
        st.info("Participants are joining the mission.")
    elif current_stage == "Team Formation":
        if st.session_state["teams_revealed"]:
            st.success("TEAM FORMATION ACTIVE — Make your sound. Find your teammates.")
            st.write("# 🎲 Teams Have Been Revealed")
        else:
            st.info("Waiting for Mission Remote to reveal teams.")
    elif "Mission" in current_stage:
        st.warning("Mission is now active.")
    elif current_stage == "Lunch Break":
        st.info("Lunch Break. Please return on time.")
    elif current_stage == "Debrief":
        st.success("Prepare for reflection and learning transfer.")
    elif current_stage == "Closing":
        st.success("Mission Complete. Thank you.")

    st.divider()

    col4, col5, col6 = st.columns(3)
    col4.metric("Expected Pax", mission["expected_pax"])
    col5.metric("Actual Pax", mission["actual_pax"])
    col6.metric("Teams", mission["number_of_teams"])


def show_participant():
    st.title("📱 Mission Companion")
    st.caption("This is what participants will see after scanning the QR code.")

    if st.button("← Back to Studio"):
        go_to("studio")

    st.divider()

    st.write("### Welcome to AURA")
    st.info("Hi! I'm AURA. I'll guide you throughout today's experience.")

    display_name = st.text_input("Display Name", value=st.session_state.get("current_participant", ""))

    if st.button("Join Mission"):
        clean_name = display_name.strip()
        if clean_name == "":
            st.warning("Please enter your display name.")
        elif clean_name in st.session_state["participants"]:
            st.session_state["current_participant"] = clean_name
            st.warning("This display name has already joined. Continuing as this participant.")
        else:
            st.session_state["participants"].append(clean_name)
            st.session_state["current_participant"] = clean_name
            st.success(f"Welcome {clean_name}!")

    st.divider()

    current_participant = st.session_state.get("current_participant", "")

    if current_participant == "":
        st.info("Enter your display name and press Join Mission.")
    else:
        st.metric("Participant", current_participant)

        if st.session_state["teams_revealed"]:
            team = st.session_state["team_assignments"].get(current_participant)
            if team:
                st.write("# Your Team")
                st.write(f'# {team["emoji"]}')
                st.write(f'## {team["name"]}')
                st.success("Find your teammates. Make your sound. Mission Control is waiting.")
            else:
                st.warning("Teams have been revealed, but you are not assigned yet. Please check with your facilitator.")
        else:
            st.metric("Participants Joined", len(st.session_state["participants"]))
            st.info("Waiting for Mission Control to reveal your team...")


def show_remote():
    st.title("🎛️ Mission Remote")
    st.caption("This is the facilitator tablet control panel.")

    if st.button("← Back to Studio"):
        go_to("studio")

    st.divider()

    col_status_1, col_status_2, col_status_3 = st.columns(3)
    col_status_1.metric("Current Stage", get_current_stage())
    col_status_2.metric("Participants Joined", len(st.session_state["participants"]))
    col_status_3.metric("Teams", get_number_of_teams())

    st.divider()

    if st.button("🎲 Smart Shuffle + Reveal Teams", use_container_width=True):
        if len(st.session_state["participants"]) == 0:
            st.warning("No participants have joined yet.")
        else:
            reveal_teams()

    if st.button("🔄 Reset Team Reveal", use_container_width=True):
        reset_teams()

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("⬅️ Previous Stage", use_container_width=True):
            previous_stage()

        st.button("📢 Announcement", use_container_width=True)

    with col2:
        if st.button("➡️ Next Stage", use_container_width=True):
            next_stage()

        st.button("🚨 Emergency Stop", use_container_width=True)

    st.divider()
    show_team_assignments()

    st.divider()
    show_stage_timeline()


if st.session_state["page"] == "studio":
    show_studio()
elif st.session_state["page"] == "mission_setup":
    show_mission_setup()
elif st.session_state["page"] == "mission_control":
    show_mission_control()
elif st.session_state["page"] == "participant":
    show_participant()
elif st.session_state["page"] == "remote":
    show_remote()
