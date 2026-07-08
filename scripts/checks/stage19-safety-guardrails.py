#!/usr/bin/env python3
"""Static Stage 19 safety guardrails for local and CI parity checks.

This scan is intentionally targeted. It checks the Stage 19 operator cockpit,
operator visibility, source-run compatibility, and rehearsal surfaces where a
small accidental write/action regression would be high risk.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

TARGET_FILES = [
    ROOT / 'apps' / 'api' / 'src' / 'routers' / 'operator.py',
    ROOT / 'apps' / 'api' / 'src' / 'operator_visibility.py',
    ROOT / 'apps' / 'importer' / 'src' / 'edsm_station_import.py',
    ROOT / 'apps' / 'importer' / 'src' / 'source_run_compatibility.py',
    ROOT / 'scripts' / 'operator' / 'stage19anr_warehouse_derived_staging_rehearsal.py',
    ROOT / 'frontend' / 'src' / 'lib' / 'api.ts',
    ROOT / 'frontend' / 'src' / 'lib' / 'api.operator.test.ts',
    ROOT / 'frontend' / 'src' / 'features' / 'operator' / 'OperatorCockpitTab.tsx',
]

PRODUCTION_DSN_PATTERNS = [
    re.compile(r'postgres(?:ql)?://[^\'"\s]+(?:ed-finder\.app|prod|production)', re.IGNORECASE),
    re.compile(r'DATABASE_URL\s*=\s*[\'"][^\'"]*(?:ed-finder\.app|prod|production)', re.IGNORECASE),
    re.compile(r'POSTGRES_PASSWORD\s*=\s*[\'"][^\'"]+', re.IGNORECASE),
]

DISALLOWED_SCHEDULER_PATTERNS = [
    re.compile(r'\bsystemctl\b', re.IGNORECASE),
    re.compile(r'(?<![A-Za-z0-9_])\.(?:timer|service)(?![A-Za-z0-9_])', re.IGNORECASE),
]

CANONICAL_APPLY_COMMAND_PATTERN = re.compile(
    r'\b(?:run|exec|execute|invoke|start|enable|trigger|call|dispatch)[\w\s:-]{0,80}canonical_apply\b',
    re.IGNORECASE,
)

OPERATOR_WRITE_DECORATOR = re.compile(
    r'@router\.(?:post|put|patch|delete)\(\s*[\'"]/api/operator',
    re.IGNORECASE,
)


def _read(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f'missing guardrail target: {path.relative_to(ROOT)}')
    return path.read_text(encoding='utf-8')


def _line_number(text: str, index: int) -> int:
    return text.count('\n', 0, index) + 1


def _record_pattern_matches(
    failures: list[str],
    *,
    path: Path,
    text: str,
    patterns: list[re.Pattern[str]],
    label: str,
) -> None:
    for pattern in patterns:
        for match in pattern.finditer(text):
            rel = path.relative_to(ROOT)
            failures.append(f'{rel}:{_line_number(text, match.start())}: {label}: {match.group(0)!r}')


def check_no_scheduler_or_prod_secret_fragments(failures: list[str]) -> None:
    for path in TARGET_FILES:
        text = _read(path)
        _record_pattern_matches(
            failures,
            path=path,
            text=text,
            patterns=DISALLOWED_SCHEDULER_PATTERNS,
            label='scheduler/service activation fragment is not allowed in Stage 19 guard targets',
        )
        _record_pattern_matches(
            failures,
            path=path,
            text=text,
            patterns=PRODUCTION_DSN_PATTERNS,
            label='production-looking DB URL or secret assignment is not allowed',
        )
        _record_pattern_matches(
            failures,
            path=path,
            text=text,
            patterns=[CANONICAL_APPLY_COMMAND_PATTERN],
            label='canonical_apply command/dispatch fragment is not allowed',
        )


def check_operator_routes_are_get_only(failures: list[str]) -> None:
    router_text = _read(ROOT / 'apps' / 'api' / 'src' / 'routers' / 'operator.py')
    _record_pattern_matches(
        failures,
        path=ROOT / 'apps' / 'api' / 'src' / 'routers' / 'operator.py',
        text=router_text,
        patterns=[OPERATOR_WRITE_DECORATOR],
        label='operator router must not expose write endpoints',
    )
    if 'transaction(readonly=True)' not in router_text:
        failures.append('apps/api/src/routers/operator.py: operator endpoints must use readonly transactions')


def check_frontend_operator_helpers_are_get_only(failures: list[str]) -> None:
    api_text = _read(ROOT / 'frontend' / 'src' / 'lib' / 'api.ts')
    lines = api_text.splitlines()
    for index, line in enumerate(lines):
        if '/api/operator' not in line:
            continue
        window = '\n'.join(lines[index:index + 5])
        if re.search(r"method\s*:\s*['\"](?:POST|PUT|PATCH|DELETE)['\"]", window, re.IGNORECASE):
            failures.append(
                'frontend/src/lib/api.ts:'
                f'{index + 1}: operator API helper must remain GET/read-only'
            )

    test_text = _read(ROOT / 'frontend' / 'src' / 'lib' / 'api.operator.test.ts')
    required_fragments = [
        "['GET', undefined]",
        'not.toMatch',
        'POST',
        'PUT',
        'PATCH',
        'DELETE',
        '/api/operator/safety-gates',
        '/api/operator/diagnostic-staging-rows',
    ]
    for fragment in required_fragments:
        if fragment not in test_text:
            failures.append(
                'frontend/src/lib/api.operator.test.ts: '
                f'missing read-only operator helper guard fragment {fragment!r}'
            )


def check_legacy_staging_fk_policy(failures: list[str]) -> None:
    importer_text = _read(ROOT / 'apps' / 'importer' / 'src' / 'edsm_station_import.py')
    compat_text = _read(ROOT / 'apps' / 'importer' / 'src' / 'source_run_compatibility.py')
    visibility_text = _read(ROOT / 'apps' / 'api' / 'src' / 'operator_visibility.py')

    required_pairs = [
        (
            importer_text,
            'staging_edsm_stations.source_run_id currently expects enrichment_source_runs.id',
            'apps/importer/src/edsm_station_import.py',
        ),
        (
            importer_text,
            'not source_runs.id from this wrapper',
            'apps/importer/src/edsm_station_import.py',
        ),
        (
            compat_text,
            'do_not_pass_source_runs_id_to_legacy_staging_source_run_id',
            'apps/importer/src/source_run_compatibility.py',
        ),
        (
            visibility_text,
            'rows_using_source_runs_id',
            'apps/api/src/operator_visibility.py',
        ),
    ]
    for text, fragment, label in required_pairs:
        if fragment not in text:
            failures.append(f'{label}: missing legacy staging FK guard fragment {fragment!r}')


def run_checks() -> list[str]:
    failures: list[str] = []
    check_no_scheduler_or_prod_secret_fragments(failures)
    check_operator_routes_are_get_only(failures)
    check_frontend_operator_helpers_are_get_only(failures)
    check_legacy_staging_fk_policy(failures)
    return failures


def main() -> int:
    failures = run_checks()
    if failures:
        print('Stage 19 safety guardrails failed:', file=sys.stderr)
        for failure in failures:
            print(f'  - {failure}', file=sys.stderr)
        return 1
    print('Stage 19 safety guardrails passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
