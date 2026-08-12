# AGENTS

This repository uses the following mandatory protocol before any EXOS or Formula R.A.C.E. work:

1. Read the following memory docs first:
   - `docs/EXOS_ARCHITECTURE.md`
   - `docs/EXOS_INVARIANTS.md`
   - `docs/EXOS_RELEASE_BASELINE.md`
   - `docs/EXOS_UAT_STATUS.md`
   - `docs/EXOS_DECISIONS.md`
   - `docs/RACE_HANDOVER.md` (when touching R.A.C.E.)

2. Confirm branch and HEAD (`git branch --show-current`, `git rev-parse --short HEAD`).
3. Inspect current working tree before editing.
4. Identify affected scope (Admin / Facilitator / Participant / Projector / Core / R.A.C.E.).
5. Confirm invariants that apply to the requested change.
6. Do not introduce architecture changes only to pass a failing test.
7. If architecture changes or policy changes are made, update repository memory docs in the same change.
