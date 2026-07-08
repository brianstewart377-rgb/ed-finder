import argparse
import json
import re
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
OPERATOR_SCRIPTS = ROOT / 'scripts' / 'operator'
if str(OPERATOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATOR_SCRIPTS))

import stage19av_expanded_source_run_staging_pilot as stage19av  # noqa: E402


AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
ROADMAP_PATH = ROOT / 'docs' / 'ROADMAP.md'
AV_DOC_PATH = DOCS / 'stage-19av-expanded-source-run-staging-pilot.md'
AV_SCRIPT_PATH = OPERATOR_SCRIPTS / 'stage19av_expanded_source_run_staging_pilot.py'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


def _db_args(host: str = '127.0.0.1', port: str = '55432') -> argparse.Namespace:
    return argparse.Namespace(
        db_host=host,
        db_port=port,
        db_name='edfinder',
        db_user='edfinder',
        secrets_file=None,
    )


@pytest.mark.unit
def test_stage19av_records_completed_pilot_while_stage19_remains_paused():
    authority = json.loads(_read(AUTHORITY_PATH))
    checkpoint = authority['stage19av_completed_checkpoint']
    av_doc = _squash(_read(AV_DOC_PATH))
    roadmap = _squash(_read(ROADMAP_PATH))

    assert authority['stage19'] == {
        'status': 'paused',
        'stage19as_au_status': 'completed',
    }
    assert checkpoint['status'] == 'completed'
    assert checkpoint['safe_db_target'] == '127.0.0.1:55432'
    assert checkpoint['source_run_key'] == 'stage19av-expanded-source-run-staging-pilot-48688d9d46067867'
    assert checkpoint['bridge_key'] == 'source_runs:stage19av-expanded-source-run-staging-pilot-48688d9d46067867'
    assert checkpoint['artifact'] == '09652a1c6e6ad661415f535a713432b0d3a76aef5b8c931c0b1874e1c52604f4'
    assert checkpoint['operator_artifact'] == 'b2d7f2649b68d9ededb965dd8442f37399bb90a1327c934ea8145258759068a1'
    assert checkpoint['staging_prerequisite_source_run_key'] == (
        '7fe4382fbde60752e026b576d92e0352c01d85799613884d2b2e7ee57cd3f5f3'
    )
    assert checkpoint['staging_prerequisite_rows'] == 125
    assert checkpoint['rows_read'] == 250
    assert checkpoint['rows_staged'] == 250
    assert checkpoint['rows_rejected'] == 0
    assert checkpoint['rows_skipped'] == 0
    assert checkpoint['canonical_writes_performed'] is False
    assert checkpoint['approved_stage19ar_baseline_preserved'] is True
    assert checkpoint['stage19as_au_checkpoint_preserved'] is True
    assert checkpoint['stage19au_verification_preserved'] is True
    assert checkpoint['post_run_live_verification_passed'] is True
    assert checkpoint['stage19_remains_paused'] is True

    assert 'Stage 19AV is the selected bounded write lane after Stage 19AU.' in av_doc
    assert 'This checkpoint records the successful Stage 19AV bounded write' in av_doc
    assert 'Stage 19AV was run on `2026-06-15T06:21:02Z`' in av_doc
    assert 'canonical writes performed: `false`' in av_doc
    assert 'Stage 19 remains paused.' in av_doc
    assert 'No canonical apply is complete.' in av_doc
    assert 'No rebaseline is complete.' in av_doc
    assert 'Stage 19AV is the completed expanded controlled source-run staging pilot lane after Stage 19AU.' in roadmap
    assert '250 read, 250 staged, 0 rejected, and 0 skipped' in roadmap


@pytest.mark.unit
def test_stage19av_wrapper_has_stage_specific_bounded_profile():
    profile = stage19av.STAGE19AV_PROFILE
    args = stage19av.parse_args(['--git-head', 'abc1234', '--limit', '250'])

    assert args.commit is False
    assert args.confirm_stage19av is False
    assert args.limit == 250
    assert args.db_host == '127.0.0.1'
    assert args.db_port == '55432'
    assert args.trigger_context == 'stage19av_expanded_source_run_staging_pilot'
    assert profile.default_limit == 250
    assert profile.hard_max_limit == 250
    assert profile.source_run_key_prefix == 'stage19av-expanded-source-run-staging-pilot-'
    assert profile.source_run_prefixes == ('stage19av-', 'stage-19av-')
    assert profile.provenance_marker_key == 'stage19av_expanded_source_run_staging_pilot'
    assert profile.artifact_dir == Path('/var/lib/ed-finder/operator-artifacts/stage-19av')
    assert profile.bridge_metadata['stage19as_au_checkpoint_preserved'] is True
    assert profile.bridge_metadata['stage19au_readonly_db_verification_required'] is True
    assert profile.bridge_metadata['rows_expected'] == 250


@pytest.mark.unit
def test_stage19av_rejects_unbounded_or_unconfirmed_committed_invocations():
    with pytest.raises(SystemExit):
        stage19av.parse_args([])

    with pytest.raises(SystemExit):
        stage19av.parse_args(['--limit', '251'])

    with pytest.raises(SystemExit):
        stage19av.parse_args(['--limit', '250', '--commit'])

    args = stage19av.parse_args(['--limit', '250', '--commit', '--confirm-stage19av'])

    assert args.commit is True
    assert args.confirm_stage19av is True
    assert args.limit == 250


@pytest.mark.unit
def test_stage19av_refuses_database_url_and_keeps_preflight_redacted():
    args = _db_args()
    env = {
        'DATABASE_URL': 'postgresql://edfinder:do-not-print-this@127.0.0.1:55432/edfinder',
        'POSTGRES_PASSWORD': 'do-not-print-this',
    }

    with pytest.raises(stage19av.pilot.Stage19ArPilotError, match='DATABASE_URL must be unset'):
        stage19av.build_db_dsn(args, env=env)

    result = stage19av.run_db_preflight(args, env=env)
    encoded = json.dumps(result, sort_keys=True)

    assert result['auth_success'] is False
    assert result['performed_no_writes'] is True
    assert result['secrets_redacted'] is True
    assert result['failure_category'] == 'database_url_must_be_unset'
    assert 'do-not-print-this' not in encoded
    assert 'postgresql://' not in encoded


@pytest.mark.unit
def test_stage19av_accepts_only_the_approved_safe_local_target():
    args = _db_args()
    env = {
        'POSTGRES_PASSWORD': 'do-not-print-this',
    }

    stage19av.assert_safe_stage19av_target(args, env=env)


@pytest.mark.unit
@pytest.mark.parametrize(
    ('host', 'port', 'match'),
    [
        ('127.0.0.1', '5432', 'direct host 5432 target'),
        ('localhost', '5432', 'direct host 5432 target'),
        ('::1', '5432', 'direct host 5432 target'),
        ('0.0.0.0', '5432', 'direct host 5432 target'),
        ('localhost', '55432', 'exactly 127.0.0.1:55432'),
        ('::1', '55432', 'exactly 127.0.0.1:55432'),
        ('10.0.0.10', '55432', 'exactly 127.0.0.1:55432'),
        ('192.168.1.10', '55432', 'exactly 127.0.0.1:55432'),
        ('203.0.113.10', '55432', 'exactly 127.0.0.1:55432'),
        ('prod-db.internal', '55432', 'exactly 127.0.0.1:55432'),
        ('127.0.0.1', '5433', 'exactly 127.0.0.1:55432'),
    ],
)
def test_stage19av_rejects_direct_5432_non_local_and_production_like_targets(host, port, match):
    with pytest.raises(stage19av.pilot.Stage19ArPilotError, match=match):
        stage19av.assert_safe_stage19av_target(_db_args(host=host, port=port), env={})


@pytest.mark.unit
def test_stage19av_rejects_environment_driven_unsafe_targets():
    args = _db_args()
    unsafe_env = {
        'POSTGRES_PASSWORD': 'do-not-print-this',
        'PGHOST': '127.0.0.1',
        'PGPORT': '5432',
    }
    with pytest.raises(stage19av.pilot.Stage19ArPilotError, match='direct host 5432 target'):
        stage19av.build_db_dsn(args, env=unsafe_env)

    unsafe_result = stage19av.run_db_preflight(args, env=unsafe_env)
    unsafe_encoded = json.dumps(unsafe_result, sort_keys=True)

    assert unsafe_result['auth_success'] is False
    assert unsafe_result['performed_no_writes'] is True
    assert unsafe_result['failure_category'] == 'host_5432_direct_target_blocked'
    assert 'do-not-print-this' not in unsafe_encoded

    production_like_env = {
        'POSTGRES_PASSWORD': 'do-not-print-this',
        'PGHOST': 'prod-db.internal',
        'PGPORT': '55432',
    }
    with pytest.raises(stage19av.pilot.Stage19ArPilotError, match='exactly 127.0.0.1:55432'):
        stage19av.build_db_dsn(args, env=production_like_env)

    production_like_result = stage19av.run_db_preflight(args, env=production_like_env)

    assert production_like_result['auth_success'] is False
    assert production_like_result['performed_no_writes'] is True
    assert production_like_result['failure_category'] == 'stage19av_safe_target_required'


@pytest.mark.unit
def test_stage19av_docs_and_script_keep_forbidden_work_blocked():
    av_doc = _squash(_read(AV_DOC_PATH))
    source = _read(AV_SCRIPT_PATH)

    for fragment in (
        'Stage 19AR with `--commit`',
        'Stage 19AS-AU with `--commit`',
        'unbounded source batches',
        'canonical table writes',
        'canonical apply',
        'rebaseline',
        'scheduler, timer, or service-manager work',
        'production-like DB targets',
        'host `5432` as a direct Stage 19 target',
        'runtime source JSON or operator artifact JSON commits',
        'Any future write-capable lane after Stage 19AV requires a separate explicit operator decision.',
    ):
        assert fragment in av_doc

    for fragment in (
        'pilot.run_pilot(',
        'profile=STAGE19AV_PROFILE',
        'verify_stage19av_prerequisites(conn)',
        'assert_stage19av_prerequisites(prereqs)',
        'DATABASE_URL must be unset for Stage 19AV operator commands',
        'direct host 5432 target is blocked for Stage 19AV',
        'Stage 19AV DB target must be exactly 127.0.0.1:55432',
        'stage19av_safe_target_required',
        'host_5432_direct_target_blocked',
        "'canonical_writes_zero'",
        "'scheduler_disabled'",
        "'production_db_access_false'",
    ):
        assert fragment in source

    assert 'systemctl' not in source.lower()
    assert re.search(r'(?<![A-Za-z0-9_])\.(?:timer|service)(?![A-Za-z0-9_])', source) is None


@pytest.mark.unit
def test_stage19av_local_ci_parity_registration_is_static_only():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage19av_expanded_source_run_staging_pilot.py' in parity
    assert 'scripts/operator/stage19' not in parity
    assert '--commit' not in parity

