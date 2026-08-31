# ED-Finder R1 — Operator Real-System Snapshot
## Review 2 — Final Pre-Code Technical Contract

Date: 2026-08-31  
Status: final pre-code Review 2; implementation authorised only inside this contract after owner continuation.  
Branch: `chatgpt-ed-new-ops-requests`  
Review 1: `docs/research/r1-operator-real-snapshot-review-1-2026-08-31.md`

## 1. Objective

Add one dedicated GitHub Actions operator workflow that executes the already-reviewed R1 real-system snapshot implementation against the configured ED-Finder candidate PostgreSQL database and returns bounded read-only canonical snapshots for explicit system names/id64s.

The workflow is an execution bridge only. It does not change the snapshot semantics, database contents, Finder, Ratings, API or frontend.

## 2. Reviewed implementation pin

The workflow must execute snapshot code from immutable revision:

`6d1cb6a13f6c118f5f61fde550c6dde09e19690b`

That revision contains:

- corrected plan-relative Finder proof;
- R1 evidence bridge;
- bounded real snapshot loader;
- operator snapshot CLI;
- focused safety tests.

The request commit must never be able to substitute different snapshot code.

## 3. Exact new workflow surface

Create only:

`.github/workflows/r1-real-system-snapshot.yml`

The workflow triggers on push to `chatgpt-ed-new-ops-requests` only when a file under:

`.github/r1-real-snapshot-requests/*.json`

changes.

`permissions` must be `contents: read` only.

Job environment: `ed-new-operator`.

No workflow_dispatch is required for this first slice; every run is bound to an auditable request commit.

## 4. Request contract

Exactly one changed request file is permitted in the triggering commit.

Exact JSON shape:

```json
{
  "operation": "r1-real-system-snapshot",
  "selectors": ["HR 1188", "Brambai DL-Y g32"]
}
```

Validation rules:

- exact keys only: `operation`, `selectors`;
- operation exactly `r1-real-system-snapshot`;
- selectors is a JSON array;
- 1–20 entries;
- every entry is a string after JSON decode;
- trim whitespace and reject empty values;
- maximum selector length 128 characters;
- selectors must be unique after trimming;
- no wildcard/glob/regex semantics;
- strings are passed as argv values through Python `subprocess`, never interpolated into shell or SQL.

The existing snapshot loader itself performs exact system-name/id64 matching and parameterized SQL.

## 5. Existing operator trust boundary to reuse

Use exactly the existing `ed-new-operator` secret family/pinned-host model:

- `ED_NEW_OPERATOR_SSH_KEY`
- `ED_NEW_OPERATOR_HOST`
- `ED_NEW_OPERATOR_PORT`
- `ED_NEW_OPERATOR_USER`
- `ED_NEW_OPERATOR_SSH_KNOWN_HOSTS` with existing fallback if needed
- `ED_NEW_CANDIDATE_DATABASE_URL`

SSH requirements:

- `IdentitiesOnly=yes`
- explicit pinned `UserKnownHostsFile`
- `GlobalKnownHostsFile=/dev/null`
- `StrictHostKeyChecking=yes`
- verify the configured host/port exists in the pinned known-hosts material before use.

No `ssh-keyscan`, TOFU, disabled host checking or unpinned fallback is permitted.

## 6. Remote execution contract

Workflow steps:

1. checkout request branch with fetch depth 2;
2. validate that the commit changes exactly one allowlisted request JSON;
3. checkout reviewed snapshot implementation at the immutable SHA into `trusted-snapshot`, `persist-credentials:false`;
4. prepare pinned SSH trust;
5. create a temporary tarball containing only the reviewed files required to run the snapshot:
   - `apps/api/src/r1_finder_compare/`
   - `apps/api/src/r1_evidence_bridge/`
   - `apps/api/src/r1_real_snapshot/`
   - `scripts/operator/actions/r1-real-system-snapshot.py`
6. copy the tarball and validated request JSON to uniquely named `/tmp` paths on the operator host;
7. pipe `ED_NEW_CANDIDATE_DATABASE_URL` over SSH stdin; never include it on the remote command line, environment display or artifact;
8. remote code:
   - create temporary workdir;
   - extract reviewed tarball;
   - read DB URL from stdin into `R1_READONLY_DATABASE_URL`;
   - load validated selectors from the request JSON with Python;
   - launch snapshot CLI via `subprocess.run([sys.executable, script, *selectors], ...)`;
   - output only the CLI JSON to stdout;
   - cleanup tarball/request/workdir via trap;
9. runner writes stdout to `r1-real-system-snapshot.json`.

The snapshot CLI already calls `conn.set_session(readonly=True, autocommit=True)`, and the loader refuses canonical reads unless `SHOW transaction_read_only` returns `on`.

## 7. Artifact validation

Before uploading, runner validation must assert:

- JSON parses;
- `transaction_read_only == "on"`;
- safety object contains:
  - `db_access_performed == true`
  - `db_read_only_confirmed == true`
  - `db_writes_performed == false`
  - `migrations_performed == false`
- `snapshots` is a list with at most 20 rows;
- every returned system name/id64 is a scalar string;
- the raw artifact does not contain `ED_NEW_CANDIDATE_DATABASE_URL` value;
- no request contains more than 20 selectors.

A system selector that is not found is not a workflow failure. Report it explicitly as not found.

## 8. Log disclosure boundary

Do not print the raw snapshot JSON to ordinary workflow logs.

Print only:

- requested selector count;
- returned system count;
- not-found selectors;
- per returned system:
  - name
  - id64
  - declared body count
  - returned/projected body count
  - body completeness state
  - extraction evidence satisfied/disposition
  - refinery evidence satisfied/disposition
  - snapshot digest prefix if available;
- safety flags.

Do not print body-by-body full payloads or database URL.

## 9. Artifact

Upload:

`r1-real-system-snapshot.json`

Artifact name:

`r1-real-system-snapshot-${{ github.run_id }}`

Use the repository's already-pinned `actions/upload-artifact` revision:

`043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`

Retention: 30 days.

## 10. Failure handling

Fail closed when:

- request shape invalid;
- pinned SSH trust incomplete;
- candidate DB secret missing;
- remote command fails;
- snapshot JSON missing/invalid;
- read-only assertion absent/false;
- safety flags indicate any write/migration;
- credential value appears in artifact.

Do not retry with weaker trust or a writable DB connection.

## 11. First three request batches

### Batch 1 — golden and ammonia regressions (20)

1. Plaa Eurk ZR-M c7-2
2. Blu Thua SU-W c2-5
3. Blu Thua JS-J d9-1
4. HIP 101924
5. HIP 294
6. HR 1188
7. Brambai DL-Y g32
8. Eorgh Prou AA-A h24
9. HIP 70564
10. Praea Euq PS-U c2-3
11. Kruger 60
12. 36 Ophiuchi
13. Lacaille 8760
14. Toolfa
15. Kokary
16. Omicron-2 Eridani
17. G 99-49
18. LP 816-60
19. G 89-32
20. Saktsak

### Batch 2 — sparse + diverse well-known systems (20)

1. Wolf 359
2. Lalande 21185
3. UV Ceti
4. Yin Sector CL-Y d127
5. Sol
6. Alpha Centauri
7. Procyon
8. Sirius
9. Lave
10. Leesti
11. Shinrarta Dezhra
12. Deciat
13. Maia
14. Robigo
15. Sothis
16. Ceos
17. Colonia
18. Sagittarius A*
19. Betelgeuse
20. Achenar

### Batch 3 — extra nearby/diverse systems (20)

1. Ross 154
2. Barnard's Star
3. Epsilon Eridani
4. Tau Ceti
5. Luyten's Star
6. Groombridge 34
7. EZ Aquarii
8. Lacaille 9352
9. Ross 128
10. 61 Cygni
11. Wolf 1061
12. Van Maanen's Star
13. Altair
14. Vega
15. Arcturus
16. Capella
17. Alioth
18. Gateway
19. Cubeo
20. Kamadhenu

Each request is a separate max-20 run/artifact. Batch 2/3 proceed only if the prior workflow proves the operator path safe and usable.

## 12. Acceptance evidence

After implementation/run, inspect:

- workflow source;
- request commit(s);
- workflow run conclusion;
- job steps/logs;
- snapshot artifact(s);
- not-found selectors;
- current canonical R1 projections;
- read-only safety proof.

No claim of successful canonical validation is made until the artifacts are actually downloaded and inspected.

## 13. Non-goals

Still excluded:

- production Finder sort/ranking changes;
- Plan Fit calibration;
- automatic candidate-plan resilience;
- database writes/migrations;
- Evidence Store mutation;
- ratings/archetype rebuild;
- deployment or merge.
