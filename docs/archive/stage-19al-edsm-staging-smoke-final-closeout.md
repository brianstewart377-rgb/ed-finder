# Stage 19AL — bounded EDSM staging smoke final closeout

## Result

Stage 19AL closes the bounded EDSM staging-smoke questline.

The warehouse has now safely proven the first committed EDSM station staging path:

`local EDSM fixture -> source_runs -> enrichment_source_runs bridge -> staging_edsm_stations`

Exactly one staging row was committed, verified, and then marked as diagnostic-only.

## Final row identity

| Item | Value |
|---|---|
| Source run key | `stage19af-edsm-staging-smoke-20260605T230613Z` |
| Legacy bridge key | `source_runs:stage19af-edsm-staging-smoke-20260605T230613Z` |
| Source run ID | `7` |
| Legacy bridge ID | `9` |
| Staging row ID | `298181` |
| Source run status | `succeeded` |
| Source rows read/staged | `1 / 1` |
| Staging source class | `diagnostic-only` |
| Staging confidence | `diagnostic-only` |
| Legacy bridge dry run | `False` |

## Artifact chain

| Stage | Artifact | Schema | File SHA-256 | Artifact integrity SHA-256 |
|---|---|---|---|---|
| 19AF recovery | `edsm_station_staging_smoke_recovery_light_20260605T231527Z.json` | `edsm_station_staging_smoke_recovery_light/v1` | `daf7e7f8b88494870dbb1fd05261608bc10725da0dca6965e8a7802fa6135580` | `44c9bde3ab8992c5388f40201f569058b6ef152dd7cbf19963c33b8ba1ef1b01` |
| 19AG corrected verification | `edsm_station_post_staging_smoke_verification_corrected_20260605T232636Z.json` | `edsm_station_post_staging_smoke_verification_corrected/v1` | `75ae66ee3a1149683c622cde7af1db701b1b42d78792a942902c30f75eba2b66` | `965dc4abc6639f528ad82dc406505ec9c4606d85333393b1c73fcb635c7b4c09` |
| 19AI impact scan | `edsm_staging_smoke_impact_scan_light_20260606T080710Z.json` | `edsm_staging_smoke_impact_scan_light/v1` | `4d68eff483abddeb7a5099195c62624301ad2eb6392c5a49a5f7eebbd4d0cb39` | `2629e63c323680c7415c10ccf09461525cc15d144d781a66efd44e88aa9c9688` |
| 19AJ diagnostic mark | `edsm_staging_smoke_diagnostic_mark_20260606T080902Z.json` | `edsm_staging_smoke_diagnostic_mark/v1` | `6b11310758707850ff421b4b88383a999caae8036269c6ec257b2e7cf49bed20` | `f059c8c6a04eb900d8220ba0811343ccc4ba46278f199e7364358a1eba990d8a` |
| 19AK post-mark verification | `edsm_staging_smoke_post_diagnostic_mark_verification_20260606T081122Z.json` | `edsm_staging_smoke_post_diagnostic_mark_verification/v1` | `085741a68a942e21edf5e7e6f08ea523d7c5143d83e118f808f57a9d9bc09b8a` | `5bfaf6b1125d0f60615c492aee67a91359d4fbaa6ff95b1cde73c623fae58a2d` |

## What happened

Stage 19AF attempted the bounded local-file EDSM staging smoke and committed successfully, but its post-check used an overly broad canonical count comparison after commit.

Stage 19AF-R recovered the committed state read-only and confirmed:

- one `source_runs` row;
- one `enrichment_source_runs` bridge row;
- one `staging_edsm_stations` row;
- staging row used the legacy `enrichment_source_runs.id` FK, not `source_runs.id`; 
- no canonical apply was performed.

Stage 19AG corrected the verification expectation: the staging row confidence was correctly `source_station_snapshot`, not `test-only`.

Stage 19AI scanned the row by primary key and recommended marking it diagnostic.

Stage 19AJ updated exactly one staging row:

- `source_class`: `semi-stable -> diagnostic-only`; 
- `confidence`: `source_station_snapshot -> diagnostic-only`; 
- provenance retained `canonical_write_allowed=false`; 
- provenance added a Stage 19AJ diagnostic marker.

Stage 19AK verified the diagnostic mark read-only.

## Final Stage 19AK verification checks

| Check | Result |
|---|---:|
| `aj_artifact_integrity_valid` | `True` |
| `aj_safety_no_canonical_apply` | `True` |
| `aj_safety_no_imports` | `True` |
| `db_read_only_confirmed` | `True` |
| `legacy_bridge_dry_run_false` | `True` |
| `legacy_bridge_key_matches` | `True` |
| `legacy_bridge_present` | `True` |
| `provenance_blocks_canonical_write` | `True` |
| `provenance_has_stage19aj_marker` | `True` |
| `provenance_preserves_stage19af_marker` | `True` |
| `source_run_counts_one` | `True` |
| `source_run_key_matches` | `True` |
| `source_run_present` | `True` |
| `source_run_succeeded` | `True` |
| `staging_row_confidence_diagnostic_only` | `True` |
| `staging_row_not_using_source_runs_id` | `True` |
| `staging_row_present` | `True` |
| `staging_row_source_class_diagnostic_only` | `True` |
| `staging_row_uses_legacy_bridge_id` | `True` |

## Safety boundary

Across this final staging-smoke chain:

- no bulk production import was run;
- no scheduler/timer was enabled;
- no migrations were run;
- no canonical table writes were performed;
- no canonical apply was performed;
- exactly one staging smoke row exists;
- that row is now diagnostic-only and explicitly blocks canonical writes.

## Production capability now proven

The warehouse is now proven for:

1. durable source-run provenance;
2. artifact integrity;
3. source-run to legacy enrichment bridge compatibility;
4. real DB rollback rehearsal;
5. committed bridge smoke;
6. committed bounded EDSM station staging smoke;
7. diagnostic marking and post-mark verification.

## Recommended next stage

Stage 19AM should be a bounded multi-row local-file EDSM staging rehearsal, still with:

- tiny fixture;
- explicit compatible stager;
- row limit;
- no scheduler;
- no canonical writes;
- no canonical apply;
- post-write verification;
- no broad table scans.

Only after multiple bounded staging runs should a real EDSM staging import be considered.

## Verdict

Stage 19AL closes the first bounded EDSM staging-smoke chain.

The Data Warehouse staging path is production-proven for one diagnostic EDSM station evidence row.

