# Infrastructure Status

## Current status

**Effective 2 September 2026, the former Hetzner V2 production host has been decommissioned and is no longer available.**

`ed-finder.app` is now served from the V3 replacement infrastructure. The V3 database, backup system, and Frontier identity service run on the replacement host while the full V3 application interface is brought into service.

Do not issue commands, deployments, recovery steps, or operator instructions that assume the former Hetzner host still exists.

## Legacy V2 data

The former V2 PostgreSQL instance is not being migrated as the V3 operating database. V3 uses a fresh PostgreSQL 18 environment.

The validated V2 custom-format PostgreSQL dump remains retained offsite as the **legacy migration vault** for selective extraction of genuinely irreplaceable/private/manual/history data if required later.

Validated legacy dump identity:

- former on-host path: `/data/backups/postgres/edfinder_20260823T021001Z.dump`
- size: `75,931,356,521` bytes
- SHA-256: `20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1`
- offsite sync recorded successful: `2026-08-23T05:32:41Z`

The dump is a migration/recovery source only. Do not restore it wholesale as the V3 operating database and do not copy the former PostgreSQL 16 physical data directory into PostgreSQL 18.

## Current source of truth

- Application and infrastructure code: GitHub repository and reviewed branches/PRs.
- V3 runtime: replacement production infrastructure.
- Public/reconstructable galaxy data: reimport/rebuild through the V3 data path.
- Legacy irreplaceable/private/manual/history data: selectively migrate from the validated offsite V2 dump when justified.
- Redis/cache state: disposable and rebuildable; do not treat old Redis state as recovery authority.
- NATS/JetStream transport state: not canonical domain truth; rebuild/rehydrate from authoritative state where required.

## Retired Hetzner material

Historical Stage 17/18/19 documents, receipts, scripts, and runbooks may continue to mention Hetzner because that is where those operations actually occurred. Preserve those references as history.

However, runbooks that instruct an operator to connect to the former Hetzner host are **retired**. They must not be followed as current production instructions. Where retained, they should carry an explicit retirement notice and point here.

Legacy assumptions that are no longer valid include:

- hostname `ed-finder` as the active production host;
- Hetzner IP `95.216.33.156` as an active ED-Finder production endpoint;
- `/opt/ed-finder` on the former Hetzner host as the production deployment authority;
- `/var/lib/ed-finder/operator-artifacts` on the former host as a live operator surface;
- the `Hetzner Operator` GitHub Actions lane as a live production-operation path;
- `scripts/deploy-hetzner-over-ssh.ps1` as a current production deployment path;
- the old hosted review lane that depended on the Hetzner production Nginx edge.

## Operator rule

Before running any production or recovery command, identify the target environment explicitly. If an instruction says "Hetzner", expects the retired hostname `ed-finder`, or relies on the former host paths without an explicit V3/replacement-host context, treat it as historical and stop.

For V3 operations, use only current runbooks that explicitly name the replacement environment and current safety boundary.
