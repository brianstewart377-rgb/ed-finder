# Stage 18J Archived Wrappers

These Hetzner-only wrappers are preserved as historical operator artifacts after
the bounded hygiene pass moved them out of the top-level `scripts/operator/`
surface.

They are not part of the current day-to-day operator command set:

- `stage18j_run_compact_summary.sh`
- `stage18j_run_identity_review_packet.sh`
- `stage18j_run_identity_load_dry_run.sh`
- `stage18j_run_identity_approval_allowlist.sh`

The active Stage 19 safety wrappers remain in `scripts/operator/` because local
tests, preflight checks, and current safety documentation still validate them
directly.
