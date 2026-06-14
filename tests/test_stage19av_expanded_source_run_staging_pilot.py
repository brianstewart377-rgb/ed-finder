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
ROADMAP_PATH = DOCS / 'stage-19-data-warehouse-utopia-roadmap.md'
AV_DOC_PATH = DOCS / 'stage-19av-expanded-source-run-staging-pilot.md'
AV_SCRIPT_PATH = OPERATOR_SCRIPTS / 'stage19av_expanded_source_run_staging_pilot.py'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


@pytest.mark.unit
def test_stage19av_keeps_authority_paused_until_pilot_succeeds():
    authority = json.loads(_read(AUTHORITY_PATH))
    av_doc = _squash(_read(AV_DOC_PATH))
    roadmap = _squash(_read(ROADMAP_PATH))

    assert authority['stage19'] == {
        'status': 'paused',
        'stage19as_au_status': 'completed',
    }
    assert 'stage19av_completed_checkpoint' not in authority
    assert 'Stage 19AV is the selected bounded write lane after Stage 19AU.' in av_doc
    assert 'The Stage 19AV bounded write was not run in this checkpoint' in av_doc
    assert 'Stage 19 remains paused.' in av_doc
    assert 'No canonical apply is complete.' in av_doc
    assert 'No rebaseline is complete.' in av_doc
    assert 'Stage 19AV is the selected expanded controlled source-run staging pilot lane after Stage 19AU.' in roadmap
    assert 'This preparation checkpoint does not run the AV bounded write.' in roadmap


@pytest.mark.unit
def test_stage19av_wrapper_has_stage_specific_bounded_profile():
    profile = stage19av.STAGE19AV_PROFILE
    args = stage19av.parse_args(['--git-head', 'abc1234'])

    assert args.commit is False
    assert args.confirm_stage19av is False
    assert args.limit == 250
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
        stage19av.parse_args(['--limit', '251'])

    with pytest.raises(SystemExit):
        stage19av.parse_args(['--commit'])

    args = stage19av.parse_args(['--commit', '--confirm-stage19av'])

    assert args.commit is True
    assert args.confirm_stage19av is True
    assert args.limit == 250


@pytest.mark.unit
def test_stage19av_refuses_database_url_and_keeps_preflight_redacted():
    args = argparse.Namespace(
        db_host='127.0.0.1',
        db_port='55432',
        db_name='edfinder',
        db_user='edfinder',
        secrets_file=None,
    )
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
