# Stage 19AN-R — warehouse-derived EDSM staging rehearsal closeout

## Result

Stage 19AN-R closed the warehouse-derived real-shape EDSM staging rehearsal.

The stage used the reviewed operator script added in PR #187, sampled five existing real-shaped `staging_edsm_stations` rows, converted them into a local EDSM-like fixture, and ran the bounded local-file staging rehearsal.

## Final state

| Item | Value |
|---|---|
| Source run key | `stage19anr-warehouse-derived-edsm-stations-ac5c2be9d0aad7f6` |
| Bridge key | `source_runs:stage19anr-warehouse-derived-edsm-stations-ac5c2be9d0aad7f6` |
| Sample path | `/var/lib/ed-finder/operator-artifacts/stage-19anr/stage19anr_edsm_sample_20260606T121945Z.json` |
| Sample rows | `5` |
| Import artifact | `/var/lib/ed-finder/operator-artifacts/stage-19anr/stage19anr_edsm_import_20260606T121945Z.json` |
| Operator artifact | `/var/lib/ed-finder/operator-artifacts/stage-19anr/stage19anr_operator_rehearsal_20260606T121945Z.json` |
| Operator artifact SHA-256 | `858908e41c0b05c40c9db1e92e00788eba54d81594fcd60fa42d818ffc4f3d22` |
| Operator artifact integrity | `0666bd45600df8cd410a52cc5be70b775895c0240038091080c1755593c3ddde` |

## Committed changes

| Table / action | Count |
|---|---:|
| `source_runs` inserted | `None` |
| `enrichment_source_runs` inserted | `None` |
| `staging_edsm_stations` inserted | `None` |
| staging rows diagnostic-marked | `None` |

## Verification checks

| Check | Result |
|---|---:|
| `canonical_table_writes_performed_by_script` | `False` |
| `exactly_limit_staging_rows_inserted` | `True` |
| `exactly_limit_staging_rows_marked_diagnostic` | `True` |
| `no_scheduler_or_service_invoked` | `True` |
| `one_legacy_bridge_inserted` | `True` |
| `one_source_run_inserted` | `True` |
| `source_run_artifact_hash_matches` | `True` |
| `source_run_artifact_integrity_matches` | `True` |
| `source_run_succeeded` | `True` |
| `staging_rows_do_not_use_source_runs_id` | `True` |
| `staging_rows_have_stage19anr_marker` | `True` |
| `staging_rows_preserve_canonical_write_block` | `True` |
| `staging_rows_use_legacy_bridge_id` | `True` |

## Safety boundary

- bulk imports performed: `None`
- scheduler enabled: `None`
- canonical writes performed: `None`
- canonical apply performed: `None`

## Verdict

The warehouse-derived EDSM staging rehearsal is complete and production-proven for a bounded five-row diagnostic sample.

Next sensible step is either a bounded 25-row staging pilot, or pausing data ingestion work to build operator/admin visibility before wider imports.

