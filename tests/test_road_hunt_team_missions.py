import unittest
from pathlib import Path


class RoadHuntTeamMissionMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = Path(
            "supabase/009_road_hunt_team_missions.sql"
        ).read_text(encoding="utf-8")

    def test_migration_exposes_session_bound_team_mission_feed(self):
        self.assertIn(
            "public.exos_road_hunt_missions",
            self.sql,
        )
        self.assertIn(
            "participant.session_token::text = trim(p_session_token)",
            self.sql,
        )
        self.assertIn("'AvailableMissions'", self.sql)
        self.assertIn("'NextStop'", self.sql)

    def test_migration_enforces_checkpoint_unlock_on_submission(self):
        self.assertIn(
            "runtime_submission_road_hunt_unlock",
            self.sql,
        )
        self.assertIn(
            "public.runtime_geofence_arrivals",
            self.sql,
        )
        self.assertIn(
            "Mission % is not unlocked for team %",
            self.sql,
        )

    def test_legacy_public_submission_rpc_is_revoked(self):
        self.assertIn(
            "from anon, authenticated;",
            self.sql,
        )
        self.assertIn(
            "to service_role;",
            self.sql,
        )


if __name__ == "__main__":
    unittest.main()
