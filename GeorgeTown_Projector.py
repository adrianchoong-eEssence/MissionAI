"""Dedicated public George Town WALK Hunt projector; no service key."""
from screens.hunt_public_projector import render_hunt_public_projector
from services.george_town_walk_hunt_event import george_town_walk_hunt_event

render_hunt_public_projector(george_town_walk_hunt_event()[0])
