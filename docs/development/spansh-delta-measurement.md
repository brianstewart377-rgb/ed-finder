# Spansh delta measurement (study step S1)

Repository tooling only. It reads Spansh's public dump files on a GitHub-hosted
runner. It uses no secrets, no database and no production host, and it changes
nothing anywhere. It is step **S1** of the V3 canonical-refresh study (the
"middle path": nightly change layers built from `galaxy_1day`, folded weekly).

## What it is

| Piece | Path | Job |
|---|---|---|
| Parser and classifier | `apps/importer/src/spansh_delta/` | Reads a `galaxy*.json.gz` one system at a time and maps each system to V3 canonical rows through the frozen V3 adapter (`v3_spansh.adapter`, imported, not edited). Decides whether anything V3 stores changed. |
| Measurement command | `scripts/dev/measure_spansh_delta.py` | Streams one dump and writes a JSON stats file. |
| Workflow | `.github/workflows/spansh-delta-measure.yml` | On demand, and nightly at 04:17 UTC once you enable it (decision D5). Downloads the dump, runs the command, uploads the stats (kept 30 days). |
| Tests | `tests/test_spansh_delta.py` | Uses the committed real Spansh fixture (12 systems) and its 2026-08-24 canonical rows. |

## How to run it

**Nightly:** the schedule (04:17 UTC, `galaxy_1day.json.gz`) is **off until you
turn it on**, because asking Spansh about recurring downloads is still your
decision D5. Until then, scheduled runs start and are skipped straight away,
and nothing is downloaded. When D5 is settled, turn it on like this:

1. On GitHub, open the repository **Settings**.
2. Go to **Secrets and variables**, then **Actions**, then the **Variables** tab.
3. Click **New repository variable**.
4. Name: `SPANSH_DELTA_NIGHTLY`. Value: `enabled`.

To turn it off again, delete that variable or change its value.

**On demand (for example the one-off `galaxy_1month` run):**

1. On GitHub, open **Actions**, then **Spansh delta measurement**.
2. Click **Run workflow**.
3. Pick the dump: `galaxy_1day.json.gz`, `galaxy_7days.json.gz` or `galaxy_1month.json.gz`.
4. When the run finishes, download the artifact named
   `spansh-delta-stats-<dump>-<run id>-<attempt>`. It holds `stats.json` and `headers.txt`.

The run summary page also shows the headline numbers as a table.

**Locally, on a file you already have** (command to run in a terminal on any
machine with CPython 3.14, from the repository root):

```bash
python scripts/dev/measure_spansh_delta.py --input galaxy_1day.json.gz --output stats.json
```

## How to read `stats.json`

| Field | Meaning |
|---|---|
| `source.file_bytes`, `source.file_sha256` | Size and SHA-256 of the downloaded file, counted while parsing. The run fails if the size differs from the server's `Content-Length`. |
| `source.decompressed_bytes` | Size of the JSON inside the gzip. |
| `source.parser` | `lines` = the file had Spansh's usual one-system-per-line layout. `ijson-fallback` = it did not, and the format-agnostic parser re-read it (`fallback_reason` says why). |
| `source.reference_time` | When the file was made: the server's `Last-Modified`, else the file time. Ages below are measured from it. |
| `counts.systems` | Systems in the file. `distinct_id64` and `duplicate_id64_records` show repeats. |
| `counts.systems_rejected_by_v3_adapter` | Systems the V3 import itself would refuse (for example missing coordinates). Reasons and samples are in `v3_adapter_rejections`. |
| `counts.bodies`, `counts.fixed_stations`, `counts.fleet_carriers` | V3 canonical rows those systems would produce. Fleet carriers are counted separately from fixed stations. |
| `canonical_rows` | Row counts per V3 canonical table. Multiply by row size for a disk estimate of one night's layer. |
| `per_system` | Histograms of bodies, fixed stations, carriers and compact record bytes per system (after an `ijson` fallback, the record is re-encoded compactly to measure it). |
| `update_times` | For the system `date` and for the newest body, fixed-station and carrier update: hours before the reference time, and counts per UTC day. |
| `touch_proxy.categories` | A rough, base-free guess at why each system is in the file (see below). |
| `overlap` | Only from the second night on. Compares tonight with last night (see below). |
| `previous_stats` | Last night's file hash and system count, for a day-to-day comparison. |

### The touch proxy (first night)

Each system is put in one group, by which update times fall inside the
window (24 hours for `galaxy_1day`):

- `bodies`: a body or its signals were updated.
- `fixed_stations`: a station other than a fleet carrier was updated.
- `carriers_only`: only fleet carriers were updated.
- `system_only`: only the system's own `date` moved. This is usually faction,
  population or power data, which V3 does not store.
- `outside_window` / `no_timestamps`: nothing inside the window, or no times at all.

This **over-counts** real change: re-scanning a body or updating a market also
moves these times. It is an upper bound.

### The overlap (from the second night)

The workflow keeps a small digest index of each night (40 bytes per system)
in the Actions cache. The next night compares against it:

- `systems_in_both`, `only_in_current`, `only_in_previous`: how many systems
  repeat from one night to the next.
- `content_changed_in_both`: of the repeating systems, how many really changed
  their V3 content, under four rules:
  - `strict`: any column V3 stores.
  - `stable`: the same, but ignoring the orbital position at scan time
    (`bodies.mean_anomaly_deg`, `bodies.distance_from_arrival_ls`,
    `stations.distance_from_arrival_ls`).
  - `strict_excluding_carriers` and `stable_excluding_carriers`: the same two
    rules, also ignoring fleet carriers.

Why `stable` exists: in the committed fixture, 9 of the 12 real systems
"changed" under `strict` between the 2026-08-24 base and the 2026-09-08
Spansh records. For 6 of those 9, the only difference is the orbital
position, which moves every time someone scans a body. Only 3 had a real
change (signals). Which rule admits a system into a nightly layer is the
owner's decision D3.

## What 7 nights of results feed

Seven nights of `stats.json` (plus one `galaxy_1month` run) give the evidence
for the delta-layer design (study step S3) and replace the study's estimates:

- systems per night, and how many repeat from night to night;
- how many of those really changed under each rule, which sets the expected
  layer size and the D3 decision;
- bodies, stations and canonical rows per night, which give disk and WAL per
  layer;
- the update-time spread, which shows how late Spansh's file is relative to
  its date and whether a 24-hour window misses anything;
- parse time and memory, which bound the nightly admission step.

The precise admission check against the published base needs a database read.
That is production step P1 and is not part of this tooling.

## Assumptions and limits

- **File layout.** The parser expects one top-level JSON array with one compact
  system per line, which is how the published `galaxy.json.gz` was laid out
  (the retained importer depends on it). Any other layout is still read
  correctly by the `ijson` fallback, and `source.parser` records which was used.
  This was not checked against a live `galaxy_1day` download, because the
  development sandbox cannot reach Spansh. The first workflow run is the check.
- **Generation time.** The 04:17 UTC schedule assumes Spansh has rebuilt the
  file by then. If it has not, the server returns the same ETag and the run
  uploads only a small `stats.json` with the different schema
  `ed-finder.spansh-delta-not-modified/1` (no counts) for that night.
- **Spansh terms (D5).** Nightly runs download about 1.1 GiB a day. The study
  lists asking Spansh before recurring downloads as owner decision D5, so the
  schedule does nothing until the `SPANSH_DELTA_NIGHTLY` variable is set to
  `enabled` (see "How to run it"). Manual runs are single downloads that you
  start yourself.
- **Cache.** If the Actions cache entry is evicted (7 days unused), the next
  night simply has no `overlap`.
