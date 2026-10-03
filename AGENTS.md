# ED-Finder Agent Contract (AGENTS.md)

This file exists so that agents and automated reviewers that read `AGENTS.md`
(e.g. Codex) see the same repository contract that Claude-based agents read in
`CLAUDE.md`.

**`CLAUDE.md` in this repository is the canonical, authoritative agent contract.
Read it in full and follow it exactly.** This file is a pointer plus the few
facts most often missed by a reviewer that only scans the working tree.

## Critical facts for code review

- **The React tree under `frontend/` is RETIRED.** It is historical migration
  and behaviour evidence only — it is **not** built, tested, a release gate, or
  a live caller. Do **not** reason about product behaviour from
  `frontend/src/...`. A finding of the form "the Finder sends X, so the API
  returns 422" is **invalid** if "the Finder" is `frontend/`.

- **The live application frontend is `apps/web/` (Svelte 5 / SvelteKit).** It is
  the sole caller of the product API. If you need to know what the client sends
  to an endpoint, read `apps/web/`, never `frontend/`. As of this branch the
  Svelte Finder (`apps/web/src/lib/features/explore/`) issues only a minimal
  default search body; the rich faceted Finder UI (population/economy/sort
  controls) is **not built yet** (roadmap "F4").

- Backend API lives under `apps/api/`; migrations under `sql/` (V3 projections
  under `sql/v3/migrations/`). Preserve fail-closed validation, parameterised
  SQL, and bounded inputs.

- V3 migrations have a **prod-promotion registration gate** — adding a file
  under `sql/v3/migrations/` can require manifest registration before the
  Finder cutover is enabled. Trace that cascade before adding one.

## Authority order

Start at `README.md`, then follow the authority chain defined in `CLAUDE.md`
(`docs/ROADMAP.md`, the V3 application-stack decision, the spatial-platform
contract and architecture decision, the browser-validation lanes, the
search/spatial derived-data decision, the Ratings V4 freeze, the infrastructure
status, then `CLAUDE.md` itself, then current code/tests on the target branch).

Git history, removed workflows, old artifacts, and superseded design documents
are **evidence only** — not current execution authority.

## CI and acceptance

Every pull request must satisfy the canonical
[Pull Request Acceptance Policy](docs/development/pull-request-acceptance-policy.md).
Acceptance is fail-closed and applies to the exact latest PR head SHA. Green CI
alone is insufficient: every substantive reviewer finding needs an explicit
recorded disposition.
