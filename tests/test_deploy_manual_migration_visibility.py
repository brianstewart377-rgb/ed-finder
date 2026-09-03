"""Contracts for manual-migration visibility after retiring the V2 deploy wrapper.

The manifest/ledger query remains useful repository tooling, but the former
`scripts/deploy_main.sh` consumer is intentionally dead. Keep the applier's
read-only pending-manual mode safe without requiring a production deploy path.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def test_v2_deploy_wrapper_is_fail_closed_and_does_not_query_migrations():
    deploy = _read('scripts', 'deploy_main.sh')

    assert 'RETIRED — V2 single-host deployment entrypoint' in deploy
    assert 'exit 64' in deploy
    assert 'apply_migrations.sh' not in deploy
    assert '--list-pending-manual' not in deploy
    assert 'docker compose' not in deploy
    assert 'psql' not in deploy


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
    runs under set -euo pipefail."""
    applier = _read('scripts', 'apply_migrations.sh')

    list_mode_start = applier.index('if [[ "$LIST_PENDING_MANUAL_ONLY" -eq 1 ]]')
    list_mode_end = applier.index('applied_count=0')
    list_mode_block = applier[list_mode_start:list_mode_end]
    assert 'grep' not in list_mode_block
    assert "while IFS='|' read" in list_mode_block
