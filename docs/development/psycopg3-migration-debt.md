# Psycopg 3 Synchronous PostgreSQL Authority

The active synchronous PostgreSQL migration is complete. Importer, maintenance,
repair, reconciliation, release/checkpoint, acceptance and test code use
Psycopg 3. `apps/importer/requirements.txt` owns the runtime pin
`psycopg[binary]==3.3.4`; synchronous check tooling uses the same pin.

The temporary psycopg2 test-path quarantine and its collection hook have been
removed. Active Python source and dependency manifests are protected by AST and
dependency-authority regression checks in
`tests/test_v3_python_runtime_validation.py`.

The deployable API and asynchronous EDDN storage remain owned by asyncpg. The
Psycopg 3 package in the API lock is a test-only dependency and is excluded from
the release runtime through `--no-group test`.

Residual `psycopg2` strings are permitted only in historical documentation,
this completion record, or regression assertions that reject the retired
dependency/import. They do not define an executable dependency or active
database code path.
