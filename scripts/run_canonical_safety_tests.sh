#!/usr/bin/env sh
set -eu

if [ -n "${PYTHON:-}" ]; then
    :
elif [ -x "apps/api/.venv/bin/python" ]; then
    PYTHON="apps/api/.venv/bin/python"
elif [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v python3.14 >/dev/null 2>&1; then
    PYTHON="$(command -v python3.14)"
else
    PYTHON="${PYTHON:-python}"
fi

"$PYTHON" -c "import platform, sys; assert platform.python_implementation() == 'CPython' and sys.version_info[:2] == (3, 14)" || {
    echo "Canonical safety tests require exact CPython 3.14; set PYTHON to the repository's 3.14 interpreter." >&2
    exit 1
}

"$PYTHON" -m pytest \
    tests/test_station_type_canonical_pilot.py \
    tests/test_enrichment_warehouse_boundary.py \
    tests/test_enrichment_staging_db_loader.py \
    tests/test_enrichment_report_contracts.py \
    tests/test_edsm_station_normalization.py \
    -q

"$PYTHON" -m py_compile \
    apps/importer/src/station_type_canonical_pilot.py \
    tests/test_station_type_canonical_pilot.py \
    tests/test_station_type_canonical_pilot_postgres.py

if [ "${EDFINDER_CONFIRM_CANONICAL_TEST_DB:-}" = "yes" ] && [ -n "${EDFINDER_CANONICAL_TEST_DSN:-}" ]; then
    "$PYTHON" -m pytest tests/test_station_type_canonical_pilot_postgres.py -q
else
    echo "Skipping disposable Postgres rehearsal tests; set EDFINDER_CANONICAL_TEST_DSN and EDFINDER_CONFIRM_CANONICAL_TEST_DB=yes to enable."
fi
