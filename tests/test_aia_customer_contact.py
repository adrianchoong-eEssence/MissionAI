import unittest

from data.aia_customer_contact import (
    AIA_CUSTOMER_CONTACT_MARKETPLACE,
    AIA_CUSTOMER_CONTACT_MISSION_PLAN,
    AIA_CUSTOMER_CONTACT_STAGES,
    AIA_CUSTOMER_CONTACT_TEAMS,
    install_aia_customer_contact_pack,
)


class FakeRuntime:
    can_publish = True

    def __init__(self, players=None):
        self.players = players or []

    def get_players(self, event_id):
        return list(self.players)

    def configure_credit_wallet(self, event_id, enabled=True, reset=False):
        return {"Enabled": enabled, "Reset": reset}

    def publish_marketplace(self, event_id, items):
        return {"ItemsPublished": len(items)}


class FakeDatabase:
    def __init__(self, players=None):
        self.runtime = FakeRuntime(players)
        self.saved_stages = []
        self.current_stage = None

    def get_event(self, event_id):
        return {"EventID": event_id, "EventName": "AIA"}

    def replace_event_teams(self, event_id, teams):
        self.teams = list(teams)
        return {"TeamsUpdated": len(teams)}

    def publish_event_to_runtime(self, event_id, reset_registration=False):
        return {"EventID": event_id, "Reset": reset_registration}

    def import_mission_templates(self, templates):
        self.templates = list(templates)
        return {"Created": len(templates), "Updated": 0, "Errors": []}

    def build_event_programme(self, **kwargs):
        self.mission_plan = list(kwargs["mission_plan"])
        return {"Missions": len(self.mission_plan)}

    def save_programme_stages(self, event_id, stages):
        self.saved_stages = list(stages)

    def set_event_stage(self, event_id, stage):
        self.current_stage = dict(stage)


class AIACustomerContactPackTests(unittest.TestCase):
    def test_pack_has_unique_teams_missions_and_ordered_stages(self):
        team_names = [row["TeamName"] for row in AIA_CUSTOMER_CONTACT_TEAMS]
        mission_ids = [row["MissionID"] for row in AIA_CUSTOMER_CONTACT_MISSION_PLAN]
        stage_numbers = [row["StageNo"] for row in AIA_CUSTOMER_CONTACT_STAGES]

        self.assertEqual(len(team_names), 6)
        self.assertEqual(len(team_names), len(set(team_names)))
        self.assertEqual(len(mission_ids), len(set(mission_ids)))
        self.assertEqual(stage_numbers, list(range(1, len(stage_numbers) + 1)))

    def test_installer_publishes_complete_pack(self):
        db = FakeDatabase()

        result = install_aia_customer_contact_pack(db, "EVT-0004")

        self.assertEqual(result["Teams"], 6)
        self.assertEqual(result["Missions"], len(AIA_CUSTOMER_CONTACT_MISSION_PLAN))
        self.assertEqual(result["Stages"], len(AIA_CUSTOMER_CONTACT_STAGES))
        self.assertEqual(result["MarketplaceItems"], len(AIA_CUSTOMER_CONTACT_MARKETPLACE))
        self.assertEqual(db.current_stage["StageName"], "Registration")

    def test_installer_refuses_to_replace_live_participants(self):
        db = FakeDatabase(players=[{"Name": "Adrian"}])

        with self.assertRaisesRegex(ValueError, "Participants already exist"):
            install_aia_customer_contact_pack(db, "EVT-0004")


if __name__ == "__main__":
    unittest.main()
