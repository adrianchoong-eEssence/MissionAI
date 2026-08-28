# Genting Theme Park Race V1 — strategic open-mission draft

This local-only package configures the reusable `THEME_PARK_RACE` engine with `StrategyMode = "OPEN_MISSION_BOARD"`. It creates no event, performs no API/database call, installs no migration, and does not change Team Formation V1, participant/team identity, Captain authority, Formula R.A.C.E., or the retained `CONFIGURED_TEAM_ROUTE` strategy.

## Strategic model

Teams have a limited programme window and make their own choices through a canonical opportunity board:

`OBSERVE → ANALYSE → DECIDE → ACT → ADAPT → OUTSMART`

The board has one configurable concurrent selection by default. It supports normal, `RIDE`, `BONUS`, and `SECRET` activity classes. The existing activity `RaceStation` payload owns the mission class, evidence contract, safety instruction, reviewed score maximum, and optional ride participation contract. `RaceConfiguration.MissionBoard.MissionOperations` owns server-controlled availability and secret release state.

Mission state is derived from Core records only: `LOCKED`, `AVAILABLE`, `SELECTED`, `SUBMITTED`, `APPROVED`, `REJECTED`, `TEMPORARILY_UNAVAILABLE`, or `CLOSED`. A participant browser never owns mission availability, selection, score, ride threshold, or completion state.

## Genting draft status

The six activities in this package are intentionally named **DRAFT PLACEHOLDER**. They are not approved Genting missions, attractions, safe points, prompts, points, or reference images. Their purpose is to provide a materialisable configuration shape for strategic-mission, ride, bonus, and secret content once Adrian and Kai supply the business decisions.

The package keeps six normal configured teams of capacity 11 (66 capacity) using Team Formation `RANDOM_ASSIGN`. It contains no mandatory routes: the opportunity board is strategic rather than cyclic.

## Ride evidence and participation

The draft ride station applies an 80% threshold of **current canonical team membership**, rounded up. For common team counts this is 11 → 9, 10 → 8, and 9 → 8 required riders. A full-team ride has zero competitive-score multiplier; non-riders may be Ground Control and remain legitimate team participants.

A ride exterior image is not completion proof. A completed ride must use one configured pathway:

- `GROUND_CONTROL`: permitted queue-entry evidence plus post-ride verification.
- `FULL_TEAM`: permitted evidence after official queue entry and before any required phone storage, plus post-ride verification.
- `FACILITATOR_VERIFIED`: controlled fallback where attraction rules make digital evidence impractical.

The selected pathway must always respect attraction and park rules. `ATTEMPTED`, `COMPLETED`, `ABORTED_BY_ATTRACTION`, and `TEAM_WITHDREW` are separate canonical ride-attempt outcomes. No compensation points have been invented; that remains a business configuration decision. A temporarily unavailable or closed ride cannot be selected and has no automatic penalty.

## Information boundaries

Captain/team view contains only their own visible board missions, selected/submitted state, operational status, instructions/evidence, team membership threshold and result. Facilitators can control operation/release, inspect private evidence, review, reject/resubmit, and score through existing review/ledger semantics. The projector shows progress/ranking, optional aggregate mission status, and a released-secret announcement; it never shows private evidence, selected/current missions, or team strategy.

## Future authorised load (not performed now)

1. Complete the business and park recce decisions in [BUSINESS_INPUTS.md](BUSINESS_INPUTS.md).
2. Create the normal event, teams, programme/module and approved `activities_v2` content through the existing EXOS flows.
3. Materialise this package with a future EventID; `materialize.py` performs no write.
4. Configure frozen Team Formation V1 first, then configure the Theme Park Race board after approved 038 deployment review.
5. Run the separate 66/250 Team Formation database-concurrency certification and event UAT before release.

`038_theme_park_race_open_mission_board.sql` is a local, uninstalled source migration. It adds no tables and is intentionally separate from unmodified 037. It uses existing `activity_runtime_v2`, `submissions_v2`, `reviews_v2`, score ledgers, event payload, participant sessions, and Captain sessions. Its rollback companion is deliberately blocked: a future reviewed restoration migration is required rather than risking loss of the original 037 route guard.
