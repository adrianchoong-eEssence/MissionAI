# RC3 Operational Certification — Facilitator Test Script

Target duration: **27 minutes**. Run only on the authorised isolated certification event. Do not use the live RACE event or real participant records.

## Before the clock starts

- [ ] Record date/time, production URL, EventID, join code and running commit.
- [ ] Confirm facilitator, observer, rollback owner and four physical browser/device combinations are ready.
- [ ] Confirm the test event has one leader, one member, one launchable activity and one submission requiring approval.
- [ ] Open Control Centre, Participant, Projector and telemetry views.
- [ ] Record starting participant, submission and credit counts.
- [ ] Abort if the event is not isolated, telemetry is unavailable or the running commit cannot be verified.

## 0:00–05:00 — Join and identity

1. On all four device/browser combinations, join once with a unique test name.
2. Record ParticipantID, TeamID, country, flag and leader status.
3. Refresh each participant page.
4. Background each browser, restore it, then close and reopen it.
5. Confirm the original identity is restored without another allocation.
6. Tap **Join** twice on one device while the first request is pending.
7. Confirm exactly one participant row exists and no credits were created.

Pass only if ParticipantID, TeamID, country, flag and leader status remain identical on every recovery.

## 05:00–10:00 — Leader recovery

1. On the leader device, record ParticipantID, TeamID and submission rights.
2. Refresh, background/resume, then close/reopen the leader browser.
3. Confirm leader status and leader-only submission rights return automatically.
4. Simulate leader loss by closing the leader browser.
5. In **Control Centre → Team Management**, enter the facilitator name, select the original leader and choose **Recover Participant**.
6. Reopen the leader device and confirm the same identity, team, country, flag, credits and leader rights.
7. Record the recovery/audit evidence. Do not use **Transfer Team Leader** unless the approved test explicitly calls for a transfer.

Pass only if one leader remains, no participant moves team and no new participant or credit row appears.

## 10:00–15:00 — Submission and approval

1. Launch the authorised test activity from Control Centre.
2. Submit one evidence item from the leader device.
3. Tap **Submit** twice while the first request is pending.
4. Confirm one canonical submission appears as **Pending**.
5. In the Control Centre approval queue, select **Approve** once.
6. Refresh the participant, leaderboard and report views.
7. Confirm one approval, one award transaction and one leaderboard increment.

Pass only if no duplicate submission or duplicate credits exist and all three views reconcile.

## 15:00–19:00 — Broadcast and recovery

1. In Control Centre, set a short test announcement and choose **Apply Broadcast**.
2. Confirm the projector shows the exact announcement and participant state is unchanged.
3. If it does not appear, follow `RC3_RECOVERY_PLAYBOOK.md` once.
4. Clear the test broadcast and confirm the projector returns to its expected state.

Pass only if broadcast is event-scoped and participant identity, submissions and credits do not change.

## 19:00–24:00 — Production load certification

1. Start the approved isolated load profile at the authorised concurrency level.
2. Exercise join, restore, submit, approve and broadcast while telemetry is recording.
3. Record request count, success rate, error rate, p50, p95, p99, database connections/CPU, lock waits and timeouts.
4. Stop immediately for any identity/team/leader mutation, duplicate participant/submission/credit, cross-event leakage, non-retryable server error or sustained database saturation.

Pass thresholds: join success **≥99.5%**, p95 **≤2 s**, p99 **≤5 s**, retryable 429/5xx **<1%**, non-retryable server errors **0**, sustained database CPU/connections **<70%**, lock-wait p95 **<250 ms**, and measured capacity **≥30% above forecast peak**.

## 24:00–27:00 — Reconcile and sign off

1. Stop load traffic and close registration on the test event.
2. Compare ending participant, submission and credit counts with expected deltas.
3. Confirm zero duplicate participants, submissions or credits and zero team/leader mutations.
4. Complete the device matrix, observer sheet and sign-off sheet.
5. Remove synthetic data only through the separately approved cleanup procedure.

Any failed acceptance condition makes RC3 **NO GO**. Capture evidence, stop the affected test and use only the matching recovery playbook action.
