#!/usr/bin/env bash
set -euo pipefail

REVIEW_REPO_DIR="${REVIEW_REPO_DIR:-/opt/ed-finder-review}"
AUTH_FILE="${REVIEW_AUTH_FILE:-$REVIEW_REPO_DIR/.secrets/review.htpasswd}"
USERNAME="${REVIEW_AUTH_USER:-review}"
FORCE=0

usage() {
  cat <<'USAGE'
Usage:
  scripts/ops/create_review_auth_file.sh [--user USERNAME] [--path AUTH_FILE] [--force]

Creates the hosted-review HTTP basic-auth file with a bcrypt htpasswd entry.
The password is prompted interactively and is not echoed.

Defaults:
  USERNAME  review
  AUTH_FILE /opt/ed-finder-review/.secrets/review.htpasswd
USAGE
}

die() {
  printf '[ERROR] %s\n' "$*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      USERNAME="$2"
      shift 2
      ;;
    --path)
      AUTH_FILE="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ "$USERNAME" =~ ^[A-Za-z0-9._-]+$ ]] || die 'username may contain only letters, numbers, dot, underscore, and dash'
command -v htpasswd >/dev/null || die 'htpasswd is required; install apache2-utils and rerun'

if [[ -e "$AUTH_FILE" && "$FORCE" -ne 1 ]]; then
  die "$AUTH_FILE already exists; pass --force to replace it intentionally"
fi

printf 'Review username: %s\n' "$USERNAME"
read -r -s -p 'Review password: ' PASSWORD
printf '\n'
read -r -s -p 'Confirm review password: ' PASSWORD_CONFIRM
printf '\n'

[[ -n "$PASSWORD" ]] || die 'password must not be empty'
[[ "$PASSWORD" == "$PASSWORD_CONFIRM" ]] || die 'passwords did not match'

AUTH_DIR="$(dirname "$AUTH_FILE")"
umask 077
mkdir -p "$AUTH_DIR"
chmod 700 "$AUTH_DIR"

TMP_FILE="$(mktemp "$AUTH_DIR/.review.htpasswd.XXXXXX")"
trap 'rm -f "$TMP_FILE"' EXIT

printf '%s\n' "$PASSWORD" | htpasswd -B -C 12 -i -c "$TMP_FILE" "$USERNAME" >/dev/null
install -m 600 "$TMP_FILE" "$AUTH_FILE"

unset PASSWORD PASSWORD_CONFIRM

printf '[OK] wrote %s with mode 600\n' "$AUTH_FILE"
