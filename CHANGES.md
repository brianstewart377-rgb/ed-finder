# ED-Finder — Development Change Log

This file records current-era development history from the 2 September 2026 infrastructure cutover onward.

Current production/infrastructure truth lives in [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md), while programme authorization and next work live in [`docs/ROADMAP.md`](docs/ROADMAP.md).

Older development history remains available through Git history and is not current operator authority.

---

## 2026-09-02 — V3 infrastructure cutover

**Production is on the replacement infrastructure** — `ed-finder.app` is served from the current V3 environment. PostgreSQL 18, the current backup/PITR boundary, Frontier identity, and replacement-host operator workflows are the production baseline while the complete product interface is brought into service.

**The repository now has one explicit infrastructure authority** — `docs/operations/infrastructure-status.md` defines current production and recovery truth. Obsolete server-specific workflows, deployment scripts, hosted-review machinery, database-maintenance procedures, and monitoring runbooks were removed from the current tree rather than carried forward as executable-looking history.

**The root README is current-only** — The repository entrypoint now describes the V3 platform, current programme authority, development workflow, migration vault, and current operator boundary without carrying obsolete deployment instructions.

**The development log is re-baselined at the cutover boundary** — Earlier entries remain available through Git history. They are intentionally not duplicated into the current tree where they could be mistaken for present-day operational guidance.

### Legacy migration vault

A validated PostgreSQL custom-format dump remains retained offsite solely as a selective migration source:

- filename: `edfinder_20260823T021001Z.dump`
- size: `75,931,356,521` bytes
- SHA-256: `20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1`
- recorded offsite sync success: `2026-08-23T05:32:41Z`

It is not the operating database. Production uses PostgreSQL 18; public/reconstructable data should be reimported or rebuilt, and only explicitly justified irreplaceable/private/manual/history data should be selectively migrated from the vault.

### Public interface transition

The public domain is on the replacement infrastructure, but full finder functionality is still being migrated. The current status surface must not be confused with completion of the Stage 27 product/runtime programme. `docs/ROADMAP.md` remains the authority for what implementation work is authorized.
