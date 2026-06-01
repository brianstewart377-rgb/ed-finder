# Stage 18A — Enrichment Operator Status Integration

Stage 18A makes station-enrichment status visible through the existing
operator/admin tooling without letting the web app run enrichment work.

## Architecture Classification

Current app/API surfaces:

- The frontend already has an Admin tab.
- The API already has an admin router with `ADMIN_TOKEN` protection for
  `/api/admin/*` write actions.
- The Admin tab itself is visible in navigation, so new sensitive status must
  be token-gated before it is fetched or displayed.

Current enrichment status tooling:

- `scripts/station_enrichment_status.py --json` is read-only and file-only. It
  does not call EDSM, open the database, invoke Docker, or write state.
- The guarded enrichment output default is
  `/tmp/edfinder-station-enrichment`.
- The API container does not currently mount that host `/tmp` path.
- The API container does mount `/data/logs`, so a shared JSON status artifact
  can be made visible there if an operator job writes it.
- The API image does not include `scripts/`, so the API must not try to invoke
  `station_enrichment_status.py` directly.

## Implemented Safe Path

The API now exposes a read-only token-gated endpoint:

```text
GET /api/admin/enrichment/station-status
```

The endpoint reads only the JSON artifact configured by:

```text
ENRICHMENT_STATUS_JSON_PATH=/data/logs/station-enrichment-status.json
```

The intended operator-side producer is:

```sh
python3 scripts/station_enrichment_status.py --json > /data/logs/station-enrichment-status.json
```

This stage does not add that producer job, cron entry, systemd timer, Docker
command, live API call, or database call. If the path is unset or missing, the
Admin tab shows the status as unavailable instead of inventing zero progress.

## Sanitisation Contract

The endpoint hides full filesystem paths from the helper output. It exposes
only safe file names and read-only counters:

- checkpoint validity and processed count, when known
- latest batch number/state/phase
- latest report counters
- fetch failure counts
- rate-limit warning counts
- latest artifact age
- latest output/log/report file names, not full paths

Errors that contain path separators are reduced to `unavailable`.

## Boundaries

- Read-only endpoint only.
- Requires `ADMIN_TOKEN`.
- No production writes.
- No EDSM calls.
- No Docker invocation.
- No database access.
- No broad public status surface.
- Missing status remains unavailable, not zero.
- Planner/search/scoring/Simulation Preview/Suggested Builds are untouched.

## Follow-Up For Full Operations

A production operator can wire a separate host-level job to periodically write
the status artifact into `/data/logs`. If the enrichment checkpoint should move
out of `/tmp`, use the guarded enrichment script's `--checkpoint-file` option
and document the new shared path in the runbook.
