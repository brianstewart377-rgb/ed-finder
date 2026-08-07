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

The query itself (manifest-driven manual-filename list vs. schema_migrations
ledger) was verified directly against real Postgres, not just as a string
match here: with both 019_nullable_coords.sql and
041_bodies_composite_identity_index.sql present in schema_migrations, the
query returns nothing; with 041 deleted (in a rolled-back transaction), it
correctly reports exactly that filename as pending.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def test_deploy_declares_a_warn_helper_distinct_from_say_ok_die():
    deploy = _read('scripts', 'deploy_main.sh')

    assert 'warn() { printf "[WARN] %s\\n" "$*" >&2; }' in deploy


def test_deploy_checks_for_pending_manual_migrations_after_apply():
    deploy = _read('scripts', 'deploy_main.sh')

    apply_index = deploy.index('bash scripts/apply_migrations.sh')
    ok_index = deploy.index('ok "migrations applied"')
    manual_check_index = deploy.index('Manual migration(s) pending')
    assert apply_index < ok_index < manual_check_index, (
        'the manual-migration check must run after apply_migrations.sh and '
        'after the "migrations applied" line — checking before either would '
        "mean it's inspecting stale ledger state"
    )

    # Reads the manifest and the real schema_migrations ledger, not a
    # hardcoded filename list — must stay in sync automatically as new
    # |manual entries are added to the manifest.
    assert "grep '|manual' sql/migration-manifest.txt" in deploy
    assert 'FROM schema_migrations' in deploy

    # A pending manual migration must be visible, not fatal — deploys with
    # a known-pending manual migration are a normal, expected state per
    # the migration plan's own multi-step rollout runbook.
    manual_block_end = deploy.index('else\n  say "Skipping SQL migrations"')
    manual_block = deploy[apply_index:manual_block_end]
    assert 'die ' not in manual_block
    assert 'warn "Manual migration(s) pending' in manual_block


def test_manual_migration_check_still_runs_if_none_are_pending():
    """The check must not assume there is always at least one |manual
    entry — an empty pending list must produce no output, not an error
    from malformed SQL (e.g. an empty ARRAY[] literal)."""
    deploy = _read('scripts', 'deploy_main.sh')

    assert 'if [[ -n "$pending_manual" ]]; then' in deploy


def test_zero_manual_entries_skips_the_query_entirely():
    """A manifest with no |manual lines at all must not reach the SQL
    query. Verified directly against real Postgres while writing this fix:
    `SELECT unnest(ARRAY[])` (no type cast) errors with "cannot determine
    type of empty array" — the original version of this check masked that
    with `2>/dev/null || true` rather than avoiding it. The bash-level
    guard here means the query is never attempted with an empty list, and
    the `::text[]` cast on the query itself is defense in depth."""
    deploy = _read('scripts', 'deploy_main.sh')

    assert 'if [[ -n "$manual_filenames_sql" ]]; then' in deploy
    assert '::text[]' in deploy
