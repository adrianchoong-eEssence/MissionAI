"""Dedicated George Town WALK Hunt Mission Control entrypoint."""
from screens.hunt_mission_control import render_hunt_mission_control
from services.george_town_walk_hunt_event import george_town_walk_hunt_event

render_hunt_mission_control(george_town_walk_hunt_event()[0])
