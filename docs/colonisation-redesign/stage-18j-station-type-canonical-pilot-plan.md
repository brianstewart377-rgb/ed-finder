# Stage 18J — Station Type Canonical Write Pilot Plan

## Executive Summary

Stage 18J should proceed, if and only if its prerequisites are satisfied, as a **narrow exact station type promotion pilot**. The pilot should update only `stations.station_type` for already-existing canonical station rows whose identity is matched by exact trusted station evidence, whose source type is present and normalized to an approved permanent station type, and whose current canonical value is eligible under a deliberately conservative update rule. This remains the safest first canonical write pilot because it changes one stable descriptive field on an existing station and does not invent systems, stations, bodies, body links, rings, distances, services, economies, planner state, scoring state, or build-plan state.[1]

Stage 18J must not be treated as a general warehouse-to-canonical bridge. The current warehouse and reconciliation pipeline is intentionally report-only: snapshot loading is offline, staging writes are gated to warehouse tables, reconciliation is read-only, operator/admin status reads prepublished JSON artifacts only, and current report candidates keep `canonical_writes_planned = 0`.[2] [3] [4] The Stage 18I design review also states that ordinary warehouse loaders must remain unable to write canonical tables, and that any future canonical write must use a separate guarded apply path with a dry-run artifact, manual approval, audit trail, rollback pre-image, and post-apply verification.[1]

The most important implementation warning is that **current reconciliation `candidate_update` rows are not apply-ready candidates**. Today, a station type difference is shaped as a report-only candidate update and is scored with `canonical_difference_review`, `reconciliation_state = source_only`, and `risk_class = risky` under the existing scoring model.[5] Stage 18J therefore needs a separate canonical pilot planner that consumes read-only evidence and produces a stricter, deterministic station-type-only dry-run artifact. That artifact must not be executable by the ordinary warehouse loader.

| Decision point | Recommendation |
|---|---|
| Safest first canonical write pilot | Yes: exact `stations.station_type` promotion for existing canonical stations only. |
| Stage 18I.5 dependency | Still blocking. PR #103 is open, mergeable, and not merged at review time; Stage 18J must wait until the boundary decision is accepted or a documented temporary equivalent safety arrangement is explicitly approved.[6] |
| Apply path placement | Use a **dedicated canonical apply module/tool**, invoked from importer/maintenance CLI wiring if needed, but not embedded in the warehouse staging loader, API, UI, scheduler, or planner. |
| First implementation mode | Start with dry-run only. Apply mode must be a separate command path and fail closed unless every approval parameter matches the deterministic artifact. |
| Production pilot size | Default to a very small limit, such as 5 rows, with an explicit maximum no higher than 20 rows for the first production pilot. |
| Production readiness | Requires a non-production rehearsal that proves only approved `stations.station_type` values changed and that rollback pre-images are sufficient. |

## Preconditions

Stage 18J should not begin merely because a report identifies station type differences. The accepted prerequisite chain is stricter. Stage 17P defines Stage 18J as a first narrow canonical write pilot only after Stage 18I and Stage 18I.5, and Stage 18I explicitly states that Stage 18J cannot begin until the warehouse database boundary is complete.[1] [7]

The current PR #103 document for Stage 18I.5 recommends Option B, a separate `edfinder_enrichment` database on the same Postgres stack if feasible, while preserving future Option C compatibility. It also states that Stage 18J cannot start until the boundary decision is accepted, and either Option B is implemented or an explicit temporary bounded arrangement with equivalent controls is accepted.[6]

| Precondition | Required state before Stage 18J implementation | Current review status |
|---|---|---|
| Stage 18I design review | Complete and merged. It recommends exact station type promotion as first pilot but authorizes no writes.[1] | Satisfied by current main-branch document. |
| Stage 18I.5 boundary review | Accepted/merged, or an explicit temporary equivalent safety arrangement is approved. | Not satisfied at review time: PR #103 is open and mergeable but not merged.[6] |
| Ordinary warehouse loader boundary | Must remain unable to write canonical tables. | Existing code and tests enforce staging table allow-lists and canonical deny-lists.[3] [8] |
| Read-only reconciliation boundary | Must remain report-only and keep `canonical_writes_planned = 0`. | Existing repository report builder hard-codes `canonical_writes_planned = 0`.[4] |
| Canonical apply identity | Must be separate from warehouse loader identity and scoped to the approved pilot. | Future requirement in Stage 18I.5; not present in current implementation.[6] |
| Operator approval | Must name a specific artifact checksum, row count, table, field, and source run. | Not implemented yet. |
| Non-production rehearsal | Must pass before production apply. | Not implemented yet. |

If Stage 18I.5 remains unmerged or the boundary implementation/temporary exception is not accepted, Stage 18J may still produce documentation and dry-run design notes, but **must not implement or run an apply path**.

## Why Station Type First

Exact station type promotion is still the safest first canonical write pilot. It has a smaller blast radius than station/body links, body fields, rings, explicit no-ring evidence, systems, services, economies, factions, government, allegiance, distances, or planner-derived signals. Updating `stations.station_type` does not create a new entity, does not attach a station to a body, does not affect ring truth, and does not require treating volatile `distanceToArrival` evidence as canonical truth.[1]

The existing warehouse architecture already stages station snapshot fields such as `system_id64`, `market_id`, `edsm_station_id`, `station_name`, `station_type`, `distance_to_arrival`, `body_name`, services, economies, faction, allegiance, government, source timestamps, source class, confidence, and provenance.[2] This is enough to build a station-type-only dry run, but not enough to authorize broad metadata promotion. Stage 18J must therefore select only the stable field that Stage 18I identified as the first pilot and reject all other differences even when they appear in the same source row.

| Candidate path | First-pilot decision | Reason |
|---|---|---|
| Exact `stations.station_type` promotion | Eligible | One existing row, one field, exact identity, reversible pre-image, and no new entity creation. |
| Exact station/body link promotion | Later only | Incorrect links affect planner capacity, lane association, and existing-infrastructure reasoning.[1] |
| Trusted body ring rows | Later only | Ring truth affects body/resource reasoning and needs stronger source semantics.[1] |
| Explicit no-ring evidence | Not first | Empty/missing arrays and no-ring semantics are too source-sensitive for the first pilot.[1] |
| `distanceFromStar` / `distanceToArrival` | Banned | Distance evidence is volatile and must not churn canonical distance values.[2] |
| Services/economies/faction/government/allegiance | Banned | Broader metadata promotion has higher churn and downstream UI/planner risk. |
| Inserts of systems/stations/bodies/links/rings | Banned | First pilot must update only an existing station row. |

## Scope

The Stage 18J pilot scope is **only** exact `stations.station_type` promotion. The only canonical target table is `stations`, and the only canonical target field is `station_type`. The target station row must already exist before the dry run is generated, and the apply path must fail if that row no longer exists or if its pre-image no longer matches the dry-run artifact.

The pilot may read warehouse staging evidence, source-run metadata, source-file metadata, raw record hashes, read-only canonical station rows, and read-only canonical system rows for identity verification. It may also write local JSON artifacts for dry-run, approval, apply audit, rollback pre-image, and post-apply verification. If a future implementation uses an apply queue or audit table, that storage must be part of a separately reviewed canonical apply boundary; it must not turn ordinary warehouse staging into an executable command channel.[6]

| Item | In scope for Stage 18J |
|---|---|
| Canonical table | `stations` only. |
| Canonical field | `station_type` only. |
| Canonical row requirement | Existing row only; exactly one row matched. |
| Evidence source | Offline staged station snapshot evidence, preferably from a named source run/file. |
| Identity keys | Exact `system_id64`, normalized station name, and explicit external station identifier: matching `market_id` or matching `edsm_station_id`. |
| Artifact outputs | Dry-run artifact, approval record, apply artifact, audit record, rollback pre-image, post-apply verification artifact. |
| Limits | Very small bounded pilot; default 5 rows and first-production maximum 20 rows. |

## Explicit Non-Scope

Everything outside `stations.station_type` is non-scope. Stage 18J must reject any candidate, artifact, command, test fixture, or implementation path that writes or implies writes to systems, stations other than the one approved field, bodies, station-body links, body rings, body scan facts, distance fields, services, economies, faction fields, government, allegiance, planner state, Build Plans, scoring, Simulation Preview, optimizers, roles, API job runners, live crawlers, or production schedulers.

| Explicitly out of scope | Required behavior |
|---|---|
| Station inserts, deletes, or row merges | Block. First pilot updates existing rows only. |
| `systems` writes | Block. |
| `bodies` writes | Block. |
| `station_body_links` writes | Block. |
| `body_rings` writes | Block. |
| `body_scan_facts` writes | Block. |
| `stations.distance_from_star` / `distanceToArrival` | Block as volatile evidence. |
| `stations.body_name` | Block for first pilot, even if staged evidence differs. |
| Services/economies/faction/government/allegiance | Block. |
| Planner, Build Plan, role, scoring, Simulation Preview, optimizer mutations | Block. |
| Live EDSM/API crawl | Block. Stage 18J should consume offline/staged evidence. |
| Docker invocation from UI/API | Block. Existing admin endpoints are read-only artifact readers.[9] |
| Production scheduler wiring | Block. |
| Broad backfill | Block. |
| Unknown, missing, source-only, stale, volatile, or risky evidence | Keep unknown/report-only; do not coerce to canonical truth. |

## Candidate Eligibility Rules

A station type candidate should be eligible only when every rule in this section is satisfied. The implementation should evaluate the rules in a deterministic order and include a pass/fail reason for every candidate considered, not just for candidates selected.

The core eligibility rule is that the source row must prove exact identity to one existing canonical station. The current reconciliation SQL allows a broad join using `market_id`, `edsm_station_id`, or station name against canonical station rows.[10] Stage 18J must be stricter than that general report. A pilot candidate must require exact `system_id64`, exactly one canonical station row, a stable station identifier, and normalized station name agreement. Name-only matches must not be eligible.

| Rule group | Required rule |
|---|---|
| Existing canonical station | The candidate must target an already-existing `stations` row. `candidate_insert_missing_canonical` is never eligible. |
| Exact match cardinality | The candidate must resolve to exactly one canonical station. Zero matches and multiple matches block. |
| System identity | Source `system_id64` must be present and equal to canonical `stations.system_id64`/canonical system `id64`. Name-only system identity is insufficient. |
| Stable station identifier | Require an explicit external match: source `market_id` to canonical `market_id`, or source `edsm_station_id` to canonical `edsm_station_id`. Internal canonical `station_id`/primary-key equality is never identity proof. |
| Station name | Source station name and canonical station name must match after the same canonicalisation rule used by the pilot. Case-only differences may match; punctuation/spacing rules must be deterministic and recorded. |
| Source station type | Source station type must be present, valid, normalized, and in the approved permanent-station-type allow-list. Unknown, blank, placeholder, carrier, transient, mobile, unsupported, or unrecognized values block. |
| Current canonical value | Current canonical station type must be missing, blank, unknown, placeholder, or explicitly eligible under a separately approved narrow replacement rule. Existing known types should not be overwritten by default. |
| Evidence quality | Candidate must satisfy the Stage 18J-specific strict filter. Source-only inserts, ambiguous identity, stale/undated evidence without exception, volatile evidence, non-station-type deltas, and transient/non-slot station types block. `missing_station_body_name` remains a station/body-link blocker but does not block an externally proven station-type comparison. |
| Source metadata | Candidate must include source name, adapter version, source run key, source file key, source record key/hash, freshness/timestamp state, and immutable source identity. |
| Duplicate/skip hygiene | Source identity conflicts, malformed/skipped rows, unsupported source linkage, or duplicate identity conflicts block. |
| Determinism | Candidate must be selected from a deterministic dry-run artifact whose canonical JSON SHA-256 is approved by the operator. |
| Rollback | Candidate must include canonical primary key, old value, new value, source identity, confidence/risk reasons, rollback pre-image, and audit metadata. |

The current confidence model labels `candidate_update` as `source_only` and risky because it is report-only and not yet a canonical write instruction.[5] A Stage 18J dry-run planner may either produce a new schema with a stricter `station_type_promotion_candidate` action or preserve the old action while adding a separate explicit `canonical_pilot_eligible = true` marker. In either case, the marker must only appear after all Stage 18J rules pass, and the ordinary reconciliation report must still keep `auto_promote_to_canonical = false` and `canonical_writes_planned = 0`.[5]

## Blocking Conditions

The pilot should prefer **block** over **guess**. A block should be explicit, recorded, and safe. A blocked row should remain evidence only and should not be silently omitted from summary counts.

| Blocking condition | Why it blocks |
|---|---|
| Stage 18I.5 not accepted | Stage 18J is explicitly gated by the warehouse boundary review.[6] |
| Dry-run artifact missing or checksum mismatch | Operator approval cannot be tied to immutable evidence. |
| Artifact schema version unsupported | Apply cannot prove it is reading the intended contract. |
| Candidate count differs from approval | Prevents broad accidental apply. |
| Approved table/field/source run mismatch | Prevents a general warehouse recommendation from becoming executable. |
| Current canonical pre-image changed | Dry-run is stale; operator approval no longer applies. |
| No canonical match | Would imply station insert or invented row. |
| More than one canonical match | Identity is ambiguous. |
| Source `system_id64` missing or different | Exact system identity is not proven. |
| Name-only station match | Stable station identity is insufficient. |
| Station name mismatch after canonicalisation | Exact identity is not proven. |
| Missing, malformed, unsupported, duplicate, or conflicting source identity | Source evidence is not stable enough. |
| Source station type missing, unknown, invalid, carrier, transient, mobile, or unsupported | No safe permanent station type to promote. |
| Existing canonical station type known and not explicitly eligible | Avoids overwriting current truth with staged evidence. |
| Risk class blocked, stale, volatile, source-only insert, or unknown | Evidence is not safe for first canonical write. Report-only candidate updates may feed a dry-run only after Stage 18J-specific eligibility passes; they are still not write instructions. |
| Freshness missing/undated without explicit operator freshness exception | Avoids silently promoting stale snapshot data. |
| Any candidate includes non-station-type differences as apply changes | Prevents scope creep. |
| Any apply SQL targets non-approved table or field | Prevents catastrophic broad write. |
| Post-apply verification not clean | Blocks wider rollout and requires investigation/rollback decision. |

A dry run may include a dedicated `freshness_exception_requested` or `operator_freshness_exception_required` field for undated source rows. Apply must still block unless the approval artifact explicitly names the exception and the affected candidate IDs. This exception should be rare and should not be available for stale evidence where source timestamps prove the data is older than the accepted policy.

## Dry-Run Artifact Contract

The dry-run artifact should be the center of the pilot. It should be a deterministic JSON document, serialized with stable key ordering, assigned a SHA-256 checksum, and archived before any apply command can run. It should be small enough for a human operator to inspect completely during the pilot.

Recommended schema name: `station_type_canonical_pilot_dry_run/v1`.

| Top-level field | Required content |
|---|---|
| `schema_version` | `station_type_canonical_pilot_dry_run/v1`. |
| `generated_at` | UTC timestamp for artifact generation. |
| `tool` | Tool/module name, version, git commit, and command arguments excluding secrets. |
| `dry_run` | Always `true`. |
| `pilot_scope` | `{ "canonical_table": "stations", "canonical_field": "station_type", "allowed_write_count_max": N }`. |
| `source_scope` | Source name, adapter version, source run key, source file key, source snapshot timestamp/freshness summary. |
| `filters` | Candidate filters, limit, explicit source run/file filters, and whether freshness exceptions are allowed. |
| `summary` | Counts for rows considered, eligible candidates, blocked candidates by reason, warnings, errors, canonical writes planned, approved table/field, and deterministic candidate count. |
| `eligible_candidates` | Row-level selected candidates, sorted deterministically. |
| `blocked_candidates` | Row-level rejected candidates with explicit blocking reasons. |
| `operator_review` | Human-readable notes, risk distributions, freshness exceptions required, and non-scope warnings. |
| `artifact_integrity` | Canonical JSON SHA-256, source input hashes if available, and artifact generation method. |

Each eligible candidate should include the following row-level fields.

| Candidate field | Required content |
|---|---|
| `candidate_id` | Deterministic ID derived from source run/file/hash, canonical station ID, and target field. |
| `canonical_table` | Always `stations`. |
| `canonical_pk` | Canonical station primary key. |
| `canonical_system_id64` | Canonical station/system ID64. |
| `canonical_station_name` | Current canonical station name. |
| `field` | Always `station_type`. |
| `old_value` | Current canonical station type pre-image. |
| `new_value` | Normalized approved permanent station type. |
| `source_identity` | `system_id64`, `market_id`, `edsm_station_id` when available, station name, station type, source run/file/record keys, and source record hash. |
| `match_proof` | Exact system match, stable identifier match type, normalized name comparison, canonical match count, duplicate checks. |
| `eligibility` | Pass/fail booleans for every rule, even for selected candidates. |
| `confidence` | Confidence/risk labels, reasons, source class, freshness class, timestamp state, and non-volatile field classification. |
| `rollback_pre_image` | Full pre-image needed to restore this field on this row. |
| `audit_metadata` | Reason codes, operator-review text, source metadata, and tool version. |

The dry-run artifact must keep `canonical_writes_planned = 0`; eligible rows are
reported separately as `eligible_station_type_updates`. Existing warehouse
reconciliation and coverage reports also continue to report
`canonical_writes_planned = 0`, because these report families are not canonical
apply instructions.[4] [5] Stage 18J-P-filter records the hardened filter in
[`stage-18j-p-filter-strict-station-type-dry-run-filter.md`](./stage-18j-p-filter-strict-station-type-dry-run-filter.md).

## Apply Contract

Apply mode must be separate from dry run and must fail closed. It should never infer approval from a file path alone, and it should never accept general `--apply` flags in existing warehouse loaders. The existing staging loader already rejects `--apply`, `--write`, and `--commit` for canonical writes and requires explicit `--write-staging`, `--dsn`, and `--confirm-staging-db` for staging-only writes.[11] Stage 18J should copy the fail-closed spirit, but not the same command, because canonical apply is a different trust boundary.

Recommended apply schema name: `station_type_canonical_pilot_apply/v1`.

| Apply parameter | Required behavior |
|---|---|
| `--artifact PATH` | Required path to dry-run artifact. |
| `--artifact-sha256 HEX` | Required exact checksum. Recompute and fail if mismatched. |
| `--expected-candidate-count N` | Required exact count. Fail if artifact count differs. |
| `--approved-table stations` | Required exact table. |
| `--approved-field station_type` | Required exact field. |
| `--approved-source-run KEY` | Required exact source run key. |
| `--approved-source-file KEY` | Strongly recommended; required for first production pilot unless multiple files are explicitly approved. |
| `--approval-id TEXT` | Required operator approval reference. |
| `--confirm-station-type-canonical-pilot` | Required explicit confirmation flag. |
| `--max-rows N` | Required limit, no greater than the approved artifact count and first-pilot cap. |
| `--dsn` or environment DSN | Must use canonical apply credentials, not warehouse loader credentials. |

Before updating any row, apply must re-read the current canonical row and prove that the pre-image still matches the dry-run artifact. It must run in one transaction for the bounded pilot batch, write the apply/audit/rollback artifacts before committing where practical, and fail closed if any row fails eligibility revalidation. If the implementation cannot safely write audit artifacts before commit, it must at least write a pre-transaction immutable intent artifact and a post-transaction audit artifact tied by apply run ID.

The only permitted SQL effect is equivalent to updating `stations.station_type` for the approved station primary keys from the recorded old value to the recorded new value. No other columns may be changed. If the database permission model cannot enforce column-level update permissions, the apply code must verify affected columns through pre/post snapshots and tests.

## Audit Trail Contract

Every apply attempt, successful or failed, should emit an audit artifact. The audit artifact should answer who changed what, why, from which source evidence, under which approval, and how to verify or roll it back. Stage 18I requires apply run ID, dry-run artifact checksum, operator approval reference, tool version, source run/file keys, source record hashes, canonical table, primary key, field, old value, new value, confidence/risk metadata, transaction timestamp, planned/applied/skipped/blocked counts, and verification result.[1]

Recommended schema name: `station_type_canonical_pilot_audit/v1`.

| Audit field | Required content |
|---|---|
| `apply_run_id` | Unique immutable run ID. |
| `dry_run_artifact_sha256` | Approved artifact checksum. |
| `approval` | Approval ID/text, operator identity if available, approved table/field/source/count. |
| `tool` | Module, version, git commit, command arguments excluding secrets. |
| `transaction` | Transaction start/end timestamps and success/failure status. |
| `rows` | For each row: station ID, system ID64, station name, old value, new value, source identity, source record hash, and result. |
| `blocked_or_skipped` | Any row that was not applied and the exact reason. |
| `post_apply_verification` | Verification artifact path/checksum and pass/fail state. |
| `secrets_redaction` | Confirmation that DSNs, API keys, private paths, and secrets were not written. |

Audit artifacts should be retained with canonical operational records rather than treated as disposable warehouse staging output. Stage 18I.5 assigns canonical apply audit and rollback ownership to the canonical apply side, not ordinary warehouse staging.[6]

## Rollback Contract

Rollback must not depend on re-reading mutable warehouse evidence after the fact. The required rollback unit is the canonical pre-image captured at dry-run/apply time. The first pilot can have a simple rollback plan because it touches one field on existing station rows.

Recommended schema name: `station_type_canonical_pilot_rollback_preimage/v1`.

| Rollback field | Required content |
|---|---|
| `apply_run_id` | Apply run being protected. |
| `dry_run_artifact_sha256` | Dry-run artifact that authorized the change. |
| `canonical_table` | Always `stations`. |
| `canonical_pk` | Station ID. |
| `field` | Always `station_type`. |
| `pre_image_value` | Value before apply, including `NULL`/blank/unknown distinction. |
| `applied_value` | Value written by apply. |
| `source_trace` | Source run/file/record hash and candidate ID. |
| `rollback_sql_preview` | Human-readable rollback intent; not executable by ordinary warehouse loader. |
| `rollback_verification_rule` | Expected value after rollback and query/check to prove it. |

A rollback command, if implemented, should itself have dry-run and apply phases. It should require artifact checksum, apply run ID, expected row count, approved table/field, and explicit rollback confirmation. If any current value no longer equals the value written by the original apply, rollback must fail closed and require manual review.

## Operator Approval Flow

Operator approval must be deliberate and artifact-specific. A general instruction to apply all warehouse recommendations is not acceptable. The pilot should produce small, reviewable artifacts and require the operator to name exactly what is being approved.

| Step | Operator action | Required gate |
|---|---|---|
| 1 | Generate a dry-run artifact from a named source run/file with a small limit. | Artifact must be deterministic and checksumed. |
| 2 | Review summary, candidate rows, blocked rows, freshness state, duplicate/source conflicts, and non-scope warnings. | No unexpected warnings, no errors, no blocked selected candidates. |
| 3 | Confirm Stage 18I.5 readiness. | PR/decision accepted, or temporary equivalent boundary explicitly approved. |
| 4 | Approve the artifact. | Approval names checksum, row count, table `stations`, field `station_type`, source run/file, and maximum rows. |
| 5 | Run non-production apply rehearsal. | Post-apply verification proves only approved station type changes occurred. |
| 6 | Archive dry-run, approval, apply audit, rollback pre-image, and verification artifacts together. | No missing artifacts. |
| 7 | Run production pilot with very small limit. | Same parameters and fail-closed gates. |
| 8 | Review post-apply verification and decide whether to stop, roll back, or plan a later wider stage. | Any anomaly stops rollout. |

The UI/API should not expose an apply button for Stage 18J. Existing admin endpoints intentionally read sanitized artifacts and do not run importer scripts, Docker, live APIs, or database queries.[9] Stage 18J should preserve that boundary.

## Post-Apply Verification

Post-apply verification must prove both the positive and negative claims: the approved rows changed to the approved values, and no unapproved canonical values changed. Re-running the read-only comparison and seeing the planned updates become no-ops is necessary but not sufficient; the verifier should also compare pre/post canonical snapshots for the approved primary keys and, where possible, an aggregate guard over the canonical table.

| Verification check | Required proof |
|---|---|
| Approved rows changed | Each approved station ID has `station_type = new_value`. |
| Pre-image matched at apply time | Audit artifact records old value exactly as dry-run recorded it. |
| No unapproved candidate applied | Applied row count equals approved candidate count. |
| No unapproved field changed | Pre/post snapshot for approved rows differs only in `station_type`. |
| No unapproved table changed | Apply tool records target table/field and tests prove no other write path. |
| Reconciliation no-op | A post-apply read-only report for the same source scope no longer proposes those station-type updates. |
| Artifact integrity | Verification artifact has schema version, checksum, tool version, and links to dry-run/apply artifacts. |
| Rollback readiness | Rollback pre-image exists for every applied row. |

Recommended verification schema name: `station_type_canonical_pilot_verification/v1`. Any verification failure should stop wider rollout. If a production pilot verification fails, the operator should preserve all artifacts, avoid rerunning apply, and decide whether to execute rollback after inspecting the exact mismatch.

## CLI / Module Placement Recommendation

The apply logic should live in a **dedicated canonical apply module**, with a thin CLI wrapper. It should not be embedded in `enrichment_staging_db_loader.py`, `enrichment_snapshot_loader.py`, `enrichment_warehouse_repository.py`, API routers, UI code, scheduler jobs, or planner code. This placement preserves the current invariant that ordinary warehouse loaders cannot write canonical tables and allows tests to prove the canonical apply path is separate.[3] [8]

| Placement option | Recommendation | Rationale |
|---|---|---|
| Existing warehouse staging loader | Reject | It currently rejects canonical flags and is responsible for warehouse-only writes.[11] |
| Existing snapshot loader | Reject | It is dry-run only, offline, and has no DB/network/write path.[2] |
| API/admin endpoint | Reject | Current admin endpoints are read-only artifact readers and should remain so.[9] |
| Production scheduler | Reject | Scheduler wiring is explicitly out of scope for the pilot. |
| Importer CLI thin wrapper around dedicated module | Accept | Keeps operational location familiar while preserving a separate canonical boundary. |
| Dedicated maintenance script/module | Prefer | Makes the trust boundary obvious and easier to test. |

A reasonable future shape is a module such as `apps/importer/src/canonical_station_type_pilot.py` with pure artifact-building functions and explicit DB functions, plus a script or module entrypoint that supports `dry-run`, `apply`, `verify`, and optionally `rollback-dry-run`. The names are illustrative; the important requirement is boundary separation, not the exact file path.

## Database Boundary Interaction

Stage 18J must follow the Stage 18I.5 boundary decision. The preferred direction is Option B: `edfinder_enrichment` as a separate warehouse database on the same Postgres stack if feasible, with future Option C compatibility.[6] Under Option B, the warehouse loader writes only to the warehouse database; reconciliation uses canonical snapshots, read-only views, FDW, or immutable exported artifacts; and a separate canonical apply user crosses the boundary only through approved artifacts or a tightly permissioned immutable queue.[6]

| Boundary concern | Stage 18J requirement |
|---|---|
| Warehouse database | Source evidence and report/write-plan proposals may live in `edfinder_enrichment`. |
| Canonical app database | Remains source of trusted current facts. |
| Warehouse loader user | Must not have canonical write privileges. |
| Warehouse read/report user | Read-only, or report-artifact write only if separately approved. |
| Canonical apply user | Separate from app and warehouse users; unavailable by default; scoped to the pilot. |
| Write-plan transfer | Immutable JSON artifact with checksum or immutable queue row; not executable by ordinary loader. |
| Audit/rollback ownership | Canonical apply side, not ordinary warehouse staging. |

If Option B has not yet been implemented but the project explicitly accepts a temporary transitional arrangement, that acceptance must be recorded before implementation. The transitional arrangement must still prove equivalent safety controls: separate credentials where practical, deny-listed warehouse code, immutable artifact transfer, read-only reconciliation, explicit apply user boundary, and rollback/audit ownership.

## Non-Production Rehearsal Plan

A production pilot must be preceded by a non-production rehearsal using disposable or staging databases. The rehearsal should exercise the same CLI, artifact checksums, approval gates, transaction behavior, audit output, rollback pre-images, and verification logic planned for production.

| Rehearsal phase | Acceptance criterion |
|---|---|
| Fixture dry run | Produces deterministic `station_type_canonical_pilot_dry_run/v1` artifact with expected eligible and blocked rows. |
| Fixture apply | Applies only the approved `stations.station_type` changes in a disposable canonical database. |
| Negative fixtures | Ambiguous, insufficient, stale, volatile, source-only, duplicate, carrier/transient, name-only, current-known-type, and pre-image-mismatch cases all block. |
| Verification | Proves only approved `station_type` fields changed and post-apply reconciliation is clean for the approved rows. |
| Rollback dry run | Produces a rollback plan from the captured pre-image. |
| Rollback apply, if implemented | Restores the original values and verifies them. |
| Artifact archive | Dry-run, approval, apply audit, rollback pre-image, and verification artifacts are complete and secret-free. |

The rehearsal should not use live EDSM/API calls. It should use fixtures and, if needed, an operator-provided offline source snapshot loaded into a disposable warehouse/staging environment.

## Production Pilot Limits

The first production pilot should be deliberately boring. The default limit should be 5 eligible rows, and the first production cap should be no higher than 20 rows. The apply command must require an expected candidate count and should refuse to apply if the artifact contains more rows than the production cap unless a later stage explicitly changes the cap.

| Limit type | Recommendation |
|---|---|
| Default dry-run candidate limit | 5 eligible candidates. |
| First production maximum | 20 eligible candidates. |
| Source scope | One source run and preferably one source file. |
| Field scope | `stations.station_type` only. |
| Table scope | `stations` only. |
| Apply transaction | One bounded transaction for the pilot batch, unless rehearsal proves a safer per-row transaction model with equivalent audit. |
| Rollout after success | Stop after the pilot and review artifacts. Do not continue into broad backfill in Stage 18J. |

A larger station-type backfill should be a later stage with separate acceptance criteria, not an automatic continuation of Stage 18J.

## Required Tests

Tests should be written before implementation or alongside the first dry-run-only implementation. They should prove that the pilot is narrower than current reconciliation and that existing warehouse/report-only guarantees remain intact.

| Test category | Required coverage |
|---|---|
| Boundary preservation | Ordinary warehouse loaders still cannot write canonical tables; `--apply`, `--write`, and `--commit` remain rejected in current loaders.[11] |
| Dry-run default | New pilot tool defaults to dry-run and writes no canonical data. |
| Artifact determinism | Same inputs produce byte-stable canonical JSON and the same SHA-256. |
| Eligibility acceptance | Exact system ID64, stable identifier, normalized name, valid permanent station type, eligible old value, clear risk state, and complete source metadata produce an eligible candidate. |
| Identity rejection | Zero matches, multiple matches, name-only matches, mismatched system ID64, mismatched normalized station name, duplicate identity conflict, and malformed/skipped linkage block. |
| Source type rejection | Missing, unknown, placeholder, unrecognized, carrier, transient, mobile, or unsupported station types block. |
| Current value rejection | Existing known canonical station types are not overwritten by default. |
| Evidence-state rejection | Ambiguous, insufficient, source-only inserts, stale, undated without approved exception, volatile, unknown, and non-station-type candidates block. Report-only reconciliation rows may feed the dry-run only after Stage 18J-specific eligibility passes; they are never canonical write instructions by themselves. |
| Scope rejection | Distance, body name, services, economies, faction, government, allegiance, systems, bodies, links, rings, scan facts, planner, scoring, optimizer, Simulation Preview, role, and Build Plan mutations block. |
| Apply gating | Apply requires artifact path, artifact SHA-256, expected count, approved table, approved field, approved source run, approval ID, and confirmation flag. |
| Pre-image safety | Apply fails if current canonical pre-image differs from dry-run pre-image. |
| Audit | Audit artifact includes source, pre-image, approval, tool version, row results, and verification metadata. |
| Rollback | Rollback pre-image can restore old values and fails closed if current values drift. |
| Verification | Post-apply verification proves only approved `stations.station_type` changed. |
| API/UI/scheduler absence | No apply endpoint, UI button, Docker invocation, live API crawl, or production scheduler path is introduced. |

Existing tests already provide useful patterns. The warehouse boundary tests prove canonical deny-list behavior and read-only reconciliation SQL enforcement.[8] The staging DB loader tests prove dry-run defaults, explicit staging-only writes, rollback on write failure, and fail-closed parsing for unsupported canonical flags.[11] The existing station enrichment guard tests and wrapper provide operational precedent for persisted artifacts, safety gates, and final dry-run verification, but Stage 18J should not reuse the live EDSM crawl path as its source of truth.[12]

## Failure Modes And Stop Conditions

The catastrophic failures are not subtle. The pilot could corrupt canonical data, overwrite trusted station types with bad snapshot values, turn name-only evidence into false identity, treat stale or source-only evidence as truth, accidentally write broad station metadata, or create a path by which ordinary warehouse loaders become canonical writers. Each of these must be converted into a stop condition.

| Catastrophic risk | Stop condition |
|---|---|
| Broad canonical write | Stop if generated SQL, DB permissions, or audit shows any table other than `stations` or any field other than `station_type`. |
| Wrong station identity | Stop if any candidate lacks exact `system_id64`, stable station identifier, normalized name match, and exactly one canonical match. |
| Source type pollution | Stop if any selected candidate has missing, unknown, unrecognized, carrier, transient, mobile, or unsupported source type. |
| Existing truth overwritten | Stop if any selected candidate overwrites a known canonical type without an explicitly approved replacement rule. |
| Stale artifact | Stop if artifact checksum, row count, source run/file, table, field, or current pre-image differs from approval. |
| Current reconciliation semantics misused | Stop if ordinary `candidate_update` rows are applied without Stage 18J-specific eligibility marking. |
| Warehouse loader gains canonical power | Stop if `enrichment_staging_db_loader.py` or warehouse repository code gains canonical write behavior. |
| Planner or scoring mutation | Stop if implementation touches planner, Build Plan, scoring, Simulation Preview, optimizer, role, or validation behavior. |
| Live API dependency | Stop if implementation calls EDSM/API, invokes Docker from UI/API, or wires a scheduler. |
| Missing audit or rollback | Stop if any applied row lacks audit and rollback pre-image. |
| Verification failure | Stop all rollout; preserve artifacts; do not re-run apply until reviewed. |
| Non-production rehearsal missing | Stop before production apply. |

Codex or any implementing agent should stop immediately when it discovers that the requested implementation would require migrations, broad permissions, production database creation, UI/API write controls, live API crawling, scheduler wiring, or non-station-type canonical writes unless the user explicitly opens a new stage to approve that broader scope.

## Recommended Codex Implementation Prompt

```md
You are implementing Stage 18J for ED-Finder. Before changing code, read:

1. docs/colonisation-redesign/README.md
2. docs/colonisation-redesign/stage-17p-current-state-forward-plan.md
3. docs/ROADMAP.md
4. docs/colonisation-redesign/enrichment-staging-architecture.md
5. docs/operations/enrichment-warehouse-runbook.md
6. docs/colonisation-redesign/stage-18h-warehouse-planner-evidence-bridge.md
7. docs/colonisation-redesign/stage-18i-canonical-write-design-review.md
8. docs/colonisation-redesign/stage-18i5-warehouse-database-boundary-review.md
9. docs/reference/colonisation/README.md
10. docs/reference/colonisation/source-priority.md
11. docs/reference/colonisation/codex-reference-prompt-snippet.md
12. docs/colonisation-redesign/stage-18j-station-type-canonical-pilot-plan.md

Hard scope: implement only exact `stations.station_type` canonical pilot support for existing canonical stations matched by exact trusted station identity. Do not implement station inserts, deletes, systems writes, bodies writes, station_body_links writes, body_rings writes, body_scan_facts writes, distance writes, service/economy/faction/government/allegiance writes, planner mutation, Build Plan mutation, scoring changes, Simulation Preview changes, optimizer changes, role changes, live EDSM/API crawl, UI/API Docker invocation, production scheduler wiring, or broad backfill.

Start with tests and a dry-run-only artifact builder. The dry-run artifact must be deterministic and versioned as `station_type_canonical_pilot_dry_run/v1`. Eligible candidates must require exact `system_id64`, exactly one canonical station match, external station identity by matching `market_id` or `edsm_station_id`, normalized station name match, valid permanent source station type, eligible old canonical value, no ambiguous/source-only-insert/stale/volatile/transient/non-station-type selected evidence, source run/file/record metadata, rollback pre-image, and audit metadata.

Do not make ordinary warehouse loaders able to write canonical tables. Do not reuse report-only `candidate_update` rows as executable write instructions. Current reconciliation reports must continue to keep `canonical_writes_planned = 0` and `auto_promote_to_canonical = false`.

Apply mode, if implemented in this stage, must be a separate guarded canonical apply path. It must require artifact path, artifact SHA-256, expected candidate count, approved table `stations`, approved field `station_type`, approved source run, approval reference, and explicit confirmation flag. It must fail closed on any mismatch, stale pre-image, blocked candidate, wrong table, wrong field, or verification failure. It must emit audit, rollback pre-image, and post-apply verification artifacts.

Before any production apply, require non-production rehearsal. First production pilot defaults to 5 rows and must not exceed 20 rows. Stop immediately if implementation requires migrations, broad permissions, live API crawling, UI/API write controls, scheduler wiring, or non-station-type canonical writes.
```

## Final Recommendation

Stage 18J should proceed only as a **strict station-type-only canonical pilot** after the Stage 18I.5 boundary decision is accepted or an explicit temporary equivalent safety arrangement is approved. The pilot should begin with tests and dry-run-only artifact generation, not with apply. Apply should be introduced only as a separate guarded canonical apply path that requires checksumed artifact approval, exact table/field/source/count parameters, a small candidate cap, audit records, rollback pre-images, and post-apply verification.

The answer to the primary risk question is therefore yes: exact station type promotion is still the safest first canonical write pilot. The answer is conditional, however. It is safe only if the implementation refuses to treat current report-only reconciliation candidates as write instructions, keeps ordinary warehouse loaders unable to write canonical tables, blocks all uncertain evidence states, and proves in non-production that only approved `stations.station_type` values can change.

## References

[1]: ./stage-18i-canonical-write-design-review.md "Stage 18I — Canonical Write Design Review"
[2]: ./enrichment-staging-architecture.md "Enrichment Staging Architecture"
[3]: ../../apps/importer/src/enrichment_warehouse.py "enrichment_warehouse.py"
[4]: ../../apps/importer/src/enrichment_warehouse_repository.py "enrichment_warehouse_repository.py"
[5]: ../../apps/importer/src/enrichment_reconciliation_scoring.py "enrichment_reconciliation_scoring.py"
[6]: ./stage-18i5-warehouse-database-boundary-review.md "Stage 18I.5 — Warehouse Database Boundary Review"
[7]: ./stage-17p-current-state-forward-plan.md "Stage 17P — Current State / Forward Plan Baseline"
[8]: ../../tests/test_enrichment_warehouse_boundary.py "test_enrichment_warehouse_boundary.py"
[9]: ../../apps/api/src/routers/admin.py "admin.py"
[10]: ../../apps/importer/src/enrichment_warehouse_sql.py "enrichment_warehouse_sql.py"
[11]: ../../tests/test_enrichment_staging_db_loader.py "test_enrichment_staging_db_loader.py"
[12]: ../../scripts/station_enrichment_guard.py "station_enrichment_guard.py"


