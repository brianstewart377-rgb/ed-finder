#!/usr/bin/env python3
"""Guarded EDSM station enrichment automation.

The enrichment script deliberately keeps dry-run, metadata writes, and
confirmed-link writes as separate operations. This wrapper automates that
sequence while validating each JSON report before moving to the next phase.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


DEFAULT_OUTPUT_ROOT = Path('/tmp/edfinder-station-enrichment')
TRUSTED_EDSM_SOURCE = 'edsm_system_api'
TRUSTED_STATION_IDENTITY_CONFIDENCE = 'exact_station_identity'
RISKY_CONFLICT_TYPES = {
    'id_name_mismatch',
    'known_station_type_mismatch',
    'station_economy_mismatch',
}
UNSAFE_WRITE_MARKERS = {
    'identity_unsafe',
    'context_unsafe',
    'identity_context_unsafe',
    'station_write_unsafe',
}


class GuardFailure(RuntimeError):
    """Raised when a safety gate blocks the guarded enrichment flow."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stderr: str = ''


@dataclass(frozen=True)
class SafetyAnalysis:
    risky_metadata_writes: int
    risky_confirmed_links: int
    precision_churn: int
    metadata_updates: int
    confirmed_links: int


@dataclass(frozen=True)
class CompactSummary:
    systems_processed: int
    metadata_updates: int
    confirmed_links: int
    conflicts: int
    skipped: int
    fetch_errors: int
    systems_fetch_failed: int
    suppressed_station_writes: int
    ignored_transient_non_slot: int
    dirty_systems_planned: int
    dirty_systems_marked: int
    file_path: Path


CommandRunner = Callable[[Sequence[str], Path, Path], CommandResult]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run guarded EDSM station enrichment dry-run/apply phases through docker compose importer.',
    )
    parser.add_argument('--limit', type=int, required=True, help='Maximum systems to process.')
    parser.add_argument('--source', choices=('edsm',), default='edsm', help='Station enrichment source.')
    parser.add_argument('--timeout', type=float, default=120.0, help='EDSM request timeout in seconds.')
    parser.add_argument('--edsm-retries', type=int, default=5, help='EDSM retry attempts after the initial request.')
    parser.add_argument(
        '--edsm-retry-backoff-seconds',
        type=float,
        default=8.0,
        help='Initial retry backoff in seconds.',
    )
    parser.add_argument(
        '--edsm-request-delay-seconds',
        type=float,
        default=0.5,
        help='Delay between EDSM requests in seconds.',
    )
    parser.add_argument(
        '--edsm-429-backoff-seconds',
        type=float,
        default=60.0,
        help='Initial EDSM 429 retry backoff when Retry-After is absent.',
    )
    parser.add_argument('--max-metadata-passes', type=int, default=3, help='Maximum metadata-only apply passes.')
    parser.add_argument('--dry-run-only', action='store_true', help='Run the initial dry-run and never apply writes.')
    parser.add_argument('--yes', '--apply', dest='allow_apply', action='store_true', help='Allow apply phases.')
    parser.add_argument(
        '--output-dir',
        default=None,
        help='Parent directory for the unique run output directory. Defaults to /tmp/edfinder-station-enrichment.',
    )
    args = parser.parse_args(argv)
    _validate_cli_args(args)
    return args


def _validate_cli_args(args: argparse.Namespace) -> None:
    errors: list[str] = []
    if args.limit < 1:
        errors.append('--limit must be greater than zero.')
    if args.timeout <= 0:
        errors.append('--timeout must be greater than zero.')
    if args.edsm_retries < 0:
        errors.append('--edsm-retries must be zero or greater.')
    if args.edsm_retry_backoff_seconds < 0:
        errors.append('--edsm-retry-backoff-seconds must be zero or greater.')
    if args.edsm_request_delay_seconds < 0:
        errors.append('--edsm-request-delay-seconds must be zero or greater.')
    if args.edsm_429_backoff_seconds < 0:
        errors.append('--edsm-429-backoff-seconds must be zero or greater.')
    if args.max_metadata_passes < 0:
        errors.append('--max-metadata-passes must be zero or greater.')
    if args.dry_run_only and args.allow_apply:
        errors.append('--dry-run-only cannot be combined with --yes/--apply.')
    if errors:
        raise GuardFailure('\n'.join(errors))


def create_output_dir(limit: int, output_dir: str | None = None, now: datetime | None = None) -> Path:
    base = Path(output_dir) if output_dir else DEFAULT_OUTPUT_ROOT
    stamp = (now or datetime.now()).strftime('%Y%m%d-%H%M%S')
    stem = f'{stamp}-limit-{limit}'
    base.mkdir(parents=True, exist_ok=True)
    for suffix in ['', *[f'-{index}' for index in range(2, 1000)]]:
        candidate = base / f'{stem}{suffix}'
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise GuardFailure(f'Could not create a unique output directory under {base}')


def load_report_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding='utf-8')
    except OSError as exc:
        raise GuardFailure(f'Could not read JSON output file {path}: {exc}') from exc
    if not raw.strip():
        raise GuardFailure(f'JSON output file is empty: {path}')
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GuardFailure(f'JSON output file is invalid: {path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise GuardFailure(f'JSON output file must contain an object: {path}')
    return payload


def station_report_section(report: Mapping[str, Any]) -> Mapping[str, Any]:
    section = report.get('stations')
    if isinstance(section, Mapping) and (
        'metadata_updates_planned' in section
        or 'confirmed_link_updates_planned' in section
        or 'systems_fetch_failed' in section
    ):
        return section
    return report


def analyse_report(report: Mapping[str, Any]) -> SafetyAnalysis:
    section = station_report_section(report)
    metadata_updates = _list_value(section, 'metadata_updates_planned')
    confirmed_links = _list_value(section, 'confirmed_link_updates_planned')
    risky_keys = _risky_station_keys(report)

    risky_metadata = sum(
        1 for update in metadata_updates
        if isinstance(update, Mapping) and _write_targets_risky_station(update, risky_keys)
    )
    risky_links = sum(
        1 for update in confirmed_links
        if isinstance(update, Mapping) and _write_targets_risky_station(update, risky_keys)
    )
    precision_churn = sum(
        1 for update in metadata_updates
        if isinstance(update, Mapping) and _is_trusted_edsm_precision_churn(update)
    )
    return SafetyAnalysis(
        risky_metadata_writes=risky_metadata,
        risky_confirmed_links=risky_links,
        precision_churn=precision_churn,
        metadata_updates=len(metadata_updates),
        confirmed_links=len(confirmed_links),
    )


def assert_safe_to_continue(report: Mapping[str, Any], *, phase: str) -> SafetyAnalysis:
    analysis = analyse_report(report)
    errors: list[str] = []
    if analysis.risky_metadata_writes:
        errors.append(f'risky metadata writes > 0 ({analysis.risky_metadata_writes})')
    if analysis.risky_confirmed_links:
        errors.append(f'risky confirmed links > 0 ({analysis.risky_confirmed_links})')
    if analysis.precision_churn:
        errors.append(f'trusted EDSM exact distance precision churn > 0 ({analysis.precision_churn})')
    if errors:
        raise GuardFailure(f'{phase} blocked by safety gate: ' + '; '.join(errors))
    return analysis


def assert_final_clean(report: Mapping[str, Any], *, phase: str = 'final dry-run') -> SafetyAnalysis:
    analysis = assert_safe_to_continue(report, phase=phase)
    errors: list[str] = []
    if analysis.metadata_updates:
        errors.append(f'metadata_updates={analysis.metadata_updates}')
    if analysis.confirmed_links:
        errors.append(f'confirmed_links={analysis.confirmed_links}')
    if errors:
        raise GuardFailure(f'{phase} did not finish cleanly: ' + '; '.join(errors))
    return analysis


def compact_summary(report: Mapping[str, Any], path: Path) -> CompactSummary:
    section = station_report_section(report)
    summary = report.get('summary') if isinstance(report.get('summary'), Mapping) else {}
    station_summary = summary.get('stations') if isinstance(summary.get('stations'), Mapping) else {}
    counts = section.get('counts') if isinstance(section.get('counts'), Mapping) else {}
    dirty = report.get('dirty') if isinstance(report.get('dirty'), Mapping) else {}

    return CompactSummary(
        systems_processed=_count_value(summary, 'systems_processed', fallback=_systems_processed(report, section)),
        metadata_updates=_planned_count(section, counts, 'metadata_updates_planned'),
        confirmed_links=_planned_count(section, counts, 'confirmed_link_updates_planned'),
        conflicts=_section_count(section, station_summary, counts, 'conflicts'),
        skipped=_section_count(section, station_summary, counts, 'skipped'),
        fetch_errors=_section_count(section, station_summary, counts, 'fetch_errors'),
        systems_fetch_failed=_section_count(section, station_summary, counts, 'systems_fetch_failed'),
        suppressed_station_writes=_suppressed_station_writes(section, counts),
        ignored_transient_non_slot=_section_count(section, station_summary, counts, 'ignored_transient_non_slot'),
        dirty_systems_planned=_dirty_planned(summary, dirty),
        dirty_systems_marked=_count_value(summary, 'dirty_systems_marked', fallback=_int_value(dirty.get('marked'))),
        file_path=path,
    )


def print_compact_summary(phase: str, report: Mapping[str, Any], path: Path) -> None:
    item = compact_summary(report, path)
    print(
        f'{phase}: '
        f'systems_processed={item.systems_processed} '
        f'metadata_updates={item.metadata_updates} '
        f'confirmed_links={item.confirmed_links} '
        f'conflicts={item.conflicts} '
        f'skipped={item.skipped} '
        f'fetch_errors={item.fetch_errors} '
        f'systems_fetch_failed={item.systems_fetch_failed} '
        f'suppressed_station_writes={item.suppressed_station_writes} '
        f'ignored_transient_non_slot={item.ignored_transient_non_slot} '
        f'dirty_marked/planned={item.dirty_systems_marked}/{item.dirty_systems_planned} '
        f'file={item.file_path}',
        flush=True,
    )


class GuardedStationEnrichmentRunner:
    def __init__(
        self,
        args: argparse.Namespace,
        *,
        repo_root: Path | None = None,
        output_dir: Path | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self.args = args
        self.repo_root = repo_root or Path(__file__).resolve().parents[1]
        self.output_dir = output_dir or create_output_dir(args.limit, args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.command_runner = command_runner or run_docker_compose_command
        self._next_index = 1

    def run(self) -> Path:
        print(f'Output directory: {self.output_dir}', flush=True)
        current = self._run_phase('initial dry-run', 'initial_dryrun', mode='dry_run')
        assert_safe_to_continue(current, phase='initial dry-run')

        if self.args.dry_run_only:
            print('Dry-run only: no apply phases run.', flush=True)
            return self.output_dir

        metadata_pass = 0
        while analyse_report(current).metadata_updates > 0:
            self._require_apply(f'metadata apply pass {metadata_pass + 1}')
            if metadata_pass >= self.args.max_metadata_passes:
                raise GuardFailure(
                    f'metadata_updates remained > 0 after {self.args.max_metadata_passes} metadata pass(es)'
                )
            metadata_pass += 1
            metadata_apply = self._run_phase(
                f'metadata apply {metadata_pass}',
                f'metadata_apply_{metadata_pass}',
                mode='metadata',
            )
            assert_safe_to_continue(metadata_apply, phase=f'metadata apply {metadata_pass}')
            current = self._run_phase(
                f'after metadata {metadata_pass} dry-run',
                f'after_metadata_{metadata_pass}_dryrun',
                mode='dry_run',
            )
            assert_safe_to_continue(current, phase=f'after metadata {metadata_pass} dry-run')

        if analyse_report(current).confirmed_links > 0:
            self._require_apply('confirmed links apply')
            links_apply = self._run_phase(
                'confirmed links apply',
                'confirmed_links_apply',
                mode='confirmed_links',
            )
            assert_safe_to_continue(links_apply, phase='confirmed links apply')

        final_path = self.output_dir / 'final_dryrun.json'
        final_report = self._run_command_to_file('final dry-run', final_path, mode='dry_run')
        print_compact_summary('final dry-run', final_report, final_path)
        assert_final_clean(final_report)
        return self.output_dir

    def _run_phase(self, phase: str, name: str, *, mode: str) -> dict[str, Any]:
        path = self.output_dir / f'{self._next_index:02d}_{name}.json'
        self._next_index += 1
        report = self._run_command_to_file(phase, path, mode=mode)
        print_compact_summary(phase, report, path)
        return report

    def _run_command_to_file(self, phase: str, path: Path, *, mode: str) -> dict[str, Any]:
        cmd = build_docker_compose_command(self.args, mode=mode, repo_root=self.repo_root)
        result = self.command_runner(cmd, self.repo_root, path)
        try:
            report = load_report_file(path)
        except GuardFailure as exc:
            if result.returncode:
                raise GuardFailure(
                    f'{phase} enrich command exited {result.returncode} and did not produce valid JSON: {exc}'
                ) from exc
            raise
        if result.returncode:
            stderr_path = path.with_name(f'{path.name}.stderr.txt')
            if result.stderr and not stderr_path.exists():
                stderr_path.write_text(result.stderr, encoding='utf-8')
            raise GuardFailure(
                f'{phase} enrich command exited {result.returncode}; stderr saved to {stderr_path}'
            )
        return report

    def _require_apply(self, phase: str) -> None:
        if not self.args.allow_apply:
            raise GuardFailure(f'Refusing {phase} before any apply; rerun with --yes or --apply to allow writes.')


def build_docker_compose_command(args: argparse.Namespace, *, mode: str, repo_root: Path | None = None) -> list[str]:
    root = repo_root or Path(__file__).resolve().parents[1]
    enrich_args = [
        '/workspace/apps/importer/src/enrich_system_data.py',
        '--stations',
        '--source',
        args.source,
        '--limit',
        str(args.limit),
        '--timeout',
        _format_float(args.timeout),
        '--edsm-retries',
        str(args.edsm_retries),
        '--edsm-retry-backoff-seconds',
        _format_float(args.edsm_retry_backoff_seconds),
        '--edsm-request-delay-seconds',
        _format_float(args.edsm_request_delay_seconds),
        '--edsm-429-backoff-seconds',
        _format_float(args.edsm_429_backoff_seconds),
        '--json',
    ]
    if mode == 'metadata':
        enrich_args.extend(['--apply-station-metadata', '--mark-dirty'])
    elif mode == 'confirmed_links':
        enrich_args.extend(['--apply-confirmed-links', '--mark-dirty'])
    elif mode != 'dry_run':
        raise ValueError(f'Unknown enrichment mode: {mode}')

    return [
        'docker',
        'compose',
        '--profile',
        'import',
        'run',
        '--rm',
        '-T',
        '--entrypoint',
        'python3',
        '-v',
        f'{root / "apps" / "importer" / "src"}:/workspace/apps/importer/src:ro',
        '-v',
        f'{root / "apps" / "api" / "src"}:/workspace/apps/api/src:ro',
        '-e',
        'LOG_FILE=/data/logs/enrich_system_data.log',
        'importer',
        *enrich_args,
    ]


def run_docker_compose_command(cmd: Sequence[str], cwd: Path, output_path: Path) -> CommandResult:
    completed = subprocess.run(
        list(cmd),
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    output_path.write_text(completed.stdout, encoding='utf-8')
    if completed.stderr:
        output_path.with_name(f'{output_path.name}.stderr.txt').write_text(completed.stderr, encoding='utf-8')
    return CommandResult(returncode=completed.returncode, stderr=completed.stderr)


def _risky_station_keys(report: Mapping[str, Any]) -> set[tuple[str, int | None, Any]]:
    keys: set[tuple[str, int | None, Any]] = set()
    for local_station, conflict in _iter_station_conflicts(report):
        if _is_risky_conflict(conflict):
            keys.update(_station_keys(local_station or {}))
    return keys


def _iter_station_conflicts(report: Mapping[str, Any]):
    section = station_report_section(report)
    for entry in _list_value(section, 'conflicts'):
        if not isinstance(entry, Mapping):
            continue
        conflict = entry.get('conflict') if isinstance(entry.get('conflict'), Mapping) else entry
        local_station = entry.get('local_station') if isinstance(entry.get('local_station'), Mapping) else None
        yield local_station, conflict

    raw_stations = report.get('stations')
    if isinstance(raw_stations, list):
        for station in raw_stations:
            if not isinstance(station, Mapping):
                continue
            local_station = station.get('local_station') if isinstance(station.get('local_station'), Mapping) else None
            for conflict in _list_value(station, 'conflicts'):
                if isinstance(conflict, Mapping):
                    yield local_station, conflict


def _is_risky_conflict(conflict: Mapping[str, Any] | None) -> bool:
    if not isinstance(conflict, Mapping):
        return False
    if conflict.get('type') in RISKY_CONFLICT_TYPES:
        return True
    if any(bool(conflict.get(marker)) for marker in UNSAFE_WRITE_MARKERS):
        return True
    write_safety = _clean_text(conflict.get('write_safety'))
    return write_safety in UNSAFE_WRITE_MARKERS


def _write_targets_risky_station(update: Mapping[str, Any], risky_keys: set[tuple[str, int | None, Any]]) -> bool:
    if any(_is_risky_conflict(conflict) for conflict in _list_value(update, 'conflicts')):
        return True
    return bool(_update_station_keys(update) & risky_keys)


def _is_trusted_edsm_precision_churn(update: Mapping[str, Any]) -> bool:
    if update.get('field') != 'distance_from_star':
        return False
    local_station = update.get('local_station') if isinstance(update.get('local_station'), Mapping) else {}
    return (
        local_station.get('distance_source') == TRUSTED_EDSM_SOURCE
        and local_station.get('distance_confidence') == TRUSTED_STATION_IDENTITY_CONFIDENCE
    )


def _update_station_keys(update: Mapping[str, Any]) -> set[tuple[str, int | None, Any]]:
    local_station = update.get('local_station') if isinstance(update.get('local_station'), Mapping) else {}
    return _station_keys(
        {
            **local_station,
            'id': _first_present(update.get('station_id'), local_station.get('id')),
            'market_id': _first_present(update.get('market_id'), local_station.get('market_id')),
            'system_id64': _first_present(update.get('system_id64'), local_station.get('system_id64')),
            'name': _first_present(local_station.get('name'), update.get('station_name')),
        }
    )


def _station_keys(station: Mapping[str, Any]) -> set[tuple[str, int | None, Any]]:
    station_id = _int_value(station.get('id'))
    market_id = _int_value(station.get('market_id'))
    system_id64 = _int_value(station.get('system_id64'))
    name = _normalise_name(station.get('name'))
    keys: set[tuple[str, int | None, Any]] = set()
    if station_id is not None:
        keys.add(('station_id', None, station_id))
        if system_id64 is not None:
            keys.add(('station_id', system_id64, station_id))
    if market_id is not None:
        keys.add(('market_id', None, market_id))
        if system_id64 is not None:
            keys.add(('market_id', system_id64, market_id))
    if system_id64 is not None and name:
        keys.add(('name', system_id64, name))
    return keys


def _planned_count(section: Mapping[str, Any], counts: Mapping[str, Any], key: str) -> int:
    values = section.get(key)
    if isinstance(values, list):
        return len(values)
    return _int_value(counts.get(key))


def _section_count(
    section: Mapping[str, Any],
    station_summary: Mapping[str, Any],
    counts: Mapping[str, Any],
    key: str,
) -> int:
    values = section.get(key)
    if isinstance(values, list):
        return len(values)
    return _count_value(station_summary, key, fallback=_int_value(counts.get(key)))


def _suppressed_station_writes(section: Mapping[str, Any], counts: Mapping[str, Any]) -> int:
    suppressed = section.get('station_writes_suppressed')
    if isinstance(suppressed, list):
        return len(suppressed)
    return _int_value(counts.get('station_write_suppressed_non_benign_conflict'))


def _systems_processed(report: Mapping[str, Any], section: Mapping[str, Any]) -> int:
    systems = section.get('systems')
    if isinstance(systems, list):
        return len({system.get('id64') for system in systems if isinstance(system, Mapping) and system.get('id64') is not None})
    return 1 if isinstance(report.get('system'), Mapping) else 0


def _dirty_planned(summary: Mapping[str, Any], dirty: Mapping[str, Any]) -> int:
    if 'dirty_systems_planned' in summary:
        return _int_value(summary.get('dirty_systems_planned'))
    system_ids = dirty.get('system_ids')
    if isinstance(system_ids, list):
        return len(system_ids)
    return 0


def _count_value(values: Mapping[str, Any], key: str, *, fallback: int = 0) -> int:
    if key in values:
        return _int_value(values.get(key))
    return fallback


def _list_value(values: Mapping[str, Any], key: str) -> list[Any]:
    value = values.get(key)
    return value if isinstance(value, list) else []


def _int_value(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalise_name(value: Any) -> str | None:
    text = _clean_text(value)
    return ' '.join(text.lower().split()) if text else None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _format_float(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        runner = GuardedStationEnrichmentRunner(args)
        output_dir = runner.run()
    except GuardFailure as exc:
        print(f'Guard failed: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Interrupted.', file=sys.stderr)
        return 130
    print(f'Guarded station enrichment completed. Output directory: {output_dir}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
