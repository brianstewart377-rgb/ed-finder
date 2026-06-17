from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
README_PATH = DOCS / 'README.md'
STAGE21_CLOSEOUT_PATH = DOCS / 'stage-21-closeout.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'

P_FILTER_PATH = DOCS / 'stage-18j-p-filter-strict-station-type-dry-run-filter.md'
P_DRYRUN_OPS_PATH = DOCS / 'stage-18j-p-dryrun-operator-safe-wrapper.md'
P2_PATH = DOCS / 'stage-18j-p2-station-type-identity-coverage-diagnostics.md'
P7_PATH = DOCS / 'stage-18j-p7-external-identity-schema-production-apply-closeout.md'
P15_PATH = DOCS / 'stage-18j-p15-identity-load-production-closeout.md'
P16A_PATH = DOCS / 'stage-18j-p16a-readonly-reconciliation-integration.md'
P18M_PATH = DOCS / 'stage-18j-p18m-dodec-and-bounded-station-type-write-closeout.md'
P18N_PATH = DOCS / 'stage-18j-p18n-final-state-snapshot.md'

OPERATOR_DRY_RUN_SCRIPT = ROOT / 'scripts' / 'operator' / 'stage18j_run_station_type_dry_run.sh'
MIGRATION_SQL = ROOT / 'sql' / '027_station_external_identity.sql'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _json(path: Path):
    return json.loads(_read(path))


def test_stage18jp_authority_records_strict_filter_and_bounded_batch_closeout():
    authority = _json(AUTHORITY_PATH)

    assert authority['stage21']['next_checkpoint'] is None

    stage18jpfilter = authority['stage18jpfilter']
    assert stage18jpfilter['status'] == 'completed'
    assert stage18jpfilter['strict_filter_implemented'] is True
    assert stage18jpfilter['identity_proof_required'] is True
    assert stage18jpfilter['identity_proof_sources'] == ['market_id', 'edsm_station_id']
    assert stage18jpfilter['dry_run_only'] is True

    assert authority['stage18jpdryrunops']['operator_wrapper_present'] is True
    assert authority['stage18jp2']['identity_coverage_summary_supported'] is True
    assert authority['stage18jp7']['station_external_identity_table_present'] is True
    assert authority['stage18jp15']['station_external_identity_rows_written'] == 20
    assert authority['stage18jp16a']['read_only_artifact_generated'] is True
    assert authority['stage18jp18m']['bounded_station_type_rows_updated'] == 4
    assert authority['stage18jp18n']['stage18_complete_for_bounded_batch'] is True


def test_stage18jp_docs_scripts_migration_and_ci_parity_exist():
    readme = _read(README_PATH)
    closeout = _read(STAGE21_CLOSEOUT_PATH)
    parity = _read(LOCAL_CI_PARITY)

    for path in (
        P_FILTER_PATH,
        P_DRYRUN_OPS_PATH,
        P2_PATH,
        P7_PATH,
        P15_PATH,
        P16A_PATH,
        P18M_PATH,
        P18N_PATH,
        OPERATOR_DRY_RUN_SCRIPT,
        MIGRATION_SQL,
    ):
        assert path.exists()

    assert 'stage-18j-p18n-final-state-snapshot.md' in readme
    assert 'Stage 18J-P18 is complete for the bounded reviewed batch' in closeout
    assert 'Stage 19 production' in closeout
    assert 'activation remains deferred.' in closeout

    for fragment in (
        'tests/test_stage18jp_station_type_production_chain_closeout.py',
        'tests/test_station_external_identity_migration.py',
        'tests/test_station_external_identity_loader.py',
        'tests/test_station_external_identity_review_packet.py',
        'tests/test_station_external_identity_approval_allowlist.py',
        'tests/test_station_external_identity_candidates.py',
        'tests/test_station_external_identity_load_plan.py',
    ):
        assert fragment in parity
