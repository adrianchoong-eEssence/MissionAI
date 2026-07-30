"""Backfill EVT-0004 M01-M04 into the expanded event-mission schema.

This migration is additive and idempotent. It never writes MissionTemplates and
does not touch submissions, scores, credits, or media/evidence references.
"""

from data.google_sheets import GoogleSheetsDB


def migrate(db=None):
    database = db or GoogleSheetsDB()
    return database.backfill_event_mission_editor_fields(
        "EVT-0004", ["M01", "M02", "M03", "M04"],
    )


if __name__ == "__main__":
    print(migrate())
