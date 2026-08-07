# Adversarial backend code review — 2026-06

**Scope:** FastAPI / importer / EDDN / maintenance backend of `ed-finder`.
**Audited ref:** `origin/main` @ `0472f86` ("Record verified status on bodies composite-identity migration plan (#428)"), inspected in a clean detached worktree.
**Mandate:** hostile, evidence-based. **Report only — no fixes applied.** Findings grouped by category, each with `file:line`, a one-sentence summary, a concrete failure scenario, literal evidence, and a verdict.

**Verdict legend**
- **CONFIRMED** — the cited code provably exhibits the described behaviour.
- **PLAUSIBLE** — the code exhibits the pattern, but whether it is a defect depends on runtime data or design intent that static analysis cannot fully settle.
- **REMEDIATED** — a previously-reported bug that is no longer present on this ref (recorded for honesty / recurrence tracking).

---

## Part A — Original 10-item catalogue: recurrence check

### A1. `bodies.id` UPSERT re-parenting (wrong uniqueness scope) — **REMEDIATED**

Both live writers now guard the `ON CONFLICT (id) DO UPDATE` with an owner check, so a colliding source `BodyID` from a different system is a no-op instead of a silent re-parent.

- `apps/eddn/src/eddn_listener.py:953-980` — the `DO UPDATE` is gated by an owner guard:
  ```
  953:  ON CONFLICT (id) DO UPDATE SET
  954:      system_id64       = EXCLUDED.system_id64,
  ...
  979:  WHERE
  980:      bodies.system_id64 = EXCLUDED.system_id64
  ```
- `apps/importer/src/import_spansh.py:461-481, 951-959` — `upsert_via_temp(..., guard_col='system_id64', returning_col='id')` builds `WHERE {target}.system_id64 = EXCLUDED.system_id64` and returns rejected owners so dependent ring rows are dropped (`flush_bodies` / `flush_rings`).
- Only other `INSERT INTO bodies` is `scripts/dev/review_environment_seed.py:232` (dev seed, not a production path).

**Residual note (PLAUSIBLE):** when the guard rejects a collision, the row from the second owner is silently discarded (no INSERT, no UPDATE). That is the intended "no-op instead of re-parent" behaviour, but it is a genuine silent drop — there is no counter/log in `eddn_listener.py` for bodies rejected this way (the importer does count ring skips, but not body rejections themselves beyond the derived ring skip).

---

### A2. `body_rings.association_status` drift from Spansh importer — **PRESENT (by-design, but fragile)**

- `apps/importer/src/import_spansh.py:632`
- **Summary:** the Spansh importer stamps every ring row `association_status = 'local_matched'` in Python rather than deriving it from the shared CASE logic used by the EDDN path.
- **Failure scenario:** if the local-ownership guarantee in `flush_rings()` is ever weakened (e.g. a future refactor stops filtering `ring_batch` against `rejected_body_ids`), every Spansh ring silently asserts a verified local match with no SQL-level check — untrusted rings promoted as trusted.
- **Evidence:**
  ```
  632:            row['association_status'] = 'local_matched'
  ```
  The surrounding comment (lines 620-632) documents that this is deliberate and relies on `flush_rings()` filtering rejected bodies first. The value is now explicit (auditable) rather than falling through to the schema default — an improvement over the original finding — but it is a hand-maintained constant that must stay in lock-step with the guard logic two functions away.
- **Verdict:** PLAUSIBLE. Correct today given the flush ordering; brittle because correctness lives in a comment, not in a constraint.

---

### A3. Dead code: `run_eddn_simulation_ingest` / the entire `ingest/eddn_client.py` ingest loop — **CONFIRMED**

- `apps/api/src/ingest/eddn_client.py:139` (and helpers `_run_ingest_loop`, `_flush_batch`, `BODY_RING_UPSERT_SQL`, `_resolve_eddn_ring_rows`, `_mark_dirty_systems_incremental`, `_ring_row_tuple`)
- **Summary:** the module's async entry point has no caller anywhere in the codebase — its only "call" is inside its own docstring.
- **Failure scenario:** the file's docstring claims it "handles ONLY the simulation-relevant event types … They can run side-by-side" with the real listener, implying it is running and writing `journal_events` / `body_scan_facts`. It is not wired into the FastAPI lifespan, so any operator trusting that docstring believes an ingest path exists that does nothing. It also carries a *third* copy of the ring-association CASE SQL that will silently diverge (see B2).
- **Evidence:**
  ```
  $ grep -rn "run_eddn_simulation_ingest" --include=*.py .
  ./apps/api/src/ingest/eddn_client.py:139:async def run_eddn_simulation_ingest(pool: 'asyncpg.Pool') -> None:
  ./apps/api/src/ingest/eddn_client.py:142:        asyncio.create_task(run_eddn_simulation_ingest(pool))   # <-- inside the docstring

  $ grep -n "create_task" apps/api/src/main.py
  200:        _sse_pubsub_task = asyncio.create_task(eddn_pubsub_bridge())   # only background task started
  ```
  The only other textual reference is a string literal in a provenance catalogue: `apps/api/src/evidence_store/source_catalog.py:48`.
- **Verdict:** CONFIRMED dead code.

---

### A4. `deploy_main.sh` applies migrations without `--include-manual` — **CONFIRMED (behaviour); PLAUSIBLE (defect)**

- `scripts/deploy_main.sh:131`
- **Summary:** the production deploy runs `apply_migrations.sh` with no `--include-manual`, so every migration marked `manual` in the manifest is skipped while the deploy still reports success.
- **Failure scenario:** `sql/migration-manifest.txt` marks `041_bodies_composite_identity_index.sql|manual` — the index that backs the very composite-identity work this ref's HEAD commit is about. A production `deploy_main.sh` run never applies it, prints `[INFO] skipping manual migration 041_...`, then `[OK] migrations applied`, and the deploy is declared complete. A reader of the top-level deploy log sees success with no obvious signal that a schema object is missing.
- **Evidence:**
  ```
  # scripts/deploy_main.sh
  130:  [[ -f scripts/apply_migrations.sh ]] || die "migration applier not found: scripts/apply_migrations.sh"
  131:  bash scripts/apply_migrations.sh          # <-- no --include-manual
  132:  ok "migrations applied"

  # contrast: scripts/seed_check.sh DOES pass it
  35:  DATABASE_URL="$DB_URL" bash "$(dirname "$0")/apply_migrations.sh" --include-manual

  # apply_migrations.sh silently skips manual entries when the flag is absent
  245:  if [[ "$mode" == "manual" && "$INCLUDE_MANUAL" -ne 1 ]]; then
  246:    printf '[INFO] skipping manual migration %s\n' "$filename"
  247:    skipped_count=$((skipped_count + 1))
  248:    continue

  # manifest manual entries
  33:  019_nullable_coords.sql|manual
  55:  041_bodies_composite_identity_index.sql|manual
  ```
- **Verdict:** PLAUSIBLE. Manual gating may be intentional (`019` and `041` are already recorded as applied in production per `CLAUDE.md`), but the deploy wrapper's `ok "migrations applied"` overstates what ran — a manual migration added in the future ships "green" and unapplied.

---

### A5. Environment variables read in code but documented nowhere — **CONFIRMED**

- `env.example` (and `docker-compose.yml`)
- **Summary:** several env vars are consumed by backend code but appear in neither `env.example` nor `docker-compose.yml`, so an operator provisioning from the documented surface silently gets defaults.
- **Failure scenario:** `CLUSTER_RADIUS_LY` / `MAX_SEARCH_RADIUS_LY` / `CELL_SIZE` change clustering and search-radius behaviour; `INARA_API_KEY` gates the Inara integration; `DB_DSN_DIRECT` overrides the pgBouncer-bypass DSN used by the importer. None are discoverable from `env.example`, so tuning/enabling them requires reading source.
- **Evidence** (each is `env.example=0 compose=0`):
  ```
  CLUSTER_RADIUS_LY            env.example=0 compose=0
  MAX_SEARCH_RADIUS_LY         env.example=0 compose=0
  CELL_SIZE                    env.example=0 compose=0
  INARA_API_KEY                env.example=0 compose=0
  INARA_APP_NAME               env.example=0 compose=0
  INARA_APP_VERSION            env.example=0 compose=0
  REGION_MAP_JSON              env.example=0 compose=0
  DB_DSN_DIRECT                env.example=0 compose=0
  DIRTY_CLEANUP_CHUNK_SIZE     env.example=0 compose=0
  ```
- **Scope correction vs. the original finding:** `REDIS_URL`, `DATABASE_URL`, `DUMP_DIR`, `BATCH_SIZE`, and `LOG_FILE` ARE documented — they are set in `docker-compose.yml` (lines 181-183, 239-240, 282-284, 384-390), just not in `env.example`. They are therefore **not** undocumented; only the list above is.
- **Verdict:** CONFIRMED for the listed vars.

---

### A6. Silent exception swallowing — **CONFIRMED (representative instances)**

- **Summary:** multiple `except … : pass` / broad `except` sites discard errors with no signal.
- **Concrete instances:**
  - `apps/importer/src/import_spansh.py:245-248` — a failed checkpoint save during a multi-hour import is swallowed:
    ```
    1245:  try:
    1246:      save_checkpoint(conn, dump_path.name, 0, total_rows + resume_offset, f_raw.tell())
    1247:  except Exception:
    1248:      pass
    ```
    **Scenario:** if the periodic checkpoint write fails (e.g. transient DB error), the importer keeps going with no log; a later crash resumes from a stale offset and re-imports millions of rows.
  - `apps/importer/src/import_spansh.py:235-247` — `increment_error_count` wraps its whole body in `except Exception: pass`, so the `errors_encountered` health counter the API surfaces can silently stop advancing.
  - `apps/api/src/ingest/eddn_client.py:188` — `except (asyncio.TimeoutError, Exception): break` treats *every* exception as a socket timeout (see B3).
- **Verdict:** CONFIRMED. Many other `except (TypeError, ValueError)` sites are narrow and legitimate; the ones above are broad and lossy. (Impact of the two importer sites is telemetry/restart-cost, not data corruption.)

---

## Part B — Broader hunt (beyond the 10-item catalogue)

### B1. `enrich_system_data.py` omits `association_status` on its `body_rings` INSERT — **CONFIRMED (fact); PLAUSIBLE (impact)**

- `apps/importer/src/enrich_system_data.py:569-585`
- **Summary:** this ring writer inserts without the `association_status` column and never updates it on conflict, so it relies entirely on the `NOT NULL DEFAULT 'local_matched'` schema default — the exact hazard documented in `CLAUDE.md` ("Any INSERT that omits the column silently asserts a verified local match").
- **Failure scenario:** the schema default is what makes these rows `local_matched`. It is currently correct because `build_ring_plan` only emits rows for bodies matched exactly via `match_local_body`. But the claim ("this ring is a verified local match") is asserted by a DDL default that no reader of this file can see, and if a future change lets an unmatched body's ring reach this INSERT, it is silently promoted as trusted.
- **Evidence:**
  ```
  569:  INSERT INTO body_rings (
  570:      system_id64, body_id, body_name,
  571:      ring_name, ring_type, ring_class,
  572:      mass_mt, inner_radius, outer_radius,
  573:      source, confidence, updated_at          -- no association_status
  574:  ) VALUES ( %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW() )
  577:  ON CONFLICT (system_id64, body_id, ring_name, source) DO UPDATE SET
  ...                                              -- association_status never set here either
  ```
  This is now the **only** live writer that omits the column (the importer `import_spansh.py`, the EDDN listener, and `journal_import/store.py` all name it explicitly), so `CLAUDE.md`'s "two of five writers omit it" has become one of five.
- **Verdict:** CONFIRMED omission; PLAUSIBLE data risk (safe today, brittle).

---

### B2. `BODY_RING_ASSOCIATION_STATUS_CASE_SQL` defined three times with no shared module — **CONFIRMED**

- `apps/eddn/src/eddn_listener.py:81`, `apps/api/src/journal_import/store.py:34`, `apps/api/src/ingest/eddn_client.py:48`
- **Summary:** the load-bearing ring-association CASE SQL is copy-pasted into three files (two live, one dead per A3); changing one does not change the others.
- **Failure scenario:** the three copies are byte-identical today. A future correctness fix to the belt/`local_matched`/`unresolved_body_identity` logic applied to the EDDN listener but not to `journal_import/store.py` produces two different association verdicts for the same physical ring depending on ingest path — invisible in review because both files still "have the CASE".
- **Evidence:**
  ```
  $ grep -rn "BODY_RING_ASSOCIATION_STATUS_CASE_SQL =" --include=*.py apps
  apps/eddn/src/eddn_listener.py:81:BODY_RING_ASSOCIATION_STATUS_CASE_SQL = """
  apps/api/src/journal_import/store.py:34:BODY_RING_ASSOCIATION_STATUS_CASE_SQL = """
  apps/api/src/ingest/eddn_client.py:48:BODY_RING_ASSOCIATION_STATUS_CASE_SQL = """
  ```
  Diff of the three blocks: identical CASE bodies (verified). `CLAUDE.md` already lists this as a known hazard; it persists on this ref.
- **Verdict:** CONFIRMED DRY / silent-divergence hazard.

---

### B3. `eddn_client.py` catches all exceptions as if they were timeouts — **CONFIRMED (in dead module)**

- `apps/api/src/ingest/eddn_client.py:186-190`
- **Summary:** `except (asyncio.TimeoutError, Exception): break` is redundant (`Exception` already covers `TimeoutError`) and, more importantly, treats any receive-side error as a benign timeout and quietly reconnects.
- **Failure scenario:** were this module ever wired in (it is currently dead — A3), a persistent decode/library error in the receive path would loop "timeout → reconnect" forever with no error surfaced, looking healthy while ingesting nothing.
- **Evidence:**
  ```
  186:  try:
  187:      raw = await asyncio.wait_for(socket.recv(), timeout=35.0)
  188:  except (asyncio.TimeoutError, Exception):
  189:      # Timeout or ZMQ error — flush what we have and reconnect
  190:      break
  ```
- **Verdict:** CONFIRMED pattern; impact gated by the module being dead.

---

### B4. `apply_ringed_scan_facts` is inert — it always skips, never applies — **CONFIRMED**

- `apps/importer/src/enrich_system_data.py:603-628`
- **Summary:** a function named `apply_ringed_scan_facts` never appends to its `applied` list under any input; every row is routed to `skipped`, so it writes nothing.
- **Failure scenario:** callers merge `scan_fact_applied` into the run report and summary (`_merge_ring_report`, `_finalise_report`), so `scan_fact_applied` is structurally always `0`. Anyone reading the enrichment report to confirm scan-fact writes will always see zero and cannot distinguish "correctly skipped by design" from "silently broken".
- **Evidence:**
  ```
  611:  applied: list[dict[str, Any]] = []
  ...
  621:  for (system_id64, body_id), row in facts.items():
  622:      skipped.append({ ... 'reason': _scan_fact_skip_reason(body_id) })
  628:  return applied, skipped        # `applied` is never appended to
  ```
  The docstring explains the intent (source `BodyID` vs `bodies.id` identity mismatch), so this is deliberate — but the function and its report field are dead weight that read as a live write path.
- **Verdict:** CONFIRMED inert path.

---

### B5. `build_archetype_scores.py` hidden `limit or 10_000_000` fallback — **CONFIRMED (latent, mitigated)**

- `apps/importer/src/build_archetype_scores.py:1249,1253,1262`
- **Summary:** when `--limit` is falsy, three queries silently cap at 10,000,000 rows.
- **Failure scenario:** an operator running the new-system scorer manually without `--limit` believes they are processing the full backlog; they silently process at most 10M rows and the rest stay unscored with no warning. Also note `limit or 10_000_000` treats `--limit 0` as "10M", not "zero".
- **Evidence:**
  ```
  1249:  """, (limit or 10_000_000,))
  1253:  """, (limit or 10_000_000,))
  1262:  """, (limit or 10_000_000,))
  ```
  Mitigation in the scheduled path: `scripts/nightly_update.sh:369` passes `--limit 5000000` explicitly and its comment (lines 354-355) calls out this exact trap — so the nightly job is safe; the hazard is for ad-hoc/manual invocation.
- **Verdict:** CONFIRMED latent footgun (documented but not defended in-code).

---

## Summary table

| # | Category | Location | Verdict |
|---|----------|----------|---------|
| A1 | UPSERT uniqueness / re-parenting | `eddn_listener.py:980`, `import_spansh.py:461-481` | REMEDIATED (silent-drop residual: PLAUSIBLE) |
| A2 | association_status drift (Spansh) | `import_spansh.py:632` | PLAUSIBLE (by-design, fragile) |
| A3 | Dead code (ingest loop) | `ingest/eddn_client.py:139` | CONFIRMED |
| A4 | Deploy skips manual migrations | `deploy_main.sh:131` | CONFIRMED behaviour / PLAUSIBLE defect |
| A5 | Undocumented env vars | `env.example` | CONFIRMED (narrowed list) |
| A6 | Silent exception swallowing | `import_spansh.py:1247,246`; `eddn_client.py:188` | CONFIRMED |
| B1 | Ring writer omits association_status | `enrich_system_data.py:569` | CONFIRMED fact / PLAUSIBLE impact |
| B2 | CASE SQL copy-pasted x3 | `eddn_listener.py:81`, `journal_import/store.py:34`, `eddn_client.py:48` | CONFIRMED |
| B3 | Catch-all-as-timeout | `eddn_client.py:188` | CONFIRMED (dead module) |
| B4 | Inert `apply_ringed_scan_facts` | `enrich_system_data.py:603` | CONFIRMED |
| B5 | Hidden `limit or 10_000_000` | `build_archetype_scores.py:1249` | CONFIRMED (mitigated in nightly) |

**Method note:** all evidence gathered by `grep`/file read against a detached worktree at `origin/main@0472f86`. No code was modified. `CLAUDE.md`'s "Known hazards" and "Debugging data drift" sections corroborate A1/A2/B1/B2; where this ref has since remediated a hazard (A1), that is stated explicitly rather than re-reported as open.
