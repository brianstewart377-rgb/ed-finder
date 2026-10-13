#!/usr/bin/env bash
# Shared fail-closed F2d operator-code identity computation. Source this file,
# then call require_f2d_operator_code_identity before any action preflight.

F2D_OPERATOR_MANIFEST_RELATIVE_PATH="deploy/v3-production/f2d-operator-code.txt"

f2d_operator_identity_refuse() {
  printf 'f2d operator identity refusal: %s\n' "$*" >&2
  return 64
}

f2d_operator_code_sha256() {
  local repo_root="${1:-}"
  local LC_ALL=C
  local manifest entry previous="" path permissions digest
  local -a entries=() digests=()

  [ -n "$repo_root" ] && [ -d "$repo_root" ] \
    || { f2d_operator_identity_refuse "repository_root_invalid:${repo_root}"; return; }
  manifest="${repo_root}/${F2D_OPERATOR_MANIFEST_RELATIVE_PATH}"
  [ ! -L "$manifest" ] \
    || { f2d_operator_identity_refuse "listed_path_symlink:${F2D_OPERATOR_MANIFEST_RELATIVE_PATH}"; return; }
  [ -e "$manifest" ] \
    || { f2d_operator_identity_refuse "listed_path_missing:${F2D_OPERATOR_MANIFEST_RELATIVE_PATH}"; return; }
  [ -f "$manifest" ] \
    || { f2d_operator_identity_refuse "listed_path_not_regular:${F2D_OPERATOR_MANIFEST_RELATIVE_PATH}"; return; }
  permissions="$(stat -c '%A' -- "$manifest" 2>/dev/null)" \
    || { f2d_operator_identity_refuse "listed_path_unreadable:${F2D_OPERATOR_MANIFEST_RELATIVE_PATH}"; return; }
  [[ "${permissions:1:1}${permissions:4:1}${permissions:7:1}" == *r* ]] \
    || { f2d_operator_identity_refuse "listed_path_unreadable:${F2D_OPERATOR_MANIFEST_RELATIVE_PATH}"; return; }

  while IFS= read -r entry || [ -n "$entry" ]; do
    [ -n "$entry" ] || continue
    [[ "$entry" == \#* ]] && continue
    [ "$entry" = "${entry#"${entry%%[![:space:]]*}"}" ] \
      && [ "$entry" = "${entry%"${entry##*[![:space:]]}"}" ] \
      || { f2d_operator_identity_refuse "manifest_malformed:surrounding_whitespace"; return; }
    if [[ "$entry" == requirement:* ]]; then
      [[ "$entry" =~ ^requirement:psycopg\[binary\]==[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        || { f2d_operator_identity_refuse "manifest_malformed:invalid_requirement"; return; }
    else
      [[ "$entry" =~ ^[A-Za-z0-9._+/@-]+$ ]] \
        || { f2d_operator_identity_refuse "manifest_malformed:invalid_path"; return; }
      [[ "/$entry/" != */../* && "/$entry/" != */./* && "$entry" != /* ]] \
        || { f2d_operator_identity_refuse "manifest_malformed:unsafe_path"; return; }
    fi
    [ -z "$previous" ] || [[ "$entry" > "$previous" ]] \
      || {
        if [ "$entry" = "$previous" ]; then
          f2d_operator_identity_refuse "manifest_duplicate_entry"
        else
          f2d_operator_identity_refuse "manifest_not_sorted"
        fi
        return
      }
    entries+=("$entry")
    previous="$entry"
  done < "$manifest" || { f2d_operator_identity_refuse "manifest_unreadable"; return; }

  [ "${#entries[@]}" -gt 0 ] || { f2d_operator_identity_refuse "manifest_empty"; return; }
  local has_self=false
  for entry in "${entries[@]}"; do
    [ "$entry" = "$F2D_OPERATOR_MANIFEST_RELATIVE_PATH" ] && has_self=true
    if [[ "$entry" == requirement:* ]]; then
      digest="$(printf '%s' "$entry" | sha256sum | awk '{print $1}')" \
        || { f2d_operator_identity_refuse "requirement_hash_failed:${entry}"; return; }
    else
      path="${repo_root}/${entry}"
      [ ! -L "$path" ] \
        || { f2d_operator_identity_refuse "listed_path_symlink:${entry}"; return; }
      [ -e "$path" ] \
        || { f2d_operator_identity_refuse "listed_path_missing:${entry}"; return; }
      [ -f "$path" ] \
        || { f2d_operator_identity_refuse "listed_path_not_regular:${entry}"; return; }
      permissions="$(stat -c '%A' -- "$path" 2>/dev/null)" \
        || { f2d_operator_identity_refuse "listed_path_unreadable:${entry}"; return; }
      [[ "${permissions:1:1}${permissions:4:1}${permissions:7:1}" == *r* ]] \
        || { f2d_operator_identity_refuse "listed_path_unreadable:${entry}"; return; }
      digest="$(sha256sum -- "$path" 2>/dev/null | awk '{print $1}')" \
        || { f2d_operator_identity_refuse "listed_path_unreadable:${entry}"; return; }
    fi
    [[ "$digest" =~ ^[0-9a-f]{64}$ ]] \
      || { f2d_operator_identity_refuse "content_hash_invalid:${entry}"; return; }
    digests+=("$digest")
  done
  [ "$has_self" = true ] || { f2d_operator_identity_refuse "manifest_missing_self_entry"; return; }

  {
    printf '['
    local index
    for ((index = 0; index < ${#entries[@]}; index++)); do
      [ "$index" -eq 0 ] || printf ','
      printf '["%s","%s"]' "${entries[$index]}" "${digests[$index]}"
    done
    printf ']'
  } | sha256sum | awk '{print $1}'
}

require_f2d_operator_code_identity() {
  local repo_root="${1:-}"
  local attested="${2-${F2D_OPERATOR_CODE_SHA256_ATTESTED:-}}"
  local actual
  [ -n "$attested" ] \
    || { f2d_operator_identity_refuse "attested_identity_missing"; return; }
  [[ "$attested" =~ ^[0-9a-f]{64}$ ]] \
    || { f2d_operator_identity_refuse "attested_identity_malformed"; return; }
  actual="$(f2d_operator_code_sha256 "$repo_root")" || return
  [ "$actual" = "$attested" ] \
    || { f2d_operator_identity_refuse "attested_identity_mismatch:expected=${attested}:actual=${actual}"; return; }
  printf '%s\n' "$actual"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  case "${1:-}" in
    compute)
      [ "$#" -eq 2 ] || { f2d_operator_identity_refuse "usage:compute REPO_ROOT"; exit $?; }
      f2d_operator_code_sha256 "$2"
      ;;
    verify)
      [ "$#" -ge 2 ] && [ "$#" -le 3 ] \
        || { f2d_operator_identity_refuse "usage:verify REPO_ROOT [ATTESTED]"; exit $?; }
      require_f2d_operator_code_identity "$2" "${3-${F2D_OPERATOR_CODE_SHA256_ATTESTED:-}}"
      ;;
    *)
      f2d_operator_identity_refuse "usage:expected compute or verify"
      exit $?
      ;;
  esac
fi
