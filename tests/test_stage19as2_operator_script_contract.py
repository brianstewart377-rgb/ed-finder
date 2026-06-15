import ast
import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'colonisation-redesign'
AUTHORITY_PATH = DOCS / 'stage-19-state-authority.json'
ROADMAP_PATH = DOCS / 'stage-19-data-warehouse-utopia-roadmap.md'
CONTRACT_DOC_PATH = DOCS / 'stage-19as2-operator-script-contract.md'
LOCAL_CI_PARITY = ROOT / 'scripts' / 'checks' / 'local-ci-parity.sh'

OPERATOR_SCRIPTS = {
    'Stage 19AR': ROOT / 'scripts' / 'operator' / 'stage19ar_edsm_25_row_staging_pilot.py',
    'Stage 19AS-AU': ROOT / 'scripts' / 'operator' / 'stage19as_au_edsm_100_row_controlled_expansion.py',
    'Stage 19AN-R': ROOT / 'scripts' / 'operator' / 'stage19anr_warehouse_derived_staging_rehearsal.py',
    'Stage 19AV': ROOT / 'scripts' / 'operator' / 'stage19av_expanded_source_run_staging_pilot.py',
}


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


def _ast_value(node: ast.AST) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    return ast.unparse(node)


def _parser_options(path: Path) -> dict[str, dict[str, object]]:
    tree = ast.parse(_read(path), filename=str(path))
    options: dict[str, dict[str, object]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != 'add_argument':
            continue
        names = [
            arg.value
            for arg in node.args
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        ]
        keywords = {
            keyword.arg: _ast_value(keyword.value)
            for keyword in node.keywords
            if keyword.arg is not None
        }
        for name in names:
            options[name] = keywords
    return options


@pytest.mark.unit
def test_stage19as2_authority_keeps_asau_and_as1_recorded_while_paused():
    authority = json.loads(_read(AUTHORITY_PATH))
    as1_doc = _read(DOCS / 'stage-19as1-disposable-postgres-constraint-tests.md')

    assert authority['stage19'] == {
        'status': 'paused',
        'stage19as_au_status': 'completed',
    }
    assert authority['stage19as_au_completed_checkpoint']['status'] == 'completed'
    assert authority['stage19as_au_completed_checkpoint']['canonical_writes_performed'] is False
    assert authority['stage19as_au_completed_checkpoint']['stage19_remains_paused'] is True

    assert 'Stage 19AS.1 adds the next safety-test checkpoint' in as1_doc
    assert 'Stage 19 remains paused.' in as1_doc
    assert 'No canonical apply is complete.' in as1_doc
    assert 'No rebaseline is complete.' in as1_doc


@pytest.mark.unit
def test_stage19as2_contract_doc_records_repo_only_safety_boundary():
    contract_doc = _read(CONTRACT_DOC_PATH)
    compact_contract_doc = _squash(contract_doc)
    roadmap = _read(ROADMAP_PATH)

    for fragment in (
        'Stage 19AS.2 - Operator Script Contract Formalization',
        'Stage 19AS-AU is complete and recorded.',
        'Stage 19AS.1 is complete and recorded.',
        'Stage 19 remains paused.',
        'No canonical apply is complete.',
        'No rebaseline is complete.',
        'does not run Stage 19 operator commands',
        'connect to a database',
        'use host `5432` as a direct committed Stage 19 target',
    ):
        assert fragment in compact_contract_doc

    assert 'Stage 19AS.2 now formalizes the operator-script contract' in roadmap
    assert 'stage-19as2-operator-script-contract.md' in roadmap


@pytest.mark.unit
def test_operator_script_cli_contracts_are_commit_gated_and_artifact_explicit():
    for stage, path in OPERATOR_SCRIPTS.items():
        options = _parser_options(path)

        assert options['--commit']['action'] == 'store_true', stage
        assert options['--commit'].get('default') is not True, stage
        assert '--limit' in options, stage
        assert '--artifact-dir' in options, stage

        artifact = options['--artifact-dir']
        assert artifact.get('required') is True or 'default' in artifact, stage

        for db_option in ('--db-host', '--db-port', '--db-name', '--db-user'):
            assert db_option in options, f'{stage} missing {db_option}'

        source = _read(path)
        assert 'commit=args.commit' in source, stage
        assert 'set_connection_mode(conn, commit=args.commit)' in source, stage
        assert re.search(r'\brollback\(conn\)|\bpilot\.rollback\(conn\)', source), stage


@pytest.mark.unit
def test_committed_pilot_scripts_keep_hard_limits_and_validation_contracts():
    stage19ar = _read(OPERATOR_SCRIPTS['Stage 19AR'])
    stage19as_au = _read(OPERATOR_SCRIPTS['Stage 19AS-AU'])
    stage19anr = _read(OPERATOR_SCRIPTS['Stage 19AN-R'])
    stage19av = _read(OPERATOR_SCRIPTS['Stage 19AV'])
    contract_doc = _read(CONTRACT_DOC_PATH)

    assert 'HARD_MAX_LIMIT = 25' in stage19ar
    assert 'if args.limit > HARD_MAX_LIMIT' in stage19ar
    assert 'if commit and limit != profile.default_limit' in stage19ar
    assert 'verify_artifact_directory_writable' in stage19ar

    assert 'hard_max_limit=100' in stage19as_au
    assert 'if args.limit > STAGE19AS_AU_PROFILE.hard_max_limit' in stage19as_au
    assert 'verify_canonical_stage19ar_baseline(conn)' in stage19as_au
    assert "secrets_values_printed': False" in stage19as_au

    assert "parser.add_argument('--artifact-dir', required=True" in stage19anr
    assert 'Stage 19AN-R' in contract_doc
    assert 'only a lower-bound `--limit` check' in contract_doc

    assert 'STAGE19AV_LIMIT = 250' in stage19av
    assert 'hard_max_limit=STAGE19AV_LIMIT' in stage19av
    assert 'if args.limit > STAGE19AV_PROFILE.hard_max_limit' in stage19av
    assert "'--confirm-stage19av'" in stage19av
    assert '--confirm-stage19av is required with --commit' in stage19av
    assert 'DATABASE_URL must be unset for Stage 19AV operator commands' in stage19av
    assert 'direct host 5432 target is blocked for Stage 19AV' in stage19av
    assert 'Stage 19AV DB target must be exactly 127.0.0.1:55432' in stage19av
    assert 'verify_stage19av_prerequisites(conn)' in stage19av
    assert 'stage19av_expanded_source_run_staging_pilot.py' in contract_doc

    for stage, source in (
        ('Stage 19AR', stage19ar),
        ('Stage 19AN-R', stage19anr),
    ):
        for fragment in (
            'write_operator_artifact',
            '_summary_for_stdout',
            'validation_checks',
            "'canonical_table_writes_performed_by_script': False",
            'assert_validation_passes',
            'source_run_artifact_hash_matches',
            'source_run_artifact_integrity_matches',
            'staging_rows_preserve_canonical_write_block',
        ):
            assert fragment in source, f'{stage} missing {fragment}'

    assert 'pilot.run_pilot(' in stage19as_au
    assert 'STAGE19AS_AU_PROFILE' in stage19as_au


@pytest.mark.unit
def test_operator_scripts_do_not_add_scheduler_canonical_apply_or_shell_dispatches():
    disallowed = [
        re.compile(r'\bsystemctl\b', re.IGNORECASE),
        re.compile(r'(?<![A-Za-z0-9_])\.(?:timer|service)(?![A-Za-z0-9_])', re.IGNORECASE),
        re.compile(r'\bcanonical_apply\b', re.IGNORECASE),
        re.compile(r'\bshell\s*=\s*True\b'),
        re.compile(r'\bproduction_import_run\s*:\s*True\b'),
    ]

    for stage, path in OPERATOR_SCRIPTS.items():
        source = _read(path)
        for pattern in disallowed:
            assert not pattern.search(source), f'{stage} matched {pattern.pattern}'


@pytest.mark.unit
def test_local_ci_parity_includes_as2_without_operator_commands():
    parity = _read(LOCAL_CI_PARITY)

    assert 'tests/test_stage19as2_operator_script_contract.py' in parity
    assert 'scripts/operator/stage19' not in parity
    assert '--commit' not in parity
