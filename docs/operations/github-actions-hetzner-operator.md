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
