# MevSpace Operator Lane

## Purpose

This lane provides an explicit, allowlisted operator surface for the NEW ED-Finder MevSpace host.

It is separate from the existing Hetzner production operator lane. The Hetzner dispatcher and environment guard remain unchanged.

## Target identity

- operator target: `mevspace`
- expected hostname: `ed-finder-prod`
- expected repository path: `/opt/ed-finder`

## Entry point

From `/opt/ed-finder`:

```sh
bash scripts/operator/dispatch-target.sh mevspace <stage>
```

The target router accepts only `hetzner` or `mevspace`. The MevSpace dispatcher accepts only named stages and never accepts arbitrary shell text.

## Initial read-only stages

| Stage | Purpose |
|---|---|
| `context` | Host, user, repo and Git identity checks. |
| `docker-status` | Docker server version and running-container status. |
| `pg18-lab-status` | Read-only identity/status checks for the exact `pg18-lab` container. |
| `pg18-lab-logs` | Reads the last 100 log lines by default; bounded to 1-500 via `PG18_LOG_LINES`. |
| `pg18-lab-settings` | Reads the selected PostgreSQL 18 tuning settings used by the lab. |

## Safety boundary

The initial MevSpace lane is intentionally read-only.

It does not:

- start, stop, restart, create, remove, or reconfigure containers;
- execute `ALTER SYSTEM` or other database writes;
- run migrations;
- modify the old Hetzner server;
- accept an arbitrary command string.

Any future write-capable action must be added as an explicit named stage and reviewed independently.

## MCP direction

The planned MCP bridge should expose these named operator actions rather than an unrestricted shell tool. The operator scripts remain the enforcement layer so GitHub Actions, MCP, or another front-end can share the same target and action allowlists.
