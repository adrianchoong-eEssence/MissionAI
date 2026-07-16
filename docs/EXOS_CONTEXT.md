# EXOS Product Context

This file preserves the decisions imported from the earlier Mission AI development discussion.

## Product model

- EXOS Studio configures and duplicates programmes.
- EXOS Runtime operates live events.
- Google Sheets remains the configuration, reporting, and export layer.
- Supabase/PostgreSQL handles concurrent registration and other transactional runtime data.
- Media belongs in object storage; spreadsheet cells store URLs only.
- Credits use an immutable Supabase transaction ledger. Earned credits,
  marketplace spending, available balance, and the final race leaderboard are
  separate measures.

## Operational rules

- Registration must support 100+ simultaneous participants and two concurrent events.
- A returning participant keeps the original team.
- Team allocation advances only after the participant is committed successfully.
- Runtime errors must never silently fall back to a second database after an event is published.
- Duplicate Project copies event configuration, teams, missions, and programme stages.
- Duplicate Project does not copy participants, submissions, conversations, scores, or leaderboard data.

## Current scoring rules

- Pipeline: `(Achieved - Lost) / Target * 100`; results may exceed 100%.
- Enterprise Pipeline: one facilitator-entered collective result; never a leaderboard team.
- Helium Stick: Yes = 100, No = 0.
- Key Punch: `Highest number / 30 * 100`.
- Catalyst: Yes = 100, No = 0; optional photo.
- NASI: individual reflection with no competitive score.

## Mission content model

Mission Studio stores every reusable mission with:

- title and story;
- participant instructions;
- facilitator instructions;
- learning objectives;
- submission type and scoring rule;
- video, image, or document URL;
- hints and debrief questions;
- version and publication status.

Mission Studio supports manual creation, CSV/Excel bulk import, reuse across
events, and event-specific mission IDs. The Live Event Console launches an
existing event mission. The Participant App renders story, instructions,
video, image, and document links from the mission record.

Mission Studio also supports private image, video, and PDF uploads to the
`exos-mission-media` Supabase Storage bucket. Mission records store stable
private references; each Streamlit app resolves them to short-lived signed URLs.

## Delivery rules

- Edit the repository directly.
- Deliver complete files or complete matched file sets.
- Compile and test before deployment.
- Use test events for development; preserve completed production event data.
