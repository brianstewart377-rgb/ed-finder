# GitHub Actions Hetzner Operator

> **RETIRED — 2 September 2026**
>
> The former Hetzner V2 production host has been decommissioned and is no longer an ED-Finder operator target. Do not run the Hetzner Operator workflow as a current production operation. This document is retained as historical operator documentation.
>
> See `docs/operations/infrastructure-status.md` for the current infrastructure boundary.

## Historical purpose

This manual workflow ran a small allowlisted set of operator checks on the former Hetzner host without pasting large shell blocks into SSH.

## Historical stages

| Stage | What it did |
|---|---|
| `context` | Showed hostname, user, repo path, git branch, recent commits, and git status. |
| `git-clean-check` | Confirmed the Hetzner repo working tree was clean. |
| `latest-artifacts` | Listed recent JSON artifacts for the selected `artifact_stage`. |
| `latest-artifact-summary` | Summarised the newest JSON artifact for the selected `artifact_stage`. |

The workflow read former operator artifacts from:

`/var/lib/ed-finder/operator-artifacts/<artifact_stage>`

That path on the retired Hetzner host is no longer an available production surface.

## Retired secrets

The workflow historically used repository secrets named:

- `HETZNER_OPERATOR_HOST`
- `HETZNER_OPERATOR_PORT`
- `HETZNER_OPERATOR_USER`
- `HETZNER_OPERATOR_SSH_KEY`

Do not recreate or rotate these solely to revive the retired lane. Remove/retire them through the repository's credential-cleanup process when no other current workflow depends on them.

## Do not transplant this workflow

Do not change the old host value, expected hostname, or paths and then run this workflow against the V3 replacement host. The replacement environment has a different architecture and safety boundary.

Any production workflow for V3 must explicitly target the replacement environment and be reviewed as a current V3 operator path.

## Current V3 recovery lane

The separate `ChatGPT ed-new Ops` workflow has a narrowly scoped recovery operation named `recover-v3-runtime-contract`. That is a replacement-host lane, not a continuation of the Hetzner Operator workflow.

It targets only the retained container `edfinder-v3-phase4c-full-20260827_r5-postgres` and derives the source root and Compose files from Docker Compose labels. It never inspects container environment values, contacts the database, or writes to the remote host. The archive is streamed to the Actions runner and uploaded with a file manifest, machine-readable safety receipt, and archive SHA-256 sidecar.

The lane requires the environment secret `ED_NEW_OPERATOR_KNOWN_HOSTS` to hold the pinned OpenSSH known-host entry for `ED_NEW_OPERATOR_HOST` and `ED_NEW_OPERATOR_PORT`. Runtime host discovery (`ssh-keyscan`) is prohibited.

Recovery is limited to Compose YAML, Dockerfile/Containerfile build inputs, `.sql`, `.sh`, `.py`, and non-secret-name `.md`, `.txt`, and `.json` files. It fails closed on `.env` and secret/credential/token/key/certificate names, logs, backups, dumps, database data/volumes, pgBackRest or SSH material, symlinks, special files, paths outside the label-resolved source root, and file-count or byte limits. File contents are not printed to Actions logs.

## Historical record rule

References in Stage 17/18/19 evidence to this workflow should remain unchanged when they describe what actually happened. They are historical evidence, not current instructions.
