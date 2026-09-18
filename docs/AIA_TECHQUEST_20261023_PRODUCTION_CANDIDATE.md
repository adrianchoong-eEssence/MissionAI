# AIA TechQuest — Production Candidate Runbook

This is a release procedure, not production-event creation authority. The final event, its team count, its team identities, its participant QR hostname, and its bounded GPS window remain owner decisions.

## Locked candidate state

- Event date: 23 October 2026.
- Expected live participants: 199.
- Engineering/load certification target: 250 clients.
- Registration: one QR entry, name capture, device-bound `RANDOM_ASSIGN`, automatic `PRESENT`, team reveal, Captain lifecycle, then Mission AI.
- The final team count and capacity are configurable and must not reuse the UAT 25×10 distribution by default.
- GPS is `INDIVIDUAL`, advisory/operational only, and has no scoring path. It remains inactive until a bounded owner-approved window is supplied.

## Final event creation procedure

1. Owner approves EventID, one participant hostname/QR URL, final team count/capacity/identities, ride recce, secret content, return deadline, and GPS start/end.
2. Take an event-scoped preflight snapshot and verify no existing event uses the proposed EventID or join code.
3. Materialise the AIA package with the approved final team configuration; never copy the UAT’s 25×10 technical fixture as a production default.
4. Create the event once, configure `RANDOM_ASSIGN` and attendance, then confirm no participant, submission, score, or runtime data exists before opening registration.
5. Deploy the participant app, Mission Control, projector, and Kai against the approved event configuration. The participant QR resolves only to the approved participant URL; it contains no credentials or team assignment.
6. Run the 250-client disposable certification and the physical mobile/video matrix. Do not open public registration until both have evidence.

## Event-day configuration

- GPS requires explicit tracking start, tracking end, explicit enable, and any approved event-specific cadence, stale threshold, and retention. Leave it disabled if any are missing.
- Mission Control verifies attendance, team distribution, Captain lifecycle, mission review/resubmit, canonical participation selection, rubric, bonus/adjustment, Hold/Resume, GPS, announcements, and leaderboard without exposing raw IDs/RPC terms in normal use.
- Projector is public read-only at five-second polling and may show rank, team, score, completed/total, progress, and READY/LIVE/HOLD only. It must never show participant identity, GPS, or evidence.
- Kai/operator uses the same EventID-scoped location and announcement operations as Mission Control.

## Freeze and recovery checklist

- Freeze only after final mission/rule, team configuration, QR hostname, ride availability, and GPS-window approval.
- Record the rollback owner, database snapshot reference, application commit, Streamlit deployment revision, and operator contacts.
- On a registration/identity/authority defect: pause registration, preserve audit data, use approved recovery, and never merge by display name.
- On runtime or scoring defect: HOLD the event, preserve submissions/evidence/score snapshots, correct only through canonical reviewed operations, then resume after facilitator verification.
- On deployment failure: roll back the application revision first. Do not delete canonical event, identity, attendance, evidence, submissions, or scores.

## Human mobile/video UAT

Test PHOTO, VIDEO, and PHOTO_OR_VIDEO on iPhone and Android. Confirm private storage, 5–10 second recommended clips, the 50 MB ceiling, retry/reopen behaviour, permission handling, and network recovery. These remain human UAT gates; no automated pass is implied.
