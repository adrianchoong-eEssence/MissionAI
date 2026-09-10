# EXOS Live Location + Announcements V1

This is a reusable, additive Core-v2 capability. It is not an AIA-only feature and it does not create a global current-event context. Every read, consent, update, checkpoint, announcement, acknowledgement, and audit row is explicitly scoped by `EventID`.

Live location is opt-in at the participant level. A participant must first enable consent through their own active session, and can stop it at any time. The browser component makes clear that it requires a visible page and that background tracking is not guaranteed. It does not award a score or change a mission state.

The Core configuration accepts a cadence from 15 to 30 seconds. The default is 20 seconds. `CURRENT` means an update was received at or inside the deterministic event setting `StaleAfterSeconds`; the default is 90 seconds. Older known updates are `STALE`. No consent, no enabled event window, permission failure, or no update is `UNAVAILABLE`.

Raw updates retain captured time, received time, accuracy (when the browser provides it), heading, speed, participant, team, and event. The default retention is 24 hours, configurable from 1 to 168 hours. `exos_v2_cleanup_live_location` performs audited event-scoped cleanup; an authorised scheduler/operator must run it. A stopped participant has no new updates; retained history remains event-scoped reporting data through the configured retention period.

Mission Control receives an authorised event map with all-team, team, and individual views. The map marks retained points `UNAVAILABLE` whenever tracking is disabled or outside its bounded window. Team location considers only `CURRENT` reporters. If current reporters are farther apart than the event separation threshold (250m by default), the team is marked `SEPARATED` and no misleading centroid is emitted. A trail is an operator-requested, bounded history read.

The checkpoint foundation is deliberately non-scoring: `OUTSIDE`, `NEAR`, and `ARRIVED` are proximity facts only. Evidence/review remains the canonical mission-completion path.

Announcements are reliable in-app messages, not native background push. Participant polling uses the existing five-second live-state watcher. `ALL + URGENT` requires an explicit Mission Control confirmation. A per-event opaque idempotency key makes a retried operator send return the original announcement instead of creating a duplicate; reuse of that key for different content is rejected. Team and participant targets are validated against the same event, and acknowledgements are participant/event/announcement scoped and audited. Kai calls the same adapter operations as Mission Control; no normal Kai path writes database tables directly.

Migration order: install `048_exos_core_v2_live_location_announcements_v1.sql`, then apply an event-specific configuration such as `049_aia_tech_live_location_v1_configuration.sql`. The AIA configuration prepares individual tracking but intentionally leaves it inactive until an owner supplies the bounded real event window.
