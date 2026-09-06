# Infrastructure Status

## Current production boundary

ED-Finder production is `ed-finder-prod` at `nb79a3d.mevnode.com` on the V3
replacement infrastructure.

The current environment uses PostgreSQL 18, the current backup/PITR design, the Frontier identity service, and the replacement-host operator boundary. Production actions must use only current V3 runbooks and workflows that explicitly target this environment.

Do not infer production authority from old Git history, archived artifacts, removed workflows, or obsolete server-side paths.

Hetzner/V2 is decommissioned. Its host, container, cron, database, backup,
maintenance, smoke-test, and rollback receipts are historical only. They do not
describe this V3 environment.

## Contabo runner and checkpoint boundary

Contabo hosts exactly three self-hosted Codex runners. It is not ED-Finder
production. It is now the selected first V3 live-checkpoint target only through
the separate environment-gated application checkpoint boundary; this does not
make it a production target or authorize production credentials/data/routing.

Read-only inspection on 2026-09-06 proved host identity
`vmi3542235` / `vmi3542235.contaboserver.net`, `x86_64`, 8 logical CPUs,
24,608,576 KiB RAM (23,340,792 KiB then available), and 268,809,076,736 bytes
free on the root filesystem. Exactly three runner services were active. Only
SSH on TCP 22 and loopback DNS on TCP 53 were listening. No container runtime,
Compose installation, containers, container networks or volumes were present.

The reviewed checkpoint namespace is `edfinder-v3-checkpoint`, limited to the
`api` and `web` application services and 2 CPUs/2 GiB combined. Its lifecycle
is persistent: application upgrades never rebuild or tear down infrastructure.
The exact stopped facts and external-authority blockers live in
`deploy/v3-live-checkpoint/target-authority.json`. In particular, there is no
authorized checkpoint database/data source, origin/edge wiring, secret mount,
GHCR pull authority or durable receipt store yet, so first-deployment mutation
remains stopped. Production PostgreSQL/data must not fill that gap.

Ollama was experimental residue used to test local inference for Octopus. It
has been removed from production and is not part of the V3 architecture.

## V3 database recovery boundary

This repository **does not currently contain an executable PostgreSQL 18 backup/restore/PITR recovery runbook**. This file records the infrastructure boundary; it is not itself a recovery procedure.

Until a reviewed V3 database recovery runbook is added or an already-authorized current V3 operator procedure is explicitly identified, repository-driven production database backup restoration, PITR execution, or disaster-recovery commands are **not authorized**. Stop rather than adapting the retired V2 PostgreSQL/Compose procedures.

The absence of an in-repo execution runbook must remain visible; do not fill it with guessed hostnames, storage targets, credentials, PostgreSQL paths, or recovery commands.

## Legacy migration vault

A validated custom-format PostgreSQL dump is retained offsite solely as a selective legacy migration source for genuinely irreplaceable/private/manual/history data.

Validated dump identity:

- source filename: `edfinder_20260823T021001Z.dump`
- size: `75,931,356,521` bytes
- SHA-256: `20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1`
- offsite sync recorded successful: `2026-08-23T05:32:41Z`

The dump is not the operating database. Do not restore it wholesale into production and do not copy an older PostgreSQL physical data directory into PostgreSQL 18.

## Current sources of truth

- Application and infrastructure code: reviewed GitHub branches and PRs.
- Programme authority: `docs/ROADMAP.md`.
- Engineering/agent constraints: `CLAUDE.md`.
- Current operator boundary: this document plus current V3 operator workflow documentation.
- Public/reconstructable galaxy data: reimport/rebuild through the current data path.
- Legacy irreplaceable/private/manual/history data: selectively migrate from the validated offsite dump only when justified.
- Redis/cache state: disposable and rebuildable.
- NATS/JetStream transport state: not canonical domain truth; rehydrate from authoritative state when required.

## Operator rule

Before any production or recovery action, identify the target environment and the current V3 runbook explicitly. If an instruction is not present in current V3 documentation, stop rather than adapting an obsolete procedure.
