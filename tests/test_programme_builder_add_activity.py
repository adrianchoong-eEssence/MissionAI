from engines.programme_hierarchy import build_programme_hierarchy
from screens.programme_builder import _add_activity


class PersistentProgrammeDB:
    def __init__(self, stages):
        self.stages = [dict(row) for row in stages]

    def save_programme_stages(self, event_id, stages):
        self.stages = [
            {**dict(stage), "EventID": event_id}
            for stage in stages
        ]

    def get_programme_stages(self, event_id):
        return [
            dict(stage)
            for stage in self.stages
            if stage.get("EventID") == event_id
        ]


def test_add_activity_persists_after_fresh_reload():
    event_id = "EVT-ENERGISER"
    db = PersistentProgrammeDB(
        [
            {
                "EventID": event_id,
                "StageNo": 1,
                "StartTime": "09:00",
                "DurationMinutes": 15,
                "StageName": "Energiser",
                "StageType": "MODULE::1::Energiser::Energiser",
                "MissionID": "",
                "DisplayMode": "Collaboration",
                "ParticipantMessage": "",
                "FacilitatorInstruction": "",
                "IsActive": "Yes",
            }
        ]
    )
    modules = build_programme_hierarchy(db.get_programme_stages(event_id))
    module = modules[0]

    activity = _add_activity(
        db,
        event_id,
        modules,
        module,
        "Quick Energiser",
        10,
    )

    assert activity["StageName"] == "Quick Energiser"
    assert activity["DurationMinutes"] == 10

    reopened_modules = build_programme_hierarchy(
        db.get_programme_stages(event_id)
    )
    reopened_activity = reopened_modules[0]["Activities"][-1]
    assert reopened_activity["StageName"] == "Quick Energiser"
    assert reopened_activity["DurationMinutes"] == 10
