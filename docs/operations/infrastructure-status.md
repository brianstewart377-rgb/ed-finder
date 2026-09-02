# Infrastructure Status

## Current production boundary

ED-Finder production is on the V3 replacement infrastructure.

The current environment uses PostgreSQL 18, the current backup/PITR design, the Frontier identity service, and the replacement-host operator boundary. Production actions must use only current V3 runbooks and workflows that explicitly target this environment.

Do not infer production authority from old Git history, archived artifacts, removed workflows, or obsolete server-side paths.

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
