## Summary

- What changed?
- Why does it exist?

## Verification

- [ ] Relevant tests were run locally
- [ ] CI/local parity impact was considered
- [ ] Docs were updated if behavior or workflow changed

## Merge Acceptance

- Exact latest PR head SHA: `________________________________________`
- [ ] All protected CI/security/coverage/status checks passed for that exact SHA
- [ ] Codex Review (`chatgpt-codex-connector`) completed — status: `________`; reviewed SHA: `________________________________________`
- [ ] Octopus Review completed — status: `________`; reviewed SHA: `________________________________________`
- [ ] Paginated top-level PR conversation comments, formal review bodies, inline review comments, and unresolved review conversations/threads were inspected
- [ ] Every substantive finding has an explicit recorded disposition and no substantive unresolved thread remains
- Finding dispositions/evidence: `____________________________________________________________`
- Owner waiver: `none` (allowed only for an actually failed or unavailable named reviewer service; record replacement manual-review evidence and accepted risk)

Any new commit invalidates all prior CI and reviewer evidence. A pending or
still-reviewing service must be triggered when needed and awaited; ordinary
pending/in-progress review cannot be waived. All other safeguards in the
canonical [Pull Request Acceptance Policy](../blob/main/docs/development/pull-request-acceptance-policy.md)
continue to apply when an owner waiver is used.

## Repo Hygiene

- [ ] This change does not introduce a new visible repo-root file without an explicit reason
- [ ] Any new route/surface is intentionally one of: canonical live product, historical reference, or local-only scratch
- [ ] Any prototype/preview/one-shot artifact has an explicit fate: promote, archive, or delete
- [ ] Historical scripts/docs were placed under an archive path instead of a live runtime path when appropriate
- [ ] Guard tests or policy docs were updated if the repo shape changed intentionally

## Notes

- Root-level control document remains `docs/ROADMAP.md`
- Repo-shape policy lives in `docs/development/repo-hygiene.md`
