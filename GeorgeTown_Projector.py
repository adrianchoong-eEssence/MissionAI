"""Dedicated public ENCA cumulative-score projector; no service key."""
from screens.enca_public_projector import render_enca_public_projector
from services.enca_george_town_event import enca_george_town_event

render_enca_public_projector(enca_george_town_event()[0])
