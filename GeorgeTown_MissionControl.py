"""Dedicated ENCA George Town Mission Control entrypoint."""
from screens.hunt_mission_control import render_hunt_mission_control
from services.enca_george_town_event import enca_george_town_event

render_hunt_mission_control(enca_george_town_event()[0], event_title="ENCA · GEORGE TOWN MISSION CONTROL")
