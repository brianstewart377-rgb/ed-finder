from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ALLOWED_VISIBLE_ROOT_FILES = {
    'CHANGES.md',
    'CLAUDE.md',
    'docker-compose.local.yml',
    'docker-compose.review-hosted.yml',
    'docker-compose.review.yml',
    'docker-compose.yml',
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


def test_journal_design_doc_lives_under_colonisation_docs():
    source = (ROOT / 'docs' / 'colonisation-redesign' / 'journal-import-and-colonisation-routing-design-v1.md').read_text(encoding='utf-8')

    assert 'Feature Design Report: Journal Import & Colonisation Proximity Routing (V1)' in source
    assert 'retained under `docs/colonisation-redesign/`' in source


def test_repo_hygiene_policy_exists_and_names_the_machine_guards():
    source = (ROOT / 'docs' / 'development' / 'repo-hygiene.md').read_text(encoding='utf-8')

    assert 'Repo Hygiene Contract' in source
    assert 'tests/test_bounded_hygiene_pass.py' in source
    assert 'tests/test_repo_hygiene_contract.py' in source
    assert 'Repo root is allowlist-only for visible files.' in source
