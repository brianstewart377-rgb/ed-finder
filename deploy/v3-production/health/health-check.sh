#!/usr/bin/env bash
set -euo pipefail
pg='edfinder-v3-phase4c-full-20260827_r5-postgres'
redis='edfinder-v3-support-redis'
nats='edfinder-v3-support-nats'
origin='http://127.0.0.1:58080'
project='edfinder-v3-production'

# Retained support services. These are preserved across promotions and never
# managed by the application Compose authority, so their names are stable.
[ "$(docker inspect -f '{{.State.Health.Status}}' "$pg")" = healthy ]
docker exec "$redis" redis-cli ping | grep -qx PONG
[ "$(docker inspect -f '{{.State.Running}}' "$nats")" = true ]
docker inspect -f '{{json .Config.Cmd}}' "$nats" | grep -q -- '--jetstream'

# Exactly one active origin, and it must be a running member of the promoted
# compose project. The check must never name a slot: the active slot changes on
# every blue/green cutover, and naming one is what broke this script when the
# legacy api and proxy were retired.
active_owner="$(
  docker ps --filter "label=com.docker.compose.project=$project" --format '{{.Names}}' \
    | while read -r name; do
        if docker port "$name" 2>/dev/null | grep -q '127.0.0.1:58080'; then printf '%s\n' "$name"; fi
      done
)"
[ "$(printf '%s\n' "$active_owner" | grep -c .)" -eq 1 ]

# The active origin serves the SPA and proxies /api/* to whichever api slot is
# live, so these two checks cover both containers without naming either.
curl -fsS --max-time 5 "$origin/api/health" \
  | python3 -c 'import json,sys; p=json.load(sys.stdin); assert p.get("status")=="ok" and p.get("database")=="connected"'
curl -fsS --max-time 5 "$origin/api/v1/auth/session" \
  | python3 -c 'import json,sys; p=json.load(sys.stdin); assert p.get("authenticated") is False'

echo 'V3 runtime health PASS'
