> Read-only study, 2026-10-21.
> Evidence, not execution authority.

# EDDN and Spansh station data in V3 production: what is true now and the smallest safe plan

Scoping written 2026-10-21. This is read-only work: no branches, commits, PRs or production access.
Repo state read: `main` at `c396eb21` (F4b prerequisites, #871).

---

## Plain-language summary

**What is true now**

1. V3 production runs **no EDDN listener of any kind**. The finding is confirmed (section A1).
2. V3 production runs **no Spansh refresh of any kind** either. The V2 nightly script drove the old
   V2 Docker stack, and that stack has been decommissioned (section C1).
3. V3's galaxy data (systems, bodies, stations) is therefore a **frozen snapshot**. It is the
   canonical import built on 2026-08-27 and published on 2026-08-28. Everything built on top of it
   is frozen too: ratings, search, archetypes and the Finder. V3's canonical tables have **no
   colonisation or population columns at all**, so there are no "colonisation flags" that could
   be going stale. V3 simply does not model colonisation state in its canonical data.
4. V3 has **no mechanism to bring in new galaxy data**. Canonical data is a set of immutable
   snapshots ("generations"). A refresh would mean building a whole new generation (about 600 GB)
   and then rebuilding every derived product. No document, workflow or action does that today.

**Smallest safe version.** Do not touch canonical data. Add a small, separate **station observation
store**: a new database schema created by one additive migration. It holds two kinds of evidence:

- **Spansh `galaxy_stations.json.gz`**, loaded by a one-shot job. This gives a whole-galaxy
  baseline of every station's type, economies with proportions, services and, where Spansh has
  it, the body the station belongs to.
- **EDDN `Docked` events**, collected by a small long-running worker. This gives live
  change-over-time evidence.

Both write **only** to the new schema. Both store a row **only when a station's state changes**,
so the store stays tiny. Neither stores uploader IDs.

**Order: do Spansh first, then EDDN.** Spansh is a one-shot job that fits the existing operator
pattern. It needs no change to the deploy tool and no new long-running service, and it brings
body association, which EDDN `Docked` events do not carry. EDDN comes second because it needs a new
service in the production deploy authority and changes to the deployer.

**How many steps.** There are 11 repo-only steps (R1–R11) and 7 production steps (P1–P7).
**Every production step needs your explicit go.**

**Timing**

- Nothing that touches frozen files is done before the Finder go-live (step 9′, 2026-10-22).
  The repo-only steps R1–R6 are safe now because they touch no frozen file.
- **Nothing in production runs while the governed purge (step P) is running.** The new writers
  would make the purge stop. You need to decide whether the observation work goes before or
  after P (decision D2).

---

## Part A: EDDN in V3 today

### A1. The finding: confirmed

The evidence:

- **Only the app slots exist.** `deploy/v3-production/compose.yml:3-6` says the compose file
  "deliberately owns two blue/green application slots and nothing else". The services at `:52-77`
  are exactly `api-blue`, `web-blue`, `api-green` and `web-green`.
- **Background writes are switched off.** `compose.yml:14-18` sets
  `EDDN_SIMULATION_INGEST_ENABLED: "false"` and `ADMIN_OPERATION_STARTUP_REAP_ENABLED: "false"`.
  The comment there says these "remain disabled after cutover until a separate reviewed worker
  authority explicitly owns them". The runbook repeats this:
  `docs/operations/v3-production-application-release.md:216-218`.
- **The deployer refuses anything extra.** `scripts/operator/v3_production_deploy.py:61-66`
  hard-codes `SERVICES` as api/web × blue/green. `:482-487` refuses any other service allowlist.
  `:1234-1240` refuses a rendered compose file with any other service. The target authority pins
  the same four services and containers: `deploy/v3-production/target-authority.json:94-105`.
- **Nothing else can reach the database network.** The database is reached over the external
  application network. Its allowlist (`target-authority.json:153-160`) names only the PostgreSQL
  container and the derived-build workers. The deployer fails a promotion if any unlisted container
  is attached (`v3_production_deploy.py:1043-1053`). No EDDN container is listed.
- **No receipt shows an EDDN container.** The latest accepted promotion receipt
  (`docs/operations/evidence/2026-10-19-v3-production-promotion-receipt-run-39228589346.json`)
  names only the app slots, PostgreSQL, the edge, Redis and NATS.
- **The V2 listener is not part of any V3 release.** `apps/eddn/` (Dockerfile, `eddn_listener.py`)
  is never built by the V3 release workflow, which builds only `apps/api/Dockerfile.release` and
  `apps/web/Dockerfile` (`.github/workflows/v3-application-release.yml:178-179, 214-215`).
  Infrastructure status says Hetzner/V2 containers are "historical only"
  (`docs/operations/infrastructure-status.md:38-40`).
- **No V3 EDDN worker exists or has been designed.** The target is locked:
  `docs/development/v3-application-stack-decision.md:115` says "EDDN | **One dedicated EDDN worker
  service**", and `:118` says to fold the simulation ingest into it and remove ingest from the API
  lifespan. `:226` forbids "duplicated EDDN consumers". No branch, commit or design doc implements
  it. A local branch `feat/journal-colonisation-and-station-observations` exists, but it sits at
  `main` with no changes; it is the sibling journal-import task, not an EDDN worker.

**Limit of this check.** It is based on repo evidence only. A live `docker ps` was not run.
The read-only `v3-app-status` or `v3-disk-inventory` operation would confirm it, if you want that.

**A note on CLAUDE.md.** CLAUDE.md's "Named runtime exception" (`CLAUDE.md:79+`) says the ingest
"default[s] on". That is true of the code default (`apps/api/src/main.py:227-228`), but production
compose overrides it to off. The ingest is also unusable in V3 as written. It writes the V2
relations `journal_events`, `body_scan_facts` and `body_rings`, and it runs
`UPDATE systems SET rating_dirty` (`apps/api/src/ingest/eddn_client.py:443, 487, 670`).
`docs/development/v2-decommission-roadmap.md:276-283` records that the V3 canonical schema has no
`rating_dirty` column, that published generations are immutable, and that this writer is
"uncuttable" until it is redesigned.

### A2. What this means for data freshness in V3

- **The current snapshot.** Canonical generation `phase4c_full_20260827_r5` was created
  2026-08-27 12:05 UTC and published 2026-08-28 19:05 UTC as publication sequence 4
  (`docs/operations/evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json:3-21`). It holds
  198,528,286 systems, 598,724,752 bodies and 830,740 stations
  (`docs/development/v3-derived-data-completion-plan.md:21-24`). It was built from a Spansh galaxy
  dump by the `v3_spansh` importer (`docs/development/ratings-v4-production-integration.md:7-16`).
  The exact date of the Spansh snapshot is **not recorded in the repo**. It is held in production
  in `v3_source.source_artifact.retrieved_at` / `effective_at` for that build's source run, and a
  read-only query would answer it.
- **Nothing updates it.** Published canonical relations are immutable
  (`sql/v3/migrations/001_v3_baseline.sql:1022-1023`, "immutable after publication"). No EDDN
  consumer and no Spansh refresh exists. Journal-import canonical promotion is explicitly deferred
  (CLAUDE.md, named runtime exception). So **systems, bodies and stations in V3 are static as of
  that import.** Everything derived from it is static too: Ratings V4 `parallel_v1`, the spatial
  pyramid, Search and the archetype products.
- **There are no colonisation flags.** The V3 canonical `systems` table
  (`001_v3_baseline.sql:1026-1056`) has no colonisation, population or controlling-faction
  columns. Stations carry type, economies and services as of the snapshot
  (`:1248-1328`). Construction depots therefore appear only as station types
  (`apps/importer/src/v3_spansh/adapter.py:140-141`) frozen at snapshot time.

---

## Part B: Collecting EDDN `Docked` events

### B0. What EDDN actually carries (sources)

- **The schema index has no colonisation schema.** The schema index
  ([README-EDDN-schemas.md](https://eddn.edcd.io/schemas/README-EDDN-schemas.md)) is a
  how-to-write-a-schema guide, not a complete list. It names no colonisation or
  construction-depot schema. Neither does [EDCD/EDDN](https://github.com/EDCD/EDDN).
- **Colonisation events are not on the journal schema's list.** The journal schema README
  ([journal-README.md](https://eddn.edcd.io/schemas/journal-README.md)) lists the source events as
  `Docked`, `FSDJump`, `Scan`, `Location`, `SAASignalsFound`, `CarrierJump` and `CodexEntry`. No
  `Colonisation*` event is listed. Senders must remove `Wanted`, `ActiveFine` and `CockpitBreach`
  from `Docked`, and every `*_Localised` key. They must add `StarPos` and `StarSystem`, plus the
  `horizons`/`odyssey` flags and `gameversion`/`gamebuild`.
- **What this means for colonisation evidence.** EDDN gives indirect colonisation evidence only:
  - `Docked` at a construction depot or colonisation ship (the station type);
  - changing station economies and services over time;
  - system-level fields in `FSDJump`/`Location`.

  There is no direct "system X is being colonised" message.
- **Probable side finding (not verified).** The V2 listener's `Colonisation*` handlers
  (`apps/eddn/src/eddn_listener.py:1305-1315`, `:1349-1350`) may never have fired from EDDN. If
  the gateway validates `journal/1` against that event list, those messages would never arrive.
  This was **not verified**: I could not fetch the JSON schema itself. Check
  `schemas/journal-v1.0.json` in EDCD/EDDN before relying on it.
- **No body on `Docked`.** EDDN `Docked` carries no body ID. Our own journal contract lists no
  Body fields for `Docked` (`apps/api/src/edfinder_api/journal/event_contract.py:49-53`), while
  `Location` does have Body/BodyID/StationName/MarketID (`:80-83`). Body association from EDDN is
  therefore weak; see Part C.
- **Uploader IDs.** EDDN says the gateway hashes `uploaderID` "with a key" that is "changed
  regularly" (schema README, header section). It is already pseudonymous. Even so: **do not store
  it, do not log it, and do not even read it.**

### B1. What production change is needed

#### Worker service

Following the locked stack decision (`v3-application-stack-decision.md:115, 118`), the target is
one dedicated EDDN worker. It runs from the **same backend image** with a different command, as
`:133` prefers ("one versioned backend image with different commands/entrypoints"). The image
already includes `pyzmq==27.2.0` (`apps/api/pyproject.toml:13`), so no new image is needed.

The governed path is the production compose authority plus the deployer. There is no other
sanctioned way to run a long-lived production service: the root compose and host scripts are not
authority (`docs/operations/v3-production-application-release.md:12-15`). That path needs these
changes, all of which are reviewed repo changes:

1. **`deploy/v3-production/compose.yml`.** Add `eddn-blue` and `eddn-green` services
   (backend image, worker command, `restart: unless-stopped`, small limits, read-only root,
   tmpfs, json-file logs). Only the active slot's worker runs. This keeps the rule that a
   candidate never does background writes during staging (`compose.yml:14-16`), and it keeps
   exactly one consumer at a time (`stack decision :226`).
2. **`scripts/operator/v3_production_deploy.py`.** It must learn the worker services.
   - `SERVICES` and `CONTAINERS` (`:61-66`).
   - The contract check (`:482-487`).
   - Compose validation (`:1234-1240`).
   - The network attachment check (`:1043-1053`).
   - The hard-coded blue/green capacity peak `{"cpus": "6.00", "memory": "10240m"}` (`:509-517`).
   - Promotion sequencing. Start `eddn-<new>` only after the public smoke passes (gate 6 in
     the runbook, `:238-243`). Stop `eddn-<old>` before the new one starts. Stop the worker on
     rollback.
3. **`deploy/v3-production/target-authority.json`.**
   - `application_contract.services`, `.containers` and `.compose_sha256` (`:87-105`).
   - Per-slot limits (`:106-122`).
   - `reviewed_capacity.blue_green_peak` (`:21-24`).
4. **`docs/operations/v3-production-application-release.md`.** Update the topology section
   (`:208-218`) and the gates.
5. **Purge interaction (important).** The purge quiesces only `api-*` writers that it enumerates
   from the target authority, and it refuses any compose-project container that is not listed
   (`scripts/operator/lib/v3_purge_delete.py:92-127`). It then requires that no other session
   holds a transaction ID, and that every app-role session started after the fence (purge design
   `docs/development/v3-governed-derived-purge-design.md:273`). A running EDDN worker would
   therefore **stop the purge**, safely but completely. Either:
   - the worker is not running during P; or
   - the purge code learns to quiesce `eddn-*`. Those purge files are F2d-frozen
     (`deploy/v3-production/f2d-operator-code.txt`), so that change needs a new release whose
     attestation carries the new operator-code identity.
6. **Every governed mutator must refuse while the purge is open.** The purge design requires this
   of every mutator and every ops-workflow worker launcher, using the shared read-only query in
   `scripts/operator/lib/` (`v3-governed-derived-purge-design.md:261`). The worker should also
   refuse to start while the purge ledger shows unresolved state. That is a read-only query of
   `v3_meta.derived_generation_purge_event`, made through the existing library and without
   editing it.

#### Database change

One additive migration, numbered **`017`**. (`007` is a reserved proposal in `sql/v3/proposals/`.
Check that the sibling journal-observation work does not claim `017` too.) The mechanism is
documented in `docs/operations/v3-production-schema-migration.md:82-99`, "How a migration lands":

1. Commit `sql/v3/migrations/017_….sql` wrapped in `BEGIN; … COMMIT;`.
2. Append `<sha256>  <ledger-name>  <path>` to `sql/v3/migration-manifest.txt`.
3. Add a new `schema_transition` (through-016 → through-017) and extend the accepted release's
   compatibility attestation in `target-authority.json`. Every prefix must be listed as
   compatible. (Today's transition is the completed through-012 → through-016 one; the operator
   refuses with "omits a transition prefix" until a new one is committed:
   `v3-production-application-release.md:326-330`.)
4. Regenerate the schema identity with `scripts/operator/v3_schema_identity.py` and pin
   `schema_identity_sha256`.
5. Merge, then dispatch the migration workflow's `plan`, review it, then separately dispatch
   `apply` with the plan run ID.

**Freeze constraint.** `sql/v3/migration-manifest.txt` and `shared_contracts/__init__.py` are
**listed in the F2d operator-code identity** (`deploy/v3-production/f2d-operator-code.txt:36, 38`).
That identity is a content hash checked by every F2d operation, including publish 9′ and purge P
(`scripts/operator/lib/f2d_operator_identity.py`). So:

- the manifest must not change before go-live;
- after go-live, the next release recomputes the identity, and **any F2d action, including P,
  needs that new release promoted and recorded first**;
- until go-live, the migration file can be drafted in `sql/v3/proposals/` without registering it.

**Template for the migration.** `014_v3_watchlist.sql:1-7` shows the house pattern: only new empty
relations, `SET LOCAL lock_timeout='5s'` and `statement_timeout='30s'`, no foreign keys to
generation tables, and no locks on populated tables.

#### Store design (smallest version)

- **Schema.** A new `v3_observe` schema for public-source, non-canonical observations. It reuses
  the V3 source ledger that already exists for exactly this purpose:
  - `v3_source.source` and `source_rights_policy` (`001:27-65`);
  - `v3_source.source_run`, whose `acquisition_kind` already allows `'STREAM_WINDOW'` and
    `'BULK_SNAPSHOT'` (`001:100-149`);
  - `v3_source.source_checkpoint` for hourly counters (`001:151-172`).

  See the appendix sketch.
- **Change-only rows.** One append-only table. A row is inserted only when a station's
  research-relevant state hash is new for that source, using `ON CONFLICT DO NOTHING`. There are
  **no hot-row UPDATEs**. That is deliberate: V2 bloated to 95% disk from continuous EDDN update
  churn (`docs/operations/database-bloat-incident-2026-08-20.md:5, 22-27`).
- **Fleet carriers.** Excluded by default (`adapter.py:267-269` already identifies them). See
  decision D3.

#### Write volume

**Not measured. No public figure was reachable.** The EDDN status page and Spansh's dump page are
not fetchable from this session, and the repo contains no measured rate.

The estimate, clearly an estimate:

- **Raw rate.** Order of 10⁴–10⁵ `Docked` messages a day, with fleet carriers a large share.
- **Stored rows.** With change-only storage, stored rows track station state changes, not dock
  count. That is roughly 10²–10⁴ rows a day at a few hundred bytes each: **under 1 GB a year**.
- **Without dedup.** Raw per-dock storage would be about 50 MB a day, or 18 GB a year at 10⁵ a
  day. That is why dedup is in the smallest version.
- **First step (R1).** Measure the real rate off production before any production step.
- **Disk context.** After step 7′ the reviewed headroom was 96 GB (`docs/ROADMAP.md:500`). The
  purge keeps a 100 GB free floor (purge design `:267`). The store must stay small, with an
  alert at 1 GB.

#### Bounding and retention

- **Messages.**
  - Accept only `$schemaRef == https://eddn.edcd.io/schemas/journal/1`. That rejects `/test`.
  - Accept only `event == "Docked"`.
  - Reject Legacy-galaxy game versions.
  - Cap the decompressed size (for example 256 KB).
  - Bound the lists: at most 8 economies, at most 128 services, strings at most 128 characters.
  - Proportions must be finite and within 0–1.
  - `MarketID` and `SystemAddress` must be positive.
  - Event timestamps must be within a window of the gateway time.
- **Buffer and flushing.**
  - Bounded in-memory buffer (for example 5,000 rows). When it is full, drop the oldest and count
    the drop.
  - Flush every 15 s or every 500 rows.
  - Session `statement_timeout` 15 s and `lock_timeout` 2 s, so the worker can never block DDL or
    a purge.
- **Failure handling.** Reuse the #864 breaker pattern. After N consecutive flush failures, exit
  non-zero and let Docker restart it (`eddn_client.py:52-162, 228-360`).
- **Retention.** Change-only rows are kept indefinitely. They are tiny and they are the research
  evidence. Review at 5 GB. Hourly checkpoint rows can be trimmed after 90 days (decision D4).

#### Bulk-write safety

- **Helper not needed.** `docs/development/bulk-database-write-safety.md:3-7` requires the
  replica-mode helper only for bulk writes to `systems`, `bodies`, clusters or `ratings`. This
  worker writes none of them.
- **Required comment.** `:20-22` still requires an adjacent code comment saying why the helper is
  not used. Never use replica mode here.
- **SQL.** Parameterised and batched (arrays plus `unnest`, or `executemany`). Never touch
  `v3_gen_*`, `v3_derived` or `v3_app`.

### B2. Reuse V2 code, or write a small new V3 worker?

**Write a new, small V3 worker.** Neither existing consumer can be reused as it stands.

- **The V2 listener (`apps/eddn/src/eddn_listener.py`) is unusable in V3.**
  - It writes V2 `public` tables: `systems`/`bodies` upserts, `eddn_log` (`:1368`), and
    `UPDATE systems` dirty marks (`:408`).
  - It needs Redis.
  - It is a separate image that the V3 release never builds.
  - It holds the colonisation handlers questioned in B0.
- **The API lifespan ingest (`apps/api/src/ingest/eddn_client.py`) writes V2 relations**, and the
  stack decision says to remove ingest from the API lifespan (`:118`). Its **patterns** are worth
  copying:
  - the ZMQ subscribe/reconnect loop (`:254-310`);
  - the #864 liveness timestamps and flush-failure counters (`:52-162`);
  - the breaker that exits on N consecutive failures;
  - the Prometheus text format in `routers/meta.py:269-280`.
- **The new module.** For example `apps/api/src/edfinder_api/observations/eddn_station_worker.py`
  plus a pure normaliser module. It writes `v3_observe` only, connects through the existing app
  DSN, and runs `SET ROLE` to a NOLOGIN least-privilege role (decision D5).
- **Liveness.**
  - Hourly `source_checkpoint` rows: read, accepted and rejected counts, plus drops.
  - A heartbeat file for a container `HEALTHCHECK`.
  - An extension to the host health check (`deploy/v3-production/health/health-check.sh`, which
    has no worker check today, and the host has no external heartbeat:
    `deploy/v3-production/health/README.md:47-60`).
- **Prometheus.** V3 production runs no Prometheus, so in-process `/metrics` would go unscraped.
  Keep it as an optional, cheap extra, not the liveness mechanism.
- **The simulation ingest stays disabled.** It stays disabled in production (`compose.yml:18`).
  Folding its body-scan handling into this worker is a later step, as the stack decision says,
  and is not part of the smallest version.

### B3. Privacy

- **Header fields.** Persist only `softwareName`, `softwareVersion`, `gatewayTimestamp`,
  `gameversion` and `gamebuild`. **Never read, store or log `header.uploaderID`.** Nothing in the
  repo stores it today (grep of `apps/` and `shared_contracts/`). An earlier design already
  decided that EDDN stays community-facing and is never used for player tracking
  (`docs/archive/superpowers-map/specs/2026-08-08-map-exploration-layer-design.md:101-105`).
- **Message fields.** Store only allowlisted, research-relevant keys. Drop `Taxi` and `Multicrew`.
  Do not keep the raw message: an unexpected sender key could otherwise ride along.
- **Personal-data registry.** `v3_observe` holds no personal data, so it needs no entry in
  `sql/v3/governance/personal_data_registry.json`, whose coverage is `v3_identity`/`v3_private`
  only. **Journal-imported (user) station observations from the sibling branch are personal.**
  They belong in `v3_private` with a registry entry. Keep the same row shape, but use a separate
  relation and never mix the two (decision D7).

---

## Part C: Spansh dumps

### C1. Is any Spansh refresh running for V3 production today? No.

- **The V2 nightly job targets the dead stack.** `scripts/nightly_update.sh` downloads:
  - `systems_1day` daily;
  - `systems_1week` on Mondays;
  - `galaxy_populated` monthly;
  - `galaxy_stations` every run (`:305-391`).

  It runs `docker compose … run importer import_spansh.py` against the **root `docker-compose.yml`**
  (`:63-66, 131-142`). It writes V2 `public` tables. The root compose is "not production
  authority" (`v3-application-stack-decision.md` production table; release runbook `:12-15`).
  V2 crons are decommissioned (`infrastructure-status.md:38-40`).
- **V3 has no scheduler for it.** The only V3 host timers are backup (`deploy/v3-production/backup/*.timer`)
  and health (`deploy/v3-production/health/*.timer`). The ops workflow allowlist
  (`.github/workflows/chatgpt-ed-new-ops.yml:10-38`) has no import or refresh operation.
- **How the V3 model would take deltas.** V3 canonical data lives in generation schemas
  `v3_gen_<key>`, which are immutable after publication (`001:1022-1023`).
  - A generation is built from a **many-run input set**, recorded in
    `v3_meta.canonical_generation_input` (`001:669-683`).
  - `source_run.acquisition_kind` allows `BULK_SNAPSHOT`, `DELTA` and `STREAM_WINDOW` (`001:107`).
  - Station and system rows carry `last_present_run_id`, `first_missing_run_id` and so on for
    snapshot reconciliation (`001:1043-1049, 1261-1268`).
  - Publication flips one pointer row (`001:691-698`).

  So the designed path for deltas is **a new canonical generation that admits base + delta runs**.
  That is a full new ~600 GB schema, not an in-place incremental update.
- **A new generation forces a full derived rebuild.** Derived generations are bound to one
  canonical generation (`sql/v3/migrations/003_ratings_v4_derived.sql:9`). The decision
  `docs/development/v3-search-spatial-derived-data-decision.md:8-18, 336-352` makes canonical
  changes flow through "a derived rebuild and atomic publication". A refresh therefore means
  rebuilding Ratings V4, Search, archetype, pyramid and clusters, and re-publishing the Finder.
  That is multi-day work and does not fit current disk without the purge.
- **No authority document defines a refresh.** `ROADMAP.md:748-750` speaks only of "recover the
  verified canonical importer". `docs/development/journal-commander-contributions.md:93` and
  `accounts-journal-ui-plan.md:105` mention a "later Spansh refresh" only as a future
  reconciliation concern. **A canonical refresh is an unmade architecture decision** (D8). It is
  out of scope for the smallest version, and nothing here should pretend to be one.

### C2. What `galaxy_stations.json.gz` carries per station, and whether it beats EDDN

**Shape.** From production inspection in Stage 18J it is **nested system records**, each with a
`stations[]` collection and `bodies[]` collections whose stations sit under their body. It is not
a flat station list (`docs/colonisation-redesign/stage-18j-q3-readonly-production-reconciliation-artifact.md:242-247`;
`stage-18j-q5-nested-edsm-station-snapshot-support.md:1-35`). The V2 script says Spansh refreshes
it hourly (`nightly_update.sh:356`); I could not confirm that against Spansh's own page. Its size
is **unknown**; measure it in R1.

**Fields our own importers read per station.** Spansh's own docs and schemas were not reachable
from this session.

- **Identity.**
  - `id`, `marketId`, `name`, `realName`, `carrierName` (`adapter.py:212, 263-264`;
    `import_spansh.py:1597`).
- **Station type.**
  - `type` / `stationType`. Construction depots map to "Planetary/Space Construction Depot"
    (`adapter.py:140-141, 268`).
- **Economies.**
  - `economies` as a list or dict of `{name, proportion}` (`adapter.py:272-287, 644-660`).
  - `primaryEconomy`, `secondaryEconomy` (`adapter.py:645-646`; `import_spansh.py:1635-1636`).
- **Services and pads.**
  - `services` (`adapter.py:336-344, 681`).
  - `landingPads{large, medium, small}`, plus `market`/`shipyard`/`outfitting` presence
    (`import_spansh.py:1605-1622`).
- **Faction and politics.**
  - `controllingFaction`, `allegiance`, `government` (`import_spansh.py:1637-1639`).
- **Position, time and body.**
  - `distanceToArrival`, `latitude`, `longitude` (`adapter.py:687, 693-695`).
  - `updateTime`, a per-station observation time (`adapter.py:679`).
  - **Body association**: stations nested under `bodies[].stations` get the body's key
    (`adapter.py:455-459`). Placement records `source_path: "bodies[].stations"` versus
    `"stations"` (`:693-700`).

**Is it a better research source than EDDN `Docked`?** For the CRE's "observed vs predicted
station economies" question, **yes, as the baseline**.

Its advantages:

- It covers the whole galaxy at once, including stations nobody has docked at this week.
- It has economies with proportions, services, type and an update time per station.
- **It has body association where Spansh has nested the station under a body.** EDDN `Docked`
  has none (B0).

Its limits:

- It is a snapshot of the latest known state, not history.
- Spansh is itself largely fed by EDDN, so the two are not independent sources.
- Rights: hosted Spansh data terms are not recorded. The repo's research report says to "seek
  explicit permission for redistribution or bulk mirroring"
  (`docs/research/2026-08-12-elite-dangerous-ecosystem-research-report.md:447, 531`).
- Body association is "where present", and the repo's own audit warns that distance-only
  association is inferred at best (`docs/colonisation-redesign/edsm-data-audit.md:279-283`).

EDDN adds what Spansh cannot give: first-hand, timestamped observations at the moment of docking,
so we can capture **before/after changes** as colonisation facilities are built.

### C3. Spansh and EDDN for V3: which first, and how they fit together

**Spansh first.**

- **It is the baseline.** One governed one-shot load gives the CRE ~800k stations of evidence on
  day one.
- **It needs no new service.** No compose, deployer or capacity change is required. It follows
  the existing detached-worker operator pattern (`scripts/operator/actions/v3-system-search-f1.sh:570-590`:
  `docker run -d --restart no --read-only`, run on the app network inside the attested backend
  image with trusted-main code).
- **Its governance work is small.** It needs one ops-workflow allowlist entry, and its container
  name added to `application_network_allowed_containers`.

**EDDN second.** It adds live change history between Spansh loads. It also needs the
compose/deployer work in B1.

**How they fit together.** Both write the **same** `v3_observe` table, told apart by `source_id`:

- Spansh: the daily or ad-hoc whole-galaxy catch-up (`BULK_SNAPSHOT` runs).
- EDDN: live updates (`STREAM_WINDOW` runs).

Research queries take "latest per station across sources" and "changes over time per source". A
recurring daily Spansh load is a **later** step. It needs a governed schedule: a host timer
installed by a reviewed action, like `v3-backup-wrapper-install`. No V3 scheduler exists for it
today.

---

## Part D: Step list

### Repo-only steps (PRs; no production access)

Steps R1–R6 are **safe before go-live**. They touch no F2d-frozen file
(`deploy/v3-production/f2d-operator-code.txt`), no `target-authority.json`, no `compose.yml`, no
deployer, and no ops workflow.

- **R1. Measure first.** Add a non-production probe. It subscribes to the EDDN relay for N hours
  and counts, without storing anything:
  - `Docked` per hour;
  - the fleet-carrier share;
  - the Live/Legacy split;
  - the distinct-`MarketID` rate;
  - the change-hash rate.

  It also downloads `galaxy_stations.json.gz` once and reports its size and record and station
  counts. It runs as a `workflow_dispatch` on a GitHub-hosted runner, with no secrets and no
  database.
- **R2. Design note.** Write `docs/development/v3-station-observation-store-design.md`, recording
  this plan, the R1 numbers and the owner decisions D1–D7.
- **R3. Draft migration `017`.** Put it under `sql/v3/proposals/`, **not** in
  `migration-manifest.txt`. It creates the `v3_observe` schema, the observation table, the
  `v3_source` seed rows and a NOLOGIN role with grants, and it is tested on a disposable PostgreSQL
  18 database.
- **R4. Pure normalisers.**
  - The EDDN `Docked` envelope becomes an observation row. Allowlisted keys only; `uploaderID`
    is never read.
  - A Spansh system record becomes station observation rows. Import the existing `v3_spansh`
    helpers read-only. **Do not edit `apps/importer/src/v3_spansh/*`**: those files are
    checksum-bound to canonical source recovery (`docs/development/v3-canonical-source-recovery.json`).
  - Synthetic-fixture tests, including the bounds and the rejection of `/test` schemas.
- **R5. EDDN worker module.** Default-off, writing `v3_observe` only. It refuses to start while
  the purge ledger is unresolved, and it includes the breaker, checkpoints, heartbeat and
  bulk-write-safety comment. Tested against a fake ZMQ publisher and a disposable database.
- **R6. Spansh one-shot loader CLI.** It streams and decompresses the file, bounds memory,
  records the artifact sha256 in `v3_source.source_artifact`, inserts change-only rows, and
  resumes by checkpoint. Tested on fixtures.

Steps R7–R11 come **after go-live 9′ is recorded**, because they touch authority, manifest or
workflow files:

- **R7. Register `017`.**
  - Move it to `sql/v3/migrations/` and add it to the manifest.
  - Add a through-016 → through-017 `schema_transition`, attest the accepted release as
    compatible, and pin the schema identity.

  Note that this **changes the F2d operator-code identity**. A new release must be promoted and
  recorded before any further F2d action, including purge P.
- **R8. Spansh ops action.** Add `v3-station-observation-spansh-load-start` and `-status`, modelled
  on `v3-system-search-f1.sh`, with the purge-state refusal. Add the ops-workflow allowlist entry.
  Add the container name to `target-authority.json` `application_network_allowed_containers`.
- **R9. EDDN worker in the deploy authority.** Change `compose.yml` (`eddn-blue`/`eddn-green`),
  the deployer (services, network, capacity, start-after-cutover, stop-on-rollback), the target
  authority contract, compose sha and capacity, and the release runbook.
- **R10. Purge awareness, if D2 is "before P".** The purge quiesces `eddn-*` as well as `api-*`
  (`v3_purge_delete.py:92-127`). These are frozen F2d files, so the change needs a new release
  plus attestation.
- **R11. Host health check.** `health-check.sh` checks the worker container's health. Installed
  in P7.

### Production steps (each needs your explicit go, in this order)

None of these runs while the purge P is running. None runs before go-live 9′ is recorded.

- **P1.** Run the migration workflow `plan` for `017`, which is read-only. Review the receipt.
- **P2.** Run the migration workflow `apply` with that plan run ID. Review the receipt: `017`
  applied, no service changes.
- **P3.** Build a release that includes R5–R10 and record its compatibility. Run preflight, then
  promote. **The EDDN worker starts at cutover.** Record the accepted release and the new
  operator-code identity in `target-authority.json`.
  - For Spansh-only first, the release can ship with the `eddn-*` services left out. P3 is then
    just the routine release that makes the new identity attested.
- **P4.** Run the first Spansh baseline load through the new ops action (start, then status).
  Review the receipt: counts, size and duration.
- **P5.** After 24–72 hours of EDDN running, run a read-only review of the numbers: rows a day,
  size, drops, failures. Decide whether to keep it on.
- **P6.** If wanted later, install a recurring Spansh schedule as a governed host timer. This is a
  separate reviewed install action.
- **P7.** Install the updated host health check.

---

## Part E: Owner decisions needed

- **D1. Order.** Spansh baseline first (recommended), or EDDN first?
- **D2. Purge timing.** Run P1–P5 **after** the governed purge P completes (simplest; no purge code
  change)? Or before P? "Before P" needs R10 plus a release before P can run, and the worker must
  be stopped for P either way.
- **D3. Fleet carriers.** Exclude them (recommended)? They move and dock constantly, and their
  economies are not colonisation evidence.
- **D4. History granularity and retention.**
  - Change-only rows kept indefinitely (recommended)? Or a daily "still seen" row (more rows,
    better confirmation)?
  - Trim hourly checkpoints after 90 days?
  - Alert at 1 GB, review at 5 GB?
- **D5. Database role.** `SET ROLE` to a NOLOGIN least-privilege role on the existing app
  credentials (no new secret)? Note that `edfinder_v3` is a superuser
  (`004_v3_search_spatial_clusters.sql:10`), so this is a guardrail, not a security boundary.
  The alternative is a separate login role with a new root-owned secret file, which you would
  author on the host, like `api.env`.
- **D6. Rights.** Record EDDN and Spansh data as `INTERNAL_USE`, not redistributed. Before any
  **recurring** Spansh bulk download, do you want to ask Spansh for permission? The repo's
  research report flags that hosted-data terms are unrecorded.
- **D7. Journal-import observations.** Should the sibling branch's user journal observations share
  the row shape but live in `v3_private`, with a registry entry, kept separate from public
  `v3_observe`? Recommended: yes.
- **D8 (separate, larger).** How should V3 ever refresh canonical galaxy data? The options are a
  new canonical generation plus a full derived rebuild, or an incremental design. This plan does
  not answer that; it only adds an evidence store beside canonical data.

---

## Technical appendix

### T1. Schema sketch for migration `017` (reference text, NOT to be run; for the R3 PR only)

```sql
-- Reference sketch only. Do not run anywhere. Final text goes in the R3 PR.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

CREATE SCHEMA v3_observe;
COMMENT ON SCHEMA v3_observe IS
  'Public-source, non-canonical station observations (EDDN, Spansh). Evidence only; never canonical truth.';

CREATE TABLE v3_observe.station_state_observation (
    observation_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id        smallint NOT NULL REFERENCES v3_source.source(source_id),
    source_run_id    uuid     NOT NULL,
    market_id        bigint   NOT NULL CHECK (market_id > 0),
    system_id64      bigint   NOT NULL CHECK (system_id64 > 0),
    station_name     text     NOT NULL CHECK (length(station_name) <= 128),
    station_type     text     CHECK (length(station_type) <= 64),
    body_local_id    smallint,            -- Spansh nesting only; NULL from EDDN Docked
    body_name        text     CHECK (length(body_name) <= 128),
    distance_ls      double precision CHECK (distance_ls IS NULL OR distance_ls >= 0),
    primary_economy  text,
    economies        jsonb    NOT NULL,   -- [{"name":..,"proportion":0..1}], <= 8 items
    services         text[]   NOT NULL,   -- sorted, <= 128 items
    landing_pads     jsonb,
    state_sha256     bytea    NOT NULL CHECK (octet_length(state_sha256) = 32),
    observed_at      timestamptz NOT NULL, -- EDDN message timestamp / Spansh updateTime
    gateway_at       timestamptz,          -- EDDN only
    received_at      timestamptz NOT NULL DEFAULT transaction_timestamp(),
    game_version     text,
    software_name    text,                 -- EDDN header; uploaderID is NEVER stored
    software_version text,
    FOREIGN KEY (source_run_id, source_id) REFERENCES v3_source.source_run(source_run_id, source_id),
    UNIQUE (source_id, market_id, state_sha256),
    CHECK (jsonb_typeof(economies) = 'array'),
    CHECK (cardinality(services) <= 128)
);
CREATE INDEX station_state_observation_market_idx
    ON v3_observe.station_state_observation (market_id, observed_at DESC);
CREATE INDEX station_state_observation_system_idx
    ON v3_observe.station_state_observation (system_id64);

-- Seed: one v3_source.source row each for 'eddn-journal-docked' and 'spansh-galaxy-stations'
-- (authority_class SECONDARY_AGGREGATED), with a rights policy rights_class 'INTERNAL_USE',
-- distribution_allowed false (decision D6).
-- Role: CREATE ROLE v3_station_observer NOLOGIN NOINHERIT (if absent), GRANT it to edfinder_v3;
-- grants limited to INSERT/SELECT on v3_observe, INSERT/UPDATE on own v3_source.source_run /
-- source_checkpoint rows (decision D5). Pattern: 016 executor role.
COMMIT;
```

The state hash covers only research fields: type, sorted economies with proportions rounded to a
fixed precision, sorted services, body, and pads. It deliberately leaves out faction, government,
allegiance and timestamps, so that background-simulation churn does not create rows. One known
limitation: an A→B→A flip-flop stores the second A only if D4 picks daily granularity.

### T2. Worker run contract (reference)

- **Command.** The same backend image runs something like
  `python -m edfinder_api.observations.eddn_station_worker`.
- **Relay.** Uses `EDDN_RELAY = tcp://eddn.edcd.io:9500`, the same as `eddn_client.py:52`. The
  app network is an egress-capable bridge (`v3_production_deploy.py:1018-1025` requires
  `Internal: false`).
- **Limits.** For example cpus 0.25, mem 256m, pids 64, read-only, tmpfs `/tmp`,
  no-new-privileges, json-file 20m×3. The deployer's hard-coded peak (`:509-517`) and the
  authority's `blue_green_peak` change with it.
- **Connections.** One pool with max 2 connections.
- **Session settings.** Each session runs `SET ROLE v3_station_observer`,
  `SET lock_timeout='2s'`, `SET statement_timeout='15s'`, and sets `application_name` so purge and
  status checks can identify it.
- **Startup check.** A read-only check of the purge ledger. If the ledger is unresolved, the
  worker exits with a named reason.

### T3. Key citations

- **The V3 production app authority owns only api/web.**
  `deploy/v3-production/compose.yml:3-6, 14-18, 52-77`; `target-authority.json:87-105, 153-160`;
  `scripts/operator/v3_production_deploy.py:61-66, 482-487, 509-517, 1043-1053, 1221-1240`.
- **Stack decision for EDDN.** `docs/development/v3-application-stack-decision.md:115, 118, 133, 154, 226`.
- **Migration mechanism.** `docs/operations/v3-production-schema-migration.md:82-99`;
  manifest format in `sql/v3/migration-manifest.txt:1-14`.
- **F2d freeze surface.** `deploy/v3-production/f2d-operator-code.txt` (includes
  `sql/v3/migration-manifest.txt`, `shared_contracts/__init__.py`, and every purge library).
- **Purge writer and mutator fences.** `docs/development/v3-governed-derived-purge-design.md:261, 267, 273`;
  `scripts/operator/lib/v3_purge_delete.py:92-127`.
- **The V2 ingest is not V3-safe.** `apps/api/src/ingest/eddn_client.py:443, 487, 670`;
  `docs/development/v2-decommission-roadmap.md:276-283`.
- **The canonical model is immutable generations.**
  `sql/v3/migrations/001_v3_baseline.sql:100-149, 641-698, 1022-1023, 1026-1056, 1248-1328`;
  `003_ratings_v4_derived.sql:9`; `docs/development/v3-search-spatial-derived-data-decision.md:8-18, 336-352`.
- **Current canonical snapshot.** `docs/operations/evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json:3-21`.
- **Spansh station fields.** `apps/importer/src/v3_spansh/adapter.py:140-141, 212, 263-287, 455-459, 644-700`;
  `apps/importer/src/import_spansh.py:1597-1640`.
- **V2 nightly refresh, which targets the dead stack.** `scripts/nightly_update.sh:63-66, 131-142, 305-391`.

External sources:

- [EDDN schemas README](https://eddn.edcd.io/schemas/README-EDDN-schemas.md)
- [EDDN journal schema README](https://eddn.edcd.io/schemas/journal-README.md)
- [EDCD/EDDN](https://github.com/EDCD/EDDN)

Not reachable this session: the EDDN status/stats page, Spansh's dumps page, and
`spansh/elite_dangerous_schemas`.
