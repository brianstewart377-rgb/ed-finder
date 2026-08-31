#!/usr/bin/env bash
set -euo pipefail

readonly AGE_VERSION=1.3.2
readonly AGE_AMD64_SHA256=cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10
readonly HANDOFF_ROOT=/opt/octopus-handoff
die() { printf 'error: %s\n' "$*" >&2; exit 64; }
install_age() {
  local bin_dir=$1 archive
  mkdir -p "$bin_dir"; archive=$(mktemp)
  curl --fail --location --silent --show-error "https://github.com/FiloSottile/age/releases/download/v${AGE_VERSION}/age-v${AGE_VERSION}-linux-amd64.tar.gz" -o "$archive"
  printf '%s  %s\n' "$AGE_AMD64_SHA256" "$archive" | sha256sum -c - >/dev/null || die 'age archive checksum mismatch'
  tar -xzf "$archive" --strip-components=1 -C "$bin_dir" "age/age" "age/age-keygen"
  rm -f "$archive"; chmod 0700 "$bin_dir/age" "$bin_dir/age-keygen"
}
[[ $# -ge 1 ]] || die 'operation required'
operation=$1; shift
case "$operation" in
  init)
    [[ $# -eq 1 && $1 =~ ^[a-f0-9]{32}$ ]] || die 'transfer id must be 32 lowercase hex characters'
    transfer=$1; dir="$HANDOFF_ROOT/$transfer"; [[ ! -e $dir ]] || die 'transfer id already exists'
    umask 077; mkdir -p "$dir/bin"; chmod 0700 "$dir"; install_age "$dir/bin"
    "$dir/bin/age-keygen" -o "$dir/identity.age" 2>"$dir/recipient"; chmod 0600 "$dir/identity.age" "$dir/recipient"
    recipient=$(sed -n 's/^Public key: //p' "$dir/recipient"); [[ $recipient =~ ^age1[0-9a-z]{58}$ ]] || die 'age recipient generation failed'
    printf 'transfer_id: %s\nrecipient: %s\nprivate_key_location: new_host_only\n' "$transfer" "$recipient"
    ;;
  export)
    [[ $# -ge 3 ]] || die 'export requires RECIPIENT SOURCE CIPHERTEXT [HTPASSWD]'
    recipient=$1; source=$2; ciphertext=$3; htpasswd=${4:-}; [[ $recipient =~ ^age1[0-9a-z]{58}$ ]] || die 'invalid recipient'
    tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT; install_age "$tmp/bin"
    args=(export --source "$source" --output "$tmp/payload.json"); [[ -z $htpasswd ]] || args+=(--htpasswd "$htpasswd")
    python3 "$(dirname "$0")/octopus_credentials.py" "${args[@]}"
    "$tmp/bin/age" -r "$recipient" -o "$ciphertext" "$tmp/payload.json"; chmod 0600 "$ciphertext"
    rm -f "$tmp/payload.json"; printf 'ciphertext_created: true\nplaintext_artifact_created: false\n'
    ;;
  import)
    [[ $# -eq 2 ]] || die 'import requires TRANSFER_ID CIPHERTEXT'
    transfer=$1; ciphertext=$2; [[ $transfer =~ ^[a-f0-9]{32}$ ]] || die 'invalid transfer id'
    dir="$HANDOFF_ROOT/$transfer"; [[ -f $dir/identity.age && -f $ciphertext ]] || die 'handoff input missing'
    tmp=$(mktemp "$dir/plaintext.XXXXXX"); trap 'rm -f "$tmp" "$dir/identity.age"; rm -rf "$dir"' EXIT
    "$dir/bin/age" -d -i "$dir/identity.age" -o "$tmp" "$ciphertext"
    python3 "$(dirname "$0")/octopus_credentials.py" merge --payload "$tmp" --env /opt/octopus/octopus.env --htpasswd /opt/octopus/ui.htpasswd
    rm -f "$tmp" "$dir/identity.age"; rm -rf "$dir"; trap - EXIT
    printf 'credentials_merged: true\none_time_identity_destroyed: true\nworkers_enabled: false\n'
    ;;
  *) die 'unsupported handoff operation' ;;
esac
