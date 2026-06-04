#!/usr/bin/env bash
set -euo pipefail

cd /opt/ed-finder

echo "== Git clean check =="
echo "PWD: $(pwd)"
echo "Branch: $(git branch --show-current)"
echo "HEAD: $(git rev-parse HEAD)"
echo

STATUS="$(git status --short)"
if [ -n "$STATUS" ]; then
  echo "$STATUS"
  echo
  echo "clean: false"
  exit 1
fi

echo "clean: true"
echo
echo "== Safety boundary =="
echo "db_access_performed: false"
echo "db_writes_performed: false"
echo "migrations_performed: false"
echo "station_type_writes_performed: false"
echo "canonical_apply_performed: false"
