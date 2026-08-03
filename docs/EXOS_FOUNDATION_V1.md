# EXOS Foundation V1

Status: approved information architecture; implementation not started.

## Foundation

EXOS is organised around five centres. Dashboard and Settings remain global surfaces outside them.

| Centre | Owns | Does not own |
|---|---|---|
| Identity Centre | ParticipantID, joining, recovery, teams, country, leader state, submission authority, identity audit | Programme design, activity content, scoring analysis |
| Event Centre | Event lifecycle, programme structure, modules, activities, schedules, assignments and readiness | Reusable experience authoring, live execution |
| Experience Centre | Reusable experiences/templates, instructions, evidence definitions, scoring rules, media and assets | Event ordering, runtime state, participant identity |
| Control Centre | Live stage, launch/end, timers, broadcast, submissions review, emergency recovery and operational overrides | Authoring source records, historical analytics |
| Intelligence Centre | Results, scores, credits analysis, reports, exports, operational and identity audit views | Live mutation and content authoring |

Dashboard gives cross-centre orientation and readiness. Settings owns platform administration, integrations, credentials, retention, archives and guarded UAT/reset tools.

## Foundation rules

1. Every persistent entity has one owning Centre and one authoritative source.
2. Google Sheets is configuration/reporting; Supabase is live transactional state.
3. Published runtime data never silently falls back to Sheets.
4. ParticipantID, TeamID, country and current leader state are backend-authoritative.
5. Experience templates are reusable; event assignments are references/copies with explicit version provenance.
6. Event Centre composes; Experience Centre authors; Control Centre executes; Intelligence Centre observes.
7. UI files orchestrate services but do not contain event-specific business rules.
8. Client/event packs belong in versioned content packs or import tools, not generic screen branches.
9. Projector is a Control Centre output surface, not a separate source of runtime truth.
10. All facilitator identity and scoring overrides are reversible where possible and audited.

## Canonical terminology

| Canonical term | Current aliases to retire later |
|---|---|
| Experience | Mission, activity content, selected team experience |
| Experience template | MissionTemplate, mission library item |
| Programme | Show flow, live programme, ordered stages |
| Module | Container, programme section |
| Activity | Stage, mission stage, programme row |
| Control Centre | Mission Control, Experience Control, Live Event Console, Show Control |
| Intelligence Centre | Command Centre reports, Results & Reports, leaderboard analysis |
| Team Leader | Leader, active leader, submission owner |

No production labels are changed by this audit.

## Centre interfaces

- Identity → Event: event joinability and published team roster.
- Event → Experience: selected experience IDs and versioned event copies.
- Event → Control: published programme/stage sequence.
- Identity → Control: participant/team/leader/submission authority.
- Experience → Control: participant brief, facilitator instructions, evidence and scoring contract.
- Control → Intelligence: submissions, decisions, scores, credits, timings and audit events.
- Intelligence → Dashboard: readiness, live health and completion summaries.

## Acceptance boundary

Foundation V1 is complete when each current surface and table is assigned once, duplicate operational routes have a retirement decision, the published runtime boundary is explicit, and the 16 core workflows can be traced without an unowned step.
