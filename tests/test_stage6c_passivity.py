"""Stage 6C static passivity test.

Asserts that no simulation, optimiser, recommendations, or mechanics
source file imports the Stage 6C comparison engine or the Stage 6A
observation store. Stage 6C is a one-way arrow: simulation/optimiser
code feeds *predictions* into Stage 6C, never the other way round.

Stage 4D's pre-existing imports inside ``simulation/`` of
``observations.comparison`` and ``observations.schemas`` are deliberately
allowed — they are the legacy in-pipeline comparison code that Stage 6C
explicitly preserved.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'

# Source trees whose modules must NEVER pull in Stage 6C / store code.
FORBIDDEN_ROOTS = (
    API_SRC / 'simulation',
    API_SRC / 'optimiser',
    API_SRC / 'recommendations',
    API_SRC / 'mechanics',
)

# Modules that simulation/optimiser/recommendations/mechanics MUST NOT import.
#
# Stage 6C hardening (PART G): the comparison engine has been split into
# a package under ``observations.comparison_engine_pkg.*``. We list the
# package root AND each sub-module explicitly so a reader can see at a
# glance which engine modules are forbidden to pull into the
# scoring/optimiser layers. The package root covers any future
# sub-module additions via the ``startswith(forbidden + '.')`` check
# below.
#
# Naming note: the package is intentionally ``comparison_engine_pkg``
# (not ``comparison``) because ``observations/comparison.py`` already
# exists as the Stage 4D in-pipeline comparison module — Stage 4D's
# pre-existing import inside ``simulation/`` of ``observations.comparison``
# is deliberately allowed and must NOT match this list.
FORBIDDEN_MODULES = (
    # Legacy / stable public compatibility wrapper for Stage 6C.
    'observations.comparison_engine',
    # Stage 6C modular comparison engine package + every sub-module.
    'observations.comparison_engine_pkg',
    'observations.comparison_engine_pkg.engine',
    'observations.comparison_engine_pkg.prediction_extractors',
    'observations.comparison_engine_pkg.observation_index',
    'observations.comparison_engine_pkg.service_rules',
    'observations.comparison_engine_pkg.economy_rules',
    'observations.comparison_engine_pkg.cp_rules',
    'observations.comparison_engine_pkg.facility_rules',
    'observations.comparison_engine_pkg.build_outcome_rules',
    'observations.comparison_engine_pkg.prediction_claim_rules',
    'observations.comparison_engine_pkg.note_rules',
    'observations.comparison_engine_pkg.summary',
    'observations.comparison_engine_pkg.shared',
    # Shared Stage 6C / Stage 6A modules.
    'observations.comparison_models',
    'observations.review_engine',
    'observations.review_models',
    'observations.store',
    'observations.api_models',
)

_IMPORT_RE = re.compile(
    r'^\s*(?:from\s+(?P<from>[\w.]+)\s+import\b|import\s+(?P<import>[\w.]+))',
    re.MULTILINE,
)


def _python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.rglob('*.py') if '__pycache__' not in p.parts]


@pytest.mark.parametrize('root', FORBIDDEN_ROOTS, ids=lambda p: p.name)
def test_no_stage6c_or_store_imports(root: Path):
    offenders: list[str] = []
    for path in _python_files(root):
        text = path.read_text(encoding='utf-8')
        for match in _IMPORT_RE.finditer(text):
            module = match.group('from') or match.group('import') or ''
            for forbidden in FORBIDDEN_MODULES:
                if module == forbidden or module.startswith(forbidden + '.'):
                    offenders.append(f'{path.relative_to(ROOT)}: imports {module}')
    assert not offenders, (
        'Stage 6C passivity violated — simulation/optimiser/recommendations/'
        'mechanics code must not import the Stage 6C engine or the Stage 6A '
        'store. Offenders:\n  ' + '\n  '.join(offenders)
    )
