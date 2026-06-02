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
- `stage18j_run_compact_summary.sh`: generates the Stage 18J compact
  reconciliation summary from an existing operator-managed artifact. It never
  runs reconciliation, station-type dry-run, or apply.
- `stage18j_run_station_type_dry_run.sh`: generates the Stage 18J-P
  station-type dry-run artifact from the validated reconciliation artifact
  after verifying its SHA-256. It requires bounded `MAX_ROWS`, caps blocked
  candidate samples, writes under the operator artifact directory, and never
  touches the database, creates approval records, or runs canonical apply.

Production artifacts are private operator files and should not be committed.
