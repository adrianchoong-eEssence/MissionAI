# Standard EXOS Core v2 vertical slice

## Runtime-path audit

| Journey | Before this change | Actual former dependency | Current standard path |
|---|---|---|---|
| Create Event / Events | Google Sheets | `GoogleSheetsDB` → Events/Teams worksheets, with later runtime publication | Core v2 `events_v2` / `teams_v2` through `StandardCoreV2Adapter` |
| Programme Builder | Hybrid | ProgrammeStages worksheet facade; Core v2 was attempted first, then legacy/Sheets fallbacks | Core v2 `programmes_v2` / `modules_v2` / `activities_v2`; no fallback |
| Facilitator / Control | Hybrid | Sheets event/programme reads plus legacy runtime control and submission helpers | Core v2 adapter; standard activity launch RPC; v2 submissions/reviews/scores |
| Participant | Hybrid | Supabase identity for some paths, `GoogleSheetsDB` for standard joins/content/submissions | Core v2 join/restore/session, live-state and submission RPCs |
| Reports / Projector | Hybrid | Sheets configuration plus runtime reads | Core v2 adapter and canonical v2 ledgers/submissions |

The dedicated Formula R.A.C.E. path remains separate and was not changed. Legacy
administration, asset, Experience Studio and explicit Legacy Operations screens
still exist outside the standard programme runtime journey.

## Implemented Core v2 boundary

- `data/standard_core_v2_adapter.py` is the only database boundary used by the
  standard Events, Create Event, Programme Builder, Control Centre, Participant,
  Reports and Projector screens.
- The adapter rejects any table not in its explicit `*_v2` allowlist and any RPC
  not prefixed `exos_v2_`. It exposes counters for the two hard assertions.
- Programme saves are non-destructive. Removed modules and activities are made
  inactive; records with participant/runtime/submission history are not deleted.
- Programme duplication remaps programme, module and activity IDs to the
  destination event and copies configuration only.
- Activity configuration now persists scoring mode, team/individual submission
  ownership and submission type.

## Genuine missing capability identified

Migration `supabase/025_standard_programme_runtime.sql` adds functions over the
existing Core v2 schema. It creates no tables.

- `exos_v2_standard_launch_activity`
- `exos_v2_standard_participant_state`
- `exos_v2_standard_submit`
- `exos_v2_standard_review_submission`

Live event state uses `events_v2.event_payload`; execution, evidence, review and
scores use the existing `activity_runtime_v2`, `submissions_v2`, `reviews_v2`
and `score_transactions_v2` tables.

## Staging UAT

Run after migration 025 is installed on a disposable Core v2 staging project:

```bash
EXOS_ENV=staging \
SUPABASE_URL=... \
SUPABASE_PUBLISHABLE_KEY=... \
SUPABASE_SECRET_KEY=... \
python3 scripts/exos_core_v2_standard_vertical_slice.py
```

The runner refuses the known production host, creates two persistent staging
events, executes all 18 acceptance gates, proves configuration-only duplication
and emits `outputs/standard-core-v2-uat.json`. It does not claim a gate passed
until the real staging response has been asserted.
