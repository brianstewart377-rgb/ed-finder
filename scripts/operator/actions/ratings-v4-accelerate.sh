#!/usr/bin/env bash
set -euo pipefail

TARGET_HOSTNAME="ed-finder-prod"
TARGET_FQDN="nb79a3d.mevnode.com"
OPERATION_LABEL="ed-finder.operation=ratings-v4-generation"
TARGET_CPUS="16"
TARGET_MEMORY="64g"
TARGET_MEMORY_BYTES="68719476736"
TARGET_NANO_CPUS="16000000000"
TARGET_PIDS="512"

fail() {
  printf 'ratings-v4 accelerate: %s\n' "$*" >&2
  exit 64
}

command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
[ "$(hostname)" = "$TARGET_HOSTNAME" ] || fail "unexpected hostname"
[ "$(hostname -f 2>/dev/null || true)" = "$TARGET_FQDN" ] || fail "unexpected fqdn"
[ "$(docker context show)" = "default" ] || fail "unexpected docker context"
docker context inspect default 2>/dev/null | grep -F 'unix:///var/run/docker.sock' >/dev/null \
  || fail "default docker context is not the local rootful socket"

mapfile -t workers < <(docker ps --filter "label=${OPERATION_LABEL}" --format '{{.Names}}')
[ "${#workers[@]}" -eq 1 ] || fail "expected exactly one running Ratings V4 worker, found ${#workers[@]}"
worker="${workers[0]}"

case "$worker" in
  edfinder-ratings-v4-prod-p[1-9][0-9]*) ;;
  *) fail "unexpected Ratings V4 worker name" ;;
esac

[ "$(docker inspect -f '{{.State.Running}}' "$worker")" = "true" ] || fail "Ratings V4 worker is not running"

before="$(docker inspect -f '{{.HostConfig.NanoCpus}} {{.HostConfig.Memory}} {{.HostConfig.PidsLimit}}' "$worker")"

docker update \
  --cpus "$TARGET_CPUS" \
  --memory "$TARGET_MEMORY" \
  --pids-limit "$TARGET_PIDS" \
  "$worker" >/dev/null

after="$(docker inspect -f '{{.HostConfig.NanoCpus}} {{.HostConfig.Memory}} {{.HostConfig.PidsLimit}}' "$worker")"
read -r nano_cpus memory_bytes pids <<< "$after"
[ "$nano_cpus" = "$TARGET_NANO_CPUS" ] || fail "CPU limit verification failed"
[ "$memory_bytes" = "$TARGET_MEMORY_BYTES" ] || fail "memory limit verification failed"
[ "$pids" = "$TARGET_PIDS" ] || fail "pid limit verification failed"

printf 'operation=ratings-v4-generation-accelerate\n'
printf 'result=updated-in-place\n'
printf 'worker_container=%s\n' "$worker"
printf 'before_limits=%s\n' "$before"
printf 'cpu_limit=%s\n' "$TARGET_CPUS"
printf 'memory_limit=%s\n' "$TARGET_MEMORY"
printf 'pids_limit=%s\n' "$TARGET_PIDS"
printf 'worker_running=%s\n' "$(docker inspect -f '{{.State.Running}}' "$worker")"
printf 'publication_performed=false\n'
printf 'migrations_performed=false\n'
printf 'canonical_writes_performed=false\n'
printf 'worker_restarted=false\n'
