# PR #807 disk-inventory review round 6 fix plan

## Scope and evidence baseline

This plan is based on immutable commit `396439c23eca424329d8e4da25dcea5e28713ae2`, which was reachable after fetching `origin/codex/run-38130707546-1`. All line references below are to that commit. The only implementation surfaces in scope are `scripts/operator/actions/v3-disk-inventory.sh`, `tests/test_v3_disk_inventory.py`, and `docs/operations/v3-finder-production-rollout-state.md`; the control-plane context is `.github/workflows/chatgpt-ed-new-ops.yml:39-45,177-197`. No production inspection is needed or authorized for these fixes.

The current action has a 1,800-second process-level budget and a 240-second post-scan SQL reserve (`scripts/operator/actions/v3-disk-inventory.sh:53-74`), while the shared workflow job has a 40-minute timeout (`.github/workflows/chatgpt-ed-new-ops.yml:39-45`). The current receipt no longer claims byte-exact closure: it compares `candidate_shortfall_bytes` with `measurement_uncertainty_bytes` and exposes `candidates_account_for_unaccounted_within_uncertainty` (`scripts/operator/actions/v3-disk-inventory.sh:3390-3444`; `docs/operations/v3-finder-production-rollout-state.md:585-626`). That distinction matters for F2, F3, F4, and F6.

## F1 — reserve closing scans against the action deadline

### (a) Correctness at the reviewed commit

The finding is correct. The action gives the pre-closing walk a nominal 1,200 seconds, configures three 300-second closing allowances (PGDATA, `pg_wal`, and `base/`), and therefore sets a 900-second reconciliation reserve (`scripts/operator/actions/v3-disk-inventory.sh:75,121-162`). `ScanBudget.remaining()` subtracts that reserve only from its scan-local deadline; its global calculation subtracts only the 240-second SQL reserve (`scripts/operator/actions/v3-disk-inventory.sh:647-710`). After a full 1,200-second walk, 600 global seconds remain and the 240-second SQL holdback leaves only 360 seconds for all closing scans. A 300-second PGDATA close can therefore leave only 60 seconds for the next scan even if intervening SQL takes no time (`scripts/operator/actions/v3-disk-inventory.sh:2295-2323,2362-2364`). `begin_closing_scan()` resets only `_deadline`; it cannot recreate time under `ACTION_DEADLINE` (`scripts/operator/actions/v3-disk-inventory.sh:670-710`). The comments claiming that the global minimum shortens the walk sufficiently, and later describing 1,200 seconds of walking plus only 600 seconds of closing, contradict the actual 900-second reserve (`scripts/operator/actions/v3-disk-inventory.sh:146-160`).

One consequence is overstated in the review wording. The PGDATA and dedicated WAL scans are required by the current reconciliation, but `base/` is an optional refinement: its failure becomes `postgres_base_directory_breakdown.available = false`, and the summary can still succeed with a null completeness verdict (`scripts/operator/actions/v3-disk-inventory.sh:2491-2507,3395-3408`; `tests/test_v3_disk_inventory.py:2751-2770`). Starving `base/` still loses attribution, but it does not necessarily stop the action. The named deadline behavior and receipt fields otherwise still exist at this commit (`scripts/operator/actions/v3-disk-inventory.sh:1482-1491,2799-2807`).

### (b) Root cause

The code composes two budget domains as though a reserve in the local `ScanBudget` were also reserved under the global action deadline. It is not: `own` deducts `self.reserve()`, while `overall` does not (`scripts/operator/actions/v3-disk-inventory.sh:700-710`). A one-line subtraction of the reserve from `overall` would fix the no-intervening-SQL example, but it would still allow SQL between closing scans to consume future scan time because `run()` consults only raw `action_remaining()` (`scripts/operator/actions/v3-disk-inventory.sh:202-235`).

### (c) Fix

Apply F3/F4 first and remove the unsafe dedicated WAL scan. That leaves two closing scans, so change `RECONCILE_RESERVE_SECONDS` from three allowances to `2 * DIRECTORY_USAGE_TIMEOUT_SECONDS`, remove `WAL_DIRECTORY_SCAN_SECONDS`, and derive the walk allocation rather than retaining the impossible 1,200-second promise (`scripts/operator/actions/v3-disk-inventory.sh:121-162`). The resulting phase maxima are 960 seconds for pre-closing scans, 600 seconds for closing scans, and 240 seconds for all non-scan work and receipt emission.

Implement explicit elapsed-time ledgers rather than another advancing deadline:

1. Define `NON_SCAN_AND_RECEIPT_BUDGET_SECONDS = 240`, `RECONCILE_RESERVE_SECONDS = 600`, and `DIRECTORY_SCAN_WALK_SECONDS = ACTION_BUDGET_SECONDS - RECONCILE_RESERVE_SECONDS - NON_SCAN_AND_RECEIPT_BUDGET_SECONDS` (960). Keep `ACTION_DEADLINE` as the final ceiling (`scripts/operator/actions/v3-disk-inventory.sh:53-75,143-162`).
2. Charge actual scan time in `du_stream()` in a `finally` path, including failed attempts, to either the walk ledger or the closing ledger (`scripts/operator/actions/v3-disk-inventory.sh:739-945`). Charge every other elapsed second from process start, including subprocesses, Python processing, and final JSON serialization, to the non-scan/receipt ledger. Clamp `run()` by both that ledger and `ACTION_DEADLINE` (`scripts/operator/actions/v3-disk-inventory.sh:202-235`).
3. Have `begin_closing_scan(300)` reserve one allowance from a `closing_scan_seconds_remaining` ledger and refuse an over-release or a third call. `ScanBudget.remaining()` must preserve all unspent future-closing time and all unspent non-scan/receipt time while the walk is active, and preserve future-closing time while a closing scan is active (`scripts/operator/actions/v3-disk-inventory.sh:647-716`).
4. Do not use a simple non-scan deadline: scan time between SQL calls must not consume the non-scan bucket. Measure category elapsed time, and decrement in `finally` so `OSError`, timeout, churn retry, and normal completion are all charged (`scripts/operator/actions/v3-disk-inventory.sh:207-235,794-945`). Avoid `ceil()` plus `max(1, ...)` when less than one second remains because that can overspend the ledger (`scripts/operator/actions/v3-disk-inventory.sh:212-217,712-716`).
5. Replace the misleading receipt values at `scripts/operator/actions/v3-disk-inventory.sh:1482-1491` with `directory_scan_walk_budget_seconds: 960`, `closing_scan_budget_seconds: 600`, `non_scan_and_receipt_budget_seconds: 240`, the remaining values after the walk, and the existing `action_budget_seconds`. Remove or redefine `scan_budget_seconds` (currently larger than the action) and rename `post_scan_sql_reserve_seconds`, because the bucket covers setup, SQL before/between/after scans, Python work, and receipt emission.

This fix intentionally removes the 1,200-second walk behavior rather than raising the shared job timeout. The workflow timeout is shared with other operations and is explicitly 40 minutes (`.github/workflows/chatgpt-ed-new-ops.yml:39-45`); the current documentation already rejects raising it for this action (`docs/operations/v3-finder-production-rollout-state.md:467-476`).

### (d) Tests

- Update `test_v3_disk_inventory_shares_one_scan_budget_within_the_job_timeout` to replace the literal 1,200-second assertion with the derived 960/600/240/1,800 arithmetic, while retaining its one-budget, threaded-budget, reconciliation-bracket, and span assertions (`tests/test_v3_disk_inventory.py:950-984`).
- Rewrite `test_v3_disk_inventory_reserves_budget_for_the_closing_reconciliation` to require two closing releases after F3/F4, require deduction of unspent future-closing and non-scan ledgers, and assert that the maxima sum to 1,800. Preserve its negative assertion that `du_rows()` has no per-call `reserve_seconds`, the minimum-call guard, the churn behavior, the closing-stream omitted-child accounting, and the separate reconciliation section (`tests/test_v3_disk_inventory.py:1007-1094`).
- Change `test_v3_disk_inventory_reports_a_reconciled_span` from a 900-second to a 600-second receipt reserve and add the 960- and 240-second receipt fields (`tests/test_v3_disk_inventory.py:1097-1108`).
- Rewrite `test_v3_disk_inventory_reserve_survives_the_sql_phase`: resetting a local deadline is the defective mechanism, so the test must simulate elapsed SQL/non-scan time and prove it reduces only the 240-second bucket while later scan allowances remain available. Keep its behavioral subject that intervening SQL cannot silently steal a later scan's allowance (`tests/test_v3_disk_inventory.py:1432-1450`).
- Update only the `begin_closing_scan()` source pin in `test_v3_disk_inventory_emits_no_base_candidate_without_the_breakdown` if the method signature changes; retain every base-unavailable assertion, including no fabricated candidate, `candidate_list_complete is False`, and a null verdict (`tests/test_v3_disk_inventory.py:2716-2774`).
- Preserve `DIRECTORY_USAGE_TIMEOUT_SECONDS = 300` in `test_v3_disk_inventory_has_fixed_read_only_runtime_targets` (`tests/test_v3_disk_inventory.py:35-50`). Add a `timeout-minutes: 40` assertion to the budget or allowlist test so the outer arithmetic is pinned (`tests/test_v3_disk_inventory.py:24-32,950-984`).

### (e) Risks and likely next review

The most likely regression is a superficially correct `overall -= self.reserve()` change that still lets intervening SQL spend future scan time. The next likely issue is undercharging exceptions/retries or overspending a sub-second remainder through integer rounding. A 240-second aggregate non-scan bucket can stop a slow but otherwise valid inventory; that is the intended fail-closed outcome and must be visible in the receipt. Python code and serialization also have to be charged if the plan claims a complete 1,800-second partition; subprocess caps alone do not prove that claim (`scripts/operator/actions/v3-disk-inventory.sh:3608-3618`).

## F2 — resolve ordinary bind sources, not only mount targets

### (a) Correctness at the reviewed commit

The finding is correct. `same_device_aliases()` reads `/proc/mounts`, collects only mount-point targets under `usage_root`, and groups only those targets by `(st_dev, st_ino)` (`scripts/operator/actions/v3-disk-inventory.sh:477-527`). In the normal bind layout, the original ordinary directory is not a mount point, so it never enters `points`; one target cannot form an alias set. Only paths after the first detected target are passed to `du --exclude`, so an undetected source/target pair is traversed twice (`scripts/operator/actions/v3-disk-inventory.sh:1330-1364`). The action still exposes the `df - du` residual and converts differences to uncertainty (`scripts/operator/actions/v3-disk-inventory.sh:2960-2986,3290-3322,3370-3386,3458-3479`), so duplicate directory candidates can be offset by the negative residual and still satisfy the current within-uncertainty verdict (`scripts/operator/actions/v3-disk-inventory.sh:3390-3408`).

No consequence is obsolete, but “closed receipt” now means the uncertainty-qualified field `candidates_account_for_unaccounted_within_uncertainty`, not the removed exact-partition model (`scripts/operator/actions/v3-disk-inventory.sh:3440-3444`; `docs/operations/v3-finder-production-rollout-state.md:585-626`). A second fail-open defect is current: failed or malformed `stat` probes are silently skipped (`scripts/operator/actions/v3-disk-inventory.sh:514-526`).

### (b) Root cause

The implementation has a correct identity predicate but an incomplete discovery set. `/proc/mounts` supplies the mounted target but does not reliably supply the original bind pathname, while the code assumes every alias is itself a mount target (`scripts/operator/actions/v3-disk-inventory.sh:477-513`). It then treats inability to verify an identity as absence of an alias (`scripts/operator/actions/v3-disk-inventory.sh:514-526`).

### (c) Fix

Replace target-only `/proc/mounts` discovery in `same_device_aliases()` with a strict `/proc/self/mountinfo` parser. Split each record at the ` - ` separator, decode the four kernel octal path escapes already handled by `mount_atime_policy()`, and retain mount ID, parent ID, major:minor, filesystem root, and mount point (`scripts/operator/actions/v3-disk-inventory.sh:415-474,477-533`). For each same-device nested mount under `usage_root`, map its filesystem root through the mount entry that provides the scanned root, reconstruct the ordinary source pathname, and verify source and target with `os.stat()` `(st_dev, st_ino)`. Fail closed on malformed input, ambiguous provider/root mapping, missing source, or failed/mismatched identity; do not retain the current `continue` behavior (`scripts/operator/actions/v3-disk-inventory.sh:493-527`).

Move alias resolution before the first `pgdata_before` scan, not merely before the root walk (`scripts/operator/actions/v3-disk-inventory.sh:1309-1351`). Build one canonical alias plan for the run, preferentially retaining the path that contains `pgdata_host`; otherwise retain the reconstructed ordinary source. Filter the exclusions to each scan root and apply them to every potentially affected `du`: opening PGDATA totals, the root depth-2 scan, PGDATA detail, drill-down, closing PGDATA, and `base/` (`scripts/operator/actions/v3-disk-inventory.sh:957-971,1021-1026,1330-1426,1472-1479,2317-2323,2499-2505`). After F3/F4 there is no dedicated WAL scan to update. Escape literal paths for GNU `du`'s pattern-valued `--exclude` option; fail closed if a path cannot be represented without matching unrelated names.

Keep `inventory.directory_scan_same_device_aliases`, but replace its weak target count with `mountinfo_entries_examined`, `alias_sets`, `aliases_present`, and per-bind `source_path`, `target_path`, `retained_path`, and `excluded_paths`. Record unresolved entries and a reason before raising so the stopped receipt explains why no scan was trusted (`scripts/operator/actions/v3-disk-inventory.sh:528-533,1345-1351`). No SQL or product receipt field changes are needed.

The safety-first fallback, if unambiguous mountinfo reconstruction proves too complex for a reviewed patch, is to stop on every same-device nested bind instead of deduplicating it. Continuing with target-only grouping is not an acceptable fallback.

### (d) Tests

- Replace the target-only literal assertions in `test_v3_disk_inventory_excludes_same_device_bind_aliases` with a synthetic mountinfo case containing an ordinary source and one bind target. Assert the exact resolved source/target/retained/excluded receipt values and that every applicable `du` receives the exclusion. Add negative assertions that the old target-only grouping and `if probe.returncode != 0: continue` path are absent (`tests/test_v3_disk_inventory.py:2954-2988`).
- Extend `_run_inventory_action` with bind and unresolved-bind modes. In the extracted test copy only, replace a fixed `PROC_SELF_MOUNTINFO = "/proc/self/mountinfo"` constant with a temporary synthetic file; do not add a production environment override. Fix the `stat` stub so `%d %i` returns two tokens, and make the `du` stub fail a bind-enabled case if the expected safe exclusion is absent (`tests/test_v3_disk_inventory.py:81-106,154-177,280-420`).
- Add a fail-closed test for an ambiguous/unresolvable bind source and assert the structured alias-report reason. The ordinary no-bind fixture must continue to succeed (`tests/test_v3_disk_inventory.py:557-624,2954-2988`).
- Preserve the whole-filesystem depth-2 assertion in `test_v3_disk_inventory_scans_the_whole_filesystem_not_only_the_pg_volume`; update only its alias-helper source shape (`tests/test_v3_disk_inventory.py:649-663`).
- Preserve all global mutation negative assertions because mount discovery and `os.stat()` remain read-only (`tests/test_v3_disk_inventory.py:53-70`).

### (e) Risks and likely next review

Mountinfo must be parsed around its separator, not by fixed positions across optional fields. Btrfs subvolumes, overlayfs, multiple mounts sharing major:minor, alias chains, and aliases containing glob metacharacters are likely review targets; ambiguity must stop rather than guess. Exclusions applied only to the root scan would leave PGDATA/base totals corrupt. Canonical selection must never exclude PGDATA or the root of the scan being measured. Use `os.stat()` rather than extra `stat` subprocesses so this fix does not consume avoidable F1 non-scan budget.

## F3 — equal WAL totals do not prove stability

### (a) Correctness at the reviewed commit

The finding is correct. The action reads `pg_ls_waldir()` before and after a dedicated `pg_wal` scan, then defines stability as endpoint equality (`scripts/operator/actions/v3-disk-inventory.sh:2340-2409`). The adjacent comment correctly observes that WAL may grow and recycle between the reads, but the next comment incorrectly says equal endpoints pair the scan to one snapshot (`scripts/operator/actions/v3-disk-inventory.sh:2380-2395`). With equal endpoints, the code exposes `listed_bytes_for_candidate`, treats `directory_paired_to_one_snapshot` as true, and emits a positive `du - SQL` difference as “subdirectories and files pg_ls_waldir does not list” (`scripts/operator/actions/v3-disk-inventory.sh:2395-2410,3077-3148`). That candidate can remain in a successful receipt because only a false within-uncertainty verdict adds a failure (`scripts/operator/actions/v3-disk-inventory.sh:3390-3408,3600-3617`).

All behavioral consequences in F3 still exist. The only terminology qualification is that the current walk-to-SQL value is an absolute measurement width, not the older signed adjustment (`scripts/operator/actions/v3-disk-inventory.sh:2980-2986,3143-3148`). The rollout document repeats the invalid between-endpoints and same-instant claims (`docs/operations/v3-finder-production-rollout-state.md:490-496,505-511`).

### (b) Root cause

The design tries to infer a point-in-time fact from three sequential observations of a live, non-monotonic directory. Equality of two endpoints establishes only endpoint equality. No read-only primitive used here produces an atomic snapshot of `pg_wal`, so an aggregate cross-time/cross-instrument difference cannot safely be classified as reclaimable content (`scripts/operator/actions/v3-disk-inventory.sh:2350-2395`).

### (c) Fix

Remove behavior rather than adding another bracket:

1. Remove `WAL_DIRECTORY_SCAN_SECONDS`, the dedicated depth-0 `du_total(pg_wal)`, the second bracketing SQL read, `wal_snapshot_stable`, and the stable/unstable candidate fork (`scripts/operator/actions/v3-disk-inventory.sh:127-145,2350-2410,3077-3148`). This is the change that reduces the F1 closing reserve from 900 to 600 seconds.
2. Keep one final `pg_ls_waldir()` aggregate, move it after the last closing scan, and continue to expose `inventory.wal.bytes_at_window_close` for `accounted_bytes` (`scripts/operator/actions/v3-disk-inventory.sh:2694-2780,2874-2889`). Moving it later improves window-close ordering but must not be described as atomic.
3. Keep the required retained `pg_wal` child check, but never emit an aggregate `pg_wal` reclaim candidate (`scripts/operator/actions/v3-disk-inventory.sh:3087-3118`). Handle `pg_xlog` independently and continue reporting it whole because PostgreSQL 18's live WAL total covers only `pg_wal` (`scripts/operator/actions/v3-disk-inventory.sh:3066-3087`; `docs/operations/v3-finder-production-rollout-state.md:375-380`).
4. Remove `directory_bytes_beside_sql_read`, `listed_bytes_before_directory_scan`, `listed_bytes_after_directory_scan`, `listed_bytes_for_candidate`, `directory_paired_to_one_snapshot`, and `listed_bytes_scan_bracket_width` (`scripts/operator/actions/v3-disk-inventory.sh:2401-2410`). Add `unlisted_directory_classification: {available: false, reason: "live_wal_cannot_be_snapshotted_read_only"}`.
5. Record one direct, non-reclaimable measurement width from the closing PGDATA child's `du` figure to final SQL, for example `pg_wal_pgdata_walk_to_window_close`, rather than summing intermediate absolute widths. Leave it in `measurement_uncertainty_terms`, not `largest_unaccounted_directories` (`scripts/operator/actions/v3-disk-inventory.sh:2978-2986,3021-3054,3386-3408`).
6. Update the summary method and rollout document to stop promising separately reported `pg_wal` subdirectories or a stable bracket (`scripts/operator/actions/v3-disk-inventory.sh:3490-3544`; `docs/operations/v3-finder-production-rollout-state.md:383-389,490-496,505-511,533-544,609-618`).

### (d) Tests

- Rename/reframe `test_v3_disk_inventory_classifies_wal_only_from_one_stable_snapshot` to prove that equal endpoints never authorize aggregate classification. Remove positive assertions for the six deleted receipt fields; preserve and strengthen the negative `max(before, after)` assertion, and add negative assertions for the equality-based stability expression and old “unlisted” candidate path (`tests/test_v3_disk_inventory.py:2285-2324`).
- Rewrite `test_v3_disk_inventory_keeps_recycled_wal_out_of_candidates` to stop pinning the dedicated scan. Preserve its core negative candidate assertion and require the direct 2,000-byte non-reclaimable width between the PGDATA child and closing SQL (`tests/test_v3_disk_inventory.py:2327-2371`).
- Keep the `bytes_at_window_close == 118000` subject in `test_v3_disk_inventory_reconciles_wal_bytes_at_window_close`, but invert its current candidate assertion: there must be no `pg_wal` candidate, classification must be unavailable, and the direct width must be 2,000 (`tests/test_v3_disk_inventory.py:2901-2917`).
- Decouple `test_v3_disk_inventory_treats_pg_xlog_as_unexpected_storage` from the current two-name subtraction loop while retaining the whole-`pg_xlog` behavior and the negative requirement that live WAL bytes are never subtracted from it (`tests/test_v3_disk_inventory.py:1465-1483`). Preserve `wal_directory_not_observed_in_data_directory` in `test_v3_disk_inventory_requires_the_wal_directory_in_the_retained_children` (`tests/test_v3_disk_inventory.py:2544-2556`).
- In `test_v3_disk_inventory_carries_negative_remainders_as_uncertainty`, preserve every negative assertion, especially `if wal_unlisted > 0` being absent, and add that the `wal_unlisted` computation itself is absent. Its default term list gains `pg_wal_pgdata_walk_to_window_close` before the database metric width (`tests/test_v3_disk_inventory.py:1866-1913`).
- Remove or repurpose the fixture's `wal_recycled` switch, dedicated `du --max-depth=0 .../pg_wal` branch, and `WAL_RECYCLED` environment variable. Add controls for the final SQL WAL value and for before/after churn scenarios (`tests/test_v3_disk_inventory.py:81-106,319-323,520-546`).
- Update collateral arithmetic without changing each test's subject: `unaccounted_inside_data_directory_bytes` becomes 15,700, `candidate_shortfall_bytes` and `measurement_uncertainty_bytes` become 3,295 in the default fixture, and the df/du-residual case becomes 15,700/13,295. These values occur in `test_v3_disk_inventory_keeps_unaccounted_pgdata_directories_as_candidates`, `test_v3_disk_inventory_keeps_statistics_directories_locatable`, `test_v3_disk_inventory_names_the_post_scan_drift_instead_of_hiding_it`, and `test_v3_disk_inventory_includes_the_df_du_residual_in_the_closure` (`tests/test_v3_disk_inventory.py:859-926,1211-1235,1681-1715,1788-1822`). The base-unavailable shortfall becomes 3,995 while its null verdict remains (`tests/test_v3_disk_inventory.py:2716-2774`).
- Replace the obsolete exact arithmetic assertion in `test_v3_disk_inventory_measures_pgdata_detail_at_window_close` with the current contract that the shortfall is judged against declared uncertainty, while preserving its closing-PGDATA assertions (`tests/test_v3_disk_inventory.py:1636-1661`). Add the new unavailable-classification field to the expected receipt test (`tests/test_v3_disk_inventory.py:557-624`).
- Add ordering to `test_v3_disk_inventory_closes_the_measurement_window_last`: the single final WAL aggregate must follow both closing scans and precede summary construction (`tests/test_v3_disk_inventory.py:1370-1392`). Apply the F1 budget-test changes already listed because this removal changes three closing calls to two (`tests/test_v3_disk_inventory.py:950-1108,1432-1450`).

Every existing negative assertion in these tests records a rejected implementation and must remain, even when its surrounding positive behavior is removed (`tests/test_v3_disk_inventory.py:1866-1889,2285-2308`).

### (e) Risks and likely next review

Real `archive_status`, `summaries`, or other persistent unlisted content will no longer be offered as a location candidate; the explicit unavailable-classification receipt object is therefore required. A large direct WAL width can make the pooled uncertainty broad enough to mask an unrelated missing-directory shortfall. The likely next review will ask either for a separate WAL verdict or for `candidate_list_complete` to become false when that width is nonzero; do not respond by restoring aggregate reclaim classification. Preserve the required `pg_wal` child guard and the separate whole-`pg_xlog` candidate.

## F4 — carry the skipped WAL walk-to-scan difference

### (a) Correctness at the reviewed commit

The control-flow finding is correct, but its named field is obsolete. Let `P` be the PGDATA walk's `pg_wal` child, `D` the dedicated WAL `du`, and `A` the SQL total after that scan. When SQL endpoints differ, the branch records only `abs(D - A)` and immediately `continue`s; it skips the later `abs(P - D)` term (`scripts/operator/actions/v3-disk-inventory.sh:3119-3148`). Because no WAL candidate is emitted in that arm, the actual WAL contribution to the shortfall is `P - A`; the recorded width can be too small and can stop an otherwise ordinary churn case (`scripts/operator/actions/v3-disk-inventory.sh:3386-3408,3600-3617`).

`candidates_partition_unaccounted_at_scan` does not exist at this commit. It belonged to the abandoned exact-identity model documented at `docs/operations/v3-finder-production-rollout-state.md:585-607`. The current field is `candidates_account_for_unaccounted_within_uncertainty`, and a false value appends `candidates_do_not_account_for_unaccounted:...` (`scripts/operator/actions/v3-disk-inventory.sh:3440-3444,3600-3604`). The stop consequence remains; only the field name and exact-closure description are stale.

### (b) Root cause

The unstable arm decomposes one end-to-end discrepancy into two sequential differences but records only the second before an early `continue`. Adding both absolute widths would also be unnecessarily loose because `abs(P-D) + abs(D-A)` can exceed `abs(P-A)` (`scripts/operator/actions/v3-disk-inventory.sh:2980-2986,3119-3148`).

### (c) Fix

Fix F4 through the F3 removal: delete the stable/unstable fork and its `continue`, remove `D`, and record exactly the direct `P-A` width as `pg_wal_pgdata_walk_to_window_close`. Keep `A` as `wal_bytes_at_window_close` for headline accounting and never classify the difference as reclaimable (`scripts/operator/actions/v3-disk-inventory.sh:2874-2889,3077-3148`). This is tighter than appending both intermediate magnitudes and eliminates the branch that skipped one. If implementation retains the dedicated scan for diagnostics, both differences must be recorded before any `continue`, but that is not the preferred plan because it preserves F3's unsafe machinery.

No additional constants or receipt fields are needed beyond the F3 changes. Documentation and failure text must use the current within-uncertainty field names (`docs/operations/v3-finder-production-rollout-state.md:585-626`).

### (d) Tests

Add a dedicated churn regression in which the earlier and final SQL WAL totals differ and the PGDATA child differs as well. Assert no `pg_wal` candidate, one direct term equal to `abs(P-A)`, no `candidates_do_not_account_for_unaccounted` failure, and a successful within-uncertainty result (`tests/test_v3_disk_inventory.py:2285-2371`). This can be a new adjacent test or a second scenario in the reframed endpoint-equality test.

Preserve the existing negative assertions against `max(before, after)` and positive-only `if wal_unlisted > 0`; they record prior wrong fixes (`tests/test_v3_disk_inventory.py:1886,2304`). Preserve the recycled-WAL test's negative candidate subject (`tests/test_v3_disk_inventory.py:2327-2371`). All collateral numeric and fixture changes are the same as F3 and should be made once.

### (e) Risks and likely next review

The direct end-to-end width is correct for the two quantities on opposite sides of the current candidate arithmetic, but it still is not a reclaimable byte count. Summing both old magnitudes would inflate uncertainty, while omitting the direct term recreates the false-stop bug. The pooled-uncertainty masking risk described under F3 is the main likely follow-up.

## F5 — sort unknown slot status after retaining slots

### (a) Correctness at the reviewed commit

The finding is correct. The bounded slot query orders first by two nullable Boolean expressions using bare `DESC`, then by `restart_lsn ASC NULLS LAST` (`scripts/operator/actions/v3-disk-inventory.sh:1664-1677`). For a null `wal_status`, both Boolean expressions are null; PostgreSQL's descending default puts nulls first, so null-status slots can consume the 50-row sample before `extended` or `reserved` slots. The third key cannot repair ordering already decided by the first two. That contradicts the source and documentation promises that WAL-retaining slots survive the bound (`scripts/operator/actions/v3-disk-inventory.sh:116-120,1618-1626`; `docs/operations/v3-finder-production-rollout-state.md:408-415`).

No consequence or named field is obsolete. The visible `replication_slots` sample, `replication_slots_truncated`, and `replication_slot_sample_order` fields still exist (`scripts/operator/actions/v3-disk-inventory.sh:1755-1773`). The all-row counters and WAL byte accounting are not corrupted because they come from separate aggregate queries (`scripts/operator/actions/v3-disk-inventory.sh:1596-1603,1627-1663`).

### (b) Root cause

The query accounted for a null `restart_lsn` but not SQL three-valued logic in its two leading sort expressions (`scripts/operator/actions/v3-disk-inventory.sh:1664-1677`).

### (c) Fix

Use:

```sql
ORDER BY (wal_status = 'extended') DESC NULLS LAST,
         (wal_status = 'reserved') DESC NULLS LAST,
         pg_replication_slots.restart_lsn ASC NULLS LAST,
         slot_name
```

Explicit `NULLS LAST` is clearer than `coalesce(..., false)` and preserves the qualified `pg_lsn` sort and deterministic name tie-break (`scripts/operator/actions/v3-disk-inventory.sh:1668-1677`). Keep `REPLICATION_SLOT_INVENTORY_LIMIT = 50`, the all-row counts, truncation flag, and existing `replication_slot_sample_order`; no receipt schema change is required (`scripts/operator/actions/v3-disk-inventory.sh:116-120,1627-1663,1755-1773`). Update the rollout explanation to say unknown statuses sort after known retaining and non-retaining states (`docs/operations/v3-finder-production-rollout-state.md:408-415`). This fix preserves rather than removes the bounded-sample behavior.

### (d) Tests

Update `test_v3_disk_inventory_bounds_replication_slots_by_wal_actually_retained` so its literal ORDER BY assertion requires `DESC NULLS LAST` on both leading expressions. Preserve the qualified `pg_replication_slots.restart_lsn ASC NULLS LAST`, the 50-row limit, the count query, the receipt assertions, and the negative `AS wal_pinning_slots` assertion (`tests/test_v3_disk_inventory.py:2573-2617`). Add negative assertions that both old bare-`DESC` fragments are absent. Strengthen the fixture so the slot query is rejected unless both clauses exist, or add a disposable PostgreSQL ordering case with more than 50 null-status rows and retained rows; the retained rows must be selected first.

### (e) Risks and likely next review

When more than 50 retaining slots exist, lower-priority details still truncate; that is intended and disclosed by `replication_slots_truncated` (`scripts/operator/actions/v3-disk-inventory.sh:1771-1773`). A reviewer may request per-status aggregate counts for null or `unreserved` states, because the current aggregate counts retaining, extended, and lost but not every status (`scripts/operator/actions/v3-disk-inventory.sh:1627-1663`). Do not claim that `restart_lsn` is an exact retained-byte measure; it remains only the oldest-first tie-break within status priority.

## F6 — disclose root-scan truncation and remove the completeness claim

### (a) Correctness at the reviewed commit

The finding is correct. `DU_DEFAULT_KEEP` is 4,000, the root depth-2 scan calls `du_rows()`, and `du_rows()` discards the omitted count and omitted record-byte total returned by `du_stream()` (`scripts/operator/actions/v3-disk-inventory.sh:169-172,739-770,887-954,1351-1364`). `exclusive_usage()` then partitions only retained rows, assigning an omitted descendant's bytes to its nearest retained ancestor (`scripts/operator/actions/v3-disk-inventory.sh:380-412`). The receipt retains only 40 root rows and has no root-cap metadata (`scripts/operator/actions/v3-disk-inventory.sh:1408-1410`). Later `candidate_count` and `candidates_omitted*` describe only the already-reduced candidate list, so they do not disclose root-stream omissions (`scripts/operator/actions/v3-disk-inventory.sh:3480-3489`). `candidate_list_complete` currently depends only on the base breakdown and can therefore be true after root truncation (`scripts/operator/actions/v3-disk-inventory.sh:3395-3408`).

The review's exact-closure phrasing is obsolete: the action now exposes a within-uncertainty verdict rather than `candidates_partition_unaccounted_at_scan` (`scripts/operator/actions/v3-disk-inventory.sh:3390-3444`; `docs/operations/v3-finder-production-rollout-state.md:585-626`). The substantive issue remains because the receipt still calls the retained rows a non-overlapping location partition and can mark the list complete without revealing that path attribution was capped (`scripts/operator/actions/v3-disk-inventory.sh:3490-3508`; `docs/operations/v3-finder-production-rollout-state.md:350-360,580-584`).

### (b) Root cause

`du_rows()` is appropriate only where omission metadata is irrelevant. It is used at the one call site where omissions change the truth of the receipt's path-completeness claim (`scripts/operator/actions/v3-disk-inventory.sh:948-954,1351-1364`). Unlike a depth-1 list of immediate children, omitted depth-2 `du` rows can contain both an ancestor and its descendant, so the returned omitted byte sum is a cumulative diagnostic and can double-count physical bytes (`scripts/operator/actions/v3-disk-inventory.sh:380-412,739-770`).

### (c) Fix

Replace only the root `du_rows()` call with direct `du_stream(..., keep=DU_DEFAULT_KEEP, expect_path=usage_root)` unpacking; do not add a second scan and do not remove the cap (`scripts/operator/actions/v3-disk-inventory.sh:1351-1364`). Add a sibling receipt object, leaving the existing list-shaped `volume_directory_usage` compatible:

```json
"volume_directory_usage_scan": {
  "record_limit": 4000,
  "records_retained": 4000,
  "records_omitted_by_cap": 17,
  "omitted_record_cumulative_bytes": 123,
  "omitted_record_bytes_may_overlap": true,
  "path_attribution_complete": false
}
```

The values above are illustrative; the field semantics are the planned contract. Never append `omitted_record_cumulative_bytes` as a candidate or uncertainty because nested totals overlap and the bytes already remain inside a retained ancestor (`scripts/operator/actions/v3-disk-inventory.sh:380-412`). Preserve `exclusive_usage()` so numerical coverage remains non-overlapping across retained rows, but compute `candidate_list_complete = bool(base_breakdown_used) and root_rows_omitted == 0`, add `candidate_list_incomplete_reasons`, and set `candidates_account_for_unaccounted_within_uncertainty` to null on root truncation through the existing incomplete-list path (`scripts/operator/actions/v3-disk-inventory.sh:3395-3408`). Add `directory_scan_path_attribution_complete` to the summary and state that retained ancestor ownership is not proven when false.

Update the method text and rollout document to distinguish complete byte coverage from complete path enumeration. The current row-cap rule mentions PGDATA and `base/` only; add the depth-2 rule and the overlapping-byte warning (`docs/operations/v3-finder-production-rollout-state.md:391-428,446-465,580-584`). This fix removes an overclaim rather than increasing memory or manufacturing an aggregate candidate.

### (d) Tests

- Add zero-omission metadata assertions to `test_v3_disk_inventory_emits_expected_read_only_receipt`, `test_v3_disk_inventory_candidates_are_a_non_overlapping_partition`, and `test_v3_disk_inventory_keeps_unaccounted_pgdata_directories_as_candidates`; retain all existing list/path and arithmetic assertions in the untruncated fixture (`tests/test_v3_disk_inventory.py:557-624,683-731,859-926`).
- Extend `test_v3_disk_inventory_bounds_each_drill_down_child_listing` to assert that the root call unpacks all three `du_stream` results and no longer calls `du_rows()`. Preserve every negative pipeline assertion (`| sort -z`, `head -z`, and nested `bash`) and the process-group timeout assertions (`tests/test_v3_disk_inventory.py:1564-1590`).
- Preserve `test_v3_disk_inventory_top_k_keeps_the_largest_and_totals_the_rest` unchanged: its sum concerns stream records, not unique physical bytes (`tests/test_v3_disk_inventory.py:1593-1622`).
- Preserve the nearest-retained-ancestor behavior and its negative immediate-parent assertion in `test_v3_disk_inventory_partitions_across_a_row_cap_ancestor_gap`; add a separate assertion that numerical partitioning does not imply path completeness (`tests/test_v3_disk_inventory.py:1916-1949`).
- Update the literal `candidate_list_complete = bool(base_breakdown_used)` assertion in `test_v3_disk_inventory_emits_no_base_candidate_without_the_breakdown` to require the root-untruncated conjunction. Preserve every base failure, OID completeness, null-verdict, and negative candidate assertion (`tests/test_v3_disk_inventory.py:2716-2774`).
- Preserve `test_v3_disk_inventory_reports_candidates_hidden_by_the_display_limit` unchanged because the top-10 display cap is distinct from the root scan cap (`tests/test_v3_disk_inventory.py:1522-1532`). Preserve list-shape assertions in tablespace and WAL refusal tests by adding a sibling metadata object rather than changing `volume_directory_usage` (`tests/test_v3_disk_inventory.py:1253-1277,1535-1552`). Preserve the PGDATA/base omitted-entry aggregate behavior and its negative stale-label assertion because those depth-1 rows do not overlap (`tests/test_v3_disk_inventory.py:1764-1785`).
- Add a fixture option that emits more than 4,000 depth-2 root records and a regression test asserting the exact omitted-record count, cumulative diagnostic, overlap warning, false path-completeness fields, `candidate_list_complete is False`, and a null within-uncertainty verdict. Assert that no candidate or uncertainty equals the cumulative omitted-byte sum.

### (e) Risks and likely next review

The most likely wrong fix is to add the omitted cumulative byte sum as a candidate or uncertainty, double-counting nested `du` records. Changing `volume_directory_usage` from a list to an object would break existing consumers and refusal tests. Increasing or removing the cap restores unbounded memory. A second root scan would consume F1's budget without making a live tree atomic. A reviewer may prefer a stopped status instead of a successful receipt with a null verdict; the planned behavior follows the existing honest-incompleteness model used when the optional base breakdown is unavailable (`scripts/operator/actions/v3-disk-inventory.sh:3395-3408`; `tests/test_v3_disk_inventory.py:2751-2770`).

## Shared causes, implementation order, and interactions

The six findings share a broad design failure: a local or bounded observation is promoted to a global completeness claim. F1 treats a scan-local reserve as global time; F2 treats mount-target enumeration as alias enumeration; F3/F4 treat sequential WAL readings as a snapshot; F5 treats nullable Boolean ordering as total ordering; and F6 treats retained top-k rows as complete path attribution (`scripts/operator/actions/v3-disk-inventory.sh:477-533,647-716,948-954,1664-1677,2380-2410,3119-3148,3395-3408`). F3 and F4 specifically have one root cause and must be fixed as one removal.

Apply the changes in this order:

1. Remove the F3/F4 WAL scan/classification and install the direct PGDATA-to-final-SQL width. This removes one scan and one SQL endpoint read, fixes both WAL arms, and determines the later budget arithmetic (`scripts/operator/actions/v3-disk-inventory.sh:2350-2410,3077-3148`).
2. Rebuild F1's phase ledgers around two closing scans: 960 walk, 600 closing, 240 non-scan/SQL/receipt (`scripts/operator/actions/v3-disk-inventory.sh:53-75,121-162,647-716`).
3. Implement F2 before any scan begins and propagate one alias plan through all scan builders. Use `os.stat()` so alias verification consumes Python/non-scan time but adds no subprocess (`scripts/operator/actions/v3-disk-inventory.sh:1309-1364`).
4. Implement F6 by retaining omission metadata from the existing root stream. It adds no scan and therefore consumes no extra scan allowance (`scripts/operator/actions/v3-disk-inventory.sh:739-770,1351-1364`). Alias exclusion happens first, so the truncation metadata describes the deduplicated stream.
5. Apply F5's independent SQL ordering correction; it adds no query and has no timing interaction (`scripts/operator/actions/v3-disk-inventory.sh:1664-1677`).
6. Update the rollout document only after the code/receipt contract is settled: timing at `docs/operations/v3-finder-production-rollout-state.md:467-476,575-579`, WAL at `:383-389,490-511,533-544,585-618`, slot ordering at `:408-415`, and truncation at `:391-428,580-584`.
7. Update the shared fixture once, then the affected literal-source and behavioral tests. Preserve every negative assertion identified above; tests that record old wrong implementations are part of the safety contract (`tests/test_v3_disk_inventory.py:53-70,1574-1587,1781-1785,1884-1889,1938-1947,2303-2308,2573-2617`).

F3/F4 frees 300 seconds and raises the corrected walk allocation from 660 seconds to 960 seconds. F2 adds bounded parsing and `os.stat()` work to the 240-second non-scan bucket. F6 reuses metadata already calculated by `du_stream()` and adds no subprocess. F5 changes only ORDER BY text. F2's canonical-path rule must preserve the configured PGDATA path so the F3 required-WAL-child guard and both remaining closing scans still observe the intended tree (`scripts/operator/actions/v3-disk-inventory.sh:1309-1316,2470-2479,3087-3118`).

## Final time-budget check after the planned fixes

The action-level allocation is:

| Phase | Guaranteed ceiling/reserve | Derivation |
|---|---:|---|
| Pre-closing directory scans, including retries and drill-down | 960 s maximum | `1,800 - 600 - 240`; replaces the current impossible 1,200-second allowance (`scripts/operator/actions/v3-disk-inventory.sh:53-75,121-162`) |
| Closing PGDATA depth-1 scan | 300 s allowance | Existing per-scan limit (`scripts/operator/actions/v3-disk-inventory.sh:75,2295-2323`) |
| Closing `base/` depth-1 scan | 300 s allowance | Existing per-scan limit (`scripts/operator/actions/v3-disk-inventory.sh:75,2491-2505`) |
| All non-scan work, SQL, Python bookkeeping, and receipt emission | 240 s aggregate maximum | Renamed and enforced form of the current reserve (`scripts/operator/actions/v3-disk-inventory.sh:68-74,202-235`) |
| Total action wall time | 1,800 s | `960 + 300 + 300 + 240` |

There is no dedicated closing WAL scan after F3/F4; the final WAL SQL aggregate is charged to the 240-second non-scan bucket. Each remaining scan keeps its full 300-second allowance so long as its own work stays within that allowance and the non-scan category stays within 240 seconds; category ledgers prevent one category from spending another's reserve. Exceeding a category stops fail-closed while preserving the global 1,800-second ceiling.

The workflow job ceiling is 2,400 seconds (`.github/workflows/chatgpt-ed-new-ops.yml:39-45`), so the action's nominal margin is 600 seconds. **Assumption:** checkout, Python setup, SSH preparation, and connection complete in less than 600 seconds; the workflow does not impose a separate ten-minute pre-action deadline (`.github/workflows/chatgpt-ed-new-ops.yml:47-124,177-197`). Therefore the code can guarantee no more than 1,800 seconds from action-process start; it cannot by itself guarantee 600 seconds of remaining job time. The implementation and documentation must state that assumption rather than claim the workflow can never kill the receipt.

## Planned validation

Run `bash -n scripts/operator/actions/v3-disk-inventory.sh`, then all 88 tests in `tests/test_v3_disk_inventory.py` under the repository's CPython 3.14 lane. Add focused synthetic cases for a resolvable bind, an unresolved bind, equal WAL endpoints with transient growth, differing WAL endpoints with a different PGDATA walk value, more than 50 null-status replication slots, root-stream truncation above 4,000 records, non-scan time near 240 seconds, and both closing scans near 300 seconds. No test may contact production; the existing fixture executes the embedded program against fake `docker`, `psql`, `df`, `du`, and host commands (`tests/test_v3_disk_inventory.py:81-554`).
