# Repository Agent Protocol

Follow this protocol before changing EXOS or Formula R.A.C.E. It applies to
Codex, Claude Code, and human contributors.

1. Read `docs/EXOS_ARCHITECTURE.md`, `docs/EXOS_INVARIANTS.md`,
   `docs/EXOS_RELEASE_BASELINE.md`, `docs/EXOS_UAT_STATUS.md`, and
   `docs/EXOS_DECISIONS.md`. Also read `docs/RACE_HANDOVER.md` for R.A.C.E.
2. Inspect `git branch --show-current`, `git rev-parse --short HEAD`,
   `git status --short`, and the diff from the frozen Standard runtime baseline
   named in `docs/EXOS_RELEASE_BASELINE.md`.
3. Identify the affected scope: Admin, Facilitator, Participant, Projector,
   Core, or R.A.C.E.; then identify the applicable invariants before editing.
4. Keep Standard Core v2 paths on their documented v2 boundary. Do not add a
   Google Sheets or legacy fallback, and do not change identity/team assignment
   or ledger semantics incidentally.
5. Do not change architecture merely to satisfy a local test. Classify test,
   staging-runner, and human-UAT evidence separately; never infer one from
   another.
6. If a migration changes, record its forward/rollback/verification category,
   dependency order, and evidence-based installation status. A SQL file in Git
   is not proof that it is installed.
7. Update these memory documents in the same change when architecture,
   invariants, migration order, UAT status, or a documented decision changes.
