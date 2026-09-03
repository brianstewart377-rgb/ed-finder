# Stage 18J Retired Wrapper Manifest

The Stage 18J shell wrappers below were Hetzner-only operator entry points. They were first moved out of, or historically remained within, the top-level `scripts/operator/` surface and are now fully retired as part of the V2/Hetzner decommission.

Their former filenames are retained here as historical evidence only; the runnable wrapper bodies are intentionally not carried into the V3 repository surface:

- `stage18j_run_compact_summary.sh`
- `stage18j_run_identity_review_packet.sh`
- `stage18j_run_identity_load_dry_run.sh`
- `stage18j_run_identity_approval_allowlist.sh`
- `stage18j_run_station_type_dry_run.sh`

Do not recreate or execute these wrappers from Git history. Historical Stage 18 reasoning remains available in the stage documents, state-authority snapshots, tests of the underlying bounded Python contracts, and repository history.

The surviving Stage 19 Python tools remain repository staging/research tooling because current tests and documentation still validate their bounded contracts. Their presence is not V3 production authorization.
