# EXOS L’Oréal Foundation Plan

Goal: the smallest structural correction set needed before L’Oréal RACE, without event-specific code or premature visual redesign.

## Recommended order of work

| Order / sprint | Work | Centre | Likely files | Migration risk | Regression risk | Acceptance criteria |
|---:|---|---|---|---|---|---|
| 1 — Sprint 010 completion | Certify durable identity and recovery | Identity | `supabase/011*`, `runtime_database.py`, `participant.py`, `control_centre.py`, identity tests | High: production identity fields/RPCs | Join, leader, team and credits | Audit reviewed; backup; migration passes; 52 mobile cells and live load pass |
| 2 — Foundation boundary | Declare runtime authority and repository legacy registry | All/Data | `google_sheets.py`, `runtime_database.py`, new domain services, docs/tests | Medium: fallback removal | Live reads and reports | Published events never silently fall back; each store has explicit role |
| 3 — Control consolidation | Make Control Centre the only stage mutation surface | Control | `control_centre.py`, `live_event_console.py`, `show_control.py`, `projector_broadcast.py`, timer/runtime APIs | Medium | Launch, timers, review, credits, GPS, projector | One mutation service; legacy screens read-only/unrouted; parity tests pass |
| 4 — Event model adapter | Stabilise Programme→Module→Activity domain adapter | Event | `programme_builder.py`, `programme_hierarchy.py`, `google_sheets.py`, programme tests | Low initially; avoid schema migration | Ordering/content links | All programmes round-trip through one model; no EVT-ID branch required |
| 5 — Experience boundary | Separate reusable authoring from event assignment | Experience/Event | `mission_setup.py`, `programme_builder.py`, media/upload modules | Medium | Template copies, media, reference images | One authoring owner; Event Centre only selects/links/orders; preview contract shared |
| 6 — Intelligence authority | Unify submissions, credits, scores and reports | Intelligence | `command_centre.py`, `live_event_console.py`, `leaderboard_display.py`, runtime queries | Medium | Results and exports | One canonical report projection; Sheets export reconciles exactly |
| 7 — Shell and terminology | Regroup navigation into five centres plus Dashboard/Settings | Global | `MissionAI.py`, branding, app state, screen entrypoints | Low data risk | Navigation bookmarks/routes | No lost capability; responsive shell; approved labels consistent |
| 8 — Mobile/tablet certification | Responsive facilitator layouts and full RACE rehearsal | Identity/Control | canonical screens/components only | None/low | Live operations | Physical matrix, facilitator tablet rehearsal, telemetry and rollback drill pass |

## P0 pre-L’Oréal minimum

1. Complete Sprint 010 production identity certification.
2. Enforce backend submission authorization on every team submission path.
3. Establish a single Control mutation service and disable legacy mutations.
4. Establish one published-runtime source contract for participants, submissions and current stage.
5. Establish a controlled close-event procedure.
6. Reconcile Intelligence reports to runtime submissions and credit ledger.

Navigation regrouping and cosmetic redesign are not prerequisites for these safety corrections.

## Migration and rollback risks

- Identity migration touches the most sensitive live records; requires audit, snapshot and explicit per-record correction approval.
- Removing Sheet fallback can expose missing runtime publication; add readiness checks before enforcement.
- Consolidating stage mutations can break facilitator muscle memory; retain read-only legacy parity during one rehearsal.
- Changing programme storage now is unnecessary risk; use an adapter before considering normalized Module/Activity tables.
- Report source changes can alter historical totals; run side-by-side reconciliation before cutover.

## Regression gates

- Identity: same ParticipantID/TeamID/country/flag/leader/credits across all recovery scenarios.
- Event: saved programme hierarchy round-trips without reordering or losing content links.
- Experience: template and event-copy edits affect only intended records; media remains resolvable.
- Control: launch/end/timer/broadcast/review/credit operations have one authoritative state transition.
- Intelligence: submission, score and credit totals reconcile; exports are repeatable.
- Cross-event: two simultaneous events never share identities, stages, submissions or credits.

## What must remain untouched

- Existing L’Oréal, AIA, MAHB and Bayu content, questions, images and evidence.
- Programme flow and scoring behavior unless separately approved.
- Sync AI and Catalyst mechanics.
- Production participant identities and historical submissions/credits without explicit record approval.
- Object-storage paths and signed-media behavior.
- Current production navigation labels until the foundation boundary and parity work is accepted.
- Completed event data, archives and audit logs.

## Final acceptance for L’Oréal RACE

- All P0 gates closed with evidence.
- No event-specific code added for L’Oréal.
- Facilitator can recover identity/leader/submission operation from one canonical surface.
- Participant mobile recovery and 100+ concurrent joins pass against production-equivalent infrastructure.
- Projector and reports reflect the same runtime state.
- Backup, rollback, telemetry and event-close rehearsals are signed off.
