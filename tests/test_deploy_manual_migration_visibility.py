"""Regression test for deploy_main.sh's silent manual-migration skip.

Emergent adversarial-review recurrence check (2026-08-07), item A4:
deploy_main.sh runs `bash scripts/apply_migrations.sh` with no
--include-manual, so every migration marked |manual in
sql/migration-manifest.txt is silently skipped — apply_migrations.sh only
logs an [INFO] line per skip, and deploy_main.sh still prints
"[OK] migrations applied" immediately after. Not passing --include-manual
by default is intentional (manual migrations are meant to be deployed in
their own separate, monitored window, not bundled into every normal
deploy — see docs/superpowers/plans/2026-08-05-bodies-composite-identity-
migration.md's rollout runbook), but the silence made a pending manual
migration easy to forget indefinitely. This adds a loud post-apply check
instead of changing which migrations actually run.

Two Codex Review findings on the first version of this fix, both stemming
from deploy_main.sh building and running its own psql query inline:
  1. `grep '|manual' sql/migration-manifest.txt` exits 1 on no match; under
     deploy_main.sh's `set -euo pipefail`, that silently killed the entire
     deploy the moment the manifest had zero |manual entries — verified
     directly (a minimal repro with the same grep|cut|sed|paste pipeline
     under set -euo pipefail exits 1 before reaching the next line).
  2. The inline query hardcoded `docker compose exec postgres` and
     `schema_migrations`, ignoring apply_migrations.sh's own
     DATABASE_MIGRATION_URL / MIGRATION_LEDGER_TABLE overrides — a
     configured override could make this check silently inspect the
     wrong database/ledger, made worse by the query's `2>/dev/null ||
     true` masking a real error as "nothing pending".

Both are fixed the same way: deploy_main.sh no longer runs any SQL of its
own. It delegates to a new `apply_migrations.sh --list-pending-manual`
mode, which reuses that script's own connection/ledger resolution
(fetch_recorded_checksum) and reads the manifest via a plain `while read`
loop with no grep-on-possibly-empty-input step to interact badly with
set -e. Verified directly against real Postgres in three states: both
current manual migrations applied (no output), one deleted (reported
pending, then restored), and a scratch manifest with zero |manual entries
(exit 0, no output, no crash — the exact case that broke under set -e).
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def test_deploy_declares_a_warn_helper_distinct_from_say_ok_die():
    deploy = _read('scripts', 'deploy_main.sh')

    assert 'warn() { printf "[WARN] %s\\n" "$*" >&2; }' in deploy


def test_deploy_delegates_the_pending_manual_check_to_the_applier():
    deploy = _read('scripts', 'deploy_main.sh')

    apply_index = deploy.index('bash scripts/apply_migrations.sh\n')
    ok_index = deploy.index('ok "migrations applied"')
    delegate_index = deploy.index('apply_migrations.sh --list-pending-manual')
    assert apply_index < ok_index < delegate_index, (
        'the manual-migration check must run after apply_migrations.sh and '
        'after the "migrations applied" line — checking before either would '
        "mean it's inspecting stale ledger state"
    )

    # No inline SQL, no direct docker/psql invocation, no manifest
    # parsing of its own — all of that lives in apply_migrations.sh now,
    # queried through its own connection/ledger resolution.
    assert 'docker compose exec' not in deploy[apply_index:delegate_index + 200]
    assert 'schema_migrations' not in deploy

    # A pending manual migration must be visible, not fatal — deploys with
    # a known-pending manual migration are a normal, expected state per
    # the migration plan's own multi-step rollout runbook.
    manual_block_end = deploy.index('else\n  say "Skipping SQL migrations"')
    manual_block = deploy[apply_index:manual_block_end]
    assert 'die ' not in manual_block
    assert 'warn "Manual migration(s) pending' in manual_block


def test_applier_exposes_a_read_only_list_pending_manual_mode():
    applier = _read('scripts', 'apply_migrations.sh')

    assert '--list-pending-manual' in applier
    assert 'LIST_PENDING_MANUAL_ONLY=1' in applier
    # Must reuse the same ledger lookup the normal apply path uses, not a
    # separate ad-hoc query — that's what guarantees it can never diverge
    # from a configured DATABASE_MIGRATION_URL / MIGRATION_LEDGER_TABLE.
    list_mode_start = applier.index('if [[ "$LIST_PENDING_MANUAL_ONLY" -eq 1 ]]')
    list_mode_end = applier.index('applied_count=0')
    list_mode_block = applier[list_mode_start:list_mode_end]
    assert 'fetch_recorded_checksum' in list_mode_block
    assert 'exit 0' in list_mode_block


def test_list_pending_manual_mode_reads_manifest_without_grep():
    """The while-read loop must parse the manifest directly, not pipe it
    through grep first — grep exits 1 on no match, and this script also
    runs under set -euo pipefail, so a grep-based approach here would
    reintroduce the exact bug this fix closes for a manifest with zero
    |manual entries."""
    applier = _read('scripts', 'apply_migrations.sh')

    list_mode_start = applier.index('if [[ "$LIST_PENDING_MANUAL_ONLY" -eq 1 ]]')
    list_mode_end = applier.index('applied_count=0')
    list_mode_block = applier[list_mode_start:list_mode_end]
    assert 'grep' not in list_mode_block
    assert "while IFS='|' read" in list_mode_block
