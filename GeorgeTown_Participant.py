"""Dedicated ENCA George Town hybrid participant entrypoint."""
from branding import apply_branding, configure_page
from screens.enca_george_town_participant import render_enca_george_town_participant
from services.enca_george_town_event import enca_george_town_event

configure_page(layout="centered")
apply_branding(participant_pwa=True)
render_enca_george_town_participant(event_id=enca_george_town_event()[0], join_code=enca_george_town_event()[1])
