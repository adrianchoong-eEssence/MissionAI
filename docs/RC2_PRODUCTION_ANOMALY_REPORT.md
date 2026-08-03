# RC2 Production Anomaly Report

Evidence date: 3 August 2026. Event: `EVT-0006` (Loreal, RACE, 19 August 2026). Google Sheets evidence was read live from `MissionAI_Database`. Supabase evidence was read live from project `EXOS Runtime` (`bqsbkdfzqyiodivhyxnq`) using SELECT-only SQL.

The three production Streamlit applications were verified at their exact URLs. Before the approved push, participant displayed `cb9dc5f`. After deployment, participant displayed `8bc4dd5`; admin started successfully, but facilitator failed while reading participants because production does not contain `runtime_participants.team_id`. No application form was submitted and no production record changed.

## Consolidated findings

| Category | Exact finding | Status |
|---|---|---|
| ParticipantIDs | Supabase contains `b305b001-f7cb-4a05-b651-981de20d5195` (Adrian Choong, Scuderia Ferrari, Waiting, 0 points) and `a356bd72-e9b5-484c-beb7-409a9cc7adfc` (Ruth Su, McLaren Racing, Waiting, 0 points). Google Participants contains zero EVT-0006 rows. | Projection mismatch |
| Duplicate identities | Zero duplicate normalized-name candidates for EVT-0006 | Verified |
| Ambiguous identities | Zero ambiguous same-name candidates for EVT-0006 | Verified |
| Team inconsistencies | Ten unique matching teams exist in both sources: F1-01 Scuderia Ferrari; F1-02 McLaren Racing; F1-03 Mercedes-AMG; F1-04 Red Bull Racing; F1-05 Aston Martin; F1-06 Alpine; F1-07 Williams Racing; F1-08 Audi F1 Team; F1-09 Haas F1 Team; F1-10 Cadillac F1 Team. All Sheet scores are 0. | Verified |
| Leader inconsistencies | Scuderia Ferrari and McLaren Racing each have one participant and zero leaders. The other eight teams have no participants. | Requires facilitator decision before leader-only submission testing |
| Orphaned submissions | Zero EVT-0006 runtime or Sheet submissions; zero orphaned submissions | Verified |
| Hierarchy conflicts | No EVT-0006 rows exist in `ProgrammeStages`; there is no programme hierarchy available to launch | Blocking configuration gap |
| Experience mapping issues | No EVT-0006 rows exist in `Missions`; there are no event Experience assignments to map or render | Blocking configuration gap |
| Credit discrepancies | EVT-0006 has zero credit transactions and zero wallets. Global legacy audit has 5 transactions and no duplicate awards. EVT-0004 balances are India 140, Malaysia 200 and Philippines 100. | Verified legacy data; canonical migration not installed |
| Leaderboard discrepancies | EVT-0006 has no canonical or legacy award rows; Sheet-only expected result is a ten-way tie at 0. Canonical leaderboard tables/views do not exist. | Blocked by migration 014 |
| Migration state | Dashboard shows no tracked migrations. Schema inventory proves 011–014 objects are absent: no identity audit/override tables, no `team_id`/country/flag columns, no runtime-control column, no Definition/Assignment tables and no canonical transaction tables/views. | Blocking deployment mismatch |
| Database health | Supabase dashboard reports Unhealthy, no backups and no migrations. | Blocking infrastructure state |
| Experience migration | 33 global legacy runtime Experiences: 21 reusable Definition candidates, 12 manual Definition reviews, 0 missing titles. EVT-0006 has zero runtime Experiences. | Migration 013 plus manual mapping review required |
| Submission migration | 72 global runtime submissions, 0 invalid submissions, 0 duplicate logical submissions; 5 legacy credit transactions, 0 duplicate legacy awards. EVT-0006 has zero of each. | Migration 014 required |

## Event record

- EventID: `EVT-0006`
- Client: `Loreal`
- Department: `Sales Rally`
- EventName: `RACE`
- EventDate: `2026-08-19`
- Venue: `Park Royal Penang`
- Status: `Draft`
- ProgrammeType: `Team Building`
- NumberOfTeams: `10`

The join code exists in the live workbook but is intentionally omitted from this committed report.

## Required completion evidence

Migration 011 is required before the deployed application can read participants. It will add durable identity columns/tables/functions and backfill `team_id` for all 362 production participants because all have a matching runtime team. It can derive country from status for 111 participants; newly added flag values remain empty unless separately corrected. Migration 012 dry-run currently fails because migration 011 is absent. Migration 013 dry-run passes structurally but reports 12 manual mappings. Migration 014 dry-run reports no invalid/duplicate legacy transactions.

Do not correct the two RACE participants, assign leaders, populate country/flag, create programme/Experience records or migrate legacy content without separate record-exact approval.

Production records changed: **false**.
