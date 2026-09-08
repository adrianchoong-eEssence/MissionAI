#!/usr/bin/env python3
"""Generate a reviewable AIA candidate setup package; never connects to Supabase."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_packs.aia_techquest_20261023_v1.materialize import materialize_aia_techquest_content
from services.personal_key_credentials import derive_personal_key_credential, team_formation_credential_hash

DEFAULT_CERT_EVENT_ID = "AIA-TECH-20261023-UAT"
DEFAULT_CERT_JOIN_CODE = "AIAUAT"
ACTOR = "aia_techquest_uat_setup"


def _literal(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _json(value: object) -> str:
    return _literal(json.dumps(value, separators=(",", ":"))) + "::jsonb"


def synthetic_roster(event_id: str, *, team_count: int = 25, capacity: int = 10) -> list[dict]:
    """Create disposable, non-human certification identities and never emit their keys."""
    rows = []
    for number in range(1, team_count * capacity + 1):
        team = (number - 1) // capacity + 1
        key = f"Q{number:05d}"  # six characters; deterministic only for a disposable fixture.
        rows.append({"DisplayName": f"AIA Certification {number:03d}", "TeamID": f"{event_id}-TEAM-{team:02d}",
                     "EnrollmentCredentialHash": team_formation_credential_hash(derive_personal_key_credential(event_id, key))})
    return rows


def owner_test_account(event_id: str = DEFAULT_CERT_EVENT_ID) -> dict[str, str]:
    """Return the one disclosed UAT account; do not publish the remaining keys."""
    return {"Name": "AIA Certification 001", "Team": f"{event_id}-TEAM-01", "PersonalKey": "Q00001"}


def build_setup_sql(event_id: str = DEFAULT_CERT_EVENT_ID, join_code: str = DEFAULT_CERT_JOIN_CODE) -> str:
    content = materialize_aia_techquest_content(event_id)
    teams, roster, missions = content["TeamTemplates"], synthetic_roster(event_id), content["Missions"]
    if len(roster) != 250 or len({row["EnrollmentCredentialHash"] for row in roster}) != 250:
        raise ValueError("Certification roster must contain 250 distinct opaque credentials.")
    capacities = content["TeamCapacities"]
    mission_rows = []
    programme_id, module_id = f"{event_id}-PROGRAMME", f"{event_id}-MISSION-BOARD"
    for mission in missions:
        station = {"Enabled": True, "DisplayOrder": mission["DisplayOrder"], "DisplayName": mission["DisplayName"],
                   "MissionClass": mission["MissionClass"], "EvidenceType": mission["EvidenceType"],
                   "AIHelpEnabled": True,
                   "Evidence": mission["Evidence"],
                   "ParticipationProrated": mission["ParticipationProrated"], "ScoringMode": mission["ScoringMode"], "Rubric": mission["Rubric"], "Scoring": mission["Scoring"],
                   "RideParticipation": mission["RideParticipation"], "ReviewRequired": True,
                   "ContentStatus": mission["ContentStatus"], "SafetyNote": "Facilitator must confirm safe, permitted mission placement before enabling."}
        mission_rows.append("(" + ",".join((_literal(mission["ActivityID"]), _literal(module_id), _literal(programme_id),
            "'MISSION'::public.exos_v2_activity_type", "'TEAM_COMPETITIVE'::public.exos_v2_scoring_mode", _literal(mission["DisplayName"]),
            str(mission["DisplayOrder"]), "0", _json({"race_station": station}), "true")) + ")")
    mission_values = ",\n".join(mission_rows)
    team_rows = [{"team_id": team["TeamID"], "team_name": team["TeamName"], "country": "", "team_flag": ""} for team in teams]
    metadata = {"Client": "AIA Tech", "Venue": "Genting SkyWorlds / GICC", "EventDate": "2026-10-23", "ExpectedParticipants": 250,
                "UAT": True, "SyntheticRoster": True, "SyntheticTeamWarning": "UAT ONLY — 25 teams × 10 is not the final AIA grouping decision.", "PersonalKeyExperience": {"SchemaVersion": 1},
                "TeamIdentityConfig": {"ThemeType": "CONFIGURABLE", "Identities": teams}}
    return f"""-- GENERATED AIA DISPOSABLE UAT. Review and owner-authorise before execution.
-- Contains only one disposable event and opaque enrollment hashes; source credentials are never emitted.
begin;
do $guard$ begin
 if exists(select 1 from public.events_v2 where event_id={_literal(event_id)} or join_code={_literal(join_code)}) then raise exception 'AIA certification event or join code already exists'; end if;
end $guard$;
select public.exos_v2_publish_event({_literal(event_id)},{_literal(join_code)},'AIA Tech — TechQuest UAT (Synthetic)', {_json(team_rows)}, 'TEAM_COMPETITIVE'::public.exos_v2_scoring_mode,'STANDARD');
update public.events_v2 set event_payload=coalesce(event_payload,'{{}}'::jsonb)||{_json(metadata)},lifecycle_status='PUBLISHED',updated_at=now() where event_id={_literal(event_id)};
select public.exos_v2_configure_team_formation({_literal(event_id)},'PREASSIGNED', {_json(capacities)}, {_json(roster)}, {_literal(ACTOR)});
insert into public.programmes_v2(programme_id,event_id,programme_name,programme_type,programme_schema_version,module_count,is_active,published_at) values({_literal(programme_id)},{_literal(event_id)},'AIA TechQuest UAT — Configurable Content','THEME_PARK_RACE',1,1,true,now());
insert into public.modules_v2(module_id,programme_id,module_name,activity_sequence,module_payload,scoring_mode,is_active) values({_literal(module_id)},{_literal(programme_id)},'Mission AI Open Board',1,'{{}}'::jsonb,'TEAM_COMPETITIVE'::public.exos_v2_scoring_mode,true);
insert into public.activities_v2(activity_id,module_id,programme_id,activity_type,scoring_mode,activity_name,activity_order,duration_seconds,activity_payload,is_active) values
{mission_values};
select public.exos_v2_theme_park_race_save_configuration({_literal(event_id)}, {_json(content['RaceConfiguration'])}, {_literal(ACTOR)});
select public.exos_v2_open_team_formation({_literal(event_id)}, {_literal(ACTOR)});
select public.exos_v2_configure_attendance({_literal(event_id)}, {_literal(ACTOR)});
do $assert$ begin
 if (select count(*) from public.participants_v2 where event_id={_literal(event_id)} and not is_archived)<>250 then raise exception 'AIA synthetic roster assertion failed'; end if;
 if (select count(*) from public.teams_v2 where event_id={_literal(event_id)} and is_active)<>25 then raise exception 'AIA certification team assertion failed'; end if;
 if exists(select 1 from public.participants_v2 where event_id={_literal(event_id)} and participant_status<>'PREASSIGNED') then raise exception 'AIA preassigned status assertion failed'; end if;
 if coalesce((select event_payload #>> '{{Attendance,SchemaVersion}}' from public.events_v2 where event_id={_literal(event_id)}),'')<>'1' then raise exception 'AIA attendance configuration assertion failed'; end if;
end $assert$;
commit;
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-id", default=DEFAULT_CERT_EVENT_ID)
    parser.add_argument("--join-code", default=DEFAULT_CERT_JOIN_CODE)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "aia-techquest-uat.sql")
    parser.add_argument("--print-owner-test-account", action="store_true")
    args = parser.parse_args()
    sql = build_setup_sql(args.event_id.strip().upper(), args.join_code.strip().upper())
    args.output.write_text(sql, encoding="utf-8")
    print(f"AIA_UAT_SQL_READY event={args.event_id} participants=250 teams=25 raw_keys_emitted=0")
    if args.print_owner_test_account:
        print(json.dumps(owner_test_account(args.event_id.strip().upper()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
