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

# GlitchTip Grafana datasource token — optional (error tracking is opt-in).
# Unlike the admin password above, an unconfigured token is not fatal: it
# just leaves the Sentry datasource (config/grafana/provisioning/datasources/
# glitchtip.yml) provisioned with an empty/placeholder authToken, which
# Grafana surfaces as a datasource-level auth error, not a startup failure.
glitchtip_token_file=/run/secrets/glitchtip_grafana_auth_token
if [ -s "$glitchtip_token_file" ]; then
  IFS= read -r GLITCHTIP_GRAFANA_AUTH_TOKEN < "$glitchtip_token_file" || true
  case "$GLITCHTIP_GRAFANA_AUTH_TOKEN" in
    ''|not-configured) GLITCHTIP_GRAFANA_AUTH_TOKEN='not-configured' ;;
  esac
else
  GLITCHTIP_GRAFANA_AUTH_TOKEN='not-configured'
fi
export GLITCHTIP_GRAFANA_AUTH_TOKEN

exec /run.sh
