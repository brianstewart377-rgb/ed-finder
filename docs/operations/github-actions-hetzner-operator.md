# GitHub Actions Hetzner Operator

## Purpose

This manual workflow runs a small allowlisted set of operator checks on Hetzner without pasting large shell blocks into SSH.

## Current stages

| Stage | What it does |
|---|---|
| `context` | Shows hostname, user, repo path, git branch, recent commits, and git status. |
| `git-clean-check` | Confirms the Hetzner repo working tree is clean. |
| `latest-artifacts` | Lists recent JSON artifacts for the selected `artifact_stage`. |
| `latest-artifact-summary` | Summarises the newest JSON artifact for the selected `artifact_stage`. |

## Artifact stage input

The workflow has an `artifact_stage` input.

Examples:

- `stage-18j`
- `stage-19`
- `stage-20a`

The value must start with `stage-` and may only contain letters, numbers, underscores, and hyphens.

The scripts read artifacts from:

`/var/lib/ed-finder/operator-artifacts/<artifact_stage>`

## Hard boundary

The workflow does not accept arbitrary shell commands.

Current stages do not perform:

- DB access;
- DB writes;
- migrations;
- station-type writes;
- canonical apply.

## Required GitHub secrets

Repository secrets:

- `HETZNER_OPERATOR_HOST`
- `HETZNER_OPERATOR_PORT`
- `HETZNER_OPERATOR_USER`
- `HETZNER_OPERATOR_SSH_KEY`

## How to run

1. Go to the GitHub repository.
2. Open the **Actions** tab.
3. Select **Hetzner Operator**.
4. Click **Run workflow**.
5. Choose a stage.
6. Enter an artifact stage if needed, for example `stage-18j`.
7. Click **Run workflow**.

## Future stages

Any future production DB write stage must be added by a separate PR and must not use arbitrary command input.

## Separate ed-new V3 recovery lane

The `ChatGPT ed-new Ops` workflow has one narrowly scoped recovery operation:
`recover-v3-runtime-contract`. It targets only the retained container
`edfinder-v3-phase4c-full-20260827_r5-postgres` and derives the source root and
Compose files from Docker Compose labels. It never inspects container
environment values, contacts the database, or writes to the remote host. The
archive is streamed to the Actions runner and uploaded with a file manifest,
machine-readable safety receipt, and archive SHA-256 sidecar.

The lane requires the environment secret `ED_NEW_OPERATOR_KNOWN_HOSTS` to hold
the pinned OpenSSH known-host entry for `ED_NEW_OPERATOR_HOST` and
`ED_NEW_OPERATOR_PORT`. Runtime host discovery (`ssh-keyscan`) is prohibited.

Recovery is limited to Compose YAML, Dockerfile/Containerfile build inputs,
`.sql`, `.sh`, `.py`, and non-secret-name `.md`, `.txt`, and `.json` files.
It fails closed on `.env` and secret/credential/token/key/certificate names,
logs, backups, dumps, database data/volumes, pgBackRest or SSH material,
symlinks, special files, paths outside the label-resolved source root, and
file-count or byte limits. File contents are not printed to Actions logs.
