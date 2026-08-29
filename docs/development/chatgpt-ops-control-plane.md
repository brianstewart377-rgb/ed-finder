# ChatGPT Operations Control Plane

## Purpose

Provide a small, auditable operations interface that lets ChatGPT manage routine ED-Finder operational tasks without requiring the owner to relay commands between ChatGPT and a shell session.

This is deliberately **not** an unrestricted remote shell. It exposes named, fail-closed operations that wrap existing guarded scripts and runbooks.

## Initial operation set

- `production-status`
- `backup-status`
- `pgbackrest-check`
- `api-smoke`
- `collect-logs`
- `restart-api`
- `restart-worker`
- `deploy-commit`
- `run-governed-migrations`

Destructive operations such as deleting volumes, pruning Docker data, dropping databases, reinitializing PostgreSQL, or rerunning Phase 4C are intentionally excluded.

## Safety model

Every mutating operation must:

1. run the canonical repository/project state gate first where applicable;
2. verify the expected target host and deployment identity;
3. call an existing guarded operator script or a purpose-built wrapper rather than ad-hoc shell commands;
4. fail closed when required inputs or safety checks are missing;
5. emit a machine-readable receipt;
6. never print credentials, tokens, passwords, or private keys.

The retained r5 production candidate remains protected by the existing `RETENTION_HOLD` and cleanup guards. No control-plane operation may bypass those protections.

## Delivery model

The first implementation should use GitHub Actions `workflow_dispatch` as the control surface because ChatGPT already has direct GitHub access. Workflows should invoke a small allowlisted dispatcher and existing operator scripts.

Server connectivity must use already-authorized deployment/SSH credentials if they exist in GitHub Actions. This repository change must not embed or create secrets in source control.

If the repository does not already have suitable Actions credentials, the workflow may be merged in an inert state and the one remaining owner action is to add the required GitHub Actions secret/runner connection.

## Receipts

Every run should record at least:

- operation name;
- requested commit/ref where relevant;
- start/end UTC;
- target host identity;
- exit status;
- bounded stdout/stderr with secret redaction;
- resulting deployment/database generation identity where relevant.

Receipts should be retained as Actions artifacts and/or in the existing operations receipt format.

## Permission boundary

The control plane is intended to let ChatGPT execute routine operational tasks directly through GitHub. Production cutover, destructive storage/database actions, and other explicitly high-risk operations remain separate owner-authorized procedures unless a later authority decision adds narrowly-scoped actions for them.
