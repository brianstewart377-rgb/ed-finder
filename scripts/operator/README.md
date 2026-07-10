# Operator Scripts

Scripts in this directory are for the Hetzner production operator shell unless
their own header says otherwise. They are not Codex/local development commands.

Run them from:

```sh
cd /opt/ed-finder
```

The shared guard `require_hetzner_operator_env.sh` checks the host, working
directory, Docker Compose availability, and required artifact directories before
server-only workflows proceed. It does not source private environment files and
does not touch the database.

Current scripts:

- `require_hetzner_operator_env.sh`: reusable fail-fast guard for
  Hetzner-only commands.
- `stage18j_run_station_type_dry_run.sh`: generates the Stage 18J-P
  station-type dry-run artifact from the validated reconciliation artifact
  after verifying its SHA-256. It requires bounded `MAX_ROWS`, caps blocked
  candidate samples, writes under the operator artifact directory, and never
  touches the database, creates approval records, or runs canonical apply.
- `stage19ba_bounded_production_staging_activation.py`: prepares the Stage 19BA
  bounded production-staging activation contract for a future manual EDSM
  staging-only run. It defaults to dry-run planning, enforces source identity,
  source hash, sanitized source-reference display, target-shape, row-cap, and
  runtime-cap checks, creates no artifact directory during dry-run, and does
  not authorize execution by itself.
- `stage19bb_first_production_staging_activation.py`: prepares or runs the exact
  Stage 19BB first production-staging activation lane. It defaults to dry-run,
  requires merged authority plus `--commit --confirm-stage19bb` for execution,
  pins the approved EDSM source SHA-256 and approved isolated target
  fingerprint, enforces the exact five-table write boundary, and blocks
  canonical apply, rebaseline, and scheduler/service dispatch.

Archived historical wrappers:

- `scripts/operator/archive/stage18j/stage18j_run_compact_summary.sh`
- `scripts/operator/archive/stage18j/stage18j_run_identity_review_packet.sh`
- `scripts/operator/archive/stage18j/stage18j_run_identity_load_dry_run.sh`
- `scripts/operator/archive/stage18j/stage18j_run_identity_approval_allowlist.sh`

These remain in-repo as historical operator receipts, but they are no longer
presented as current top-level commands in `scripts/operator/`.

The sanitized execution evidence for the completed bounded `100 -> 1,000 ->
10,000` Stage 19BB ladder is recorded in
`docs/colonisation-redesign/stage-19bb-production-staging-execution-closeout.md`.

Production artifacts are private operator files and should not be committed.
