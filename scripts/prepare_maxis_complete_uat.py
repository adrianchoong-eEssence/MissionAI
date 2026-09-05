#!/usr/bin/env python3
"""Emit the guarded, content-only Maxis complete-UAT configuration SQL.

The event and its canonical 68-person PREASSIGNED roster already exist.  This
tool only creates its programme/module/activity content and persists the
existing generic Theme Park Race configuration through the guarded RPC.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "content_packs/maxis_complete_uat_v1/maxis_complete_uat_v1.json"
ACTOR = "maxis_complete_uat_content_setup"


def load_pack(path: Path = PACK_PATH) -> dict:
    pack = json.loads(path.read_text(encoding="utf-8"))
    if pack.get("PackageKind") != "THEME_PARK_RACE_UAT_CONTENT":
        raise ValueError("Maxis UAT package kind is invalid.")
    if pack.get("EventID") != "MAXIS-UAT-PREASSIGNED":
        raise ValueError("Maxis UAT package event identity is invalid.")
    missions = pack.get("Missions")
    if not isinstance(missions, list) or not missions:
        raise ValueError("Maxis UAT package requires missions.")
    return pack


def validate_pack(pack: dict) -> None:
    config = pack["RaceConfiguration"]
    if config.get("EngineKind") != "THEME_PARK_RACE" or config.get("StrategyMode") != "OPEN_MISSION_BOARD":
        raise ValueError("Maxis UAT package must select THEME_PARK_RACE OPEN_MISSION_BOARD.")
    if config.get("RuntimePhase") != "READY":
        raise ValueError("Maxis UAT package must start READY.")
    if int(config.get("MissionBoard", {}).get("MaximumConcurrentSelections", 0)) < 2:
        raise ValueError("Maxis UAT must allow multiple simultaneous mission selections.")
    mission_ids = [str(mission.get("ActivityID", "")) for mission in pack["Missions"]]
    if len(mission_ids) != len(set(mission_ids)) or not all(mission_ids):
        raise ValueError("Maxis UAT mission ActivityIDs must be unique.")
    operations = config["MissionBoard"].get("MissionOperations", {})
    if set(operations) != set(mission_ids):
        raise ValueError("Each Maxis UAT mission must have exactly one board operation.")
    required = {"DisplayName", "MissionClass", "Zone", "LocationDescription", "ParticipantInstruction", "FacilitatorInstruction", "Evidence", "Scoring", "SafetyNote"}
    for mission in pack["Missions"]:
        missing = sorted(field for field in required if not mission.get(field))
        if missing:
            raise ValueError(f"{mission.get('ActivityID', 'mission')}: missing {', '.join(missing)}.")
        evidence = mission["Evidence"]
        for evidence_kind in ("Text", "Photo", "NumericResult"):
            if evidence_kind not in evidence or "Required" not in evidence[evidence_kind]:
                raise ValueError(f"{mission['ActivityID']}: incomplete {evidence_kind} evidence contract.")
        if mission["MissionClass"] == "RIDE":
            ride = mission.get("RideParticipation", {})
            if ride.get("RequiredPercent") != 80 or ride.get("Rounding") != "CEILING":
                raise ValueError(f"{mission['ActivityID']}: ride participation must remain 80% ceiling.")
            if ride.get("FullParticipationBonus") != 0:
                raise ValueError(f"{mission['ActivityID']}: full participation cannot alter score.")
    classes = {mission["MissionClass"] for mission in pack["Missions"]}
    if not {"RIDE", "STANDARD", "SECRET"} <= classes:
        raise ValueError("Maxis UAT requires rides, tasks and visible Secret Missions.")
    if sum(mission["MissionClass"] == "SECRET" for mission in pack["Missions"]) < 2:
        raise ValueError("Maxis UAT requires at least two visible Secret Missions.")


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _json(value: object) -> str:
    return _literal(json.dumps(value, ensure_ascii=False, separators=(",", ":"))) + "::jsonb"


def station_payload(mission: dict, display_order: int) -> dict:
    return {
        "race_station": {
            "Enabled": True,
            "DisplayOrder": display_order,
            "DisplayName": mission["DisplayName"],
            "MissionClass": mission["MissionClass"],
            "Zone": mission["Zone"],
            "LocationDescription": mission["LocationDescription"],
            "ParticipantInstruction": mission["ParticipantInstruction"],
            "FacilitatorInstruction": mission["FacilitatorInstruction"],
            "EvidenceType": mission.get("EvidenceType", "PHOTO" if mission["Evidence"].get("Photo", {}).get("Required") else "TEXT"),
            "Evidence": mission["Evidence"],
            "RideParticipation": mission.get("RideParticipation", {}),
            "PrivateReferenceImage": {"Required": False, "Visibility": "FACILITATOR_ONLY", "StorageReference": "", "Status": "NOT_REQUIRED"},
            "ReviewRequired": True,
            "Scoring": mission["Scoring"],
            "SafetyNote": mission["SafetyNote"],
            "CompletionState": {"OnSubmit": "SUBMITTED", "OnApprove": "APPROVED", "OnReject": "REJECTED"},
            "Resubmission": {"AllowedAfter": "REJECTED", "Mechanism": "EXISTING_SUBMISSION_REVISION"},
        }
    }


def build_setup_sql(pack: dict) -> str:
    validate_pack(pack)
    event_id = pack["EventID"]
    programme = pack["Programme"]
    programme_id = programme["ProgrammeID"]
    module_id = programme["ModuleID"]
    activity_values = []
    for index, mission in enumerate(pack["Missions"], 1):
        activity_values.append(
            "(" + ",".join((
                _literal(mission["ActivityID"]), _literal(module_id), _literal(programme_id),
                "'MISSION'::public.exos_v2_activity_type", "'TEAM_COMPETITIVE'::public.exos_v2_scoring_mode",
                _literal(mission["DisplayName"]), str(index), "0", _json(station_payload(mission, index)), "true",
            )) + ")"
        )
    activities_sql = ",\n".join(activity_values)
    return f"""-- Generated Maxis complete-UAT content loader. No schema changes.
begin;

do $guard$
begin
    if not exists (select 1 from public.events_v2 where event_id = {_literal(event_id)} and join_code = 'MXKEY7') then
        raise exception 'Maxis UAT event identity is unavailable';
    end if;
    if coalesce((select event_payload #>> '{{TeamFormation,Mode}}' from public.events_v2 where event_id = {_literal(event_id)}), '') <> 'PREASSIGNED'
       or coalesce((select event_payload #>> '{{TeamFormation,Phase}}' from public.events_v2 where event_id = {_literal(event_id)}), '') <> 'REGISTRATION_OPEN' then
        raise exception 'Maxis UAT must remain in canonical PREASSIGNED registration before content setup';
    end if;
    if exists (select 1 from public.programmes_v2 where event_id = {_literal(event_id)})
       or exists (select 1 from public.activity_runtime_v2 where event_id = {_literal(event_id)})
       or exists (select 1 from public.submissions_v2 where event_id = {_literal(event_id)}) then
        raise exception 'Maxis UAT already has programme or authoritative play state; refusing content setup';
    end if;
    if coalesce((select event_payload #>> '{{RaceConfiguration,EngineKind}}' from public.events_v2 where event_id = {_literal(event_id)}), '') not in ('', 'THEME_PARK_RACE') then
        raise exception 'Maxis UAT is owned by another race engine';
    end if;
end;
$guard$;

insert into public.programmes_v2(programme_id,event_id,programme_name,programme_type,programme_schema_version,module_count,is_active,published_at)
values ({_literal(programme_id)},{_literal(event_id)},{_literal(programme['ProgrammeName'])},'THEME_PARK_RACE',1,1,true,now());

insert into public.modules_v2(module_id,programme_id,module_name,activity_sequence,module_payload,scoring_mode,is_active)
values ({_literal(module_id)},{_literal(programme_id)},{_literal(programme['ModuleName'])},1,'{{"module_order":1,"day":1,"status":"Active"}}'::jsonb,'TEAM_COMPETITIVE'::public.exos_v2_scoring_mode,true);

insert into public.activities_v2(activity_id,module_id,programme_id,activity_type,scoring_mode,activity_name,activity_order,duration_seconds,activity_payload,is_active)
values
{activities_sql};

select public.exos_v2_theme_park_race_save_configuration(
    {_literal(event_id)},
    {_json(pack['RaceConfiguration'])},
    {_literal(ACTOR)}
);

do $assert$
begin
    if (select count(*) from public.activities_v2 where programme_id = {_literal(programme_id)} and is_active) <> {len(pack['Missions'])} then
        raise exception 'Maxis UAT mission count did not reconcile';
    end if;
    if coalesce((select event_payload #>> '{{RaceConfiguration,EngineKind}}' from public.events_v2 where event_id = {_literal(event_id)}), '') <> 'THEME_PARK_RACE'
       or coalesce((select event_payload #>> '{{RaceConfiguration,StrategyMode}}' from public.events_v2 where event_id = {_literal(event_id)}), '') <> 'OPEN_MISSION_BOARD'
       or coalesce((select event_payload #>> '{{RaceConfiguration,RuntimePhase}}' from public.events_v2 where event_id = {_literal(event_id)}), '') <> 'READY' then
        raise exception 'Maxis UAT RaceConfiguration did not reconcile';
    end if;
end;
$assert$;

commit;
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    pack = load_pack()
    validate_pack(pack)
    args.output.write_text(build_setup_sql(pack), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
