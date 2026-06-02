# Operator Command Contexts

## Purpose

This document separates ED-Finder command contexts so production-only operator
commands are not accidentally run from Codex, DAVE2 local development, or any
other non-Hetzner shell.

Codex is for repo, code, docs, tests, commits, and PR work. The Hetzner
production operator shell is for `/opt/ed-finder`, `/var/lib/ed-finder`,
Docker/Postgres production containers, production artifacts, and operator
commands. DAVE2/local development is not production.

## The Three Environments

ED-Finder currently has three common command contexts:

| Environment | Typical path | Purpose |
|---|---|---|
| Codex / repo environment | A checked-out repo under a local workspace | Code, docs, tests, validation, commits, and PRs. |
| DAVE2 local dev environment | A developer checkout or local services | Local development and non-production validation. |
| Hetzner production operator shell | `/opt/ed-finder` | Production operator artifacts, Docker Compose services, and production-only checks. |

If a command depends on `/opt/ed-finder`, `/var/lib/ed-finder`, production
Docker services, or production Postgres containers, it belongs in the Hetzner
operator shell.

## Codex / Repo Environment

Use Codex for:

- editing code and docs,
- writing tests,
- running local test suites,
- running local syntax checks,
- opening and updating PRs,
- documenting operator commands without executing them.

Codex must not run production operator commands. If a pasted command starts
with `cd /opt/ed-finder`, reads `/var/lib/ed-finder`, calls production Docker
Compose services, or reads production artifacts, treat it as a Hetzner operator
command and do not run it from Codex.

## DAVE2 Local Dev Environment

DAVE2/local dev is useful for local builds, local services, and non-production
experiments. It is not the production operator shell.

Do not treat a local checkout, local Docker stack, or local Postgres instance
as proof that a production operator command is safe. Production artifact paths
and production Docker service names still belong on Hetzner.

## Hetzner Production Operator Shell

The Hetzner production operator shell is the only place for commands that need:

- `/opt/ed-finder`,
- `/var/lib/ed-finder/operator-artifacts`,
- production Docker Compose services,
- production Postgres containers,
- operator-managed production artifacts.

Operator commands must be explicit, bounded, and reviewed. They should print
clear stop messages when the host, path, artifact directory, or Docker context
is wrong.

## Commands Codex Must Not Run

Codex must not run commands that:

- change into `/opt/ed-finder`,
- read or write `/var/lib/ed-finder/operator-artifacts`,
- invoke production Docker Compose services,
- query production Postgres containers,
- run imports or warehouse loads against production inputs,
- run production reconciliation,
- run the compact summarizer against production artifacts,
- run station-type dry-run against production artifacts,
- run canonical apply,
- install or wire cron/scheduler jobs on production.

Codex may edit scripts and docs that describe these workflows, and may run
local syntax/tests against those scripts.

## Commands That Must Run Only On Hetzner

Run these only from the Hetzner production operator shell:

- Stage 18J compact summary generation from production artifacts,
- production artifact file permission changes,
- production artifact checksum or size inspection,
- Docker Compose production service inspection,
- read-only production station count checks,
- any future operator-approved production dry-run,
- any future explicitly approved manual canonical apply.

Scheduled jobs must never run canonical apply.

## Required Hetzner Paths

Required production paths include:

- `/opt/ed-finder`
- `/var/lib/ed-finder/operator-artifacts/stage-18j`

If these paths do not exist, the command is not running in the expected
operator context.

## Artifact Directory Rules

Production artifacts are private operator files. They should not be committed
to git.

Rules:

- Keep production artifacts under operator-managed directories.
- Commit only synthetic fixtures or explicitly sanitized examples.
- Compact summaries generated from production evidence default to
  `safe_for_git = false`.
- Use domain-qualified artifact names from Stage 19A for new outputs.
- Keep load, reconciliation, compact summary, dry-run, approval packet, and
  apply artifacts separate.

## Secret Handling

Never paste real DSNs/passwords/secrets into chat or Git. Do not commit private
environment files. Operator scripts must not source private environment files
unless a later reviewed stage explicitly adds that behavior.

When sharing output, prefer schema versions, counts, basenames, file sizes, and
hashes. Do not share full production artifact paths if a basename is enough.

## How To Recognise The Right Prompt

Use Codex when the prompt asks for repo edits, docs, tests, validation, commits,
or PRs.

Use Hetzner when the prompt asks to operate on `/opt/ed-finder`,
`/var/lib/ed-finder`, production Docker services, production Postgres
containers, or production artifacts.

Use DAVE2/local dev when the prompt asks for local application development or
non-production service checks.

If the prompt mixes contexts, split it. Codex can prepare the PR; the Hetzner
operator terminal runs the production command.

## How To Use Operator Scripts

Operator scripts live under `scripts/operator`.

For Stage 18J compact summary generation, run from Hetzner only:

```sh
cd /opt/ed-finder
scripts/operator/stage18j_run_compact_summary.sh
```

Optional environment overrides:

- `ART_DIR`
- `RECON_ARTIFACT`
- `COMPACT_SUMMARY`
- `MAX_CANDIDATE_SAMPLES`
- `CHECK_CANONICAL_COUNT=yes`

The compact summary script calls the shared environment guard first. It fails
fast outside the expected host/path/Docker/artifact context.

For a future Stage 18J-P station-type dry-run, after the operator has been
separately prompted, run from Hetzner only:

```sh
cd /opt/ed-finder
MAX_ROWS=5 scripts/operator/stage18j_run_station_type_dry_run.sh
```

Optional environment overrides:

- `ART_DIR`
- `RECON_ARTIFACT`
- `EXPECTED_RECON_SHA256`
- `DRY_RUN_ARTIFACT`
- `MAX_ROWS`
- `BLOCKED_CANDIDATE_SAMPLE_LIMIT`

The station-type dry-run wrapper calls the shared environment guard, verifies
the reconciliation artifact checksum, refuses `MAX_ROWS > 20`, writes output
under the operator artifact directory, and prints only compact summary fields.
It does not connect to the database, create approval records, or run canonical
apply.

## Stage 18J Current Operator Artifacts

Stage 18J currently uses an operator-managed reconciliation artifact basename:

```text
enrichment_staging_reconciliation_20260602T112948Z.json
```

The compact summary output basename is:

```text
reconciliation_compact_summary_20260602T112948Z.json
```

The future station-type dry-run wrapper defaults to this output basename:

```text
station_type_canonical_pilot_dry_run_20260602T112948Z.json
```

Both are production/operator artifacts and must stay out of git unless a future
review explicitly produces a synthetic or sanitized example.

## Stage 19 Roadmap Impact

Stage 19A.1 adds guardrails before broader warehouse work continues. Future
Stage 19 chunks should keep Codex/repo work separate from Hetzner operator
work, and server-only scripts should fail fast outside Hetzner.

Stage 19 scheduler planning remains disabled by default. Scheduler jobs may
refresh warehouse artifacts only after explicit approval and must never run
canonical apply.

## Final Recommendation

Use Codex for repository work and PRs. Use DAVE2/local dev for non-production
development. Use the Hetzner production operator shell for `/opt/ed-finder`,
`/var/lib/ed-finder`, Docker/Postgres production services, and production
artifacts. Keep operator artifacts private, keep secrets out of chat and Git,
and rely on fail-fast operator scripts for server-only commands.
