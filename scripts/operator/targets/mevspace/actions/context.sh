#!/usr/bin/env bash
set -euo pipefail

cd /opt/ed-finder
bash scripts/operator/targets/mevspace/require_mevspace_operator_env.sh

echo "== MevSpace operator context =="
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
echo "target: mevspace"
echo "db_access_performed: false"
echo "db_writes_performed: false"
echo "docker_writes_performed: false"
echo "migrations_performed: false"
