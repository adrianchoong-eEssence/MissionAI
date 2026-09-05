#!/usr/bin/env python3
"""Generate the clean-state final Maxis live-event SQL package.

The package composes the already-certified eleven-mission UAT base with the
approved final two-mission delta.  It never reads or changes UAT runtime data,
and the generated SQL contains only event-scoped enrollment hashes — never
raw Personal Keys or derived credentials.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_maxis_personal_key_uat import (
    EXPECTED_COUNTS,
    TEAM_CONFIG,
    load_authoritative_roster,
)
from services.personal_key_credentials import (
    derive_personal_key_credential,
    team_formation_credential_hash,
)


BASE_PACK = ROOT / "content_packs/maxis_complete_uat_v1/maxis_complete_uat_v1.json"
DELTA_PACK = ROOT / "content_packs/maxis_final_content_delta_v1/maxis_final_content_delta_v1.json"
DEFAULT_EVENT_ID = "MAXIS-20260907-MISSION-AI"
DEFAULT_JOIN_CODE = "MAXIS7"
DEFAULT_EVENT_NAME = "Maxis Corporate & Mid-Market — Mission AI"
ACTOR = "maxis_live_event_setup"


def _literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _json(value: object) -> str:
    return _literal(json.dumps(value, ensure_ascii=False, separators=(",", ":"))) + "::jsonb"


def _replace_event_identity(value, old_event_id: str, event_id: str):
    if isinstance(value, dict):
        return {
            _replace_event_identity(key, old_event_id, event_id): _replace_event_identity(item, old_event_id, event_id)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_event_identity(item, old_event_id, event_id) for item in value]
    if isinstance(value, str):
        return value.replace(old_event_id, event_id)
    return value


def load_final_content(event_id: str = DEFAULT_EVENT_ID) -> dict:
    """Compose, validate and event-scope the approved 13-mission board."""
    base = json.loads(BASE_PACK.read_text(encoding="utf-8"))
    delta = json.loads(DELTA_PACK.read_text(encoding="utf-8"))
    old_event_id = str(base["EventID"])
    if delta.get("PackageKind") != "THEME_PARK_RACE_CONTENT_DELTA":
        raise ValueError("Maxis final content delta package kind is invalid.")
    if delta.get("EventID") != old_event_id:
        raise ValueError("Maxis final content delta does not match the certified base event identity.")
    resolved = _replace_event_identity(base, old_event_id, event_id)
    additions = _replace_event_identity(delta.get("Missions", []), old_event_id, event_id)
    if not isinstance(additions, list) or len(additions) != 2:
        raise ValueError("Maxis final content delta must contain Boot Camp and Mannequin only.")
    resolved["PackageKind"] = "THEME_PARK_RACE_FINAL_LIVE_CONTENT"
    resolved["EventID"] = event_id
    resolved["Programme"] = {
        "ProgrammeID": f"{event_id}-TPR-PROGRAMME",
        "ProgrammeName": DEFAULT_EVENT_NAME,
        "ModuleID": f"{event_id}-TPR-MODULE-01",
        "ModuleName": "Mission Board",
    }
    resolved["Missions"] = list(resolved["Missions"]) + additions
    operations = resolved["RaceConfiguration"]["MissionBoard"]["MissionOperations"]
    for mission in additions:
        operations[mission["ActivityID"]] = {"OperationalStatus": "AVAILABLE", "SecretState": "RELEASED"}
    resolved["ContentSources"] = {
        "Base": str(BASE_PACK.relative_to(ROOT)),
        "FinalDelta": str(DELTA_PACK.relative_to(ROOT)),
    }
    validate_final_content(resolved)
    return resolved


def validate_final_content(content: dict) -> None:
    config = content.get("RaceConfiguration", {})
    missions = list(content.get("Missions") or [])
    if config.get("EngineKind") != "THEME_PARK_RACE" or config.get("StrategyMode") != "OPEN_MISSION_BOARD":
        raise ValueError("Final Maxis content must select THEME_PARK_RACE OPEN_MISSION_BOARD.")
    if config.get("RuntimePhase") != "READY" or config.get("MissionBoard", {}).get("MaximumConcurrentSelections") != 3:
        raise ValueError("Final Maxis content must begin READY with three concurrent selections.")
    mission_ids = [str(mission.get("ActivityID", "")) for mission in missions]
    if len(missions) != 13 or not all(mission_ids) or len(mission_ids) != len(set(mission_ids)):
        raise ValueError("Final Maxis content requires exactly thirteen unique missions.")
    operations = config.get("MissionBoard", {}).get("MissionOperations", {})
    if set(operations) != set(mission_ids):
        raise ValueError("Every final mission requires exactly one board operation.")
    if sum(mission.get("MissionClass") == "RIDE" for mission in missions) != 4:
        raise ValueError("Final Maxis content requires four verified rides.")
    if sum(mission.get("MissionClass") == "SECRET" for mission in missions) != 3:
        raise ValueError("Final Maxis content requires three visible Secret Missions.")
    by_name = {mission.get("DisplayName"): mission for mission in missions}
    mannequin = by_name.get("Mannequin Challenge", {})
    boot_camp = by_name.get("Boot Camp Training", {})
    if mannequin.get("Scoring", {}).get("Maximum") != 140 or mannequin.get("EvidenceType") != "PHOTO_OR_VIDEO":
        raise ValueError("Mannequin Challenge evidence/score contract is invalid.")
    if boot_camp.get("Scoring", {}).get("Maximum") != 150 or boot_camp.get("Zone") != "Andromeda Base":
        raise ValueError("Boot Camp Training score/location contract is invalid.")
    for mission in missions:
        if mission.get("MissionClass") == "RIDE":
            ride = mission.get("RideParticipation", {})
            if ride.get("RequiredPercent") != 80 or ride.get("Rounding") != "CEILING":
                raise ValueError("Every verified ride must retain the 80% ceiling threshold.")


def _team_rows(event_id: str) -> list[dict]:
    return [
        {
            "team_id": f"{event_id}-TEAM-{number:02d}",
            "team_name": country,
            "country": country,
            "team_flag": flag,
        }
        for number, (country, flag, _greeting) in TEAM_CONFIG.items()
    ]


def _metadata(event_id: str) -> dict:
    return {
        "Client": "Maxis",
        "Venue": "Genting SkyWorlds",
        "EventDate": "2026-09-07",
        "NumberOfTeams": 6,
        "PersonalKeyExperience": {"SchemaVersion": 1, "CredentialDerivation": "EXOS_TEAM_FORMATION_PERSONAL_KEY_V1"},
        "TeamIdentityConfig": {
            "ThemeType": "COUNTRY", "ThemeName": "Countries",
            "Identities": [
                {"TeamID": f"{event_id}-TEAM-{number:02d}", "TeamIdentity": country,
                 "Country": country, "Emoji": flag, "Greeting": greeting}
                for number, (country, flag, greeting) in TEAM_CONFIG.items()
            ],
        },
    }


def _roster_payload(roster, event_id: str) -> list[dict]:
    return [
        {
            "EnrollmentCredentialHash": team_formation_credential_hash(
                derive_personal_key_credential(event_id, member.personal_key)
            ),
            "DisplayName": member.name,
            "TeamID": f"{event_id}-TEAM-{member.team_number:02d}",
        }
        for member in roster
    ]


def _station_payload(mission: dict, display_order: int) -> dict:
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
            "CompletionState": mission.get("CompletionState", {"OnSubmit": "SUBMITTED", "OnApprove": "APPROVED", "OnReject": "REJECTED"}),
            "Resubmission": mission.get("Resubmission", {"AllowedAfter": "REJECTED", "Mechanism": "EXISTING_SUBMISSION_REVISION"}),
        }
    }


def build_setup_sql(roster, content: dict, event_id: str, join_code: str, event_name: str) -> str:
    validate_final_content(content)
    if content["EventID"] != event_id:
        raise ValueError("Final content is not scoped to the requested event.")
    roster_payload = _roster_payload(roster, event_id)
    if len(roster_payload) != 68 or len({row["EnrollmentCredentialHash"] for row in roster_payload}) != 68:
        raise ValueError("Final roster hashes do not reconcile.")
    capacities = {f"{event_id}-TEAM-{number:02d}": count for number, count in EXPECTED_COUNTS.items()}
    programme = content["Programme"]
    activity_rows = []
    for order, mission in enumerate(content["Missions"], 1):
        activity_rows.append("(" + ",".join((
            _literal(mission["ActivityID"]), _literal(programme["ModuleID"]), _literal(programme["ProgrammeID"]),
            "'MISSION'::public.exos_v2_activity_type", "'TEAM_COMPETITIVE'::public.exos_v2_scoring_mode",
            _literal(mission["DisplayName"]), str(order), "0", _json(_station_payload(mission, order)), "true",
        )) + ")")
    activity_sql = ",\n".join(activity_rows)
    team_count_assertions = " union all ".join(
        f"select {_literal(f'{event_id}-TEAM-{number:02d}')}::text, {count}::bigint"
        for number, count in EXPECTED_COUNTS.items()
    )
    sql = f"""-- Generated final Maxis live-event setup. No raw or derived Personal Keys.
begin;

do $guard$
begin
    if exists (select 1 from public.events_v2 where event_id = {_literal(event_id)}) then
        raise exception 'Final Maxis event ID already exists';
    end if;
    if exists (select 1 from public.events_v2 where join_code = {_literal(join_code)}) then
        raise exception 'Final Maxis join code already exists';
    end if;
end;
$guard$;

select public.exos_v2_publish_event(
    {_literal(event_id)}, {_literal(join_code)}, {_literal(event_name)},
    {_json(_team_rows(event_id))}, 'TEAM_COMPETITIVE'::public.exos_v2_scoring_mode, 'STANDARD'
);

update public.events_v2
   set event_payload = coalesce(event_payload, '{{}}'::jsonb) || {_json(_metadata(event_id))},
       lifecycle_status = 'PUBLISHED', updated_at = now()
 where event_id = {_literal(event_id)};

select public.exos_v2_configure_team_formation(
    {_literal(event_id)}, 'PREASSIGNED', {_json(capacities)}, {_json(roster_payload)}, {_literal(ACTOR)}
);

insert into public.programmes_v2(programme_id,event_id,programme_name,programme_type,programme_schema_version,module_count,is_active,published_at)
values ({_literal(programme['ProgrammeID'])},{_literal(event_id)},{_literal(programme['ProgrammeName'])},'THEME_PARK_RACE',1,1,true,now());

insert into public.modules_v2(module_id,programme_id,module_name,activity_sequence,module_payload,scoring_mode,is_active)
values ({_literal(programme['ModuleID'])},{_literal(programme['ProgrammeID'])},{_literal(programme['ModuleName'])},1,'{{"module_order":1,"day":1,"status":"Active"}}'::jsonb,'TEAM_COMPETITIVE'::public.exos_v2_scoring_mode,true);

insert into public.activities_v2(activity_id,module_id,programme_id,activity_type,scoring_mode,activity_name,activity_order,duration_seconds,activity_payload,is_active)
values
{activity_sql};

select public.exos_v2_theme_park_race_save_configuration(
    {_literal(event_id)}, {_json(content['RaceConfiguration'])}, {_literal(ACTOR)}
);

select public.exos_v2_open_team_formation({_literal(event_id)}, {_literal(ACTOR)});

do $assert$
begin
    if (select count(*) from public.events_v2 where event_id = {_literal(event_id)} and join_code = {_literal(join_code)}) <> 1 then
        raise exception 'Final event identity assertion failed';
    end if;
    if coalesce((select event_payload #>> '{{TeamFormation,Mode}}' from public.events_v2 where event_id = {_literal(event_id)}), '') <> 'PREASSIGNED'
       or coalesce((select event_payload #>> '{{TeamFormation,Phase}}' from public.events_v2 where event_id = {_literal(event_id)}), '') <> 'REGISTRATION_OPEN' then
        raise exception 'Final event registration assertion failed';
    end if;
    if (select count(*) from public.participants_v2 where event_id = {_literal(event_id)} and not is_archived) <> 68
       or (select count(distinct enrollment_credential_hash) from public.participants_v2 where event_id = {_literal(event_id)} and not is_archived) <> 68 then
        raise exception 'Final event roster assertion failed';
    end if;
    if exists (select 1 from public.participants_v2 where event_id = {_literal(event_id)} and (participant_status <> 'PREASSIGNED' or enrollment_credential_hash !~ '^[0-9a-f]{{64}}$' or participant_payload::text ~* 'personal.?key|derived.?credential')) then
        raise exception 'Final event roster privacy assertion failed';
    end if;
    if exists (
        select 1 from ({team_count_assertions}) expected(team_id, expected_count)
        where (select count(*) from public.participants_v2 p where p.event_id = {_literal(event_id)} and p.team_id = expected.team_id and not p.is_archived) <> expected.expected_count
    ) then
        raise exception 'Final event country-count assertion failed';
    end if;
    if (select count(*) from public.activities_v2 where programme_id = {_literal(programme['ProgrammeID'])} and is_active) <> 13 then
        raise exception 'Final event mission-count assertion failed';
    end if;
    if coalesce((select event_payload #>> '{{RaceConfiguration,EngineKind}}' from public.events_v2 where event_id = {_literal(event_id)}), '') <> 'THEME_PARK_RACE'
       or coalesce((select event_payload #>> '{{RaceConfiguration,StrategyMode}}' from public.events_v2 where event_id = {_literal(event_id)}), '') <> 'OPEN_MISSION_BOARD'
       or coalesce((select event_payload #>> '{{RaceConfiguration,RuntimePhase}}' from public.events_v2 where event_id = {_literal(event_id)}), '') <> 'READY' then
        raise exception 'Final event race configuration assertion failed';
    end if;
    if exists (select 1 from public.activity_runtime_v2 where event_id = {_literal(event_id)})
       or exists (select 1 from public.submissions_v2 where event_id = {_literal(event_id)})
       or exists (select 1 from public.score_transactions_v2 where event_id = {_literal(event_id)})
       or exists (select 1 from public.team_access_sessions_v2 where event_id = {_literal(event_id)} and team_formation_captain_participant_id is not null) then
        raise exception 'Final event must remain clean before event-day lifecycle operations';
    end if;
end;
$assert$;

commit;
"""
    forbidden = [member.personal_key for member in roster] + [derive_personal_key_credential(event_id, member.personal_key) for member in roster]
    if any(value in sql for value in forbidden):
        raise RuntimeError("Generated live SQL contains a raw or derived credential.")
    return sql


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--event-id", default=DEFAULT_EVENT_ID)
    parser.add_argument("--join-code", default=DEFAULT_JOIN_CODE)
    parser.add_argument("--event-name", default=DEFAULT_EVENT_NAME)
    args = parser.parse_args()
    event_id, join_code = args.event_id.strip().upper(), args.join_code.strip().upper()
    roster = load_authoritative_roster(args.workbook)
    content = load_final_content(event_id)
    args.output.write_text(build_setup_sql(roster, content, event_id, join_code, args.event_name.strip()), encoding="utf-8")
    print("MAXIS_LIVE_EVENT_PACKAGE_READY participants=68 missions=13 raw_keys_emitted=0 derived_credentials_emitted=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
