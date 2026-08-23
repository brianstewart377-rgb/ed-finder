#!/usr/bin/env bash
set -euo pipefail

cd /opt/ed-finder
bash scripts/operator/targets/mevspace/require_mevspace_operator_env.sh

echo "== Docker status =="
docker version --format 'Server: {{.Server.Version}}'
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'

echo
echo "== Safety boundary =="
echo "target: mevspace"
echo "db_access_performed: false"
echo "db_writes_performed: false"
echo "docker_writes_performed: false"
