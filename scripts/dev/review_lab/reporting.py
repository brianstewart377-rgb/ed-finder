from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .contract import LATEST_REPORT_POINTER, REQUIRED_PHASE_NAMES, VERIFY_TMP_ROOT, VerifyContext


def phase_result(*, status: str, duration_ms: int, summary: str, failure_code: str | None, safe_diagnostics: Any) -> dict[str, Any]:
    return {
        'status': status,
        'duration_ms': duration_ms,
        'summary': summary,
        'failure_code': failure_code,
        'safe_diagnostics': safe_diagnostics,
    }


def default_phase_results(skipped_summary: str = 'Not run.') -> dict[str, dict[str, Any]]:
    return {
        phase_name: phase_result(
            status='skipped',
            duration_ms=0,
            summary=skipped_summary,
            failure_code=None,
            safe_diagnostics={},
        )
        for phase_name in REQUIRED_PHASE_NAMES
    }


def browser_phase_result(duration_ms: int, phase: dict[str, Any]) -> dict[str, Any]:
    return {
        **phase,
        'duration_ms': duration_ms,
    }


def first_failed_phase(phases: Mapping[str, Mapping[str, Any]], *, start_at: str) -> tuple[str, Mapping[str, Any]] | None:
    start_index = REQUIRED_PHASE_NAMES.index(start_at)
    for phase_name in REQUIRED_PHASE_NAMES[start_index:]:
        phase = phases[phase_name]
        if phase['status'] == 'failed':
            return phase_name, phase
    return None


def create_verify_context(mode: str, scenarios: tuple[Any, ...]) -> VerifyContext:
    VERIFY_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + str(os.getpid()) + '-' + uuid4().hex[:8]
    run_dir = VERIFY_TMP_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return VerifyContext(mode=mode, scenarios=scenarios, run_id=run_id, run_dir=run_dir, report_path=run_dir / 'report.json')


def write_verify_report(context: VerifyContext, report: Mapping[str, Any]) -> None:
    context.report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    LATEST_REPORT_POINTER.write_text(
        json.dumps({'run_id': context.run_id, 'report_file': str(context.report_path)}, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )


def load_latest_report() -> dict[str, Any]:
    if not LATEST_REPORT_POINTER.is_file():
        raise FileNotFoundError('No Review Lab report has been written yet.')
    pointer = json.loads(LATEST_REPORT_POINTER.read_text(encoding='utf-8'))
    report_path = Path(pointer['report_file'])
    if not report_path.is_file():
        raise FileNotFoundError('The latest Review Lab report no longer exists.')
    return json.loads(report_path.read_text(encoding='utf-8'))
