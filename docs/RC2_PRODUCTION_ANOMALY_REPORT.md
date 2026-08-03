# RC2 Production Anomaly Report

Evidence date: 3 August 2026. Event: `EVT-0006` (Loreal, RACE, 19 August 2026). Google Sheets evidence was read live from `MissionAI_Database`. Supabase sections remain unverified because the production project and credentials are not available.

## Consolidated findings

| Category | Exact finding | Status |
|---|---|---|
| ParticipantIDs | No EVT-0006 rows exist in the Google `Participants` tab | Sheet verified; Supabase unverified |
| Duplicate identities | None can exist in the empty Sheet participant projection | Supabase unverified |
| Ambiguous identities | None can exist in the empty Sheet participant projection | Supabase unverified |
| Team inconsistencies | Ten unique teams exist: F1-01 Scuderia Ferrari; F1-02 McLaren Racing; F1-03 Mercedes-AMG; F1-04 Red Bull Racing; F1-05 Aston Martin; F1-06 Alpine; F1-07 Williams Racing; F1-08 Audi F1 Team; F1-09 Haas F1 Team; F1-10 Cadillac F1 Team. All have Score 0 and Active status. Country and Language are blank for all ten. | Sheet verified; Supabase publication unverified |
| Leader inconsistencies | No participants or leaders exist in the Sheet projection; each configured team currently has zero leaders | Pre-registration state; Supabase unverified |
| Orphaned submissions | No EVT-0006 rows exist in the Google `Submissions` tab | Sheet verified; Supabase unverified |
| Hierarchy conflicts | No EVT-0006 rows exist in `ProgrammeStages`; there is no programme hierarchy available to launch | Blocking configuration gap |
| Experience mapping issues | No EVT-0006 rows exist in `Missions`; there are no event Experience assignments to map or render | Blocking configuration gap |
| Credit discrepancies | Sheet Teams are all 0 and there are no Sheet Submissions; canonical Supabase Awards and balances cannot be read | Supabase reconciliation blocked |
| Leaderboard discrepancies | Sheet-only expected order is a ten-way tie at 0; canonical Supabase leaderboard cannot be read | Supabase reconciliation blocked |

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

Run the SELECT-only Supabase identity and transaction audits plus migration dry runs 011–014 for EVT-0006. Merge their exact ParticipantIDs, duplicates, leader/team findings, orphaned submissions, Award differences and leaderboard differences into this report before any migration or deployment approval.

Production records changed: **false**.
