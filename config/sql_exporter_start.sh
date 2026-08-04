#!/bin/sh
set -eu

if [ -z "${POSTGRES_PASSWORD:-}" ]; then
  echo 'SQL Exporter refused to start: POSTGRES_PASSWORD is empty.' >&2
  exit 78
fi

# SQL Exporter requires a URL-form DSN. Encode every password byte so password
# rotations remain safe even when they contain URL-reserved characters.
password_hex="$(printf '%s' "$POSTGRES_PASSWORD" | od -An -tx1 | tr -d ' \n')"
encoded_password="$(printf '%s' "$password_hex" | sed 's/../%&/g')"
SQLEXPORTER_TARGET_DSN="postgresql://edfinder:${encoded_password}@postgres:5432/edfinder?sslmode=disable"
export SQLEXPORTER_TARGET_DSN
unset POSTGRES_PASSWORD password_hex encoded_password

exec /bin/sql_exporter "$@"
