# AIA Tech disposable UAT deployment

This is a UAT-only event: `AIA-TECH-20261023-UAT` / `AIAUAT`. It starts empty and uses `RANDOM_ASSIGN` self-registration into a 25-team × 10 technical capacity fixture. The fixture is conspicuously UAT-only and is not the final AIA grouping decision.

## Prepare the event

Generate the scoped SQL with:

```bash
python scripts/prepare_aia_techquest_candidate.py
```

The resulting [UAT setup SQL](../outputs/aia-techquest-uat.sql) is intentionally not automatically executed. It creates an empty `RANDOM_ASSIGN` fixture and enables canonical attendance. The fixed-event AIA registration wrapper in `supabase/046_aia_tech_random_registration_attendance.sql` composes the existing Core random-assignment RPC with an idempotent first-arrival `PRESENT` write.

## Deploy entrypoints

Deploy `AIA_Participant.py` as `mission-ai-aia-tech-uat` with these secrets/environment values:

```text
SUPABASE_URL=<authorised staging URL>
SUPABASE_PUBLISHABLE_KEY=<publishable key>
AIA_EVENT_ID=AIA-TECH-20261023-UAT
AIA_JOIN_CODE=AIAUAT
```

Deploy `AIA_Projector.py` as `mission-ai-aia-tech-projector-uat` with only `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`. It deliberately cannot use a service key.

Projector deployment additionally requires explicit owner approval and installation of `supabase/045_aia_tech_public_projector_projection.sql`. Until then the participant/Mission Control UAT remains deployable; the standalone public projector does not.

## Operator UAT sequence

1. Open the one AIA participant link and register an AIA UAT test name; this writes `PRESENT` automatically.
2. Select `AIA-TECH-20261023-UAT` in Mission Control and confirm live registered/present counts.
3. Open Captain selection, claim/transfer/clear a Captain, then activate teams.
4. Launch the open board; exercise a participation-prorated mission, rubric review, resubmit, adjustment, Hold, and Resume.
5. Run `python scripts/aia_250_certification.py --execute` only after the stated staging credentials and guarded confirmation are present.
