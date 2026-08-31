# ED-Finder R1 — Operator Real-System Snapshot
## Review 2A — Retained-PG18 Connection Amendment

Date: 2026-08-31  
Status: pre-code correction to Review 2 after first execution failed before DB access.

## Triggering evidence

Batch-01 workflow run `33397399419` passed request validation, immutable reviewed-code checkout and pinned SSH trust, then failed before any DB access because `ED_NEW_CANDIDATE_DATABASE_URL` is not configured in the `ed-new-operator` environment.

No snapshot artifact was produced and no PostgreSQL query was executed.

## Corrected connection strategy

Do **not** add or require a new database secret.

Reuse the already-reviewed retained-PG18 discovery/tunnel pattern from `.github/workflows/ed-new-db-discover-audit.yml`:

1. pinned SSH into the existing operator host;
2. inspect only the fixed retained PostgreSQL container `edfinder-v3-phase4c-full-20260827_r5-postgres`;
3. derive its PostgreSQL user/password from container environment in a temporary runner-only metadata file;
4. enumerate connectable databases with `docker exec ... psql`;
5. require exactly one database containing `systems`, `bodies`, and `body_rings` (and preferably `ratings` for ED-Finder identity diagnostics);
6. derive the container/host reachable PostgreSQL address exactly as the existing discovery workflow does;
7. open an SSH local-forward tunnel from the GitHub runner to that PostgreSQL endpoint;
8. install pinned `psycopg2-binary==2.9.12` on the ephemeral runner;
9. construct the tunnel DSN in runner memory only, mask it immediately, and pass it as `R1_READONLY_DATABASE_URL` to the immutable snapshot script;
10. snapshot script sets the PostgreSQL session `readonly=True`, `autocommit=True` and refuses canonical reads unless `SHOW transaction_read_only` returns `on`.

## Credential boundary

- discovered password/DSN must not be printed;
- discovery metadata stays in `$RUNNER_TEMP` and is never uploaded;
- full DSN is immediately registered with `::add-mask::`;
- only the validated snapshot JSON is uploaded;
- artifact validation still rejects any occurrence of the DSN/password if present;
- SSH tunnel is terminated by trap at step exit.

## Execution simplification

Because the snapshot can run on the ephemeral GitHub runner through the tunnel, remove the remote tarball/SCP execution layer. The runner checks out the immutable reviewed implementation at:

`6d1cb6a13f6c118f5f61fde550c6dde09e19690b`

Selectors remain loaded from validated request JSON and passed to the script through Python `subprocess.run([...])`, never shell interpolation.

## Safety unchanged

This amendment does not broaden scope:

- max 20 exact selectors;
- static parameterized SELECT/SHOW only;
- no DB writes/migrations;
- no Finder/ratings changes;
- no Plan Fit or plan-resilience calculation;
- no broad system discovery beyond identifying the one retained ED-Finder database container/database needed to make the read-only connection.

If container discovery is ambiguous or the session is not read-only, fail closed.
