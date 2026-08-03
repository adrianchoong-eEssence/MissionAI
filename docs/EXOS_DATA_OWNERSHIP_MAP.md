# EXOS Data Ownership Map

Thirty physical tables were audited: 12 Google Sheets worksheets and 18 Supabase runtime tables. Object-storage references and content-pack files are also persistent resources but are not included in the table count.

## Google Sheets configuration and reporting

| Table | Centre owner | Role | Duplication / drift |
|---|---|---|---|
| Events | Event Centre | Event definition, join code, schedule metadata | Duplicated by `runtime_events`; metadata JSON carries runtime flags |
| Participants | Identity Centre | Reporting/backfill view of participants | Conflicts with authoritative `runtime_participants`; must never be live fallback |
| Teams | Identity Centre | Planned team definitions | Duplicated by `runtime_teams`; scores/status mix planning and reporting |
| Missions | Experience Centre | Event-specific experience copies | Also represented by runtime missions and ProgrammeStages linkage |
| MissionTemplates | Experience Centre | Reusable experience definitions | Naming conflicts with Experience terminology |
| ProgrammeStages | Event Centre | Programme/module/activity sequence encoded in flat rows | Modules/Activities are conceptual, not independent tables |
| EventState | Control Centre | Sheet mirror of current stage | Conflicts with authoritative fields in `runtime_events` |
| Submissions | Intelligence Centre | Reporting/export mirror | Conflicts with transactional `runtime_submissions` |
| Conversations | Intelligence Centre | Legacy AI transcript reporting | Duplicated by `runtime_ai_messages` |
| AIFacilitators | Experience Centre | Reusable AI persona configuration | Assigned in participant UI after identity resolution |
| ProgrammePacks | Event Centre | Reusable programme/team/marketplace JSON bundles | Stores multiple entity types in JSON; weak ownership boundary |
| Assets | Experience Centre | Reusable media catalogue | Media references also embedded directly in Missions/Templates |

## Supabase live transactional data

| Table | Centre owner | Role | Duplication / drift |
|---|---|---|---|
| runtime_events | Event Centre | Published event plus live stage/broadcast/wallet/GPS flags | Mixes Event and Control concerns in one row |
| runtime_teams | Identity Centre | Published TeamID/name ordering | Mirrors Sheets Teams |
| runtime_participants | Identity Centre | Durable identity, team, country, leader/session state | Mirrors Sheets Participants; legacy status string encodes fields |
| runtime_missions | Experience Centre | Published event-experience payload | Mirrors Sheets Missions |
| runtime_submissions | Intelligence Centre | Transactional evidence and decisions | Mirrors Sheets Submissions; Control writes, Intelligence owns record |
| runtime_team_wallets | Intelligence Centre | Team balance snapshot | Derived from/paired with transaction ledger |
| runtime_credit_transactions | Intelligence Centre | Immutable credit ledger | Points also exist on participant and submissions |
| runtime_marketplace_items | Experience Centre | Published event marketplace catalogue | Programme packs also embed marketplace JSON |
| runtime_marketplace_purchases | Intelligence Centre | Purchase ledger | Control executes; Intelligence owns record |
| runtime_ai_messages | Intelligence Centre | Transactional Sync/AI conversation history | Mirrors Conversations sheet |
| runtime_ai_hint_state | Control Centre | Current participant/mission hint progression | AI rules authored in Missions |
| runtime_route_stops | Event Centre | Published route/checkpoint configuration | Mission rows also contain GPS fields |
| runtime_team_trackers | Control Centre | Team GPS-control state | Road-hunt-specific runtime structure |
| runtime_team_locations | Control Centre | Current team location | Projector/operations consume it |
| runtime_location_history | Intelligence Centre | Historical location trail | Derived operational analytics |
| runtime_geofence_arrivals | Intelligence Centre | Arrival evidence/audit | Consumed by Control and participant route |
| runtime_identity_audit_log | Intelligence Centre | Immutable identity override audit | Written by Identity/Control operations |
| runtime_submission_overrides | Identity Centre | Current event/team submission authority | Controlled by facilitator; authorization concern |

## Conceptual records without dedicated tables

- Modules and Activities are encoded into ProgrammeStages through `StageType`, generated IDs and JSON-like conventions. Owner: Event Centre. This limits independent editing/versioning.
- Leaders are encoded in `runtime_participants.status` using `|LEADER`. Owner: Identity Centre. No dedicated assignment history before migration 011 audit log.
- Evidence is contained in runtime submissions and object storage, not a distinct table. Owner: Intelligence Centre.
- Broadcast state is embedded in `runtime_events`. Owner: Control Centre.
- Reports/Analytics are computed views, not persisted models. Owner: Intelligence Centre.

## Other persistent resources

- Supabase Storage: submission evidence, mission media, library assets—Experience or Intelligence ownership depends on object purpose.
- `content_packs/bayu_beach_labyrinth_v1.json`: reusable/event-derived content; should be Experience Centre content pack.
- `data/aia_customer_contact.py` and `data/mahb_media_explore.py`: executable client packs combining Event and Experience records.

## Conflicting sources of truth

Six material conflicts exist:

1. Participants: Sheets versus Supabase.
2. Teams: Sheets versus Supabase.
3. Submissions: Sheets versus Supabase.
4. Current event/stage state: EventState versus runtime_events.
5. Missions/experiences: Missions versus runtime_missions payloads.
6. AI conversations: Conversations versus runtime_ai_messages.

Rules should make Supabase authoritative after publication and Sheets an explicit configuration/reporting projection.
