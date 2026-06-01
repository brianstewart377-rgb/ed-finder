#!/usr/bin/env sh
set -eu

if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="${PYTHON:-python}"
fi

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
