## Summary

- What changed?
- Why does it exist?

## Verification

- [ ] Relevant tests were run locally
- [ ] CI/local parity impact was considered
- [ ] Docs were updated if behavior or workflow changed

## Repo Hygiene

- [ ] This change does not introduce a new visible repo-root file without an explicit reason
- [ ] Any new route/surface is intentionally one of: canonical live product, historical reference, or local-only scratch
- [ ] Any prototype/preview/one-shot artifact has an explicit fate: promote, archive, or delete
- [ ] Historical scripts/docs were placed under an archive path instead of a live runtime path when appropriate
- [ ] Guard tests or policy docs were updated if the repo shape changed intentionally

## Notes

- Root-level control document remains `docs/ROADMAP.md`
- Repo-shape policy lives in `docs/development/repo-hygiene.md`
