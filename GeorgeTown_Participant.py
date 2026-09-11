"""Dedicated George Town WALK Hunt participant entrypoint."""
from branding import apply_branding, configure_page
from screens.hunt_participant import render_hunt_participant
from services.george_town_walk_hunt_event import george_town_walk_hunt_event

configure_page(layout="centered")
apply_branding(participant_pwa=True)
render_hunt_participant(event_id=george_town_walk_hunt_event()[0], join_code=george_town_walk_hunt_event()[1],
                        event_title="GEORGE TOWN · MISSION AI WALK HUNT")
