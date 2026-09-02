# Operator Command Contexts

## Infrastructure status

**The former Hetzner V2 production host was decommissioned on 2 September 2026 and no longer exists as an ED-Finder operator target.**

See `docs/operations/infrastructure-status.md` for the current infrastructure boundary and legacy-data disposition.

Any instruction that expects the retired Hetzner hostname `ed-finder`, the old production IP, or the former host's `/opt/ed-finder` or `/var/lib/ed-finder` paths is historical unless a current V3 runbook explicitly says otherwise. Do not attempt to revive or reinterpret an old Hetzner command against the replacement host.

## Purpose

This document separates ED-Finder command contexts so repository work, local development, current V3 production operations, and retired V2 instructions are not confused.

## Current environments

| Environment | Typical context | Purpose |
|---|---|---|
| Codex / repo environment | A checked-out repository or GitHub branch/PR | Code, docs, tests, validation, commits, and PRs. |
| DAVE2 / local development | Developer checkout and disposable local services | Local development and non-production validation. |
| V3 replacement production | Current replacement-host runbooks only | Current production services, backup/recovery, identity, and V3 operations. |
| Retired Hetzner V2 | Historical documents only | Evidence of former V2 operations; **not an executable operator target**. |

## Codex / repo environment

Use Codex/repository tooling for:

- editing code and documentation;
- writing and running repository tests;
- local/static validation;
- opening and updating PRs;
- documenting operator procedures without executing production commands.

Repository automation must not infer that an old Hetzner runbook is current merely because the script or document remains in Git history.

## DAVE2 / local development

DAVE2/local development is useful for local builds, disposable services, and non-production experiments. It is not proof that a production command is safe.

Do not substitute a local Docker stack or local PostgreSQL instance for current V3 production when validating production procedures.

## V3 replacement production

Production commands must come from a current runbook that explicitly identifies the replacement environment and its safety boundary.

Before any production action:

1. identify the target host/environment explicitly;
2. verify the current runbook is V3/replacement-host guidance rather than a retained Hetzner document;
3. verify the intended host identity before executing destructive or stateful commands;
4. preserve the current V3 backup, credential, and least-privilege boundaries.

Do not transplant commands from retired Hetzner runbooks onto the replacement host simply because paths or Docker service names look similar.

## Retired Hetzner V2 context

The following former operator assumptions are retired:

- hostname `ed-finder` as the active production host;
- Hetzner IP `95.216.33.156` as an active ED-Finder production endpoint;
- `/opt/ed-finder` on the old Hetzner host as the live deployment checkout;
- `/var/lib/ed-finder/operator-artifacts` on the old host as a live artifact surface;
- old production Docker/PostgreSQL containers on that machine;
- the `Hetzner Operator` GitHub Actions workflow as a live production control path;
- the Windows Hetzner SSH deployment wrapper as a current production deployment path;
- the hosted review environment that depended on the old Hetzner production Nginx edge.

Historical Stage 17/18/19 documentation may retain these names and paths because they accurately describe where that work occurred. Historical accuracy is not execution authority.

## Commands that must stop when they target retired Hetzner

Do not run a command as current production guidance if it:

- says to SSH to the former Hetzner host;
- changes into `/opt/ed-finder` specifically on the retired host;
- expects `/var/lib/ed-finder/operator-artifacts` from the retired host;
- invokes the former production Docker Compose project;
- queries the former PostgreSQL 16 production containers;
- runs old imports, warehouse loads, reconciliation, canonical apply, or scheduler wiring against that retired environment.

These commands may remain in historical records, archived scripts, and closeout evidence.

## Legacy V2 artifacts and data

The old server is not the recovery boundary. The validated V2 PostgreSQL dump is retained offsite as the legacy migration vault.

Use it only through a purpose-built, allowlisted migration/recovery process. Do not restore it wholesale as V3 and do not copy the old PostgreSQL physical data directory into PostgreSQL 18.

Production artifacts that were not deliberately retained off-host should be considered unavailable after Hetzner decommission unless another recorded copy exists.

## Secret handling

Never paste real DSNs, passwords, secrets, private keys, recovery codes, or credential-bearing URLs into chat or Git.

Current V3 credentials must be managed through the current recovery/secret process. Do not recover obsolete V2 credentials merely to make an old runbook executable.

## How to recognise the right prompt

Use Codex/repository tooling when the prompt asks for repo edits, docs, tests, validation, commits, or PRs.

Use DAVE2/local development for non-production application work.

Use current V3 operator procedures only when the prompt explicitly concerns the replacement production environment and the relevant current runbook has been identified.

If a prompt says "Hetzner", references the old hostname/IP, or relies on an old Hetzner-only path, treat it as historical and stop unless the task is explicitly archival analysis.

## Operator scripts

`scripts/operator/` contains a mixture of current replacement-host helpers and retained legacy/operator-history material. Read `scripts/operator/README.md` before executing anything from that directory.

A script whose guard requires the retired Hetzner environment is not a current production command. Do not weaken its guard just to make it run somewhere else.

## Final recommendation

Keep four concepts separate:

- repository work;
- local/non-production development;
- current V3 replacement-host operations;
- retired Hetzner V2 history.

The former Hetzner host is gone. Preserve its records as history, use the offsite V2 dump only as a selective migration vault, and require explicit current V3 runbooks for all production operations.
