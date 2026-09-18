# ENCA George Town Mission AI — Architecture UAT Candidate

The source-only fixture is `ENCA-GEORGETOWN-20261024-UAT` for ENCA Group Team
Building 2026 on 24 October 2026 in George Town, Penang. It is an architecture
candidate, not a deployed event, approved country list, route, checkpoint,
mission rule, or scoring schedule.

## Fixed architecture

- Capacity is exactly **134**: ten distinct temporary country slots, four with
  capacity 14 and six with capacity 13.
- The ten named HOD anchors are pre-assigned one per country slot. Their
  Personal Keys are generated and distributed externally; Git stores no raw
  Personal Key. An HOD's first successful key claim marks canonical attendance
  `PRESENT` but never grants Captain authority.
- The remaining **124** people use one common QR: first/last name → opaque
  browser credential → server-randomized least-occupied eligible team →
  automatic `PRESENT`. Same-device retry is idempotent; a new device needs the
  applicable canonical recovery path and never causes re-assignment.
- Captain selection remains an explicit Team Formation lifecycle decision.
  HOD membership and Captain authority are separate.

## Competition, privacy, and surfaces

- VISION TOWER, CROSSING THE BLACK SEA, and GEORGE TOWN MISSION AI HUNT are
  ordered, scored stages sharing `score_transactions_v2` and one cumulative
  leaderboard. Stage content and point values are owner-pending.
- Energizers and the 25 October Rollercoaster Challenge are explicitly
  non-scored. The Walk Hunt is `OPEN_HUNT`, but no route, checkpoint, mission,
  or final rule is created by this fixture.
- Facilitators can use individual live-location views when separately enabled
  and consented. Participant sharing defaults to `OFF`; `TEAM_LEADERS` may
  reveal only another team's effective Captain location. Own-team display is a
  separate decision. GPS and proximity are never scoring inputs.
- The fixed participant, Mission Control, and public-projector entrypoints
  contain the EventID/join code as deployment configuration, not participant
  inputs. The projector receives current stage, country/flag, rank, and
  cumulative score only.

## Hunt content foundation — not final mission content

- The Walk Hunt uses a compact central/southern George Town heritage arena and
  an owner-pending target pool of about 20 missions. Mission classes are
  `COMMON`, `RANDOM`, and `SECRET`; categories are observation, photo, video,
  AI, creative, collaboration, heritage, food/culture, and checkpoint.
- Teams will receive balanced random optional subsets, rather than the same
  board or a forced linear route. The final subset sizes, individual missions,
  release logic, rules, evidence requirements, and points remain owner-pending.
- Candidate zones are Hin Bus Depot; Keng Kwee/Penang Road Chendul;
  Campbell/Carnarvon; Armenian; Cannon; Khoo Kongsi; Acheh; Little
  India/Harmony; Ah Quee; Beach Street; and Chew/Clan Jetties. They are
  configuration labels only, with no coordinates, clues, route, or checkpoint
  content. Hin Bus Depot remains available as a high-value outer candidate.
  Fort Cornwallis is excluded.
- The participant map can show the consented **You** location and, only after
  owner-approved coordinates, mission/checkpoint and Return-to-Base pins.
  Other-team visibility defaults to `OFF`; `TEAM_LEADERS` is the only optional
  participant setting. Facilitators retain consented individual/trail views.
- Return to Base is a permanent non-scored operational pin. Its exact location,
  human-facing guidance, and distance calculation are owner-pending. The
  supported announcement states are **30 minutes remaining** and **Return to
  Base now**.

## Migration and UAT status

`051_exos_core_v2_hunt_engine_v1.sql` and
`053_enca_hybrid_event_architecture.sql` are **prepared, not installed**.
`053` has a guarded rollback and a read-only verifier, but must not be applied
until an owner authorises a verified dedicated target. No deployment or event
creation has been attempted.

The local certification harness exercises 10 HOD claims, a concurrent 124-way
general-registration burst, capacity distribution, same-device idempotency,
automatic attendance, independent Captain selection, stage-ledger shape,
participant visibility modes, and Nera EventID isolation. This is local source
evidence only—not database concurrency certification, deployed/staging proof,
or human UAT.

After authorised installation, test iPhone/Android HOD and common-QR paths,
key/device recovery, Captain transitions, score-stage lifecycle, projector
privacy, opt-in live location, background/screen-lock/network recovery, final
Hunt content, and a simultaneous Nera fixture.
