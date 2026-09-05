# ED-Finder

ED-Finder is an Elite Dangerous exploration, system-finding, spatial inspection,
colony-planning, evidence-review, and export project. The product journey is:

> **Explore → Inspect → Plan → Review / Export**

## Current V3 baseline

- Production is the V3 environment `ed-finder-prod` at
  `nb79a3d.mevnode.com`, using PostgreSQL 18. Hetzner/V2 is gone; V2 deployment,
  database, recovery, and smoke-test receipts are history only.
- Contabo hosts three Codex runners. It is not production and must not be used
  as an assumed or hard-coded release-checkpoint target.
- [`apps/web/`](apps/web/) is the V3 browser target: Svelte/SvelteKit with a
  fresh Babylon renderer behind renderer-neutral boundaries.
- React, React Three Fiber (R3F), and Three.js are migration and historical
  evidence, not the target architecture. R3F winning the Stage 26 bake-off is
  an accurate historical fact, not current implementation authority.

## Current authority

Use this entry point and then the authority for the question being answered:

1. [`docs/ROADMAP.md`](docs/ROADMAP.md) — current status, execution order, and
   authorization.
2. [`docs/development/v3-application-stack-decision.md`](docs/development/v3-application-stack-decision.md)
   — locked V3 application stack and ownership boundaries.
3. [`docs/colonisation-redesign/spatial-platform-product-contract.md`](docs/colonisation-redesign/spatial-platform-product-contract.md)
   — current spatial product and truth contract.
4. [`docs/colonisation-redesign/spatial-platform-architecture-decision.md`](docs/colonisation-redesign/spatial-platform-architecture-decision.md)
   — current renderer-neutral spatial architecture.
5. [`docs/development/v3-browser-validation-lanes.md`](https://github.com/Alien-alien/ed-finder/blob/12eebac48ca9286e0fd8c180cc5f552dc922d07e/docs/development/v3-browser-validation-lanes.md)
   on the active PR #601 integration lane — browser validation lanes and
   evidence expectations.
6. [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md)
   — current production and recovery boundary.
7. [`CLAUDE.md`](CLAUDE.md) — agent and repository rules only; it is not
   product authority.

The V3 coordination control plane is supporting process documentation, not
product authority. Stage 27A audits are supporting evidence.

## Current work

[PR #601](https://github.com/Alien-alien/ed-finder/pull/601) is the active
integration lane. Its known head
`12eebac48ca9286e0fd8c180cc5f552dc922d07e` contains real
Explore/Finder → Babylon → Inspect integration and the Review Lab rebase work;
it is not foundation-only. Exact-head validation remains red and is being
stabilized, so that head is not yet accepted or promoted.

The immediate sequence is maintained in the
[`ROADMAP`](docs/ROADMAP.md). Search and spatial-index/grid/cluster design,
scoring and archetype-versus-Ratings ownership, and PostgreSQL 18 derived-data
bootstrap remain open decision gates. This documentation update does not decide
them.

## Historical-document rule

Stage 17–26 documents, Stage 25/26 status prose, the Stage 26 R3F result,
superpowers map plans, V2 receipts, and old deployment/runbook material are
historical evidence. They may explain prior decisions but never authorize
current implementation or operations. If they conflict with the current
authorities above, the current authorities win.

Preserve useful history rather than rewriting it to look current. Start at
[`docs/archive/README.md`](docs/archive/README.md) for the archive rule and at
[`docs/colonisation-redesign/README.md`](docs/colonisation-redesign/README.md)
for the spatial-document index.

ED-Finder is an unofficial community project and is not endorsed by Frontier
Developments. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
