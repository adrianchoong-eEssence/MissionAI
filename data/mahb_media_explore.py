"""Ready-made MAHB Media Explore GPS Road Hunt programme pack."""


MAHB_MEDIA_EXPLORE_TEAMS = [
    {"TeamID": "MAHB-01", "TeamName": "Runway Rangers"},
    {"TeamID": "MAHB-02", "TeamName": "Terminal Titans"},
    {"TeamID": "MAHB-03", "TeamName": "Sky Navigators"},
    {"TeamID": "MAHB-04", "TeamName": "Gate Pioneers"},
    {"TeamID": "MAHB-05", "TeamName": "Airside Explorers"},
    {"TeamID": "MAHB-06", "TeamName": "Horizon Crew"},
    {"TeamID": "MAHB-07", "TeamName": "Flight Path"},
    {"TeamID": "MAHB-08", "TeamName": "Compass Crew"},
    {"TeamID": "MAHB-09", "TeamName": "Cloud Chasers"},
    {"TeamID": "MAHB-10", "TeamName": "Aero Catalysts"},
]


def _template(
    template_id,
    title,
    story,
    instructions,
    facilitator,
    objectives,
    submission_type,
    scoring_rule,
    points,
    clue,
    answer,
    hints,
    debrief,
):
    return {
        "TemplateID": template_id,
        "Title": title,
        "Story": story,
        "ParticipantInstructions": instructions,
        "FacilitatorInstructions": facilitator,
        "LearningObjectives": objectives,
        "SubmissionType": submission_type,
        "ScoringRule": scoring_rule,
        "Points": points,
        "Clue": clue,
        "Answer": answer,
        "Hint1": hints[0],
        "Hint2": hints[1],
        "Hint3": hints[2],
        "DebriefQuestions": debrief,
        "AIHelpEnabled": "Yes",
        "Status": "ACTIVE",
        "Version": "1.0",
    }


MAHB_MEDIA_EXPLORE_TEMPLATES = [
    _template(
        "MT-MAHB-IPOH-CAVE",
        "Ipoh 1: Hidden Cave Evidence",
        "The limestone landscape holds clues about time, change and resilience.",
        (
            "When your team reaches the approved Gua Tempurung meeting point, "
            "find a safe public viewpoint that represents resilience. Create one "
            "team photograph and a one-sentence caption connecting the image to "
            "how airport teams adapt under pressure. Stay in approved public areas."
        ),
        (
            "Confirm the safe parking and meeting point before launch. This is not "
            "a cave-entry task unless access, tickets and supervision were arranged."
        ),
        "Observation; resilience; metaphor; teamwork; safety awareness",
        "PHOTO",
        "Manual score out of 120: evidence 35, insight 35, creativity 25, teamwork and safety 25.",
        120,
        "Read the landscape as a story of pressure, time and adaptation.",
        "A safe team image with a clear resilience or adaptation insight.",
        (
            "Look for layers, openings, light or weathered stone.",
            "Connect the scene to change at work.",
            "The driver must not handle the phone while the vehicle is moving.",
        ),
        "What helped the team turn an unfamiliar environment into a useful insight?",
    ),
    _template(
        "MT-MAHB-IPOH-MIRROR",
        "Ipoh 2: Mirror Lake Perspective",
        "A change in perspective can reveal what was hidden in plain sight.",
        (
            "At the approved Tasik Cermin public zone, create one photograph using "
            "reflection, framing or perspective. Add a caption explaining what your "
            "team learned about seeing a familiar challenge differently. Follow all "
            "site instructions and do not enter restricted areas."
        ),
        "Verify the exact entrance, parking area, opening hours and group access before event day.",
        "Perspective-taking; creativity; shared observation; reframing",
        "PHOTO",
        "Manual score out of 120: perspective 40, insight 35, visual execution 25, teamwork 20.",
        120,
        "The strongest image may show two views at once.",
        "A reflection or perspective image with a meaningful workplace insight.",
        (
            "Use water, shadow or framing.",
            "Ask what becomes visible when the angle changes.",
            "Choose one caption that every team member supports.",
        ),
        "Where could a different perspective improve a real operational decision?",
    ),
    _template(
        "MT-MAHB-IPOH-VOICE",
        "Ipoh 3: Voice of the City",
        "Places become memorable through the people who bring them to life.",
        (
            "With clear permission, speak to a local business owner, worker or resident. "
            "Ask: What makes visitors feel genuinely welcome in Ipoh? Submit one quote, "
            "the team's interpretation and one idea that could improve a traveller's "
            "airport experience. Do not record names, images or audio without consent."
        ),
        "Remind teams that participation is voluntary and consent must be explicit.",
        "Listening; empathy; customer insight; respectful engagement",
        "TEXT",
        "Manual score out of 100: authentic insight 35, airport relevance 35, respect 15, clarity 15.",
        100,
        "Ask about welcome, not tourism facts.",
        "A consent-based local insight translated into an airport experience idea.",
        (
            "Introduce the team and explain the activity first.",
            "Listen for emotions and small gestures.",
            "Translate the quote into one practical action.",
        ),
        "What did the local perspective reveal that desk research would have missed?",
    ),
    _template(
        "MT-MAHB-IPOH-COFFEE",
        "Ipoh 4: White Coffee Story",
        "A simple product became part of Ipoh's identity through experience and story.",
        (
            "In an approved Ipoh Old Town area, find evidence of the white coffee story. "
            "Create a photograph that captures product, place and people without showing "
            "unconsenting individuals. Add one sentence explaining how a routine service "
            "can become a memorable brand experience. Purchase or consumption is optional."
        ),
        "Check dietary requirements and keep this mission observation-based; no purchase is required.",
        "Brand experience; service design; storytelling; observation",
        "PHOTO",
        "Manual score out of 80: story 30, brand insight 25, evidence 15, clarity 10.",
        80,
        "Look beyond the drink to the rituals and setting around it.",
        "An image and insight showing how a routine service becomes a distinctive experience.",
        (
            "Observe presentation, atmosphere and customer ritual.",
            "Ask what people remember after they leave.",
            "Connect the insight to an airport touchpoint.",
        ),
        "What makes an experience feel local, human and memorable?",
    ),
    _template(
        "MT-MAHB-IPOH-HERITAGE",
        "Ipoh 5: Heritage Explorer",
        "Old Town is a network of signs, stories and choices waiting to be decoded.",
        (
            "Within the approved Old Town zone, find three details from three categories: "
            "architecture, wayfinding and human activity. Submit the three observations "
            "and identify which one offers the strongest lesson for designing a clear and "
            "welcoming airport journey."
        ),
        "Define the permitted walking boundary and regroup point before releasing teams.",
        "Systems observation; wayfinding; prioritisation; customer journey thinking",
        "TEXT",
        "Manual score out of 120: observations 40, analysis 35, airport transfer 30, clarity 15.",
        120,
        "A journey is shaped by what people see, understand and do next.",
        "Three observations with one well-reasoned airport journey lesson.",
        (
            "Notice entrances, junctions and transitions.",
            "Look for both helpful and confusing signals.",
            "Prioritise the insight with the greatest customer impact.",
        ),
        "Which environmental signal most strongly influenced your team's behaviour?",
    ),
    _template(
        "MT-MAHB-IPOH-BONUS",
        "Ipoh Bonus: The Unexpected Welcome",
        "Great experiences often come from one small, unexpected detail.",
        (
            "Find one safe, legal and respectful example of an unexpected welcome in the "
            "approved Ipoh zone. Submit one team photograph and a caption of no more than "
            "20 words."
        ),
        "Use as an optional bonus. Reject unsafe, staged-without-consent or restricted-area evidence.",
        "Curiosity; concise storytelling; positive customer experience",
        "PHOTO",
        "Manual bonus out of 60: relevance 25, originality 20, clarity 15.",
        60,
        "Small details can carry a large emotional signal.",
        "A respectful example of a small detail that makes people feel welcome.",
        (
            "Look for gestures, signs or thoughtful design.",
            "Keep the caption short.",
            "Do not photograph identifiable people without consent.",
        ),
        "How could MAHB create more small moments of unexpected welcome?",
    ),
    _template(
        "MT-MAHB-GT-ART",
        "George Town 1: Street Art Story",
        "Public art turns a wall into a conversation between place and people.",
        (
            "In the approved George Town heritage zone, find one public artwork. Create a "
            "team photograph that interacts with it respectfully, then explain the story "
            "your image tells about connection, movement or travel. Do not block traffic "
            "or climb on protected structures."
        ),
        "Set a safe pedestrian boundary and remind teams to stay off the roadway.",
        "Visual storytelling; creativity; place awareness; teamwork",
        "PHOTO",
        "Manual score out of 120: story 35, creativity 35, place connection 25, safety 25.",
        120,
        "Let the team become part of the story rather than merely standing beside it.",
        "A safe, respectful image with a clear travel or connection narrative.",
        (
            "Plan the composition before taking the photograph.",
            "Give each person a purposeful role.",
            "Use the artwork's visual direction to guide the story.",
        ),
        "How did the physical environment help your team communicate an idea?",
    ),
    _template(
        "MT-MAHB-GT-STORIES",
        "George Town 2: Local Stories",
        "Heritage survives when people connect facts to meaning.",
        (
            "Find a public heritage marker or interpretation panel in the approved zone. "
            "Submit one fact, why it matters today and one question your team would ask a "
            "local expert. Use public information; do not enter private property."
        ),
        "Approve responses that distinguish an observed fact from the team's interpretation.",
        "Research; interpretation; curiosity; cultural respect",
        "TEXT",
        "Manual score out of 100: accurate fact 30, meaning 35, question quality 20, clarity 15.",
        100,
        "Do not collect facts only; ask why the story still matters.",
        "A sourced heritage fact, modern relevance and a thoughtful question.",
        (
            "Read the full marker before choosing the fact.",
            "Connect history to present-day experience.",
            "Ask a question that cannot be answered by the marker alone.",
        ),
        "How can organisations preserve identity while continuing to modernise?",
    ),
    _template(
        "MT-MAHB-GT-FLAVOUR",
        "George Town 3: Flavour Hunt",
        "Food journeys combine choice, anticipation, service and memory.",
        (
            "Observe one public food or beverage experience in the approved zone. Submit a "
            "photograph of the product, menu or setting and identify one design choice that "
            "makes ordering easier or more memorable. Purchase and consumption are optional."
        ),
        "Check dietary and allergy needs; never make consumption a condition of completion.",
        "Service observation; choice architecture; customer experience; inclusion",
        "PHOTO",
        "Manual score out of 80: observation 30, service insight 25, airport relevance 15, clarity 10.",
        80,
        "Study the experience before, during and after the purchase decision.",
        "A visible service-design choice with a clear customer experience insight.",
        (
            "Look at menus, queues, ordering and collection.",
            "Notice how uncertainty is reduced.",
            "Relate the insight to time-pressured travellers.",
        ),
        "What could airport F&B learn from a strong local food experience?",
    ),
    _template(
        "MT-MAHB-GT-PUZZLE",
        "George Town 4: Heritage Puzzle",
        "A good navigator notices patterns before choosing a direction.",
        (
            "Find three public clues in the approved heritage zone that represent different "
            "eras or influences. Submit the clues, the order your team placed them in and "
            "the reasoning behind that sequence."
        ),
        "Prepare an optional reference sheet after the route recce if the selected zone lacks clear markers.",
        "Pattern recognition; reasoning; collaborative decision-making; heritage awareness",
        "TEXT",
        "Manual score out of 120: clue quality 35, sequence logic 40, teamwork 20, clarity 25.",
        120,
        "Look for materials, languages, dates and architectural styles.",
        "Three observable clues arranged with coherent reasoning.",
        (
            "Photograph or note each clue before deciding.",
            "Separate evidence from assumptions.",
            "Explain why your order is more plausible than an alternative.",
        ),
        "How did your team handle uncertainty when the evidence was incomplete?",
    ),
    _template(
        "MT-MAHB-GT-CREATIVE",
        "George Town 5: The Traveller's Postcard",
        "Your team has one image to make a future visitor curious about the journey.",
        (
            "Create an original team postcard photograph in a safe public location. It must "
            "include every team member, one recognisable sense of place and a five-word "
            "message about the future of travel."
        ),
        "Reject photographs taken in roads, restricted sites or locations that obstruct the public.",
        "Creative direction; inclusion; concise communication; place branding",
        "PHOTO",
        "Manual score out of 150: concept 45, teamwork 35, sense of place 35, five-word message 35.",
        150,
        "Five words are enough when the image carries the rest of the story.",
        "An inclusive, safe team postcard with a clear five-word future-of-travel message.",
        (
            "Choose the five words before staging the image.",
            "Make every person part of the concept.",
            "Use depth, framing or repetition to strengthen the composition.",
        ),
        "What did the team remove or simplify to make the message stronger?",
    ),
    _template(
        "MT-MAHB-GT-BONUS",
        "George Town Bonus: Better Wayfinding",
        "The best navigators notice where other people may become uncertain.",
        (
            "Find one public decision point where a first-time visitor might hesitate. Submit "
            "a photograph and one practical wayfinding improvement. Do not photograph private "
            "information or identifiable people without consent."
        ),
        "Use as an optional bonus and prioritise observations relevant to transport environments.",
        "Wayfinding; empathy; rapid improvement; customer journey",
        "PHOTO",
        "Manual bonus out of 60: problem evidence 20, usefulness 25, clarity 15.",
        60,
        "Stand where a first-time visitor must decide what to do next.",
        "A clear decision-point problem and a practical improvement.",
        (
            "Look at junctions, entrances and transitions.",
            "Identify the exact decision a visitor must make.",
            "Propose one simple change, not a total redesign.",
        ),
        "Which wayfinding principle transfers most directly to an airport?",
    ),
    _template(
        "MT-MAHB-AIRPORT-INNOVATION",
        "Airport Finale 1: Innovation Lens",
        "The route ends where thousands of individual journeys connect every day.",
        (
            "From the facilitator-approved public landside area, identify one traveller need "
            "that could be better served through people, process or technology. Submit the "
            "need, the proposed improvement and how success would be measured. Do not enter "
            "restricted areas or record security procedures."
        ),
        "Use only a pre-approved public landside meeting zone and comply with airport security instructions.",
        "Innovation; traveller empathy; practical improvement; outcome measurement",
        "TEXT",
        "Manual score out of 120: traveller need 30, solution 40, feasibility 25, measure 25.",
        120,
        "Start with the traveller need, not the technology.",
        "A specific traveller need, feasible improvement and measurable outcome.",
        (
            "Observe without disrupting operations.",
            "Separate the symptom from the underlying need.",
            "Choose one measure a team could actually track.",
        ),
        "Which route insight most influenced your airport improvement idea?",
    ),
    _template(
        "MT-MAHB-AIRPORT-ARRIVAL",
        "Airport Finale 2: Crew Arrival",
        "Every successful route ends with the whole crew accounted for and ready to reflect.",
        (
            "At the facilitator-approved final meeting point, take one complete team photograph. "
            "Add one sentence naming the behaviour that helped your crew navigate the day safely "
            "and successfully."
        ),
        "Account for every participant before approving. Use the photograph only in accordance with event consent.",
        "Accountability; team reflection; safety; closure",
        "PHOTO",
        "Manual score out of 50: complete crew 20, reflection 20, safe completion 10.",
        50,
        "The finish line includes every member of the crew.",
        "A complete team image and one clear success behaviour.",
        (
            "Confirm all members are present.",
            "Choose one behaviour, not a list.",
            "Keep clear of passenger flows and operational areas.",
        ),
        "Which team behaviour should be carried into MAHB's daily operations?",
    ),
]


MAHB_MEDIA_EXPLORE_MISSION_PLAN = [
    {"TemplateID": "MT-MAHB-IPOH-CAVE", "MissionID": "I01", "DurationMinutes": 25, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-IPOH-MIRROR", "MissionID": "I02", "DurationMinutes": 25, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-IPOH-VOICE", "MissionID": "I03", "DurationMinutes": 25, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-IPOH-COFFEE", "MissionID": "I04", "DurationMinutes": 20, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-IPOH-HERITAGE", "MissionID": "I05", "DurationMinutes": 30, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-IPOH-BONUS", "MissionID": "I06", "DurationMinutes": 15, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-GT-ART", "MissionID": "G01", "DurationMinutes": 25, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-GT-STORIES", "MissionID": "G02", "DurationMinutes": 25, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-GT-FLAVOUR", "MissionID": "G03", "DurationMinutes": 20, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-GT-PUZZLE", "MissionID": "G04", "DurationMinutes": 25, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-GT-CREATIVE", "MissionID": "G05", "DurationMinutes": 25, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-GT-BONUS", "MissionID": "G06", "DurationMinutes": 15, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-AIRPORT-INNOVATION", "MissionID": "P01", "DurationMinutes": 20, "IncludeDebrief": False},
    {"TemplateID": "MT-MAHB-AIRPORT-ARRIVAL", "MissionID": "P02", "DurationMinutes": 10, "IncludeDebrief": False},
]


MAHB_MEDIA_EXPLORE_ROUTE = [
    {
        "StopID": "START",
        "Position": 1,
        "StopName": "MAHB Corporate Office — Flag Off",
        "Latitude": 2.7875009,
        "Longitude": 101.6743056,
        "RadiusMeters": 350,
        "MissionIDs": [],
        "Instructions": "Account for the full crew, complete the safety briefing and start GPS before flag off.",
        "Active": True,
    },
    {
        "StopID": "GUA",
        "Position": 2,
        "StopName": "Gua Tempurung — Approved Meeting Point",
        "Latitude": 4.416025,
        "Longitude": 101.187682,
        "RadiusMeters": 500,
        "MissionIDs": ["I01"],
        "Instructions": "Use only the pre-approved parking and public meeting zone. Cave entry is not assumed.",
        "Active": True,
    },
    {
        "StopID": "TASIK",
        "Position": 3,
        "StopName": "Tasik Cermin — Approved Visitor Zone",
        "Latitude": 4.5593,
        "Longitude": 101.1197,
        "RadiusMeters": 600,
        "MissionIDs": ["I02"],
        "Instructions": "Follow site opening hours, ticketing and safety rules. Reconfirm the exact meeting pin after route recce.",
        "Active": True,
    },
    {
        "StopID": "IPOH",
        "Position": 4,
        "StopName": "Ipoh Old Town — Heritage Zone",
        "Latitude": 4.5962,
        "Longitude": 101.07841,
        "RadiusMeters": 900,
        "MissionIDs": ["I03", "I04", "I05", "I06"],
        "Instructions": "Park legally, walk only within the facilitator-approved boundary and regroup at the published meeting point.",
        "Active": True,
    },
    {
        "StopID": "GEORGETOWN",
        "Position": 5,
        "StopName": "George Town — Armenian Street Heritage Zone",
        "Latitude": 5.414744,
        "Longitude": 100.338111,
        "RadiusMeters": 1200,
        "MissionIDs": ["G01", "G02", "G03", "G04", "G05", "G06"],
        "Instructions": "Use public pedestrian areas, respect heritage property and regroup before the airport transfer.",
        "Active": True,
    },
    {
        "StopID": "PEN",
        "Position": 6,
        "StopName": "Penang International Airport — Public Landside Finale",
        "Latitude": 5.295556,
        "Longitude": 100.272222,
        "RadiusMeters": 700,
        "MissionIDs": ["P01", "P02"],
        "Instructions": "Use only the pre-approved public landside meeting point. Do not enter or record restricted and security areas.",
        "Active": True,
    },
]


MAHB_MEDIA_EXPLORE_STAGES = [
    {"StageNo": 1, "StartTime": "07:30", "DurationMinutes": 15, "StageName": "Registration & Vehicle Check", "StageType": "Registration", "MissionID": "", "DisplayMode": "Registration", "ParticipantMessage": "Register, meet your crew and report to your assigned vehicle.", "FacilitatorInstruction": "Confirm attendance, vehicles, drivers, emergency contacts and team navigators.", "IsActive": "Yes"},
    {"StageNo": 2, "StartTime": "07:45", "DurationMinutes": 15, "StageName": "Safety & GPS Briefing", "StageType": "Briefing", "MissionID": "", "DisplayMode": "Collaboration", "ParticipantMessage": "Safety first: the driver never handles EXOS while the vehicle is moving.", "FacilitatorInstruction": "Brief route, emergency protocol, public conduct, GPS consent and navigator responsibilities.", "IsActive": "Yes"},
    {"StageNo": 3, "StartTime": "08:00", "DurationMinutes": 165, "StageName": "Flag Off & Travel to Ipoh", "StageType": "RoadHuntTravel", "MissionID": "", "DisplayMode": "Collaboration", "ParticipantMessage": "Start GPS, follow the approved route and drive safely to the first checkpoint.", "FacilitatorInstruction": "Release vehicles in sequence and monitor team location status without encouraging speeding.", "IsActive": "Yes"},
    {"StageNo": 4, "StartTime": "10:45", "DurationMinutes": 165, "StageName": "Ipoh Mission Circuit", "StageType": "RoadHuntMissions", "MissionID": "I01", "DisplayMode": "Current Mission", "ParticipantMessage": "Complete the approved Ipoh route missions and submit evidence through EXOS.", "FacilitatorInstruction": "Monitor Gua, Tasik Cermin and Old Town checkpoints; launch or validate I01–I06.", "IsActive": "Yes"},
    {"StageNo": 5, "StartTime": "13:30", "DurationMinutes": 45, "StageName": "Lunch & Crew Check", "StageType": "Break", "MissionID": "", "DisplayMode": "Credit Leaderboard", "ParticipantMessage": "Pause, refuel and confirm every crew member before departure.", "FacilitatorInstruction": "Check welfare, vehicle readiness and route timing before releasing teams.", "IsActive": "Yes"},
    {"StageNo": 6, "StartTime": "14:15", "DurationMinutes": 105, "StageName": "Travel to George Town", "StageType": "RoadHuntTravel", "MissionID": "", "DisplayMode": "Collaboration", "ParticipantMessage": "Travel safely to the George Town heritage checkpoint.", "FacilitatorInstruction": "Monitor route progress and contact delayed teams without creating time pressure.", "IsActive": "Yes"},
    {"StageNo": 7, "StartTime": "16:00", "DurationMinutes": 105, "StageName": "George Town Mission Circuit", "StageType": "RoadHuntMissions", "MissionID": "G01", "DisplayMode": "Current Mission", "ParticipantMessage": "Explore the approved heritage zone and complete the George Town missions.", "FacilitatorInstruction": "Monitor the walking boundary and validate G01–G06 submissions.", "IsActive": "Yes"},
    {"StageNo": 8, "StartTime": "17:45", "DurationMinutes": 30, "StageName": "Transfer to Penang Airport", "StageType": "RoadHuntTravel", "MissionID": "", "DisplayMode": "Credit Leaderboard", "ParticipantMessage": "Regroup, account for the crew and travel to the final checkpoint.", "FacilitatorInstruction": "Confirm every team has departed the heritage zone before moving operations to the airport.", "IsActive": "Yes"},
    {"StageNo": 9, "StartTime": "18:15", "DurationMinutes": 30, "StageName": "Airport Innovation Finale", "StageType": "RoadHuntMissions", "MissionID": "P01", "DisplayMode": "Current Mission", "ParticipantMessage": "Complete the final innovation and full-crew arrival missions in the public landside zone.", "FacilitatorInstruction": "Account for all participants and validate P01–P02 without disrupting airport operations.", "IsActive": "Yes"},
    {"StageNo": 10, "StartTime": "18:45", "DurationMinutes": 45, "StageName": "Debrief, Awards & Close", "StageType": "Closing", "MissionID": "P02", "DisplayMode": "Winner", "ParticipantMessage": "Connect the journey to teamwork, customer experience and the future of travel.", "FacilitatorInstruction": "Debrief route insights, announce awards and close only after the final headcount.", "IsActive": "Yes"},
]


def install_mahb_media_explore_pack(db, event_id):
    """Install and publish the complete GPS Road Hunt into an empty event."""
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
        MAHB_MEDIA_EXPLORE_TEAMS,
    )
    first_publish = db.publish_event_to_runtime(
        clean_event_id,
        reset_registration=True,
    )
    template_result = db.import_mission_templates(
        MAHB_MEDIA_EXPLORE_TEMPLATES,
    )
    programme_result = db.build_event_programme(
        event_id=clean_event_id,
        mission_plan=MAHB_MEDIA_EXPLORE_MISSION_PLAN,
        start_time="07:30",
        include_registration=False,
        include_team_discovery=False,
        debrief_minutes=0,
        include_marketplace=False,
        include_closing=False,
    )
    db.save_programme_stages(
        clean_event_id,
        MAHB_MEDIA_EXPLORE_STAGES,
    )
    db.set_event_stage(
        clean_event_id,
        MAHB_MEDIA_EXPLORE_STAGES[0],
    )
    final_publish = db.publish_event_to_runtime(
        clean_event_id,
        reset_registration=True,
    )

    credit_result = {}
    road_hunt_result = {}
    route_result = {}
    if db.runtime.can_publish:
        credit_result = db.runtime.configure_credit_wallet(
            clean_event_id,
            enabled=True,
            reset=True,
        )
        road_hunt_result = db.runtime.configure_road_hunt(
            clean_event_id,
            enabled=True,
            location_interval_seconds=20,
            reset=True,
        )
        route_result = db.runtime.publish_road_hunt_route(
            clean_event_id,
            MAHB_MEDIA_EXPLORE_ROUTE,
        )

    return {
        "EventID": clean_event_id,
        "Teams": team_result.get("TeamsUpdated", 0),
        "TemplatesCreated": template_result.get("Created", 0),
        "TemplatesUpdated": template_result.get("Updated", 0),
        "Missions": programme_result.get("Missions", 0),
        "Stages": len(MAHB_MEDIA_EXPLORE_STAGES),
        "RouteStops": route_result.get("StopsPublished", len(MAHB_MEDIA_EXPLORE_ROUTE)) if route_result else 0,
        "RuntimePublished": bool(first_publish or final_publish),
        "CreditsEnabled": bool(credit_result),
        "RoadHuntEnabled": bool(road_hunt_result),
    }
