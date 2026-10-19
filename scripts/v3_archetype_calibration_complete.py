#!/usr/bin/env python3
'''Complete, read-only calibration pass for the V3 system-archetype model.

State layout under ``--state-dir``:

``checkpoint.json``
    Small, rewritten atomically after every chunk: the generation and
    operator-code identity it is bound to, the chunk plan digest, cumulative
    per-key tier totals, ``next_chunk_index`` and the running digest of the
    per-chunk log. The production generation has ~200,000 canonical chunks, so
    the per-chunk counts never live in this file.
``per-chunk.jsonl``
    Append-only, one canonical JSON line per scored chunk in chunk order:
    ``{"chunk_ordinal", "row_count", "per_archetype": {key: {"tier_histogram"}}}``.
    The checkpoint pins its exact byte length and SHA-256; on resume the prefix
    is re-hashed and re-summed, and any bytes past the pinned length (a torn
    append) are truncated before scoring continues.
``receipt.json`` / ``failure-receipt.json``
    Sealed with ``content_sha256`` over the canonical body. The receipt carries
    the per-key totals and binds the per-chunk log by digest and byte length
    (``per_chunk``) and the chunk plan by digest (``chunk_plan``).
'''
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import ModuleType
from typing import Any
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.operator.lib import f2d_operator_identity  # noqa: E402


COMPLETE_VERSION = 'v3-archetype-calibration-complete-1'
# Bounded per-chunk retry for transient database errors (statement timeout
# under backup I/O contention, a dropped connection). A chunk is only ever
# checkpointed after it is fully scored, so a retry never double-counts.
CHUNK_RETRY_ATTEMPTS = 3
CHUNK_RETRY_BACKOFF_SECONDS = (2.0, 10.0, 30.0)
ERROR_DETAIL_LIMIT = 500

DEFAULT_DATABASE_URL_ENV = 'V3_ARCHETYPE_COMPLETE_DATABASE_URL'
DEFAULT_IDENTITY_ENV = 'F2D_OPERATOR_CODE_SHA256_ATTESTED'
# Per-launch nonce from the operator start action. Written into the checkpoint
# only after this run's identity, generation and checkpoint-state checks pass,
# so the start action can tell a fresh proof from a checkpoint left by an
# earlier run (a resume does not otherwise rewrite it until a chunk completes).
LAUNCH_ID_ENV = 'V3_ARCHETYPE_COMPLETE_LAUNCH_ID'
TIERS = ('S', 'A', 'B', 'C', 'D')
CHECKPOINT_SCHEMA = 'ed-finder/v3-archetype-calibration-checkpoint/v1'
RECEIPT_SCHEMA = 'ed-finder/v3-archetype-calibration-complete/v1'
PER_CHUNK_SCHEMA = 'ed-finder/v3-archetype-calibration-per-chunk/v1'
PER_CHUNK_FILE = 'per-chunk.jsonl'
EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def seal_receipt(body: dict[str, Any]) -> dict[str, Any]:
    if 'content_sha256' in body:
        raise ValueError('receipt body already contains content_sha256')
    return {**body, 'content_sha256': canonical_sha256(body)}


def validate_complete_receipt(receipt: object) -> dict[str, Any]:
    '''Validate the complete-mode discriminator and canonical content seal.'''
    if not isinstance(receipt, dict):
        raise ValueError('complete receipt must be an object')
    if receipt.get('mode') != 'complete':
        raise ValueError('calibration receipt mode is not complete')
    seal = receipt.get('content_sha256')
    if not isinstance(seal, str) or len(seal) != 64:
        raise ValueError('complete receipt content_sha256 is missing or malformed')
    try:
        bytes.fromhex(seal)
    except ValueError as exc:
        raise ValueError('complete receipt content_sha256 is missing or malformed') from exc
    body = dict(receipt)
    del body['content_sha256']
    if canonical_sha256(body) != seal:
        raise ValueError('complete receipt content_sha256 mismatch')
    return receipt


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # The worker is PID 1 in its container, so a pid-based temporary name is
    # the same on every run: a hard kill (SIGKILL, OOM, host reboot) inside
    # the write window left `.checkpoint.json.tmp-1` behind and O_EXCL then
    # refused every later resume. Clear stale temporaries of this file first
    # and use a per-write nonce; fsync + rename semantics are unchanged.
    for stale in path.parent.glob(f'.{path.name}.tmp-*'):
        if not stale.is_symlink() and stale.is_file():
            stale.unlink(missing_ok=True)
    temporary = path.with_name(f'.{path.name}.tmp-{uuid.uuid4().hex}')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(canonical_json(payload))
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'{path.name} is unreadable or invalid') from exc
    if not isinstance(value, dict):
        raise ValueError(f'{path.name} is not a JSON object')
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation-key', required=True)
    parser.add_argument('--generation-id', required=True)
    parser.add_argument('--publication-sequence', type=int, required=True)
    parser.add_argument('--state-dir', type=Path, default=Path('/state'))
    parser.add_argument('--database-url-env', default=DEFAULT_DATABASE_URL_ENV)
    parser.add_argument(
        '--image-model-file',
        type=Path,
        default=Path('/app/shared_contracts/v3_system_archetype_model.py'),
    )
    # Five minutes: a single chunk read under concurrent pgBackRest I/O must
    # not cancel the multi-hour complete read; the probe's 60 s was too tight.
    parser.add_argument('--statement-timeout-ms', type=int, default=300_000)
    parser.add_argument('--stop-after-chunks', type=int)
    args = parser.parse_args(argv)
    if args.publication_sequence < 1:
        parser.error('--publication-sequence must be positive')
    if args.statement_timeout_ms < 1:
        parser.error('--statement-timeout-ms must be positive')
    if args.stop_after_chunks is not None and args.stop_after_chunks < 1:
        parser.error('--stop-after-chunks must be positive')
    return args


def require_image_model_match(image_model_file: Path) -> str:
    '''Bind the checkout model to the model vendored in the running API image.'''
    checkout_model = ROOT / 'shared_contracts/v3_system_archetype_model.py'
    if image_model_file.is_symlink() or not image_model_file.is_file():
        raise ValueError('API image archetype model file is missing or symlinked')
    try:
        checkout_sha = hashlib.sha256(checkout_model.read_bytes()).hexdigest()
        image_sha = hashlib.sha256(image_model_file.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError('API image archetype model file is unreadable') from exc
    if image_sha != checkout_sha:
        raise ValueError('API image and checkout archetype model files differ')
    return image_sha


def _load_scoring_modules() -> tuple[ModuleType, ModuleType, ModuleType]:
    from scripts import v3_archetype_calibration_probe as probe
    from scripts import v3_system_archetype as builder
    from shared_contracts import v3_system_archetype_model as model

    return probe, builder, model


def _listed_paths() -> set[str]:
    entries = f2d_operator_identity.manifest_entries(ROOT)
    return {entry for entry in entries if not entry.startswith('requirement:')}


def refuse_unlisted_checkout_modules() -> None:
    '''Refuse a loaded repository module not covered by the operator manifest.'''
    root = ROOT.resolve()
    listed = _listed_paths()
    unlisted: list[str] = []
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        try:
            relative = Path(filename).resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
        if relative.endswith(('.pyc', '.pyo')):
            relative = relative.rsplit('__pycache__/', 1)[0] + relative.rsplit('/', 1)[-1].split('.')[0] + '.py'
        if relative not in listed:
            unlisted.append(relative)
    if unlisted:
        raise ValueError(
            'loaded checkout module is absent from F2d operator manifest: '
            + ', '.join(sorted(set(unlisted)))
        )


def _generation(connection: Any, generation_key: str) -> tuple[Any, ...] | None:
    return connection.execute(
        '''SELECT g.derived_generation_id::text,g.generation_key,
                  g.lifecycle_state,g.expected_systems,
                  g.canonical_generation_id::text,
                  g.canonical_publication_sequence,
                  g.manifest,
                  p.publication_sequence
             FROM v3_meta.derived_generation g
             LEFT JOIN v3_meta.current_derived_generation p
               ON p.singleton AND p.derived_generation_id=g.derived_generation_id
            WHERE g.generation_key=%s''',
        (generation_key,),
    ).fetchone()


def _empty_histogram(keys: tuple[str, ...]) -> dict[str, dict[str, int]]:
    return {key: {tier: 0 for tier in TIERS} for key in keys}


def _new_checkpoint(
    *,
    generation_key: str,
    generation_id: str,
    publication_sequence: int,
    f2d_identity: str,
    chunk_plan_sha256: str,
    keys: tuple[str, ...],
) -> dict[str, Any]:
    return {
        'schema_version': CHECKPOINT_SCHEMA,
        'generation_key': generation_key,
        'derived_generation_id': generation_id,
        'publication_sequence': publication_sequence,
        'f2d_operator_code_sha256': f2d_identity,
        'chunk_plan_sha256': chunk_plan_sha256,
        'next_chunk_index': 0,
        'system_count': 0,
        'tier_histograms': _empty_histogram(keys),
        'per_chunk_bytes': 0,
        'per_chunk_sha256': EMPTY_SHA256,
        'started_at': _utc_now(),
    }


def _require_checkpoint_identity(
    checkpoint: dict[str, Any],
    *,
    generation_key: str,
    generation_id: str,
    publication_sequence: int,
    f2d_identity: str,
    chunk_plan_sha256: str,
) -> None:
    expected = {
        'schema_version': CHECKPOINT_SCHEMA,
        'generation_key': generation_key,
        'derived_generation_id': generation_id,
        'publication_sequence': publication_sequence,
        'f2d_operator_code_sha256': f2d_identity,
        'chunk_plan_sha256': chunk_plan_sha256,
    }
    for field, value in expected.items():
        if checkpoint.get(field) != value:
            raise ValueError(f'checkpoint {field} mismatch')


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_per_chunk_line(line: bytes) -> dict[str, Any]:
    try:
        chunk = json.loads(line.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('per-chunk log line is not valid JSON') from exc
    if not isinstance(chunk, dict):
        raise ValueError('per-chunk log line is not a JSON object')
    return chunk


def _validate_chunk_record(
    chunk: dict[str, Any],
    *,
    planned: dict[str, int],
    keys: tuple[str, ...],
) -> None:
    if (
        chunk.get('chunk_ordinal') != planned['chunk_ordinal']
        or chunk.get('row_count') != planned['row_count']
        or not isinstance(chunk.get('per_archetype'), dict)
        or set(chunk['per_archetype']) != set(keys)
    ):
        raise ValueError('per-chunk log sequence does not match the chunk plan')
    for key in keys:
        entry = chunk['per_archetype'][key]
        histogram = entry.get('tier_histogram') if isinstance(entry, dict) else None
        if not isinstance(histogram, dict) or set(histogram) != set(TIERS):
            raise ValueError('per-chunk log histogram shape is invalid')
        if (
            not all(_is_count(value) for value in histogram.values())
            or sum(histogram.values()) != planned['row_count']
        ):
            raise ValueError('per-chunk log histogram total is invalid')


def read_per_chunk_log(
    path: Path,
    *,
    chunk_plan: list[dict[str, int]],
    keys: tuple[str, ...],
    expected_bytes: int | None = None,
    expected_sha256: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]], int, str]:
    '''Validate a per-chunk log against the chunk plan and return its contents.

    Returns ``(chunks, cumulative histograms, byte length, sha256)``. When
    ``expected_bytes`` is given only that prefix is read and verified; the
    caller decides what to do with any bytes beyond it.
    '''
    if path.is_symlink() or not path.is_file():
        raise ValueError('per-chunk log is missing or not a regular file')
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError('per-chunk log is unreadable') from exc
    if expected_bytes is not None:
        if len(data) < expected_bytes:
            raise ValueError('per-chunk log is shorter than the checkpoint records')
        data = data[:expected_bytes]
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError('per-chunk log digest does not match the checkpoint')
    if data and not data.endswith(b'\n'):
        raise ValueError('per-chunk log does not end at a line boundary')
    lines = data.split(b'\n')[:-1] if data else []
    if len(lines) > len(chunk_plan):
        raise ValueError('per-chunk log has more chunks than the chunk plan')
    chunks: list[dict[str, Any]] = []
    totals = _empty_histogram(keys)
    for index, line in enumerate(lines):
        chunk = _parse_per_chunk_line(line)
        _validate_chunk_record(chunk, planned=chunk_plan[index], keys=keys)
        for key in keys:
            histogram = chunk['per_archetype'][key]['tier_histogram']
            for tier in TIERS:
                totals[key][tier] += histogram[tier]
        chunks.append(chunk)
    return chunks, totals, len(data), digest


def _validate_checkpoint_state(
    checkpoint: dict[str, Any],
    *,
    state_dir: Path,
    chunk_plan: list[dict[str, int]],
    keys: tuple[str, ...],
) -> tuple[int, Any]:
    '''Verify the checkpoint against the per-chunk log.

    Returns ``(resume index, live SHA-256 object over the verified log)``. A
    torn append (bytes past the checkpointed length) is truncated so the log
    and the checkpoint agree before any further chunk is scored.
    '''
    next_index = checkpoint.get('next_chunk_index')
    system_count = checkpoint.get('system_count')
    totals = checkpoint.get('tier_histograms')
    per_chunk_bytes = checkpoint.get('per_chunk_bytes')
    per_chunk_sha256 = checkpoint.get('per_chunk_sha256')
    if (
        not _is_count(next_index)
        or next_index > len(chunk_plan)
        or not _is_count(system_count)
        or not _is_count(per_chunk_bytes)
        or not isinstance(per_chunk_sha256, str)
        or not isinstance(totals, dict)
        or set(totals) != set(keys)
    ):
        raise ValueError('checkpoint progress shape is invalid')
    log_path = state_dir / PER_CHUNK_FILE
    if next_index == 0 and per_chunk_bytes == 0 and not log_path.exists():
        if system_count != 0 or totals != _empty_histogram(keys):
            raise ValueError('checkpoint cumulative totals are invalid')
        return 0, hashlib.sha256()
    chunks, recomputed, _, _ = read_per_chunk_log(
        log_path,
        chunk_plan=chunk_plan,
        keys=keys,
        expected_bytes=per_chunk_bytes,
        expected_sha256=per_chunk_sha256,
    )
    if len(chunks) != next_index:
        raise ValueError('per-chunk log chunk count does not match the checkpoint')
    recomputed_systems = sum(chunk['row_count'] for chunk in chunks)
    if recomputed_systems != system_count or recomputed != totals:
        raise ValueError('checkpoint cumulative totals are invalid')
    if log_path.stat().st_size > per_chunk_bytes:
        with log_path.open('r+b') as handle:
            handle.truncate(per_chunk_bytes)
            handle.flush()
            os.fsync(handle.fileno())
    with log_path.open('rb') as handle:
        verified = handle.read(per_chunk_bytes)
    log_digest = hashlib.sha256(verified)
    if log_digest.hexdigest() != per_chunk_sha256:
        raise ValueError('per-chunk log digest does not match the checkpoint')
    return next_index, log_digest


def _append_per_chunk(path: Path, record: dict[str, Any]) -> bytes:
    line = (canonical_json(record) + '\n').encode('utf-8')
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, 'ab') as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    return line


def _score_chunk(
    raw_rows: dict[int, tuple[Any, tuple[tuple[int, int, int], ...]]],
    model: ModuleType,
) -> tuple[dict[str, dict[str, int]], int]:
    histograms = _empty_histogram(tuple(model.ARCHETYPE_KEYS))
    for system_id64 in sorted(raw_rows):
        vector, groups = raw_rows[system_id64]
        scored = model.score_raw_system(vector, groups)
        for key in model.ARCHETYPE_KEYS:
            histograms[key][scored[f'{key}_tier']] += 1
    return histograms, len(raw_rows)


def _chunk_record(
    *,
    ordinal: int,
    expected_rows: int,
    histograms: dict[str, dict[str, int]],
    actual_rows: int,
) -> dict[str, Any]:
    if actual_rows != expected_rows:
        raise ValueError(
            f'chunk {ordinal} row count mismatch: expected {expected_rows}, got {actual_rows}'
        )
    for key, histogram in histograms.items():
        if sum(histogram.values()) != actual_rows:
            raise ValueError(f'chunk {ordinal} {key} tier total mismatch')
    return {
        'chunk_ordinal': ordinal,
        'row_count': actual_rows,
        'per_archetype': {
            key: {'tier_histogram': histogram}
            for key, histogram in histograms.items()
        },
    }


def _apply_chunk(
    checkpoint: dict[str, Any],
    *,
    record: dict[str, Any],
    appended: bytes,
    log_digest: Any,
) -> None:
    '''Fold one appended per-chunk record into the cumulative checkpoint.

    ``log_digest`` is the live SHA-256 object over the per-chunk log so far.
    '''
    for key, entry in record['per_archetype'].items():
        for tier in TIERS:
            checkpoint['tier_histograms'][key][tier] += entry['tier_histogram'][tier]
    checkpoint['system_count'] += record['row_count']
    checkpoint['next_chunk_index'] += 1
    log_digest.update(appended)
    checkpoint['per_chunk_bytes'] += len(appended)
    checkpoint['per_chunk_sha256'] = log_digest.hexdigest()


def _sigma_all(histograms: dict[str, dict[str, int]], total: int) -> float:
    sigma = Fraction()
    for histogram in histograms.values():
        s_count = histogram['S']
        a_count = histogram['A']
        b_count = histogram['B']
        sigma += Fraction(s_count + a_count + b_count, total)
        sigma += Fraction(s_count + a_count, total)
        sigma += Fraction(s_count, total)
    return float(sigma)


def _receipt_body(
    *,
    checkpoint: dict[str, Any],
    generation: Any,
    chunk_plan: list[dict[str, int]],
    chunk_plan_sha256: str,
    builder: ModuleType,
    model: ModuleType,
    f2d_identity: str,
    model_file_sha256: str,
) -> dict[str, Any]:
    system_count = int(checkpoint['system_count'])
    expected = int(generation.expected_systems)
    if system_count != expected:
        raise ValueError(
            f'complete system count mismatch: expected {expected}, got {system_count}'
        )
    if checkpoint['next_chunk_index'] != len(chunk_plan):
        raise ValueError('complete read has not scored every canonical chunk')
    per_archetype: dict[str, Any] = {}
    for key in model.ARCHETYPE_KEYS:
        histogram = checkpoint['tier_histograms'][key]
        if sum(histogram.values()) != system_count:
            raise ValueError(f'{key} tier total does not equal system_count')
        per_archetype[key] = {'tier_histogram': histogram}

    expected_manifest = builder.product_manifest(generation)
    return {
        'schema_version': RECEIPT_SCHEMA,
        'complete_version': COMPLETE_VERSION,
        'mode': 'complete',
        'status': 'completed',
        'generation': {
            'generation_key': generation.key,
            'derived_generation_id': generation.identifier,
            'publication_sequence': checkpoint['publication_sequence'],
            'canonical_generation_id': generation.canonical_generation_id,
            'canonical_publication_sequence': generation.canonical_publication_sequence,
        },
        'system_count': system_count,
        'chunk_plan': {
            'chunk_count': len(chunk_plan),
            'first_chunk_ordinal': chunk_plan[0]['chunk_ordinal'],
            'last_chunk_ordinal': chunk_plan[-1]['chunk_ordinal'],
            'sha256': chunk_plan_sha256,
        },
        'per_chunk': {
            'file': PER_CHUNK_FILE,
            'schema_version': PER_CHUNK_SCHEMA,
            'chunk_count': checkpoint['next_chunk_index'],
            'bytes': checkpoint['per_chunk_bytes'],
            'sha256': checkpoint['per_chunk_sha256'],
        },
        'per_archetype': per_archetype,
        'coefficients': builder._coefficients(),
        'code_identity': builder.code_identity(),
        'archetype_model_sha256': model.archetype_model_sha256(),
        'model_file_sha256': model_file_sha256,
        'f2d_operator_code_sha256': f2d_identity,
        'expected_product_manifest': expected_manifest,
        'expected_product_manifest_sha256': canonical_sha256(expected_manifest),
        'sigma_all': _sigma_all(checkpoint['tier_histograms'], system_count),
        'read_only': True,
        'db_writes_performed': False,
    }


def configure_session(connection: Any, statement_timeout_ms: int) -> None:
    '''Apply the read-only, bounded, custom-plan session settings.

    Called on the initial connection and again after a reconnect.
    '''
    connection.read_only = True
    connection.execute(
        "SELECT set_config('default_transaction_read_only','on',false)",
    )
    connection.execute(
        "SELECT set_config('statement_timeout',%s,false)",
        (f'{statement_timeout_ms}ms',),
    )
    # The two shared read constants select their branch with parameter
    # NULL tests. Custom plans fold those per execution so every one of the
    # ~200,000 chunk reads keeps the (generation, chunk_ordinal) index path
    # instead of a generic plan chosen without the parameter values.
    connection.execute(
        "SELECT set_config('plan_cache_mode','force_custom_plan',false)",
    )
    # autocommit is off: the settings above live in a transaction until this
    # commit, and a later rollback would otherwise discard them.
    connection.commit()


class ChunkReadError(RuntimeError):
    '''A chunk could not be read after the bounded retries.'''

    def __init__(self, ordinal: int, cause: BaseException) -> None:
        super().__init__(f'chunk {ordinal}: {_error_detail(cause)}')
        self.ordinal = ordinal
        self.cause = cause


def _error_detail(exc: BaseException) -> str:
    text = f'{type(exc).__name__}: {exc}'.replace('\n', ' ')
    return text[:ERROR_DETAIL_LIMIT]


def _sqlstate(exc: BaseException) -> str | None:
    value = getattr(exc, 'sqlstate', None)
    return value if isinstance(value, str) else None


def _is_database_error(exc: BaseException) -> bool:
    psycopg = sys.modules.get('psycopg')
    return psycopg is not None and isinstance(exc, psycopg.Error)


def _connection_unusable(connection: Any) -> bool:
    # psycopg marks a connection closed or broken once the server link is
    # gone; a statement cancel (QueryCanceled is an OperationalError too)
    # leaves the connection usable after a rollback.
    return bool(getattr(connection, 'closed', False) or getattr(connection, 'broken', False))


def _read_and_score_chunk(
    connection: Any,
    *,
    reconnect: Any,
    probe: ModuleType,
    model: ModuleType,
    generation_id: str,
    ordinal: int,
    statement_timeout_ms: int,
    sleep: Any = time.sleep,
) -> tuple[Any, dict[str, dict[str, int]], int]:
    '''Read and score one chunk with bounded retries.

    Returns ``(connection, histograms, row_count)``; the connection is a new
    one when a reconnect was needed. Nothing is checkpointed here, so a retry
    can never double-count a chunk.
    '''
    last: BaseException | None = None
    # None means "replace the connection before the next attempt"; a failed
    # reconnect or session configuration counts against the same budget, so
    # it can never escape this loop without the chunk ordinal.
    for attempt in range(CHUNK_RETRY_ATTEMPTS):
        try:
            if connection is None:
                # Keep the connection None until it is fully configured: a
                # configuration failure must not leave a half-set-up
                # connection that the next attempt would use unconfigured.
                candidate = reconnect()
                try:
                    configure_session(candidate, statement_timeout_ms)
                except BaseException:
                    try:
                        candidate.close()
                    except Exception:  # noqa: BLE001 - best effort
                        pass
                    raise
                connection = candidate
            raw_rows = probe._read_chunk_rows(connection, generation_id, ordinal)
            histograms, actual_rows = _score_chunk(raw_rows, model)
            connection.commit()
            return connection, histograms, actual_rows
        except Exception as exc:  # noqa: BLE001 - classified below
            if not _is_database_error(exc):
                raise
            last = exc
            print(
                f'chunk {ordinal} attempt {attempt + 1}/{CHUNK_RETRY_ATTEMPTS} failed: '
                f'{_error_detail(exc)}',
                file=sys.stderr,
            )
            if attempt + 1 >= CHUNK_RETRY_ATTEMPTS:
                break
            replace = connection is None or _connection_unusable(connection)
            if not replace:
                try:
                    connection.rollback()
                except Exception as rollback_exc:  # noqa: BLE001
                    if not _is_database_error(rollback_exc):
                        raise
                    replace = True
            if replace and connection is not None:
                try:
                    connection.close()
                except Exception:  # noqa: BLE001 - the old connection is dead
                    pass
                connection = None
            sleep(CHUNK_RETRY_BACKOFF_SECONDS[min(attempt, len(CHUNK_RETRY_BACKOFF_SECONDS) - 1)])
    assert last is not None
    raise ChunkReadError(ordinal, last) from last


def run_complete(
    connection: Any,
    args: argparse.Namespace,
    *,
    f2d_identity: str,
    model_file_sha256: str | None = None,
    reconnect: Any = None,
    sleep: Any = time.sleep,
) -> tuple[int, dict[str, Any] | None]:
    configure_session(connection, args.statement_timeout_ms)
    if reconnect is None:
        def reconnect() -> Any:
            raise ValueError('database connection lost and no reconnect is available')
    row = _generation(connection, args.generation_key)
    if row is None:
        raise ValueError('generation not found')
    (
        generation_id,
        generation_key,
        lifecycle_state,
        expected_systems,
        canonical_generation_id,
        canonical_publication_sequence,
        manifest,
        publication_sequence,
    ) = row
    if (
        generation_id != args.generation_id
        or generation_key != args.generation_key
        or lifecycle_state != 'PUBLISHED'
        or publication_sequence != args.publication_sequence
    ):
        raise ValueError('pinned current published generation identity mismatch')

    probe, builder, model = _load_scoring_modules()
    refuse_unlisted_checkout_modules()
    chunks = probe._chunk_rows(connection, generation_id)
    chunk_plan = [
        {'chunk_ordinal': int(ordinal), 'row_count': int(row_count)}
        for ordinal, row_count in chunks
    ]
    if not chunk_plan:
        raise ValueError('canonical chunk plan is empty')
    if sum(chunk['row_count'] for chunk in chunk_plan) != int(expected_systems):
        raise ValueError('canonical chunk plan total does not equal expected systems')
    chunk_plan_sha256 = canonical_sha256(
        [[chunk['chunk_ordinal'], chunk['row_count']] for chunk in chunk_plan]
    )
    connection.commit()

    generation = builder.Generation(
        identifier=generation_id,
        key=generation_key,
        state=lifecycle_state,
        canonical_generation_id=canonical_generation_id,
        canonical_publication_sequence=int(canonical_publication_sequence),
        canonical_schema=manifest.get('canonical_schema'),
        expected_systems=int(expected_systems),
    )
    checkpoint_path = args.state_dir / 'checkpoint.json'
    if checkpoint_path.exists():
        checkpoint = _read_json(checkpoint_path)
        _require_checkpoint_identity(
            checkpoint,
            generation_key=generation_key,
            generation_id=generation_id,
            publication_sequence=int(publication_sequence),
            f2d_identity=f2d_identity,
            chunk_plan_sha256=chunk_plan_sha256,
        )
    else:
        checkpoint = _new_checkpoint(
            generation_key=generation_key,
            generation_id=generation_id,
            publication_sequence=int(publication_sequence),
            f2d_identity=f2d_identity,
            chunk_plan_sha256=chunk_plan_sha256,
            keys=tuple(model.ARCHETYPE_KEYS),
        )
        _atomic_json(checkpoint_path, checkpoint)

    next_index, log_digest = _validate_checkpoint_state(
        checkpoint,
        state_dir=args.state_dir,
        chunk_plan=chunk_plan,
        keys=tuple(model.ARCHETYPE_KEYS),
    )
    launch_id = os.environ.get(LAUNCH_ID_ENV, '').strip()
    if launch_id:
        # Proof of life for this launch. Progress-only field: the sealed
        # receipt body never carries it.
        checkpoint['launch_id'] = launch_id
        checkpoint['updated_at'] = _utc_now()
        _atomic_json(checkpoint_path, checkpoint)
    log_path = args.state_dir / PER_CHUNK_FILE
    processed_this_run = 0
    for index in range(next_index, len(chunk_plan)):
        chunk = chunk_plan[index]
        connection, histograms, actual_rows = _read_and_score_chunk(
            connection,
            reconnect=reconnect,
            probe=probe,
            model=model,
            generation_id=generation_id,
            ordinal=chunk['chunk_ordinal'],
            statement_timeout_ms=args.statement_timeout_ms,
            sleep=sleep,
        )
        record = _chunk_record(
            ordinal=chunk['chunk_ordinal'],
            expected_rows=chunk['row_count'],
            histograms=histograms,
            actual_rows=actual_rows,
        )
        appended = _append_per_chunk(log_path, record)
        _apply_chunk(
            checkpoint, record=record, appended=appended, log_digest=log_digest,
        )
        # Progress fields for the status reader only; the sealed receipt never
        # carries them, so a resumed run and a fresh run seal identical bodies.
        checkpoint['chunk_count'] = len(chunk_plan)
        checkpoint['updated_at'] = _utc_now()
        _atomic_json(checkpoint_path, checkpoint)
        processed_this_run += 1
        if (
            args.stop_after_chunks is not None
            and processed_this_run >= args.stop_after_chunks
            and checkpoint['next_chunk_index'] < len(chunk_plan)
        ):
            return 75, None

    # Final consistency pass over the whole per-chunk log before sealing: the
    # log must reproduce the cumulative totals and the chunk plan identity.
    chunks, recomputed, _, _ = read_per_chunk_log(
        log_path,
        chunk_plan=chunk_plan,
        keys=tuple(model.ARCHETYPE_KEYS),
        expected_bytes=checkpoint['per_chunk_bytes'],
        expected_sha256=checkpoint['per_chunk_sha256'],
    )
    if len(chunks) != len(chunk_plan) or recomputed != checkpoint['tier_histograms']:
        raise ValueError('per-chunk log does not reproduce the cumulative totals')
    if _chunk_plan_sha256_of(chunks) != chunk_plan_sha256:
        raise ValueError('per-chunk log does not reproduce the chunk plan identity')

    body = _receipt_body(
        checkpoint=checkpoint,
        generation=generation,
        chunk_plan=chunk_plan,
        chunk_plan_sha256=chunk_plan_sha256,
        builder=builder,
        model=model,
        f2d_identity=f2d_identity,
        model_file_sha256=(
            model_file_sha256
            if model_file_sha256 is not None
            else hashlib.sha256(
                (ROOT / 'shared_contracts/v3_system_archetype_model.py').read_bytes()
            ).hexdigest()
        ),
    )
    receipt = seal_receipt(body)
    _atomic_json(args.state_dir / 'receipt.json', receipt)
    return 0, receipt


def _chunk_plan_sha256_of(chunks: list[dict[str, Any]]) -> str:
    return canonical_sha256(
        [[int(chunk['chunk_ordinal']), int(chunk['row_count'])] for chunk in chunks]
    )


def validate_per_chunk_log(receipt: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    '''Verify a per-chunk log against a validated complete receipt.

    Consumers (the capacity gate) call this when the log accompanies the
    committed receipt: the log must hash to the receipt's ``per_chunk`` digest
    and length, reproduce the chunk plan digest, and sum to the per-key totals
    and ``system_count``. Returns the parsed chunk records.
    '''
    validate_complete_receipt(receipt)
    binding = receipt.get('per_chunk')
    plan = receipt.get('chunk_plan')
    totals = receipt.get('per_archetype')
    if (
        not isinstance(binding, dict)
        or not isinstance(plan, dict)
        or not isinstance(totals, dict)
        or not _is_count(binding.get('bytes'))
        or not _is_count(binding.get('chunk_count'))
        or not isinstance(binding.get('sha256'), str)
        or not isinstance(plan.get('sha256'), str)
    ):
        raise ValueError('complete receipt per_chunk or chunk_plan binding is malformed')
    keys = tuple(totals)
    if path.is_symlink() or not path.is_file():
        raise ValueError('per-chunk log is missing or not a regular file')
    data = path.read_bytes()
    if len(data) != binding['bytes'] or hashlib.sha256(data).hexdigest() != binding['sha256']:
        raise ValueError('per-chunk log does not match the receipt binding')
    if data and not data.endswith(b'\n'):
        raise ValueError('per-chunk log does not end at a line boundary')
    lines = data.split(b'\n')[:-1] if data else []
    if len(lines) != binding['chunk_count']:
        raise ValueError('per-chunk log chunk count does not match the receipt')
    chunks = [_parse_per_chunk_line(line) for line in lines]
    recomputed = _empty_histogram(keys)
    system_count = 0
    for chunk in chunks:
        planned = {
            'chunk_ordinal': chunk.get('chunk_ordinal'),
            'row_count': chunk.get('row_count'),
        }
        if not _is_count(planned['chunk_ordinal']) or not _is_count(planned['row_count']):
            raise ValueError('per-chunk log sequence does not match the chunk plan')
        _validate_chunk_record(chunk, planned=planned, keys=keys)
        system_count += chunk['row_count']
        for key in keys:
            for tier in TIERS:
                recomputed[key][tier] += chunk['per_archetype'][key]['tier_histogram'][tier]
    if _chunk_plan_sha256_of(chunks) != plan['sha256']:
        raise ValueError('per-chunk log does not reproduce the chunk plan identity')
    if system_count != receipt.get('system_count'):
        raise ValueError('per-chunk log does not reproduce system_count')
    for key in keys:
        if totals[key].get('tier_histogram') != recomputed[key]:
            raise ValueError(f'per-chunk log does not reproduce the {key} tier totals')
    return chunks


def _failure_receipt(
    state_dir: Path,
    reason: str,
    identity: str,
    *,
    error: str | None = None,
    sqlstate: str | None = None,
    chunk_ordinal: int | None = None,
) -> None:
    body: dict[str, Any] = {
        'schema_version': RECEIPT_SCHEMA,
        'mode': 'complete',
        'status': 'failed',
        'failures': [reason],
        'f2d_operator_code_sha256': identity,
        'read_only': True,
        'db_writes_performed': False,
    }
    if error is not None:
        body['error'] = error[:ERROR_DETAIL_LIMIT]
    if sqlstate is not None:
        body['sqlstate'] = sqlstate
    if chunk_ordinal is not None:
        body['chunk_ordinal'] = chunk_ordinal
    try:
        _atomic_json(state_dir / 'failure-receipt.json', seal_receipt(body))
    except OSError as exc:
        print(f'failure receipt could not be written: {_error_detail(exc)}', file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    attested = os.environ.get(DEFAULT_IDENTITY_ENV, '')
    try:
        f2d_identity = f2d_operator_identity.require_operator_code_identity(
            ROOT, attested,
        )
    except f2d_operator_identity.OperatorIdentityError as exc:
        print(f'operator code identity refusal: {exc}', file=sys.stderr)
        return 2
    dsn = os.environ.get(args.database_url_env)
    if not dsn:
        print(f'database URL environment variable {args.database_url_env} is missing', file=sys.stderr)
        return 2

    try:
        import psycopg
    except ImportError:
        print('psycopg is not installed in the worker environment', file=sys.stderr)
        return 2

    # psycopg exceptions never carry the connection string; the DSN is read
    # from the environment and formatted nowhere in this program.
    def reconnect() -> Any:
        return psycopg.connect(dsn, autocommit=False)

    try:
        model_file_sha256 = require_image_model_match(args.image_model_file)
        with psycopg.connect(dsn, autocommit=False) as connection:
            exit_code, receipt = run_complete(
                connection,
                args,
                f2d_identity=f2d_identity,
                model_file_sha256=model_file_sha256,
                reconnect=reconnect,
            )
    except ChunkReadError as exc:
        _failure_receipt(
            args.state_dir, f'database error: {type(exc.cause).__name__}', f2d_identity,
            error=_error_detail(exc.cause), sqlstate=_sqlstate(exc.cause),
            chunk_ordinal=exc.ordinal,
        )
        print(f'database error on chunk {exc.ordinal}: {_error_detail(exc.cause)}', file=sys.stderr)
        return 4
    except (ValueError, OSError) as exc:
        _failure_receipt(args.state_dir, str(exc), f2d_identity, error=_error_detail(exc))
        print(f'complete calibration refused: {exc}', file=sys.stderr)
        return 3
    except psycopg.Error as exc:
        _failure_receipt(
            args.state_dir, f'database error: {type(exc).__name__}', f2d_identity,
            error=_error_detail(exc), sqlstate=_sqlstate(exc),
        )
        print(f'database error: {_error_detail(exc)}', file=sys.stderr)
        return 4
    except Exception as exc:  # noqa: BLE001 - every failure must leave a receipt
        _failure_receipt(
            args.state_dir, f'internal error: {type(exc).__name__}', f2d_identity,
            error=_error_detail(exc),
        )
        print(f'internal error: {_error_detail(exc)}', file=sys.stderr)
        return 5

    if receipt is not None:
        print(canonical_json(receipt))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
