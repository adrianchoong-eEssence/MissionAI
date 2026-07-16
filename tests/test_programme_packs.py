import json
import unittest

from data.google_sheets import GoogleSheetsDB


class FakeWorksheet:
    def __init__(self, headers):
        self.headers = list(headers)
        self.appended = []

    def row_values(self, row_number):
        return list(self.headers)

    def append_row(self, values, value_input_option=None):
        self.appended.append(list(values))


class FakeRuntime:
    can_publish = True

    def __init__(self, players=None):
        self.players = list(players or [])
        self.configured = []
        self.marketplaces = []

    def get_players(self, event_id):
        return list(self.players)

    def get_credit_wallet_status(self, event_id):
        return {
            "Enabled": True,
            "Items": [{
                "ItemID": "PROP-01",
                "ItemName": "Props",
                "CreditCost": 100,
            }],
        }

    def configure_credit_wallet(self, event_id, enabled=True, reset=False):
        self.configured.append((event_id, enabled, reset))
        return {"Enabled": enabled}

    def publish_marketplace(self, event_id, items):
        self.marketplaces.append((event_id, list(items)))
        return {"ItemsPublished": len(items)}


class ProgrammePackTests(unittest.TestCase):
    def test_saves_event_as_reusable_pack(self):
        database = GoogleSheetsDB.__new__(GoogleSheetsDB)
        database.runtime = FakeRuntime()
        database.programme_packs = FakeWorksheet([
            "PackID",
            "PackName",
            "Description",
            "SourceEventID",
            "TeamsJSON",
            "MissionsJSON",
            "StagesJSON",
            "MarketplaceJSON",
            "CreditWalletEnabled",
            "Status",
            "Version",
            "CreatedAt",
            "UpdatedAt",
        ])
        database.get_event = lambda event_id: {
            "EventID": event_id,
            "EventName": "AIA Customer Contact",
        }
        database.get_programme_packs = lambda include_archived=False: []
        database.get_teams = lambda event_id: [{
            "TeamID": "TEAM-01",
            "TeamName": "Team Engage",
        }]
        database.get_event_missions = lambda event_id: [{
            "MissionID": "M01",
            "Title": "Signal in the Noise",
        }]
        database.get_programme_stages = lambda event_id: [{
            "StageNo": 1,
            "StageName": "Registration",
        }]
        database.generate_next_pack_id = lambda: "PACK-0001"
        database.clear_cache = lambda: None

        result = database.save_event_as_programme_pack(
            "EVT-0004",
            "AIA Customer Contact",
            "Innovate to Elevate",
        )

        self.assertEqual(result["PackID"], "PACK-0001")
        self.assertEqual(result["Teams"], 1)
        self.assertEqual(result["Missions"], 1)
        self.assertEqual(result["Stages"], 1)
        self.assertEqual(result["MarketplaceItems"], 1)
        saved = dict(zip(
            database.programme_packs.headers,
            database.programme_packs.appended[0],
        ))
        self.assertEqual(saved["CreditWalletEnabled"], "Yes")
        self.assertEqual(json.loads(saved["TeamsJSON"])[0]["TeamName"], "Team Engage")

    def test_installs_pack_into_empty_event(self):
        database = GoogleSheetsDB.__new__(GoogleSheetsDB)
        database.runtime = FakeRuntime()
        database.get_event = lambda event_id: {"EventID": event_id}
        database.get_programme_pack = lambda pack_id: {
            "PackID": pack_id,
            "PackName": "AIA Customer Contact",
            "Teams": [{"TeamID": "TEAM-01", "TeamName": "Team Engage"}],
            "Missions": [{"MissionID": "M01", "Title": "Mission One"}],
            "Stages": [{
                "StageNo": 1,
                "StageName": "Registration",
                "StageType": "Registration",
            }],
            "Marketplace": [{"ItemID": "PROP-01", "ItemName": "Props"}],
            "CreditWalletEnabled": True,
        }
        database.replace_event_teams = lambda event_id, teams: {
            "TeamsUpdated": len(teams),
        }
        database.replace_event_missions = lambda event_id, missions: len(missions)
        database.saved_stages = []
        database.save_programme_stages = (
            lambda event_id, stages: database.saved_stages.extend(stages)
        )
        database.published = []
        database.publish_event_to_runtime = (
            lambda event_id, reset_registration=False:
            database.published.append((event_id, reset_registration))
        )
        database.current_stage = None
        database.set_event_stage = (
            lambda event_id, stage: setattr(database, "current_stage", dict(stage))
        )
        database.clear_cache = lambda: None

        result = database.install_programme_pack("PACK-0001", "EVT-0010")

        self.assertEqual(result["Teams"], 1)
        self.assertEqual(result["Missions"], 1)
        self.assertEqual(result["Stages"], 1)
        self.assertEqual(result["MarketplaceItems"], 1)
        self.assertEqual(database.published, [("EVT-0010", True)])
        self.assertEqual(database.current_stage["StageName"], "Registration")

    def test_refuses_to_install_pack_with_live_participants(self):
        database = GoogleSheetsDB.__new__(GoogleSheetsDB)
        database.runtime = FakeRuntime(players=[{"Name": "Adrian"}])
        database.get_event = lambda event_id: {"EventID": event_id}
        database.get_programme_pack = lambda pack_id: {
            "PackID": pack_id,
            "Teams": [],
            "Missions": [],
            "Stages": [],
        }

        with self.assertRaisesRegex(ValueError, "Participants already exist"):
            database.install_programme_pack("PACK-0001", "EVT-0010")


if __name__ == "__main__":
    unittest.main()
