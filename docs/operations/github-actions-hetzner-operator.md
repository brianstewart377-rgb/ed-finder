# GitHub Actions Hetzner Operator

## Purpose

This manual workflow lets us run a tiny allowlisted set of safe operator checks on Hetzner without pasting large shell blocks into SSH.

## Current stages

The first version is read-only only.

| Stage | What it does |
|---|---|
| `context` | Shows hostname, user, repo path, git branch, recent commits, and git status. |
| `latest-artifacts` | Lists recent Stage 18J JSON artifacts and prints safe summaries. |

## Hard boundary

The first version does not perform:

- DB access;
- DB writes;
- migrations;
- station-type writes;
- canonical apply;
- arbitrary shell command execution.

## Required GitHub secrets

Add these repository secrets:

- `HETZNER_OPERATOR_HOST`
- `HETZNER_OPERATOR_PORT`
- `HETZNER_OPERATOR_USER`
- `HETZNER_OPERATOR_SSH_KEY`

## How to run

1. Go to the GitHub repository.
2. Open the **Actions** tab.
3. Select **Hetzner Operator**.
4. Click **Run workflow**.
5. Choose `context` or `latest-artifacts`.
6. Click **Run workflow**.

## Future stages

Any future production DB write stage must be added by a separate PR and must not use arbitrary command input.
