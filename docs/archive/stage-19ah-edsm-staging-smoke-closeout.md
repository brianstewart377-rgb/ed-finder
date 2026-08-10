# Stage 19AH — bounded EDSM staging smoke closeout

## Result

Stage 19AH closes the bounded local-file EDSM station staging smoke.

The production warehouse has now proven a complete bounded staging path:

`local EDSM fixture -> source_runs -> enrichment_source_runs bridge -> staging_edsm_stations`

Exactly one EDSM station evidence row was committed to staging.

No bulk import was run. No scheduler/timer was enabled. No canonical write or canonical apply was performed.

## Committed smoke identity

| Item | Value |
|---|---|
| Source run key | `stage19af-edsm-staging-smoke-20260605T230613Z` |
| Legacy bridge key | `source_runs:stage19af-edsm-staging-smoke-20260605T230613Z` |
| Station name | `Stage 19AF Smoke Station 20260605T230613Z` |
| Source run ID | `7` |
| Legacy enrichment source run ID | `9` |
| Staging row ID | `298181` |
| Staging row source_run_id | `9` |
| Staging row type | `Coriolis Starport` |
| Staging row confidence | `source_station_snapshot` |

## Artifact chain

| Artifact | File | Schema | File SHA-256 | Artifact integrity SHA-256 |
|---|---|---|---|---|
| Source fixture | `edsm_station_smoke_fixture_20260605T230613Z.json` | fixture | `2263f8deb12da07819dc377d3549cd515842b8c00e674c60561999ba352d09c4` | n/a |
| 19AF import artifact | `edsm_station_import_smoke_artifact_20260605T230613Z.json` | `stage_19t_edsm_station_import_mvp/v1` | `f11463694f973e8fd4bbd2ae79e73b9c36681e025f9187b2bd67b07e02959c23` | `9dd55f22622a0c5d818623eebfa0f81f9b50ec79bd91371d36d8f9e88a8ab9f2` |
| 19AF recovery artifact | `edsm_station_staging_smoke_recovery_light_20260605T231527Z.json` | `edsm_station_staging_smoke_recovery_light/v1` | `daf7e7f8b88494870dbb1fd05261608bc10725da0dca6965e8a7802fa6135580` | `44c9bde3ab8992c5388f40201f569058b6ef152dd7cbf19963c33b8ba1ef1b01` |
| 19AG original verification | `edsm_station_post_staging_smoke_verification_corrected_20260605T232636Z.json` | `edsm_station_post_staging_smoke_verification_corrected/v1` | `75ae66ee3a1149683c622cde7af1db701b1b42d78792a942902c30f75eba2b66` | `965dc4abc6639f528ad82dc406505ec9c4606d85333393b1c73fcb635c7b4c09` |
| 19AG corrected verification | `edsm_station_post_staging_smoke_verification_corrected_20260605T232636Z.json` | `edsm_station_post_staging_smoke_verification_corrected/v1` | `75ae66ee3a1149683c622cde7af1db701b1b42d78792a942902c30f75eba2b66` | `965dc4abc6639f528ad82dc406505ec9c4606d85333393b1c73fcb635c7b4c09` |

## What was committed

| Table | Committed change |
|---|---:|
| `source_runs` | `+1` row |
| `enrichment_source_runs` | `+1` compatibility bridge row |
| `staging_edsm_stations` | `+1` bounded EDSM source-evidence row |
| canonical tables | `0` rows written |

## Key verification facts

- the `staging_edsm_stations.source_run_id` uses the legacy `enrichment_source_runs.id`, not the new `source_runs.id`;
- the source run completed with `rows_read=1`, `rows_staged=1`, `rows_rejected=0`, `rows_skipped=0`; 
- the import artifact hash and integrity match the committed `source_runs` row;
- the staging row provenance includes `canonical_write_allowed=false`; 
- the staging row is source evidence only;
- no canonical apply was performed.

## Recovery note

The first Stage 19AF post-check failed after commit because the verification script used an overly broad canonical table count comparison.

That broad check was replaced by focused row-level verification in the Stage 19AF recovery artifact and corrected Stage 19AG verification.

The smoke itself was valid and was not rerun.

## Corrected Stage 19AG verification checks

| Check | Result |
|---|---:|
| `db_read_only_confirmed` | `True` |
| `exactly_one_stage19af_legacy_run` | `True` |
| `exactly_one_stage19af_source_run` | `True` |
| `exactly_one_stage19af_staging_row` | `True` |
| `import_artifact_integrity_valid` | `True` |
| `import_artifact_present` | `True` |
| `legacy_bridge_dry_run_false` | `True` |
| `legacy_bridge_present` | `True` |
| `legacy_bridge_targets_enrichment_source_runs` | `True` |
| `no_import_scheduler_or_canonical_apply_in_recovery` | `True` |
| `recovery_artifact_integrity_valid` | `True` |
| `single_matching_staging_row` | `True` |
| `source_file_present` | `True` |
| `source_run_artifact_file_sha_matches` | `True` |
| `source_run_artifact_integrity_matches` | `True` |
| `source_run_artifact_path_matches` | `True` |
| `source_run_counts_one` | `True` |
| `source_run_finished_after_started` | `True` |
| `source_run_present` | `True` |
| `source_run_succeeded` | `True` |
| `staging_row_confidence_is_source_station_snapshot` | `True` |
| `staging_row_name_matches` | `True` |
| `staging_row_not_using_source_runs_id` | `True` |
| `staging_row_present` | `True` |
| `staging_row_provenance_marks_no_canonical_write` | `True` |
| `staging_row_provenance_marks_stage19af` | `True` |
| `staging_row_source_class_is_semi_stable` | `True` |
| `staging_row_type_matches` | `True` |
| `staging_row_uses_legacy_source_run_id` | `True` |

## Safety boundary

Across this staging smoke closeout:

- no bulk import was run;
- no scheduler/timer was enabled;
- no migrations were run;
- no canonical table writes were performed;
- no canonical apply was performed;
- exactly one staging evidence row was committed;
- the smoke remains bounded and auditable through source-run and artifact provenance.

## Operational meaning

The Data Warehouse has now moved beyond provenance-only production readiness.

It has successfully committed one bounded EDSM station staging evidence row using the correct compatibility bridge path.

## Recommended next stage

Stage 19AI should be a read-only staging-smoke impact scan before any wider import:

- inspect the committed staging row;
- verify no accidental canonical side effects;
- verify row-level provenance and source classification;
- inspect duplicate/collision behaviour around the fixture source record hash;
- decide whether to remove the synthetic smoke row, retain it as a permanent smoke marker, or mark it as diagnostic-only through metadata.

After that, the next real import step should be a tiny bounded multi-row local-file staging rehearsal, still with no scheduler and no canonical apply.

## Verdict

Stage 19AH closes the bounded EDSM staging smoke.

The warehouse staging path is now production-proven for one local-file EDSM station evidence row.

