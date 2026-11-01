# Handoff drafts from Claude session claude-11 (2026-11-01)

Not for merging. Local-only working files from the session that ran the
Colony Planner, the 2026-10-31 audit fixes and the 3fd8e719 release, pushed
when that chat was retired.

- `s4b2-raven-import-task-draft.txt`: the Colony Planner S4b part 2 (Raven
  import button) Codex task, drafted but never dispatched. Its last paragraph
  adds the audit's lossless-ID requirement, the unmapped Raven type names and
  the Primary Port rules.
- `economy_spec_check.py`: an independent hundredths implementation of the S5a
  economy rules, used to confirm every answer key in tests/test_cpe_economy.py
  before dispatch. Run: `python economy_spec_check.py <repo root>`.
- `merge_when_required.sh`, `ci_then_merge_out_of_scope.sh`,
  `ci_then_octopus.sh`, `wait_head.sh`: the PR watcher scripts that session
  used (update-branch, required checks, Codex state, one Octopus request).
