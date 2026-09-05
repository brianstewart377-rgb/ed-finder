# ED-Finder Roadmap

This is the authority for current programme status, execution order, and
authorization. It answers “what next?”. Older stage plans and status text do
not.

## Authority

Read this roadmap with the authority for the surface being changed:

- [`../README.md`](../README.md) — repository front door and current summary.
- [`development/v3-application-stack-decision.md`](development/v3-application-stack-decision.md)
  — locked V3 application stack and ownership boundaries.
- [`colonisation-redesign/spatial-platform-product-contract.md`](colonisation-redesign/spatial-platform-product-contract.md)
  — spatial product, journey, and truth contract.
- [`colonisation-redesign/spatial-platform-architecture-decision.md`](colonisation-redesign/spatial-platform-architecture-decision.md)
  — renderer-neutral spatial architecture.
- [`development/v3-browser-validation-lanes.md`](https://github.com/Alien-alien/ed-finder/blob/12eebac48ca9286e0fd8c180cc5f552dc922d07e/docs/development/v3-browser-validation-lanes.md)
  on the active PR #601 integration lane — exact-head browser-validation lanes
  and evidence expectations.
- [`operations/infrastructure-status.md`](operations/infrastructure-status.md)
  — production, database, backup, and recovery boundary.
- [`../CLAUDE.md`](../CLAUDE.md) — agent and repository rules only.

The V3 coordination control plane supports integration process and does not set
product direction. Stage 27A audits support decisions with evidence; they do not
supersede these authorities.

## Current baseline

- The product journey is **Explore → Inspect → Plan → Review / Export**.
- Production is `ed-finder-prod` at `nb79a3d.mevnode.com` on PostgreSQL 18.
  Hetzner/V2 has been decommissioned, and V2 receipts cannot prove current
  production state.
- Contabo consists of three Codex runners. It is neither production nor an
  implicit checkpoint environment.
- The V3 browser target is [`../apps/web/`](../apps/web/): Svelte/SvelteKit plus
  a fresh Babylon implementation behind the current renderer-neutral contracts.
  React/R3F/Three is retained only as migration, parity, and historical
  evidence. R3F's Stage 26 bake-off win remains history, not present authority.
- [PR #601](https://github.com/Alien-alien/ed-finder/pull/601) is the active
  integration lane. Known head
  `12eebac48ca9286e0fd8c180cc5f552dc922d07e` includes real
  Explore/Finder → Babylon → Inspect and Review Lab rebase code. Exact-head
  validation is still red/stabilizing; the head is not yet accepted.

## Current execution order

Work proceeds in this order:

1. Stabilize browser validation on the exact latest PR #601 head.
2. Harden the CPython 3.14 and uv release path.
3. Obtain exact-head CI and reviewer acceptance with substantive findings
   resolved or explicitly dispositioned.
4. Merge PR #601 only after those exact-head gates pass.
5. Run the immutable-release checkpoint and owner test against the explicitly
   selected target supplied by the current reviewed workflow/runbook. Do not
   encode a checkpoint host in this roadmap.
6. Perform an explicit, separately authorized production promotion only after
   the checkpoint evidence is accepted.

Passing an earlier step does not authorize a later one. In particular, merge
does not itself authorize production promotion.

## Active decision gates

These questions are active and unresolved. Work that depends on them must stop
at the gate or present evidence for an explicit decision:

- the search contract and spatial-index, reference-grid, and cluster design;
- scoring ownership and the archetype-versus-Ratings model;
- the PostgreSQL 18 derived-data bootstrap and its proof of completeness,
  repeatability, and safe release integration.

Do not infer an answer from Stage 17–26 documents, existing dependencies,
historical schemas, V2 data receipts, or an implementation experiment.

## Later/deferred capabilities

The following remain part of the product direction but are not authorized by
this immediate execution sequence:

- later System Map, Digital Twin, Commander History, route, and richer planning
  capabilities beyond the accepted PR #601 slice;
- retirement of React/R3F/Three or historical browser evidence before
  equivalent V3 behavior and validation have been accepted;
- production data repair, migration, or derived-data rebuild before its current
  gate and an explicit safe operator path are approved;
- further spatial performance, indexing, grid, clustering, and scoring work
  whose design gates remain open.

## History

Stage 17–26 plans and closeouts, Stage 25/26 status and authorization prose,
Stage 27A audits, superpowers map plans, the Stage 26 R3F selection/cutover
record, and all V2/Hetzner receipts remain useful historical or supporting
evidence. They do not answer “what next?” and do not authorize current work or
operations.

Historical documents should normally be preserved, with their original context,
rather than rewritten to simulate current authority. See
[`archive/README.md`](archive/README.md) and
[`colonisation-redesign/README.md`](colonisation-redesign/README.md).

If another document conflicts with this roadmap about current programme status,
sequencing, or authorization, this roadmap wins. For production and recovery
boundaries, [`operations/infrastructure-status.md`](operations/infrastructure-status.md)
wins.
