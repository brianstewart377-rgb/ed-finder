# Operator Command Contexts

## Purpose

This document separates ED-Finder command contexts so repository work, local development, and current V3 production operations are not confused.

## Current environments

| Environment | Typical context | Purpose |
|---|---|---|
| Codex / repo environment | A checked-out repository or GitHub branch/PR | Code, docs, tests, validation, commits, and PRs. |
| DAVE2 / local development | Developer checkout and disposable local services | Local development and non-production validation. |
| V3 production | Current replacement-host runbooks and workflows only | Production services, backup/recovery, identity, and operator actions. |

## Codex / repo environment

Use Codex/repository tooling for:

- editing code and documentation;
- writing and running repository tests;
- local/static validation;
- opening and updating PRs;
- documenting operator procedures without executing production commands.

Git history and removed operational artifacts are not current execution authority.

## DAVE2 / local development

DAVE2/local development is useful for local builds, disposable services, and non-production experiments. It is not proof that a production command is safe.

Do not substitute a local Docker stack or local PostgreSQL instance for production when validating production procedures.

## V3 production

Production commands must come from a current runbook or workflow that explicitly identifies the replacement environment and its safety boundary.

Before any production action:

1. identify the target host/environment explicitly;
2. verify the procedure is part of the current V3 operator surface;
3. verify the intended host identity before executing destructive or stateful commands;
4. preserve current backup, credential, and least-privilege boundaries;
5. stop if the requested procedure exists only in Git history or an archived artifact.

## Legacy migration data

A validated offsite database dump is retained only as a selective migration source. Use it through a purpose-built, allowlisted migration/recovery process. Do not restore it wholesale as production and do not copy an older PostgreSQL physical data directory into PostgreSQL 18.

## Secret handling

Never paste real DSNs, passwords, secrets, private keys, recovery codes, or credential-bearing URLs into chat or Git.

Production credentials must be managed through the current V3 recovery/secret process.

## How to recognise the right prompt

Use Codex/repository tooling when the prompt asks for repo edits, docs, tests, validation, commits, or PRs.

Use DAVE2/local development for non-production application work.

Use current V3 operator procedures only when the prompt explicitly concerns production and the relevant current runbook/workflow has been identified.

If a requested production action is not present in the current V3 operator surface, stop rather than adapting an obsolete procedure.

## Operator scripts

`scripts/operator/` contains current replacement-host helpers only. Read `scripts/operator/README.md` before executing anything from that directory.

## Final recommendation

Keep repository work, local/non-production development, and current V3 production operations clearly separated. Production work requires explicit current authority and a verified target environment.
