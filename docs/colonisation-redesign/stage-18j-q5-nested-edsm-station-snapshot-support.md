# Stage 18J-Q5 - Nested EDSM Station Snapshot Support

## Purpose

Stage 18J-Q5 hardens the offline warehouse station loader for the source shape
observed on the production server:

```text
/data/dumps/galaxy_stations.json.gz
```

The file was not inspected or committed in this stage. The production dry-run
finding was that the file appears to contain nested EDSM system records with
station/body collections, not a flat station-only snapshot. The previous loader
reported `unsupported_source_shape` and `nested_body_collection` warnings and
the warehouse staging tables remained empty.

## Implemented Outcome

Option A was implemented using only small synthetic fixtures.

The `edsm_nightly_stations` loader now supports nested system records with a
`stations` array:

- each full source system record is preserved as one raw warehouse record,
- each nested station becomes a deterministic staging station row,
- each station row receives a station-specific `source_record_hash` and
  `source_record_key`,
- station rows retain `source_run_key`, `source_file_key`, and parent raw
  source provenance,
- parent raw system hashes are used to link station staging rows back to
  `enrichment_raw_records` during staging writes,
- `system_name` and `system_id64` are inherited from the parent system when
  missing from the station payload,
- `market_id` and `edsm_station_id` are preserved when present,
- station type source labels are preserved while provenance records normalized
  labels and permanent/transient/unknown classification,
- fleet carriers and megaships remain labelled `transient_non_slot` evidence,
- nested `bodies` collections remain raw-only unsupported-source-shape warning
  evidence.

Nested body support was not added. The station source path does not populate
`staging_edsm_bodies`, `staging_body_rings`, canonical `bodies`, or canonical
`body_rings`.

## Boundary Confirmations

This stage does not authorize production execution.

- No production data was used or committed.
- No production source artifact was copied into git.
- No production load was run.
- No production reconciliation was run.
- No production apply was run.
- No canonical tables are written by the loader.
- No station-type canonical dry-run was generated.
- No live EDSM/API crawl was added.
- Unknown values remain unknown.
- Source-only nested body evidence remains source-only.

## Production Status

The production warehouse currently has the warehouse tables and read-only role,
but the staging tables are empty. Stage 18J-Q3 remains blocked until this loader
support is merged and the production staging load is explicitly retried in a
separate approved operation.

After a successful separate staging load, Stage 18J-Q3 can retry its read-only
reconciliation artifact path. Stage 18J-P and Stage 18K remain blocked until
their own prerequisites are satisfied.
