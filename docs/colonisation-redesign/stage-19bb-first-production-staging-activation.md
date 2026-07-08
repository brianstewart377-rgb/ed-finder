# Stage 19BB - First Production-Staging Activation

## Purpose

Stage 19BB is the exact authorization checkpoint for the first real bounded
production-staging execution lane. It authorizes a later merged wrapper to run
only the reviewed EDSM staging-only path against the approved isolated local
staging target.

This checkpoint authorizes source resolution, source fingerprinting, read-only
target preflight, wrapper/docs/tests preparation, and merge of the reviewed
authorization PR. The authority status recorded for this checkpoint is
`authorized_after_merge`. It does not execute a staging import in this PR.

## Approved source

- source name: `edsm`;
- logical batch label: `edsm-stations-20260619T190906Z`;
- sanitized source reference: `https://www.edsm.net/dump/stations.json.gz`;
- basename: `stations.json.gz`;
- approved SHA-256:
  `b256017814a1015fb24748c8027f1a00cba2f187a257ef3e0f9e3a6ba6e45984`;
- size bytes: `2616931545`;
- eligible station rows: `714117`;
- format: `json`;
- record stream shape: `json_array`;
- compression: `gzip`;
- acquisition timestamp: `2026-06-19T19:09:06Z`.

The original approved snapshot for this checkpoint had SHA-256
`09225e43323464e332a792f8716a6e4264ef5999ce1544f1157bfc60f406f4a2` and
size `2614426684`, but the live EDSM dump rotated after PR `#243`
authorization. This checkpoint therefore records a narrow source-artifact
refresh only; it does not broaden the target boundary, authorize canonical
apply, authorize rebaseline, or enable any scheduler/service path.

Source acquisition completed before this PR was merged. The source file itself
is not committed, private full paths are not committed, and signed or secret
query parameters are not recorded.

## Approved target

- target type: `isolated_persistent_local_staging`;
- host: `127.0.0.1`;
- port: `56432`;
- database: `edfinder_stage19_staging`;
- role: `stage19_loader`;
- setup-reported fingerprint:
  `759499c54f9d41cd636b4b5aa54e9bda1e4435c49e7a9a9bc34450b8671945b2`;
- recomputed Stage 19BB fingerprint:
  `fb59921a3c4f913c318e12709e602261450edf3632e8e20e0b669fd8f1622753`.

The fingerprint mismatch was reviewed as a formula mismatch, not target drift.
The stricter Stage 19BB fingerprint input includes:

- target type;
- host;
- port;
- database;
- role;
- sorted exact required table set;
- canonical-table-absence result;
- restricted-loader result.

The approved runtime fingerprint for Stage 19BB is therefore
`fb59921a3c4f913c318e12709e602261450edf3632e8e20e0b669fd8f1622753`.

## Exact boundary

The factual Stage 19BB execution boundary is exactly these five non-canonical
tables:

- `source_runs`;
- `enrichment_source_runs`;
- `enrichment_source_files`;
- `enrichment_raw_records`;
- `staging_edsm_stations`.

Canonical application tables must remain absent from the isolated target:

- `systems`;
- `stations`;
- `bodies`;
- `body_rings`;
- `station_body_links`;
- `body_scan_facts`;
- `observed_facts`.

No broader warehouse, canonical, or scheduler boundary is authorized.

## Stage 19BA correction

Stage 19BA recorded a control-baseline shorthand of three tables:

- `source_runs`;
- `enrichment_source_runs`;
- `staging_edsm_stations`.

The later executable loader audit established that the real tested loader path
also depends on two additional non-canonical support tables:

- `enrichment_source_files`;
- `enrichment_raw_records`.

This is a correction to the executable dependency map, not a rewrite of Stage
19BA history and not permission for arbitrary warehouse writes. Stage 19BA did
not execute and did not previously authorize a five-table run.

## Authorized scale

After merge, Stage 19BB authorizes no more than these successful runs:

- `100` rows with a maximum runtime of `900` seconds;
- `1,000` rows with a maximum runtime of `1,800` seconds;
- `10,000` rows with a maximum runtime of `3,600` seconds.

Because the approved eligible source count is above `10,000`, the third run is
exactly `10,000` rows rather than full-under-10,000.

No other successful batch size is authorized. No run above `10,000` rows is
authorized.

## Wrapper contract

The merged wrapper at
`scripts/operator/stage19bb_first_production_staging_activation.py` must:

- default to dry-run and read-only target preflight;
- require `--commit`;
- require `--confirm-stage19bb`;
- require merged authority on `origin/main` before execution;
- require `EDSM_STATION_SNAPSHOT`;
- require `EDFINDER_STAGING_DSN`;
- require `SAFE_ARTIFACT_DIR`;
- require the exact approved source SHA-256 on every run;
- require the exact approved target fingerprint on every run;
- approve localhost only for the reviewed fingerprinted target;
- reject arbitrary localhost targets;
- enforce the exact five-table boundary;
- fail closed on schema drift;
- fail closed on overlap;
- fail on malformed or rejected rows in the selected batch;
- block canonical apply;
- block rebaseline;
- block scheduler/service dispatch;
- stop after one selected batch.

The wrapper reuses the existing parser and staging helpers. It does not invent a
competing loader.

## Preflight proof

Read-only preflight confirmed:

- PostgreSQL server reachable on the approved host/port;
- exact required five tables present;
- expected columns, constraints, and indexes present;
- canonical application tables absent;
- no blocking active or failed Stage 19 run present;
- restricted loader role proven;
- create-database, create-role, schema-create, and unrelated-table creation
  privileges absent.

## This PR does not do

This authorization PR does not:

- execute a staging import;
- create a runtime `source_runs` row;
- create a runtime artifact;
- write EDSM rows into the staging target;
- perform canonical writes;
- run canonical apply;
- run rebaseline;
- enable a scheduler or service.

The authorization PR contains no execution evidence. Runtime source files and
runtime artifacts remain evidence only and are not committed authority.

