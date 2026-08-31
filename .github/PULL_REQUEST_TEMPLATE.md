## Summary

- What changed?
- Why does it exist?

## Verification

- [ ] Relevant tests were run locally
- [ ] CI/local parity impact was considered
- [ ] Docs were updated if behavior or workflow changed

## Merge Acceptance

- Latest PR head SHA: `________________________`
- [ ] All required CI/security/coverage/status checks passed for that head
- [ ] Codex Review (`chatgpt-codex-connector`) completed — status: `________`; reviewed SHA: `________________________`
- [ ] Octopus Review completed — status: `________`; reviewed SHA: `________________________`
- [ ] Paginated top-level conversation comments, formal review bodies, inline review comments, and unresolved review conversations were inspected
- [ ] Every substantive finding has a recorded disposition and no substantive unresolved conversation remains
- Finding dispositions/evidence: `____________________________________________________________`
- Explicit owner waiver (normally `none`; if used, name unavailable reviewer, replacement manual review/evidence, and accepted risk): `none`

Any new commit invalidates older review evidence. Pending, still-reviewing, or
errored reviewers are fail-closed unless the repository owner records the
explicit written waiver above.

## Repo Hygiene

- [ ] This change does not introduce a new visible repo-root file without an explicit reason
- [ ] Any new route/surface is intentionally one of: canonical live product, historical reference, or local-only scratch
- [ ] Any prototype/preview/one-shot artifact has an explicit fate: promote, archive, or delete
- [ ] Historical scripts/docs were placed under an archive path instead of a live runtime path when appropriate
- [ ] Guard tests or policy docs were updated if the repo shape changed intentionally

## Notes

- Root-level control document remains `docs/ROADMAP.md`
- Repo-shape policy lives in `docs/development/repo-hygiene.md`
