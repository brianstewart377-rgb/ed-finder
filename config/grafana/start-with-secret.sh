#!/bin/sh
set -eu

password_file=/run/secrets/grafana_admin_password
if [ ! -s "$password_file" ]; then
  echo "Grafana refused to start: admin password file is missing or empty." >&2
  exit 78
fi

IFS= read -r GF_SECURITY_ADMIN_PASSWORD < "$password_file" || true
case "$GF_SECURITY_ADMIN_PASSWORD" in
  ''|admin|change-me|not-configured)
    echo "Grafana refused to start: configure a non-placeholder admin password file." >&2
    exit 78
    ;;
esac
export GF_SECURITY_ADMIN_PASSWORD

exec /run.sh
