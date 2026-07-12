# Known Issues

## edfinder_api.state / state dual-import (pre-existing)

Discovered 2026-07-12 during Phase B integration test run.
tests/integration/conftest.py imports state via flat path;
apps/api/src/main.py sets pool via edfinder_api.state package
path. Python treats these as two separate module objects so
pool is None in integration tests. Does not affect production
(single import path). Fix in a separate stage before relying
on integration tests for endpoint verification.
