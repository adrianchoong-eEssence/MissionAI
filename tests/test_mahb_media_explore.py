import unittest

from data.mahb_media_explore import (
    MAHB_MEDIA_EXPLORE_MISSION_PLAN,
    MAHB_MEDIA_EXPLORE_ROUTE,
    MAHB_MEDIA_EXPLORE_STAGES,
    MAHB_MEDIA_EXPLORE_TEAMS,
    MAHB_MEDIA_EXPLORE_TEMPLATES,
    install_mahb_media_explore_pack,
)


class FakeRuntime:
    can_publish = True

    def __init__(self, players=None):
        self.players = players or []
        self.route = []

    def get_players(self, event_id):
        return list(self.players)

    def configure_credit_wallet(self, event_id, enabled=True, reset=False):
        return {"Enabled": enabled, "Reset": reset}

    def configure_road_hunt(
        self,
        event_id,
        enabled=True,
        location_interval_seconds=20,
        reset=False,
    ):
        return {
            "Enabled": enabled,
            "Interval": location_interval_seconds,
            "Reset": reset,
        }

    def publish_road_hunt_route(self, event_id, stops):
        self.route = list(stops)
        return {"StopsPublished": len(self.route)}


class FakeDatabase:
    def __init__(self, players=None):
        self.runtime = FakeRuntime(players)
        self.saved_stages = []
        self.current_stage = None

    def get_event(self, event_id):
        return {"EventID": event_id, "EventName": "MAHB Media Explore"}

    def replace_event_teams(self, event_id, teams):
        self.teams = list(teams)
        return {"TeamsUpdated": len(self.teams)}

    def publish_event_to_runtime(self, event_id, reset_registration=False):
        return {"EventID": event_id, "Reset": reset_registration}

    def import_mission_templates(self, templates):
        self.templates = list(templates)
        return {"Created": len(self.templates), "Updated": 0, "Errors": []}

    def build_event_programme(self, **kwargs):
        self.mission_plan = list(kwargs["mission_plan"])
        return {"Missions": len(self.mission_plan)}

    def save_programme_stages(self, event_id, stages):
        self.saved_stages = list(stages)

    def set_event_stage(self, event_id, stage):
        self.current_stage = dict(stage)


class MAHBMediaExplorePackTests(unittest.TestCase):
    def test_pack_has_unique_identifiers_and_ordered_route(self):
        team_names = [row["TeamName"] for row in MAHB_MEDIA_EXPLORE_TEAMS]
        template_ids = [row["TemplateID"] for row in MAHB_MEDIA_EXPLORE_TEMPLATES]
        mission_ids = [row["MissionID"] for row in MAHB_MEDIA_EXPLORE_MISSION_PLAN]
        stop_ids = [row["StopID"] for row in MAHB_MEDIA_EXPLORE_ROUTE]
        positions = [row["Position"] for row in MAHB_MEDIA_EXPLORE_ROUTE]
        stage_numbers = [row["StageNo"] for row in MAHB_MEDIA_EXPLORE_STAGES]

        self.assertEqual(len(team_names), 10)
        self.assertEqual(len(team_names), len(set(team_names)))
        self.assertEqual(len(template_ids), len(set(template_ids)))
        self.assertEqual(len(mission_ids), len(set(mission_ids)))
        self.assertEqual(len(stop_ids), len(set(stop_ids)))
        self.assertEqual(positions, list(range(1, len(positions) + 1)))
        self.assertEqual(stage_numbers, list(range(1, len(stage_numbers) + 1)))

    def test_every_route_mission_exists_in_programme(self):
        mission_ids = {
            row["MissionID"]
            for row in MAHB_MEDIA_EXPLORE_MISSION_PLAN
        }
        route_mission_ids = {
            mission_id
            for stop in MAHB_MEDIA_EXPLORE_ROUTE
            for mission_id in stop["MissionIDs"]
        }

        self.assertEqual(route_mission_ids, mission_ids)

    def test_installer_publishes_complete_pack(self):
        db = FakeDatabase()

        result = install_mahb_media_explore_pack(db, "EVT-MAHB")

        self.assertEqual(result["Teams"], len(MAHB_MEDIA_EXPLORE_TEAMS))
        self.assertEqual(result["Missions"], len(MAHB_MEDIA_EXPLORE_MISSION_PLAN))
        self.assertEqual(result["Stages"], len(MAHB_MEDIA_EXPLORE_STAGES))
        self.assertEqual(result["RouteStops"], len(MAHB_MEDIA_EXPLORE_ROUTE))
        self.assertTrue(result["CreditsEnabled"])
        self.assertTrue(result["RoadHuntEnabled"])
        self.assertEqual(db.current_stage["StageName"], "Registration & Vehicle Check")
        self.assertEqual(db.runtime.route, MAHB_MEDIA_EXPLORE_ROUTE)

    def test_installer_refuses_to_replace_live_participants(self):
        db = FakeDatabase(players=[{"Name": "Adrian"}])

        with self.assertRaisesRegex(ValueError, "Participants already exist"):
            install_mahb_media_explore_pack(db, "EVT-MAHB")


if __name__ == "__main__":
    unittest.main()
