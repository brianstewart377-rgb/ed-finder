#!/usr/bin/env bash
# LEGACY/SELF-HOST/LOCAL COMPOSE HELPER; NOT V3 PRODUCTION AUTHORITY.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash scripts/prepare_monitoring.sh [--check]

Prepare retained local/self-host monitoring files for their non-root
containers. The default mode fixes ownership and permissions. --check is
read-only and exits non-zero when a file is missing or incorrectly protected.
EOF
}

mode=apply
case "${1:-}" in
  '') ;;
  --check) mode=check ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 64 ;;
esac

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$script_dir/.." && pwd)"
env_file="$repo_dir/.env"

die() {
  printf '[ERROR] %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '[OK] %s\n' "$*"
}

[[ "$(uname -s)" == Linux* ]] || die 'this local monitoring permission helper requires Linux'
[[ -f "$env_file" ]] || die "$env_file is missing"
command -v stat >/dev/null || die 'stat is required'

env_path() {
  local key="$1"
  local fallback="$2"
  local value
  value="$(sed -n "s/^${key}=//p" "$env_file" | tail -n 1)"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf '%s' "${value:-$fallback}"
}

absolute_path() {
  case "$1" in
    /*) printf '%s' "$1" ;;
    ./*) printf '%s/%s' "$repo_dir" "${1#./}" ;;
    *) printf '%s/%s' "$repo_dir" "$1" ;;
  esac
}

grafana_password="$(absolute_path "$(env_path GRAFANA_PASSWORD_FILE ./config/grafana_admin_password.disabled)")"
healthchecks_token="$(absolute_path "$(env_path HEALTHCHECKS_PROMETHEUS_TOKEN_FILE ./config/healthchecks_readonly_api_key.disabled)")"
healthchecks_targets="$(absolute_path "$(env_path HEALTHCHECKS_PROMETHEUS_TARGETS_FILE ./config/healthchecks_targets.empty.yml)")"
healthchecks_disabled_token="$(absolute_path ./config/healthchecks_readonly_api_key.disabled)"
healthchecks_disabled_targets="$(absolute_path ./config/healthchecks_targets.empty.yml)"
healthchecks_disabled=false
if [[ "$healthchecks_token" == "$healthchecks_disabled_token" \
  && "$healthchecks_targets" == "$healthchecks_disabled_targets" ]]; then
  healthchecks_disabled=true
fi

[[ -s "$grafana_password" ]] || die 'Grafana password file is missing or empty'
[[ -s "$healthchecks_token" ]] || die 'Healthchecks read-only key file is missing or empty'
[[ -s "$healthchecks_targets" ]] || die 'Healthchecks target file is missing or empty'

single_nonempty_line() {
  local path="$1"
  local description="$2"
  local count
  count="$(awk 'NF { count += 1 } END { print count + 0 }' "$path")"
  [[ "$count" -eq 1 ]] || die "$description must contain exactly one non-empty line"
}

single_nonempty_line "$grafana_password" 'Grafana password file'
single_nonempty_line "$healthchecks_token" 'Healthchecks key file'

if grep -Eq '^(not-configured|admin|change-me)[[:space:]]*$' "$grafana_password"; then
  die 'Grafana password file still contains a placeholder'
fi
if [[ "$healthchecks_disabled" == false ]]; then
  grep -Eq '^hcr_[A-Za-z0-9_-]+[[:space:]]*$' "$healthchecks_token" \
    || die 'Healthchecks key file does not contain a read-only hcr_ key'
  grep -q 'healthchecks.io' "$healthchecks_targets" \
    || die 'Healthchecks target file does not contain healthchecks.io'
fi
if grep -q 'replace-with-project-uuid' "$healthchecks_targets"; then
  die 'Healthchecks target file still contains the example project UUID'
fi

expected_state() {
  local path="$1"
  local owner="$2"
  local mode_bits="$3"
  local actual
  actual="$(stat -c '%u:%g %a' "$path")"
  [[ "$actual" == "$owner $mode_bits" ]] \
    || die "$(basename "$path") has $actual; expected $owner $mode_bits"
  ok "$(basename "$path"): $owner $mode_bits"
}

if [[ "$mode" == apply ]]; then
  [[ "${EUID:-$(id -u)}" -eq 0 ]] \
    || die 'run without --check as root (for example: sudo bash scripts/prepare_monitoring.sh)'

  chown 472:0 "$grafana_password"
  chmod 0400 "$grafana_password"
  if [[ "$healthchecks_disabled" == false ]]; then
    chown 65534:65534 "$healthchecks_token"
    chmod 0400 "$healthchecks_token"
    chown 0:0 "$healthchecks_targets"
    chmod 0644 "$healthchecks_targets"
  fi
fi

expected_state "$grafana_password" '472:0' '400'
if [[ "$healthchecks_disabled" == false ]]; then
  expected_state "$healthchecks_token" '65534:65534' '400'
  expected_state "$healthchecks_targets" '0:0' '644'
fi
ok "monitoring file permissions are ready ($mode mode)"
