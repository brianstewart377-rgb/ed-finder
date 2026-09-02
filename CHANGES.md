# ED-Finder — Development Change Log

This file records the **V3-era** development history from the 2 September 2026 infrastructure cutover onward.

The complete V2-era development log through 31 August 2026 is preserved immutably at:

- [V2-era `CHANGES.md` at the final pre-decommission `main` commit](https://github.com/brianstewart377-rgb/ed-finder/blob/1dcc6531f61c2ac6ac6f1cc774f53cdee760b1fd/CHANGES.md)

Current production/infrastructure truth lives in [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md), while programme authorization and next work live in [`docs/ROADMAP.md`](docs/ROADMAP.md).

Do not treat historical production statements in the linked V2 log as current operator instructions.

---

## 2026-09-02 — V3 infrastructure cutover and Hetzner V2 decommission

**The former Hetzner V2 production host is retired** — The old host has been decommissioned and is no longer an ED-Finder production or operator target. `ed-finder.app` is now served from the V3 replacement infrastructure. The replacement backend, PostgreSQL 18 data plane, backup path, and Frontier identity foundation are online while the complete V3 product interface is brought into service.

**The repository now has one explicit infrastructure authority** — Added `docs/operations/infrastructure-status.md` to state the current production boundary, legacy-data disposition, retired host assumptions, and operator stop rules. Historical Stage 17/18/19 evidence keeps its original Hetzner references where those references describe what actually happened.

**Old Hetzner runbooks are now visibly retired** — Reworked the operator-command context, operator-script README, GitHub Actions Hetzner Operator guide, Windows SSH deployment guide, and hosted Hetzner review guide so they cannot reasonably be mistaken for current V3 instructions. Retired scripts/runbooks must not be repointed at the replacement host simply by changing hostnames, IPs, paths, or environment variables.

**The root README is V3-first** — Replaced the former giant Hetzner/PostgreSQL-16 setup guide with a current project entrypoint covering the V3 transition, Stage 27 authority, current source-of-truth documents, repository layout, frontend/backend development paths, production/operator boundaries, and the retained V2 migration vault. The old README remains available immutably in Git history for forensic and historical use.

**The development log is re-baselined at the cutover boundary** — This `CHANGES.md` now starts with the V3 infrastructure era instead of carrying a stale header that said production lived on Hetzner/Docker. The full earlier changelog remains linked above at the immutable pre-decommission commit rather than being silently discarded or rewritten.

### Legacy V2 migration vault

The validated V2 PostgreSQL custom-format dump remains retained offsite as a selective migration/recovery source:

- former on-host path: `/data/backups/postgres/edfinder_20260823T021001Z.dump`
- size: `75,931,356,521` bytes
- SHA-256: `20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1`
- recorded offsite sync success: `2026-08-23T05:32:41Z`

It is **not** the V3 operating database. V3 uses a fresh PostgreSQL 18 environment; do not copy the former PostgreSQL 16 physical data directory into it. Public/reconstructable data should be reimported/rebuilt, with only explicitly justified irreplaceable/private/manual/history data selectively migrated from the vault.

### Public interface transition

The public domain is on the replacement infrastructure, but full finder functionality is still being migrated. The temporary V3 transition/status surface must not be confused with completion of the Stage 27 product/runtime programme. `docs/ROADMAP.md` remains the authority for what implementation work is actually authorized.

---

## Historical boundary

All development entries dated **31 August 2026 and earlier** remain part of the project record in the immutable V2-era changelog linked at the top of this file.

Those records include the Stage 25 product programme, Stage 26 renderer/map work, Stage 27A contract opening, data repair and storage recovery, CI restoration, production deployments, migration/operator history, and earlier application work. They are intentionally preserved as written rather than edited to make their old production language sound current.
