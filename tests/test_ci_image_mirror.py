"""Contract for upstream base images and their CI registry mirror."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MIRROR_LIST = ROOT / '.github/ci-image-mirror.txt'
WORKFLOW = ROOT / '.github/workflows/ci-image-mirror.yml'
NAMESPACE = 'ghcr.io/brianstewart377-rgb/ed-finder/mirror/'
# Keep the forbidden literal out of this executable file, including its fixtures.
UPSTREAM_HOST = 'public.' + 'ecr.aws'
SOURCE = re.compile(
    r'public\.ecr\.aws/docker/library/[a-z0-9._-]+:[A-Za-z0-9._-]+(?:@sha256:[0-9a-f]{64})?'
)
MIRROR_REFERENCE = re.compile(
    re.escape(NAMESPACE) + r'[a-z0-9._-]+:[A-Za-z0-9._-]+(?:@[A-Za-z0-9:._+-]+)?'
)
ADJACENT_LITERALS = re.compile(r"(?<=[A-Za-z0-9:@/._-])(['\"])\s*\n\s*\1")
SCANNED_SUFFIXES = {'.yml', '.yaml', '.py', '.sh', ''}


def mirror_entries():
    entries = []
    for line in MIRROR_LIST.read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        source, destination = line.split()
        entries.append((source, destination))
    return entries


def image_parts(reference):
    name_tag, _, digest = reference.rpartition('/')[-1].partition('@')
    name, tag = name_tag.split(':', 1)
    return name, tag, digest


def reference_is_mirrored(reference, entries):
    name, tag, digest = image_parts(reference)
    if not digest:
        return any(reference == destination for _, destination in entries)
    for source, destination in entries:
        source_name, source_tag, source_digest = image_parts(source)
        destination_tag = image_parts(destination)[1]
        if (name == source_name and tag in {source_tag, destination_tag}
                and digest == source_digest):
            return True
    return False


def contract_violations(paths, entries):
    upstream = set()
    unlisted = set()
    for path in paths:
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        text = path.read_text(errors='ignore')
        if path.suffix == '.py':
            # Join adjacent string literals split across lines, as Python does.
            text = ADJACENT_LITERALS.sub('', text)
        executable = (path.suffix in SCANNED_SUFFIXES or path.name.startswith('Dockerfile')
                      or bool(path.stat().st_mode & 0o111))
        if (executable and path != MIRROR_LIST and relative.parts[0] != 'docs'
                and relative != Path('CHANGES.md') and UPSTREAM_HOST in text):
            upstream.add(str(relative))
        for reference in MIRROR_REFERENCE.findall(text):
            if not reference_is_mirrored(reference, entries):
                unlisted.add((str(relative), reference))
    return upstream, unlisted


def test_mirror_entries_are_unique_well_formed_and_in_namespace():
    entries = mirror_entries()
    assert len({source for source, _ in entries}) == len(entries)
    assert len({destination for _, destination in entries}) == len(entries)
    for source, destination in entries:
        assert SOURCE.fullmatch(source), source
        name, tag, digest = image_parts(source)
        expected = NAMESPACE + name + ':' + tag
        if digest:
            # A pin keeps its own tag so floating refreshes never untag it.
            expected += '-pin-' + digest.removeprefix('sha256:')[:12]
        assert destination == expected, (source, destination)


def test_every_executable_uses_the_mirror_and_every_mirror_reference_is_listed():
    # Include new files while excluding ignored dependencies and generated outputs.
    tracked = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    paths = [ROOT / path for path in tracked.split('\0') if path]
    upstream, unlisted = contract_violations(paths, mirror_entries())
    assert not upstream, sorted(upstream)
    assert not unlisted, sorted(unlisted)


def test_mirror_workflow_is_bounded_and_preserves_digests():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    triggers = workflow.get(True) or workflow.get('on')
    assert set(triggers) == {'workflow_dispatch', 'schedule'}
    assert workflow['permissions'] == {'contents': 'read'}
    job = workflow['jobs']['mirror']
    assert job['runs-on'] == 'ubuntu-latest'
    assert job['permissions'] == {'contents': 'read', 'packages': 'write'}
    text = WORKFLOW.read_text()
    assert '--all --preserve-digests' in text
    # Fallback sources serve the same official images; pins are still verified.
    assert '"mirror.gcr.io/library/$reference" "$listed" "docker.io/library/$reference"' in text
    assert 'source_prefix="${source%/*}/"' in text
    assert 'reference="${source##*/}"' in text
    assert 'listed="$source_prefix$reference"' in text
    # Pinned sources drop the tag: skopeo refuses name:tag@digest.
    assert 'reference="${reference%%:*}@${reference##*@}"' in text
    assert '[ "$pinned" != "$destination_digest" ]' in text
    assert '--password-stdin' in text and '--password ' not in text
    assert NAMESPACE + '*' in text
    for step in job['steps']:
        uses = step.get('uses')
        if uses:
            assert re.fullmatch(r'[\w.-]+/[\w.-]+@[0-9a-f]{40}', uses.split(' ')[0]), uses


def test_scan_joins_adjacent_python_literals():
    prefix = NAMESPACE + 'postgres:18-alpine@sha256:'
    text = "IMAGE = ('" + prefix + "'\n         '" + '7' * 64 + "')\n"
    joined = ADJACENT_LITERALS.sub('', text)
    assert MIRROR_REFERENCE.findall(joined) == [prefix + '7' * 64]


@pytest.mark.parametrize('reference, expected', [
    ('postgres:18-alpine', True),
    ('postgres:18-alpine-pin-' + '7' * 12, True),
    ('postgres:18-alpine@sha256:' + '7' * 64, True),
    ('postgres:18-alpine-pin-' + '7' * 12 + '@sha256:' + '7' * 64, True),
    ('postgres:18-alpine@sha256:' + '8' * 64, False),
    ('postgres:18-alpine-extra@sha256:' + '7' * 64, False),
    ('postgres:17-alpine@sha256:' + '7' * 64, False),
    ('redis:18-alpine@sha256:' + '7' * 64, False),
    ('postgres:17-alpine', False),
    ('postgres:18-alpine@sha256:invalid', False),
])
def test_reference_requires_the_listed_name_tag_and_digest(reference, expected):
    upstream = UPSTREAM_HOST + '/docker/library/postgres:18-alpine'
    entries = [
        (upstream, NAMESPACE + 'postgres:18-alpine'),
        (upstream + '@sha256:' + '7' * 64, NAMESPACE + 'postgres:18-alpine-pin-' + '7' * 12),
    ]
    assert reference_is_mirrored(NAMESPACE + reference, entries) is expected


def test_scan_rejects_upstream_literals_and_checks_mirrors_in_docs(tmp_path, monkeypatch):
    monkeypatch.setattr(f'{__name__}.ROOT', tmp_path)
    paths = [tmp_path / 'run.py', tmp_path / 'docs/runbook.md', tmp_path / 'Dockerfile.test',
             tmp_path / 'CHANGES.md', tmp_path / 'tool.custom']
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(UPSTREAM_HOST + '/docker/library/postgres:18-alpine\n')
    paths[-1].chmod(0o755)
    paths[1].write_text(UPSTREAM_HOST + '\n' + NAMESPACE + 'unlisted:latest\n')
    upstream, unlisted = contract_violations(paths, [])
    assert upstream == {'run.py', 'Dockerfile.test', 'tool.custom'}
    assert unlisted == {('docs/runbook.md', NAMESPACE + 'unlisted:latest')}


def test_scan_checks_the_complete_digest_in_adjacent_python_literals(tmp_path, monkeypatch):
    monkeypatch.setattr(f'{__name__}.ROOT', tmp_path)
    path = tmp_path / 'image.py'
    prefix = NAMESPACE + 'postgres:18-alpine@sha256:'
    path.write_text("IMAGE = ('" + prefix + "'\n         '" + '8' * 64 + "')\n")
    source = UPSTREAM_HOST + '/docker/library/postgres:18-alpine@sha256:' + '7' * 64
    destination = NAMESPACE + 'postgres:18-alpine-pin-' + '7' * 12
    upstream, unlisted = contract_violations([path], [(source, destination)])
    assert not upstream
    assert unlisted == {('image.py', prefix + '8' * 64)}


def test_fallback_deadlines_fit_inside_the_job_timeout():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    job_minutes = workflow['jobs']['mirror']['timeout-minutes']
    per_candidate = int(re.search(r'timeout (\d+) skopeo copy', WORKFLOW.read_text()).group(1))
    worst_case_minutes = len(mirror_entries()) * 3 * per_candidate / 60
    # Leave at least 30 minutes for setup, verification and the anonymous check.
    assert worst_case_minutes + 30 <= job_minutes, (worst_case_minutes, job_minutes)


@pytest.mark.parametrize('reference', ['nginx:1.29-alpine@sha256:' + 'a' * 64, 'postgres:18-alpine'])
def test_pinned_reference_is_rewritten_to_name_at_digest(reference):
    workflow = yaml.safe_load(WORKFLOW.read_text())
    steps = workflow['jobs']['mirror']['steps']
    copy_script = next(step['run'] for step in steps if step['name'].startswith('Copy images'))
    # Exercise the actual source transformation rather than a parallel implementation.
    start = copy_script.index('source_prefix=')
    end = copy_script.index('copied_from=', start)
    transform = copy_script[start:end]
    script = 'source="$1"\n' + transform + 'printf "%s\\n%s" "$reference" "$listed"'
    prefix = UPSTREAM_HOST + '/docker/library/'
    result = subprocess.run(['bash', '-c', script, '_', prefix + reference],
                            capture_output=True, text=True, check=True).stdout
    expected = reference.split(':', 1)[0] + '@' + reference.split('@')[1] if '@' in reference else reference
    assert result.splitlines() == [expected, prefix + expected]
