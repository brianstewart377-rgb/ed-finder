#!/bin/bash
set -uo pipefail

# Resolve the compose directory as the parent of this script's directory so the
# wrapper works regardless of where the repository is installed.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ ! -f "$COMPOSE/docker-compose.yml" ]]; then
    echo "ERROR: map refresh cannot find docker-compose.yml at $COMPOSE" >&2
    exit 1
fi

# Host cron does not load the compose environment. Read only the heartbeat key
# rather than sourcing .env, because other values may contain shell syntax.
if [[ -z "${MAP_REFRESH_HEARTBEAT_URL+x}" ]] && [[ -r "$COMPOSE/.env" ]]; then
    while IFS= read -r env_line || [[ -n "$env_line" ]]; do
        env_line="${env_line%$'\r'}"
        case "$env_line" in
            MAP_REFRESH_HEARTBEAT_URL=*)
                MAP_REFRESH_HEARTBEAT_URL="${env_line#*=}"
                break
                ;;
        esac
    done < "$COMPOSE/.env"
fi
MAP_REFRESH_HEARTBEAT_URL="${MAP_REFRESH_HEARTBEAT_URL-}"

cd "$COMPOSE" || {
    compose_exit_code=$?
    echo "ERROR: map refresh cannot enter compose directory $COMPOSE" >&2
    exit "$compose_exit_code"
}

docker compose exec -T postgres psql \
    -v ON_ERROR_STOP=1 \
    -U edfinder \
    -d edfinder \
    -c 'SELECT * FROM refresh_map_mviews(TRUE)'
refresh_exit_code=$?

if (( refresh_exit_code != 0 )); then
    echo "ERROR: map refresh failed (exit ${refresh_exit_code})" >&2
    exit "$refresh_exit_code"
fi

echo "map refresh: completed successfully"

if [[ -z "$MAP_REFRESH_HEARTBEAT_URL" ]]; then
    echo "map refresh heartbeat: skipped (unconfigured)"
    exit 0
fi

ping_exit_code=0
curl -fsS -m 10 --retry 3 "$MAP_REFRESH_HEARTBEAT_URL" || ping_exit_code=$?
if (( ping_exit_code == 0 )); then
    echo "map refresh heartbeat: sent"
else
    echo "ERROR: map refresh heartbeat: ping-failed (curl exit ${ping_exit_code})" >&2
fi

# Heartbeat delivery never changes a successful refresh exit status.
exit 0
