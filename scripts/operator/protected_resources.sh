# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/protected_resources.env"

# Refuse to remove any volume whose EXACT name is protected, unless the explicit
# override env is set to the retention id. Fail-closed: any protected match exits 1.
# Usage: protected_volumes_refuse <space-separated volume names>
protected_volumes_refuse() {
  local v p
  for v in $1; do
    for p in $EDFINDER_PROTECTED_VOLUMES; do
      if [[ "$v" == "$p" ]]; then
        if [[ "${EDFINDER_ALLOW_PROTECTED_CLEANUP:-}" == "$EDFINDER_PROTECTED_RETENTION_ID" ]]; then
          echo "PROTECTED_CLEANUP_OVERRIDE: $v" >&2
          return 0
        fi
        echo "REFUSE: volume '$v' is a PROTECTED retained resource (V3 r5 production-candidate canonical dataset)." >&2
        echo "Set EDFINDER_ALLOW_PROTECTED_CLEANUP=${EDFINDER_PROTECTED_RETENTION_ID} to override (separate explicit owner authorization required)." >&2
        exit 1
      fi
    done
  done
}
