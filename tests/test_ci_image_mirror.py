"""Contract for the CI base-image mirror (public.ecr.aws -> ghcr.io)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MIRROR_LIST = ROOT / '.github/ci-image-mirror.txt'
WORKFLOW = ROOT / '.github/workflows/ci-image-mirror.yml'
NAMESPACE = 'ghcr.io/brianstewart377-rgb/ed-finder/mirror/'
SOURCE = re.compile(
    r'public\.ecr\.aws/docker/library/[a-z0-9._-]+:[A-Za-z0-9._-]+(?:@sha256:[0-9a-f]{64})?'
)
ADJACENT_LITERALS = re.compile(r"(?<=[A-Za-z0-9:@/._-])(['\"])\s*\n\s*\1")
# Prose records history; executable references are what CI pulls.
SCANNED_SUFFIXES = {'.yml', '.yaml', '.py', '.sh', ''}


def mirror_entries():
    entries = []
    for line in MIRROR_LIST.read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        source, destination = line.split()
        entries.append((source, destination))
    return entries


def test_mirror_entries_are_unique_well_formed_and_in_namespace():
    entries = mirror_entries()
    assert len({source for source, _ in entries}) == len(entries)
    assert len({destination for _, destination in entries}) == len(entries)
    for source, destination in entries:
        assert SOURCE.fullmatch(source), source
        assert destination.startswith(NAMESPACE), destination
        name = source.split('/')[-1].split(':')[0]
        tag = source.split(':', 1)[1].split('@')[0]
        assert destination.startswith(NAMESPACE + name + ':' + tag), (source, destination)
        if '@sha256:' in source:
            # A pin keeps its own tag so floating refreshes never untag it.
            assert destination.endswith('-pin-' + source.split('@sha256:')[1][:12])


def test_every_executable_public_ecr_reference_is_mirrored():
    mirrored = {source for source, _ in mirror_entries()}
    missing = set()
    for path in ROOT.rglob('*'):
        if not path.is_file() or any(part in {'.git', 'node_modules', '__pycache__'} for part in path.parts):
            continue
        if path.suffix not in SCANNED_SUFFIXES and not path.name.startswith('Dockerfile'):
            continue
        if path == MIRROR_LIST or path.parts[len(ROOT.parts)] == 'docs':
            continue
        text = path.read_text(errors='ignore')
        if path.suffix == '.py':
            # Join adjacent string literals split across lines, as Python does.
            text = ADJACENT_LITERALS.sub('', text)
        for reference in SOURCE.findall(text):
            if reference not in mirrored:
                missing.add((str(path.relative_to(ROOT)), reference))
    assert not missing, sorted(missing)


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
    assert '"mirror.gcr.io/library/$reference" "$source" "docker.io/library/$reference"' in text
    assert '[ "$pinned" != "$destination_digest" ]' in text
    assert '--password-stdin' in text and '--password ' not in text
    assert 'ghcr.io/brianstewart377-rgb/ed-finder/mirror/*' in text
    for step in job['steps']:
        uses = step.get('uses')
        if uses:
            assert re.fullmatch(r'[\w.-]+/[\w.-]+@[0-9a-f]{40}', uses.split(' ')[0]), uses


def test_scan_joins_adjacent_python_literals():
    text = ("IMAGE = ('public.ecr.aws/docker/library/postgres:18-alpine@sha256:'\n"
            "         '" + '7' * 64 + "')\n")
    joined = ADJACENT_LITERALS.sub('', text)
    assert SOURCE.findall(joined) == ['public.ecr.aws/docker/library/postgres:18-alpine@sha256:' + '7' * 64]
