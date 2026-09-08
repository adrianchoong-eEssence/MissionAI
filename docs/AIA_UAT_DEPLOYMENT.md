# AIA Tech disposable UAT deployment

This is a UAT-only event: `AIA-TECH-20261023-UAT` / `AIAUAT`. Its 250 roster and 25 `Quest` teams are synthetic, conspicuously marked as UAT-only, and must not be interpreted as the final AIA grouping.

## Prepare the event

Generate the scoped SQL with:

```bash
python scripts/prepare_aia_techquest_candidate.py --print-owner-test-account
```

The resulting [UAT setup SQL](../outputs/aia-techquest-uat.sql) is intentionally not automatically executed. An authorised staging operator must run it against the intended non-production Core v2 environment; it enables canonical attendance as part of setup. This operation requires a Supabase URL, service credential, and owner-selected target database; none are configured in this workspace.

## Deploy entrypoints

Deploy `AIA_Participant.py` as `mission-ai-aia-tech-uat` with these secrets/environment values:

```text
SUPABASE_URL=<authorised staging URL>
SUPABASE_PUBLISHABLE_KEY=<publishable key>
SUPABASE_SECRET_KEY=<server-side application key>
AIA_PERSONAL_KEY_EVENT_ID=AIA-TECH-20261023-UAT
AIA_PERSONAL_KEY_JOIN_CODE=AIAUAT
```

Deploy `AIA_Projector.py` as `mission-ai-aia-tech-projector-uat` with only `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`. It deliberately cannot use a service key.

Projector deployment additionally requires explicit owner approval and installation of `supabase/045_aia_tech_public_projector_projection.sql`. Until then the participant/Mission Control UAT remains deployable; the standalone public projector does not.

## Operator UAT sequence

1. Select `AIA-TECH-20261023-UAT` in Mission Control.
2. Mark the owner test account PRESENT.
3. Open Captain selection, claim/transfer/clear a Captain, then activate teams.
4. Launch the open board; exercise a participation-prorated mission, rubric review, resubmit, adjustment, Hold, and Resume.
5. Run `python scripts/aia_250_certification.py --execute` only after the stated staging credentials and guarded confirmation are present.
