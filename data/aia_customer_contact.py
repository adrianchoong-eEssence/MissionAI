"""Reusable AIA Customer Contact programme pack."""


AIA_CUSTOMER_CONTACT_TEAMS = [
    {"TeamID": "AIA-01", "TeamName": "Team Engage"},
    {"TeamID": "AIA-02", "TeamName": "Team Connect"},
    {"TeamID": "AIA-03", "TeamName": "Team Empower"},
    {"TeamID": "AIA-04", "TeamName": "Team Innovate"},
    {"TeamID": "AIA-05", "TeamName": "Team Elevate"},
    {"TeamID": "AIA-06", "TeamName": "Team Excel"},
]


AIA_CUSTOMER_CONTACT_TEMPLATES = [
    {
        "TemplateID": "MT-AIA-MAI-SIGNAL",
        "Title": "Mission 1: Signal in the Noise",
        "Story": (
            "A customer has contacted AIA three times. The fragments are clear "
            "but the real need is hidden: app reset / policy due / called twice / "
            "still waiting / please do not make me repeat everything again."
        ),
        "ParticipantInstructions": (
            "You have 10 minutes. Identify: (1) what happened, (2) how the "
            "customer is likely feeling, and (3) the one outcome that would "
            "restore confidence. Submit one concise three-part response per team."
        ),
        "FacilitatorInstructions": (
            "Approve responses that recognise repeated effort, emotional "
            "frustration, clear ownership and an immediate next step."
        ),
        "LearningObjectives": (
            "Customer listening; empathy; problem definition; ownership; "
            "concise communication"
        ),
        "SubmissionType": "TEXT",
        "ScoringRule": (
            "Manual score out of 100: insight 30, empathy 25, practical action "
            "30, clarity 15."
        ),
        "Points": 100,
        "Clue": (
            "Listen below the words. The customer is asking for more than information."
        ),
        "Answer": (
            "The customer needs one person to own the issue, avoid repetition "
            "and confirm the immediate next step."
        ),
        "Hint1": "Separate the facts from the feelings.",
        "Hint2": "Look for the effort the customer has already made.",
        "Hint3": "Design one immediate action that rebuilds confidence.",
        "DebriefQuestions": (
            "What changed when you listened for the need beneath the words?; "
            "What does ownership sound like to a customer?"
        ),
        "AIHelpEnabled": "Yes",
        "Status": "ACTIVE",
        "Version": "1.0",
    },
    {
        "TemplateID": "MT-AIA-MAI-HUMAN",
        "Title": "Mission 2: Human × AI Decision Lab",
        "Story": (
            "The future contact centre succeeds when AI handles routine work "
            "and people bring judgement, empathy and creativity."
        ),
        "ParticipantInstructions": (
            "You have 10 minutes. Classify password reset, standard FAQ wording, "
            "call summary, next-best-action suggestion, suspected fraud, "
            "bereavement claim, identity-sensitive complaint and VIP escalation "
            "into AI HANDLES, AI ASSISTS A HUMAN, or HUMAN LEADS. Explain two "
            "difficult choices."
        ),
        "FacilitatorInstructions": (
            "Score the reasoning, recognition of risk and protection of empathy. "
            "Challenge automation without human accountability."
        ),
        "LearningObjectives": (
            "AI judgement; risk awareness; human value; decision quality; "
            "responsible innovation"
        ),
        "SubmissionType": "TEXT",
        "ScoringRule": (
            "Manual score out of 120: classification logic 40, reasoning 40, "
            "risk and empathy 25, clarity 15."
        ),
        "Points": 120,
        "Clue": (
            "Routine is not the same as low risk. Emotion is not the only reason "
            "a human should lead."
        ),
        "Answer": (
            "Automate routine work, use AI to support judgement, and keep humans "
            "accountable for sensitive, emotional or high-risk decisions."
        ),
        "Hint1": "Assess repetition, risk and emotional sensitivity.",
        "Hint2": "Ask where a human must remain accountable.",
        "Hint3": (
            "Use AI to create time for empathy, creativity and decision-making."
        ),
        "DebriefQuestions": (
            "Where did your team disagree?; Which task looked easy to automate "
            "but carried hidden risk?"
        ),
        "AIHelpEnabled": "Yes",
        "Status": "ACTIVE",
        "Version": "1.0",
    },
    {
        "TemplateID": "MT-AIA-MAI-FRICTION",
        "Title": "Mission 3: Friction Safari",
        "Story": (
            "Bayu Beach Resort becomes a living customer journey. Every space "
            "contains moments that make an experience easier, harder, warmer or "
            "more confusing."
        ),
        "ParticipantInstructions": (
            "You have 15 minutes. Use only permitted areas. Find one example of "
            "friction and one example of delight. Choose the more important "
            "insight and create one team photograph that clearly represents it."
        ),
        "FacilitatorInstructions": (
            "Define permitted and restricted zones after the venue reconnaissance. "
            "Approve evidence showing a real observation and customer relevance."
        ),
        "LearningObjectives": (
            "Observation; customer journey thinking; shared awareness; "
            "evidence-based insight; creativity"
        ),
        "SubmissionType": "PHOTO",
        "ScoringRule": (
            "Manual score out of 150: observation 50, customer relevance 40, "
            "clarity of evidence 30, creativity and teamwork 30."
        ),
        "Points": 150,
        "Clue": "Look at the venue through a first-time customer's eyes.",
        "Hint1": "Notice moments of waiting, uncertainty, effort or welcome.",
        "Hint2": "Ask what information a visitor needs at each transition.",
        "Hint3": "Choose one insight that could transfer to AIA customer contact.",
        "DebriefQuestions": (
            "What had become too familiar to notice?; How could AI reduce "
            "friction without removing human warmth?"
        ),
        "AIHelpEnabled": "Yes",
        "Status": "ACTIVE",
        "Version": "1.0",
    },
    {
        "TemplateID": "MT-AIA-MAI-ELEVATE",
        "Title": "Mission 4: Elevate the Moment",
        "Story": (
            "Innovation creates value when human insight and AI capability solve "
            "a real customer need together."
        ),
        "ParticipantInstructions": (
            "You have 15 minutes. Create a simple visual prototype showing the "
            "customer problem, what AI does, what the human does and the improved "
            "customer outcome. Photograph it with your team and submit it."
        ),
        "FacilitatorInstructions": (
            "Issue one A3 sheet and marker set per team. Approve only when the "
            "solution keeps meaningful human responsibility and clear customer value."
        ),
        "LearningObjectives": (
            "Rapid prototyping; human-centred innovation; collaboration; value "
            "creation; customer impact"
        ),
        "SubmissionType": "PHOTO",
        "ScoringRule": (
            "Manual score out of 180: customer problem 35, Human × AI design 55, "
            "customer value 45, creativity 25, team clarity 20."
        ),
        "Points": 180,
        "Clue": (
            "Do not start with technology. Start with the customer moment that "
            "needs to improve."
        ),
        "Hint1": "Name the customer problem in one sentence.",
        "Hint2": "Give AI a specific routine, analytical or assistive role.",
        "Hint3": (
            "Protect the human role in empathy, judgement or relationship-building."
        ),
        "DebriefQuestions": (
            "How did AI amplify rather than replace human value?; What would make "
            "this idea practical at AIA?"
        ),
        "AIHelpEnabled": "Yes",
        "Status": "ACTIVE",
        "Version": "1.0",
    },
    {
        "TemplateID": "MT-AIA-SYNC-CREATE",
        "Title": "SYNC AI: Create the Performance",
        "Story": (
            "Transform Innovation Credits, team ideas and an AI teammate into a "
            "performance that makes the future of customer contact memorable."
        ),
        "ParticipantInstructions": (
            "Purchase resources and create a 3–4 minute performance. Use your AI "
            "Facilitator for the concept, lyrics or chant, storyline, roles and "
            "rehearsal plan. Submit the title, theme, chorus and key message."
        ),
        "FacilitatorInstructions": (
            "Give each team a different theme. Confirm purchases before releasing "
            "physical items and enforce the technical-check deadline."
        ),
        "LearningObjectives": (
            "Creative confidence; storytelling; AI co-creation; resource decisions; "
            "inclusive teamwork"
        ),
        "SubmissionType": "TEXT",
        "ScoringRule": (
            "Preparation checkpoint only. Final judging occurs during the live performance."
        ),
        "Points": 0,
        "Clue": (
            "A strong performance has one clear message, a memorable hook and a "
            "role for every member."
        ),
        "Hint1": "Start with the message before writing lyrics.",
        "Hint2": "Give every person a visible or meaningful role.",
        "Hint3": "Use purchased resources to strengthen the story.",
        "DebriefQuestions": (
            "How did your credit choices shape the performance?; Where did AI "
            "accelerate creativity?"
        ),
        "AIHelpEnabled": "Yes",
        "Status": "ACTIVE",
        "Version": "1.0",
    },
    {
        "TemplateID": "MT-AIA-SYNC-PERFORM",
        "Title": "SYNC AI: Live Performance",
        "Story": (
            "Six teams. Six interpretations. One stage celebrating human creativity "
            "and artificial intelligence working together."
        ),
        "ParticipantInstructions": (
            "Perform for 3–4 minutes, include your AI-created song or chant, use "
            "only purchased resources and finish with one clear message for AIA "
            "Customer Contact. Submit one final team photograph."
        ),
        "FacilitatorInstructions": (
            "Run the published order, 60-second changeovers and one judging rubric. "
            "Score message, Human × AI integration, creativity, participation and impact."
        ),
        "LearningObjectives": (
            "Confidence; performance; collective creativity; message discipline; celebration"
        ),
        "SubmissionType": "PHOTO",
        "ScoringRule": (
            "Manual score out of 100: message 25, Human × AI integration 20, "
            "creativity 20, participation 20, audience impact 15."
        ),
        "Points": 100,
        "Clue": "Make the audience remember one message.",
        "Hint1": "Open with energy and clarity.",
        "Hint2": "Make the chorus easy for the audience to understand.",
        "Hint3": "End together on the customer-impact message.",
        "DebriefQuestions": (
            "What made the performance feel genuinely human?; How did AI support "
            "rather than dominate the team?"
        ),
        "AIHelpEnabled": "Yes",
        "Status": "ACTIVE",
        "Version": "1.0",
    },
    {
        "TemplateID": "MT-CATALYST",
        "Title": "Creating Enterprise Success: Catalyst Challenge",
        "Story": (
            "Each team builds one part of a larger system. Enterprise success "
            "depends on every connection working at the right moment."
        ),
        "ParticipantInstructions": (
            "Build and test your assigned section. Integrate it with the other "
            "teams and complete the full enterprise chain reaction."
        ),
        "FacilitatorInstructions": (
            "Mark Completed only after an end-to-end run reaches the agreed outcome."
        ),
        "LearningObjectives": (
            "Systems thinking; integration; interdependence; enterprise execution"
        ),
        "SubmissionType": "CATALYST",
        "ScoringRule": "Completed = 100 points; Not completed = 0 points.",
        "Points": 100,
        "Clue": "Optimise the connections between teams, not only each section.",
        "Hint1": "Agree on every section's input and output.",
        "Hint2": "Test interfaces before attempting the full run.",
        "Hint3": "Trace failures from the final outcome backwards.",
        "DebriefQuestions": (
            "Where did integration fail?; What enabled the enterprise chain to succeed?"
        ),
        "AIHelpEnabled": "Yes",
        "Status": "ACTIVE",
        "Version": "1.0",
    },
]


AIA_CUSTOMER_CONTACT_MISSION_PLAN = [
    {"TemplateID": "MT-AIA-MAI-SIGNAL", "MissionID": "M01", "DurationMinutes": 10, "IncludeDebrief": False},
    {"TemplateID": "MT-AIA-MAI-HUMAN", "MissionID": "M02", "DurationMinutes": 10, "IncludeDebrief": False},
    {"TemplateID": "MT-AIA-MAI-FRICTION", "MissionID": "M03", "DurationMinutes": 15, "IncludeDebrief": False},
    {"TemplateID": "MT-AIA-MAI-ELEVATE", "MissionID": "M04", "DurationMinutes": 15, "IncludeDebrief": False},
    {"TemplateID": "MT-AIA-SYNC-CREATE", "MissionID": "S01", "DurationMinutes": 70, "IncludeDebrief": False},
    {"TemplateID": "MT-AIA-SYNC-PERFORM", "MissionID": "S02", "DurationMinutes": 60, "IncludeDebrief": False},
    {"TemplateID": "MT-CATALYST", "MissionID": "C01", "DurationMinutes": 120, "IncludeDebrief": False},
]


AIA_CUSTOMER_CONTACT_MARKETPLACE = [
    {"ItemID": "AIA-PROPS", "ItemName": "Props & Accessories Pack", "Description": "A mixed prop pack for the SYNC AI performance.", "CreditCost": 100, "StockQuantity": 6, "Active": True, "Position": 1},
    {"ItemID": "AIA-COSTUME", "ItemName": "Costume Accent Pack", "Description": "Simple costume pieces or character accessories.", "CreditCost": 120, "StockQuantity": 6, "Active": True, "Position": 2},
    {"ItemID": "AIA-MUSIC", "ItemName": "Music & SFX Support", "Description": "Facilitator support for music playback or sound effects.", "CreditCost": 80, "StockQuantity": 6, "Active": True, "Position": 3},
    {"ItemID": "AIA-SPECIAL-FX", "ItemName": "Special Effects Pack", "Description": "A limited visual-effects pack for added stage impact.", "CreditCost": 150, "StockQuantity": 3, "Active": True, "Position": 4},
    {"ItemID": "AIA-TIME", "ItemName": "Five-Minute Time Extender", "Description": "Five additional rehearsal minutes before technical check.", "CreditCost": 100, "StockQuantity": 6, "Active": True, "Position": 5},
    {"ItemID": "AIA-COACH", "ItemName": "Creative Coaching Pass", "Description": "Five minutes of focused facilitator coaching.", "CreditCost": 60, "StockQuantity": 12, "Active": True, "Position": 6},
]


AIA_CUSTOMER_CONTACT_STAGES = [
    {"StageNo": 1, "StartTime": "08:45", "DurationMinutes": 15, "StageName": "Registration", "StageType": "Registration", "MissionID": "", "DisplayMode": "Registration", "ParticipantMessage": "Register, meet your assigned team and prepare for the experience.", "FacilitatorInstruction": "Monitor registration and help participants locate their teams.", "IsActive": "Yes"},
    {"StageNo": 2, "StartTime": "09:00", "DurationMinutes": 15, "StageName": "Team Formation", "StageType": "TeamDiscovery", "MissionID": "", "DisplayMode": "Registration", "ParticipantMessage": "Find your team and create your team identity.", "FacilitatorInstruction": "Confirm six complete teams and introduce each AI Facilitator.", "IsActive": "Yes"},
    {"StageNo": 3, "StartTime": "09:15", "DurationMinutes": 45, "StageName": "Bridge of Trust", "StageType": "Activity", "MissionID": "", "DisplayMode": "Collaboration", "ParticipantMessage": "Build trust, connection and communication with your new team.", "FacilitatorInstruction": "Run Bridge of Trust and connect the experience to psychological safety.", "IsActive": "Yes"},
    {"StageNo": 4, "StartTime": "10:00", "DurationMinutes": 5, "StageName": "Mission AI Briefing", "StageType": "MissionBriefing", "MissionID": "", "DisplayMode": "Current Mission", "ParticipantMessage": "Four missions. One AI teammate. Earn Innovation Credits together.", "FacilitatorInstruction": "Explain submissions, controlled hints, scoring and the 60-minute mission clock.", "IsActive": "Yes"},
    {"StageNo": 5, "StartTime": "10:05", "DurationMinutes": 10, "StageName": "Signal in the Noise", "StageType": "MissionActive", "MissionID": "M01", "DisplayMode": "Current Mission", "ParticipantMessage": "Listen beneath the words and restore customer confidence.", "FacilitatorInstruction": "Launch M01 and announce a two-minute warning.", "IsActive": "Yes"},
    {"StageNo": 6, "StartTime": "10:15", "DurationMinutes": 10, "StageName": "Human × AI Decision Lab", "StageType": "MissionActive", "MissionID": "M02", "DisplayMode": "Current Mission", "ParticipantMessage": "Decide what AI handles, assists or leaves to human leadership.", "FacilitatorInstruction": "Launch M02 and challenge unsafe or empathy-blind automation.", "IsActive": "Yes"},
    {"StageNo": 7, "StartTime": "10:25", "DurationMinutes": 15, "StageName": "Friction Safari", "StageType": "MissionActive", "MissionID": "M03", "DisplayMode": "Current Mission", "ParticipantMessage": "Observe Bayu Beach through a first-time customer's eyes.", "FacilitatorInstruction": "Launch M03 only after confirming permitted venue zones and safety controls.", "IsActive": "Yes"},
    {"StageNo": 8, "StartTime": "10:40", "DurationMinutes": 15, "StageName": "Elevate the Moment", "StageType": "MissionActive", "MissionID": "M04", "DisplayMode": "Current Mission", "ParticipantMessage": "Turn a real customer friction point into a Human × AI solution.", "FacilitatorInstruction": "Issue A3 materials, launch M04 and prepare the rapid gallery review.", "IsActive": "Yes"},
    {"StageNo": 9, "StartTime": "10:55", "DurationMinutes": 15, "StageName": "Mission AI Debrief", "StageType": "Debrief", "MissionID": "M04", "DisplayMode": "Credit Leaderboard", "ParticipantMessage": "Connect the mission insights to customer contact and human value.", "FacilitatorInstruction": "Debrief listening, judgement, friction and Human × AI value creation.", "IsActive": "Yes"},
    {"StageNo": 10, "StartTime": "14:00", "DurationMinutes": 20, "StageName": "SYNC AI Innovation Market", "StageType": "Marketplace", "MissionID": "", "DisplayMode": "Credit Leaderboard", "ParticipantMessage": "Spend Innovation Credits strategically on your performance resources.", "FacilitatorInstruction": "Open the marketplace and release only purchased items.", "IsActive": "Yes"},
    {"StageNo": 11, "StartTime": "14:20", "DurationMinutes": 70, "StageName": "SYNC AI Create & Rehearse", "StageType": "MissionActive", "MissionID": "S01", "DisplayMode": "Current Mission", "ParticipantMessage": "Create your Human × AI story, song or chant and rehearse every role.", "FacilitatorInstruction": "Launch S01, monitor safety and run the technical check deadline.", "IsActive": "Yes"},
    {"StageNo": 12, "StartTime": "15:30", "DurationMinutes": 60, "StageName": "SYNC AI Performance & Judging", "StageType": "MissionActive", "MissionID": "S02", "DisplayMode": "Leaderboard", "ParticipantMessage": "Perform, inspire and make one customer-impact message memorable.", "FacilitatorInstruction": "Launch S02 and run six performances with 60-second changeovers.", "IsActive": "Yes"},
    {"StageNo": 13, "StartTime": "16:30", "DurationMinutes": 15, "StageName": "Day 1 Celebration", "StageType": "Closing", "MissionID": "", "DisplayMode": "Winner", "ParticipantMessage": "Celebrate creativity, collaboration and Human × AI confidence.", "FacilitatorInstruction": "Recognise teams, freeze Day 1 credits and close the day.", "IsActive": "Yes"},
    {"StageNo": 14, "StartTime": "09:00", "DurationMinutes": 120, "StageName": "Catalyst Challenge", "StageType": "MissionActive", "MissionID": "C01", "DisplayMode": "Current Mission", "ParticipantMessage": "Build one connected enterprise system across all six teams.", "FacilitatorInstruction": "Launch C01 and test both team sections and end-to-end integration.", "IsActive": "Yes"},
    {"StageNo": 15, "StartTime": "11:00", "DurationMinutes": 60, "StageName": "Debrief & Action Plan", "StageType": "Debrief", "MissionID": "C01", "DisplayMode": "Collaboration", "ParticipantMessage": "Turn two days of experience into practical commitments.", "FacilitatorInstruction": "Debrief systems thinking and complete personal and team action plans.", "IsActive": "Yes"},
    {"StageNo": 16, "StartTime": "12:00", "DurationMinutes": 15, "StageName": "Programme Closing", "StageType": "Closing", "MissionID": "", "DisplayMode": "Winner", "ParticipantMessage": "Together, we innovate. Together, we elevate.", "FacilitatorInstruction": "Close with commitments, recognition and next steps.", "IsActive": "Yes"},
]


def install_aia_customer_contact_pack(db, event_id):
    """Install the complete pack into an empty event and publish its runtime."""
    clean_event_id = str(event_id).strip()
    if not db.get_event(clean_event_id):
        raise ValueError(f"Event {clean_event_id} was not found.")

    runtime_players = (
        db.runtime.get_players(clean_event_id)
        if db.runtime.can_publish
        else []
    )
    if runtime_players:
        raise ValueError(
            "Participants already exist. Export or clear them before replacing "
            "teams and the programme."
        )

    team_result = db.replace_event_teams(
        clean_event_id,
        AIA_CUSTOMER_CONTACT_TEAMS,
    )
    first_publish = db.publish_event_to_runtime(
        clean_event_id,
        reset_registration=True,
    )
    template_result = db.import_mission_templates(
        AIA_CUSTOMER_CONTACT_TEMPLATES,
    )
    programme_result = db.build_event_programme(
        event_id=clean_event_id,
        mission_plan=AIA_CUSTOMER_CONTACT_MISSION_PLAN,
        start_time="08:45",
        include_registration=False,
        include_team_discovery=False,
        debrief_minutes=0,
        include_marketplace=False,
        include_closing=False,
    )
    db.save_programme_stages(
        clean_event_id,
        AIA_CUSTOMER_CONTACT_STAGES,
    )
    db.set_event_stage(
        clean_event_id,
        AIA_CUSTOMER_CONTACT_STAGES[0],
    )
    final_publish = db.publish_event_to_runtime(
        clean_event_id,
        reset_registration=True,
    )

    credit_result = {}
    marketplace_result = {}
    if db.runtime.can_publish:
        credit_result = db.runtime.configure_credit_wallet(
            clean_event_id,
            enabled=True,
            reset=True,
        )
        marketplace_result = db.runtime.publish_marketplace(
            clean_event_id,
            AIA_CUSTOMER_CONTACT_MARKETPLACE,
        )

    return {
        "EventID": clean_event_id,
        "Teams": team_result.get("TeamsUpdated", 0),
        "TemplatesCreated": template_result.get("Created", 0),
        "TemplatesUpdated": template_result.get("Updated", 0),
        "Missions": programme_result.get("Missions", 0),
        "Stages": len(AIA_CUSTOMER_CONTACT_STAGES),
        "MarketplaceItems": marketplace_result.get("ItemsPublished", 0),
        "RuntimePublished": bool(first_publish or final_publish),
        "CreditsEnabled": bool(credit_result),
    }
