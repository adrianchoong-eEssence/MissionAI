# EXOS Current-State Audit

Audit date: 3 August 2026. Scope: complete production repository including entry routes, 19 screen files, seven engines, eight data modules, runtime schema and ten numbered migrations, Google Sheets integration, six scripts, 30 test modules, content packs, models and legacy/unrouted files. No production code, navigation or data was changed by this audit.

## System shape

- Admin workspace: one Streamlit application with nine sidebar destinations.
- Facilitator: separate route into legacy Live Event Console.
- Participant: separate mobile application plus query-param route through admin app.
- Persistence: 12 required Google worksheets, 18 Supabase tables and object storage.
- Runtime: Supabase RPCs for transactional joins, submissions, credits, stages, AI and GPS; Sheets remains configuration/reporting but still participates in some live reads.
- Tests: 30 modules / 193 passing tests at audit start.

## Interface drift

### Navigation duplication

Events and Create Event coexist with a large unrouted Event Manager that repeats creation and management. Experience Studio is internally named Mission Studio. Programme Builder contains an Experience Library, event-experience editors and client installers. Administration contains event-specific operational tools. Command Centre dashboard exists but is not routed.

### Mission Control / Control Centre / Live Event Console

Four names represent overlapping live-operation concepts: canonical Control Centre, standalone Live Event Console, legacy Show Control and placeholder Mission Control/Experience Control. The canonical screen imports review, scoring and credit widgets from the legacy console, so ownership is visually newer but technically coupled.

### Programme structure and editing

ProgrammeStages is a flat worksheet. Modules and Activities are encoded through `StageType` strings and generated IDs. Programme Builder mixes ordering, module/activity editing, recommendations, reusable packs, Sync AI/Catalyst configuration and AIA/MAHB installation. This makes the core flow hard to reason about and difficult on tablets.

### Experience Studio clarity

The screen mixes reusable templates, event copies, bulk import, activation, reference-image editing, media and assignment. “Mission”, “Experience”, “Template”, “Library” and “Event Experience” coexist. The participant preview in Control Centre uses hierarchy fields, while participant rendering uses mission-specific and EVT-0004 branches; parity is not guaranteed by one renderer.

### Mobile and tablet

- Participant is designed for mobile, but lifecycle recovery still requires physical certification.
- Main admin navigation forces an expanded, locked sidebar and wide layout.
- Programme Builder, Experience Studio, Event Manager, Administration and Live Console contain wide forms/dataframes and multi-column actions.
- Facilitator recovery, scoring, GPS and programme control are desktop-first.
- Projector is intentionally large-screen; its controller belongs in facilitator layout rather than participant mobile.

### Inconsistent naming

Mission/Experience, MissionID/Experience, Stage/Activity, Container/Module, Command/Control/Mission/Show Control, points/score/credits, and team name/TeamID are used inconsistently across Admin, facilitator and participant surfaces.

## Architecture and business-rule findings

| ID | Priority | Finding | Evidence | Smallest structural correction |
|---|---|---|---|---|
| F01 | P0 | Production participant identity migration/certification incomplete | Migration 011 exists but is unapplied; Sprint 009.5 blocked | Complete read-only audit, migration, device matrix and telemetry |
| F02 | P0 | Live transactional and Sheet fallbacks remain conceptually duplicated | Participants/Teams/Submissions/EventState mirrors | Enforce published-runtime authority and projection-only sync |
| F03 | P0 | Submission authority is partly mediated in participant UI | Leader gate calls UI/runtime; legacy paths coexist | Make one backend authorization contract mandatory for every team submission |
| F04 | P0 | Multiple live controllers can mutate stage/runtime state | Control Centre, Live Console, Show Control | Route all stage mutations through canonical Control service/screen |
| F05 | P0 | Close-event flow is fragmented | Control, Administration and Event Manager actions | Add one documented transactional close checklist before UI consolidation |
| F06 | P0 | Reports can reconcile mixed sources inconsistently | Sheets/runtime submissions and multiple leaderboard functions | Define runtime ledger/submission views as report source after publish |
| F07 | P1 | Event creation exists twice | Create Event and Event Manager | Preserve guided flow; migrate missing admin functions |
| F08 | P1 | Experience assignment/editing exists in two centres | Mission Setup and Programme Builder | Experience authors; Event only links/orders |
| F09 | P1 | Four live-control names/interfaces | Control, Live Console, Show Control, Mission Control | Canonicalise internally before renaming navigation |
| F10 | P1 | Flat ProgrammeStages models modules and activities indirectly | Hierarchy encoder/decoder | Stabilise canonical domain adapter before schema change |
| F11 | P1 | Programme Builder is a mixed-responsibility 1,900-line screen | Packs, installers, editors, recommendations | Extract services/components without changing behavior |
| F12 | P1 | Participant screen holds identity, rendering, forms, AI, GPS and marketplace rules | 2,400+ lines | Extract domain/render modules under regression lock |
| F13 | P1 | Live Console owns reusable logic imported by Control Centre | Review/credit functions imported | Move widgets/services to neutral modules |
| F14 | P1 | Event/client code in generic screens and engines | EVT-0004, AIA, MAHB branches | Move to versioned content-pack adapters |
| F15 | P1 | Leader/country encoded partly in status strings | `COUNTRY:x|LEADER` | Complete typed migration 011 fields and audited transitions |
| F16 | P1 | Points, scores and Intelligence Credits overlap | participant points, submission score, credit ledger | Publish canonical metric glossary and typed APIs |
| F17 | P1 | Programme packs combine multiple ownership domains in JSON | Teams/Missions/Stages/Marketplace JSON | Define versioned import contract with centre-specific validation |
| F18 | P1 | Unrouted legacy screens obscure supported paths | home, experience_library, show_control, event_manager | Mark legacy registry and retire after parity tests |
| F19 | P1 | Participant preview and live renderer are different implementations | Control preview vs participant branches | Create shared read-only experience presentation model |
| F20 | P2 | Expanded locked sidebar obstructs phone/tablet admin use | `MissionAI.py` wide/expanded branding lock | Responsive shell after foundation ownership work |
| F21 | P2 | Dense dataframes/forms lack tablet action hierarchy | Builder/Studio/Admin/Console | Responsive component pass after service extraction |
| F22 | P2 | Empty Remote and placeholder Mission Control remain | legacy files | Remove after route/reference verification |
| F23 | P2 | Emoji/icon/title patterns vary by surface | screen headings | Apply terminology/design tokens after navigation approval |
| F24 | P2 | Dashboard readiness surface is dormant | `show_command_centre` unrouted | Reconnect as global Dashboard after centre routing exists |
| F25 | P2 | Asset/media placement is unclear | Asset Library plus inline media fields | Keep data ownership; improve discoverability later |

Priority totals: six P0, thirteen P1 and six P2.

## Event-specific code

Five event/client-specific families are embedded in generic application code:

1. EVT-0004/Bayu country, Labyrinth, AI identity and board branches.
2. AIA Customer Contact programme, teams and marketplace installer.
3. MAHB Media Explore teams, missions and GPS route installer.
4. Formula RACE marketplace/team setup and scoring labels.
5. Activity-type-specific Pipeline, Helium Stick, Key Punch, Catalyst and NASI forms/calculations.

Activity types may be reusable capabilities, but their rules should be registered through typed experience definitions rather than screen conditionals. L’Oréal work must not add another event-ID branch.

## Legacy/superseded structures

- Unrouted: Event Manager, Home, Experience Library, Show Control, Mission Control, Remote.
- Superseded SQL functions remain historically in numbered migrations by design; current definition depends on applying every migration in order.
- `data/mission_database.py` is an empty abstract skeleton.
- `engines/flow_engine.py` is empty; other early engines are light recommendation/transformation wrappers.
- Scripts include one-off EVT-0004/AIA migration and content-build utilities that should remain operational tools, not runtime imports.

## Audit totals

- Screens/routes audited: 21.
- Workflows audited: 16.
- Physical tables audited: 30.
- Duplicate interface clusters: 7.
- Conflicting source-of-truth pairs: 6.
- Event/client-specific code families: 5.
- Priority issues: P0 6, P1 13, P2 6.
