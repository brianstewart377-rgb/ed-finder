#!/usr/bin/env bash
set -euo pipefail

cd /opt/ed-finder

echo "== DB read-only health =="
echo "Loading /opt/ed-finder/.env without printing secrets..."

set -a
source /opt/ed-finder/.env
set +a

test -n "${POSTGRES_PASSWORD:-}" || { echo "STOP: POSTGRES_PASSWORD is not set" >&2; exit 1; }

python3 -c '
import os
import psycopg2
import psycopg2.extras

password = os.environ.get("POSTGRES_PASSWORD")
dsn = (
    "host=127.0.0.1 "
    "port=5432 "
    "dbname=edfinder "
    "user=edfinder "
    f"password={password} "
    "sslmode=disable"
)

conn = psycopg2.connect(dsn)
try:
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SHOW transaction_read_only")
        read_only = cur.fetchone()["transaction_read_only"]

        cur.execute("""
            SELECT
              current_database() AS current_database,
              current_user AS current_user,
              inet_server_addr()::text AS server_addr,
              inet_server_port() AS server_port
        """)
        ident = dict(cur.fetchone())

        cur.execute("SELECT COUNT(*)::int AS station_rows FROM stations")
        station_rows = dict(cur.fetchone())["station_rows"]

        cur.execute("SELECT COUNT(*)::int AS identity_rows FROM station_external_identity")
        identity_rows = dict(cur.fetchone())["identity_rows"]

        cur.execute("""
            SELECT station_type::text AS station_type, COUNT(*)::int AS rows
            FROM stations
            GROUP BY station_type
            ORDER BY station_type
        """)
        type_counts = [dict(row) for row in cur.fetchall()]

        print("transaction_read_only:", read_only)
        print("current_database:", ident["current_database"])
        print("current_user:", ident["current_user"])
        print("server_addr:", ident["server_addr"])
        print("server_port:", ident["server_port"])
        print("station_rows:", station_rows)
        print("identity_rows:", identity_rows)
        print("station_type_counts:", type_counts)

        if read_only != "on":
            raise SystemExit("STOP: transaction was not read-only")
finally:
    conn.close()
'

echo
echo "== Safety boundary =="
echo "db_access_performed: true"
echo "db_read_only_confirmed: true"
echo "db_writes_performed: false"
echo "migrations_performed: false"
echo "station_type_writes_performed: false"
echo "canonical_apply_performed: false"
