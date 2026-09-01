from pathlib import Path
import subprocess
import tempfile


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
    'THIRD_PARTY_NOTICES.md',
}


def _visible_root_files() -> set[str]:
    result = subprocess.run(
        ['git', '-C', str(ROOT), 'ls-files', '--'],
        capture_output=True,
        text=True,
        check=True,
    )
    return {
        Path(line).name
        for line in result.stdout.splitlines()
        if line
        and '/' not in line.replace('\\', '/')
        and not Path(line).name.startswith('.')
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
    assert 'Repo root is allowlist-only for tracked visible files.' in source


def _octopus_ignored_paths(paths: set[str]) -> set[str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        sandbox = Path(temp_dir)
        subprocess.run(
            ['git', 'init', '--quiet', str(sandbox)],
            check=True,
        )
        (sandbox / '.gitignore').write_text(
            (ROOT / '.octopusignore').read_text(encoding='utf-8'),
            encoding='utf-8',
        )
        result = subprocess.run(
            ['git', '-C', str(sandbox), 'check-ignore', '--no-index', *sorted(paths)],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode in {0, 1}
    return set(result.stdout.splitlines())


def test_octopus_ignore_excludes_only_review_noise():
    expected_noise = {
        'frontend/dist/assets/app.js',
        'frontend/src/types/api.gen.ts',
        'docs/development/evidence/example/browser.png',
        'artifacts/map-foundation/example/screenshot.jpg',
        'captured-review.patch',
    }
    protected_review_targets = {
        '.github/workflows/ci.yml',
        'apps/api/src/main.py',
        'config/grafana/provisioning/dashboards/default.yml',
        'docker-compose.yml',
        'env.example',
        'frontend/package.json',
        'frontend/yarn.lock',
        'frontend/public/assets/elite-dangerous-region-map.svg',
        'scripts/apply_migrations.sh',
        'sql/001_initial_schema.sql',
        'tests/fixtures/edsm_body_ring_snapshot.json',
        'tests/test_repo_hygiene_contract.py',
    }

    candidates = expected_noise | protected_review_targets
    assert _octopus_ignored_paths(candidates) == expected_noise
