#!/usr/bin/env bash
set -euo pipefail

cd /opt/ed-finder

echo "== Hetzner operator context =="
echo "Host: $(hostname)"
echo "User: $(whoami)"
echo "PWD: $(pwd)"
echo "UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo
echo "== Git =="
git branch --show-current
git log --oneline -5
git status --short

echo
echo "== Safety boundary =="
echo "db_access_performed: false"
echo "db_writes_performed: false"
echo "migrations_performed: false"
echo "station_type_writes_performed: false"
echo "canonical_apply_performed: false"
