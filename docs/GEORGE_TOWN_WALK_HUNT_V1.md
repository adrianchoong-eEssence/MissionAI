# George Town WALK Hunt V1 — UAT Candidate

The disposable UAT event is `GEORGE-TOWN-WALK-20261024-UAT`. Its six teams of
six, experiential names, dates, identifiers, missions, and synthetic
coordinates are fixtures only. They are not a final roster, published route,
or approved George Town venue claim.

## Source scope

- Dedicated `GeorgeTown_Participant.py`, `GeorgeTown_MissionControl.py`, and
  `GeorgeTown_Projector.py` entrypoints.
- One common QR path: first/last name → opaque browser credential →
  `RANDOM_ASSIGN` → atomic first-arrival `PRESENT` attendance → team reveal.
  Reconnect uses the persisted credential/device binding, never a name merge.
- Explicit individual live-location consent, 20-second default cadence,
  90-second stale threshold, bounded trails/retention, separated-team guard,
  non-scoring checkpoint proximity, announcements, and event-scoped Kai reads.
- WALK mission board, private photo/video evidence (50 MB video ceiling),
  Captain participant selection, authoritative review/ledger scoring, and a
  read-only public leaderboard with no GPS or evidence.

## Migration and deployment state

`051_exos_core_v2_hunt_engine_v1.sql` is **prepared, not installed**. Do not
install it until an owner authorises the dedicated target after migration
history verification. No deployment has been attempted.

## Required human UAT after installation

Test iPhone/Android consent, permissions, screen lock/background pause,
reopen, network loss/recovery, urban accuracy, photo/video retry, Captain
recovery/transfer, return/hold/close transitions, public projector privacy,
and a separate concurrent Nera fixture. The supplied load harness is explicitly
non-executed and is not a PASS assertion.
