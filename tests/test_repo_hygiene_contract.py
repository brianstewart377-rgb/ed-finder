from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ALLOWED_VISIBLE_ROOT_FILES = {
    'CHANGES.md',
    'docker-compose.local.yml',
    'docker-compose.review-hosted.yml',
    'docker-compose.review.yml',
    'docker-compose.yml',
    'ED_FINDER_JOURNAL_IMPORT_AND_COLONISATION_ROUTING_DESIGN_V1.md',
    'env.example',
    'Makefile',
    'pyproject.toml',
    'README.md',
    'setup.sh',
}


def _visible_root_files() -> set[str]:
    return {
        path.name
        for path in ROOT.iterdir()
        if path.is_file() and not path.name.startswith('.')
    }


def test_visible_repo_root_files_stay_on_the_allowlist():
    assert _visible_root_files() <= ALLOWED_VISIBLE_ROOT_FILES


def test_journal_design_root_doc_is_explicitly_marked_as_historical_reference():
    source = (ROOT / 'ED_FINDER_JOURNAL_IMPORT_AND_COLONISATION_ROUTING_DESIGN_V1.md').read_text(encoding='utf-8')

    assert 'Historical design reference kept at repo root' in source
    assert 'not a second roadmap or an active control' in source


def test_repo_hygiene_policy_exists_and_names_the_machine_guards():
    source = (ROOT / 'docs' / 'development' / 'repo-hygiene.md').read_text(encoding='utf-8')

    assert 'Repo Hygiene Contract' in source
    assert 'tests/test_bounded_hygiene_pass.py' in source
    assert 'tests/test_repo_hygiene_contract.py' in source
    assert 'Repo root is allowlist-only for visible files.' in source
