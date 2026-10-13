#!/usr/bin/env python3
'''Complete, read-only calibration pass for the V3 system-archetype model.'''
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.operator.lib import f2d_operator_identity  # noqa: E402


COMPLETE_VERSION = 'v3-archetype-calibration-complete-1'
DEFAULT_DATABASE_URL_ENV = 'V3_ARCHETYPE_COMPLETE_DATABASE_URL'
DEFAULT_IDENTITY_ENV = 'F2D_OPERATOR_CODE_SHA256_ATTESTED'
TIERS = ('S', 'A', 'B', 'C', 'D')
CHECKPOINT_SCHEMA = 'ed-finder/v3-archetype-calibration-checkpoint/v1'
RECEIPT_SCHEMA = 'ed-finder/v3-archetype-calibration-complete/v1'


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
    temporary = path.with_name(f'.{path.name}.tmp-{os.getpid()}')
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
    parser.add_argument('--statement-timeout-ms', type=int, default=60_000)
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
        'per_chunk': [],
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


def _validate_checkpoint_state(
    checkpoint: dict[str, Any],
    *,
    chunk_plan: list[dict[str, int]],
    keys: tuple[str, ...],
) -> int:
    next_index = checkpoint.get('next_chunk_index')
    system_count = checkpoint.get('system_count')
    per_chunk = checkpoint.get('per_chunk')
    totals = checkpoint.get('tier_histograms')
    if (
        not isinstance(next_index, int)
        or isinstance(next_index, bool)
        or not 0 <= next_index <= len(chunk_plan)
        or not isinstance(system_count, int)
        or isinstance(system_count, bool)
        or system_count < 0
        or not isinstance(per_chunk, list)
        or len(per_chunk) != next_index
        or not isinstance(totals, dict)
        or set(totals) != set(keys)
    ):
        raise ValueError('checkpoint progress shape is invalid')
    recomputed = _empty_histogram(keys)
    recomputed_systems = 0
    for index, chunk in enumerate(per_chunk):
        planned = chunk_plan[index]
        if (
            not isinstance(chunk, dict)
            or chunk.get('chunk_ordinal') != planned['chunk_ordinal']
            or chunk.get('row_count') != planned['row_count']
            or not isinstance(chunk.get('per_archetype'), dict)
        ):
            raise ValueError('checkpoint chunk sequence is invalid')
        for key in keys:
            entry = chunk['per_archetype'].get(key)
            histogram = entry.get('tier_histogram') if isinstance(entry, dict) else None
            if not isinstance(histogram, dict) or set(histogram) != set(TIERS):
                raise ValueError('checkpoint chunk histogram shape is invalid')
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in histogram.values()
            ) or sum(histogram.values()) != planned['row_count']:
                raise ValueError('checkpoint chunk histogram total is invalid')
            for tier in TIERS:
                recomputed[key][tier] += histogram[tier]
        recomputed_systems += planned['row_count']
    if recomputed_systems != system_count or recomputed != totals:
        raise ValueError('checkpoint cumulative totals are invalid')
    return next_index


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


def _apply_chunk(
    checkpoint: dict[str, Any],
    *,
    ordinal: int,
    expected_rows: int,
    histograms: dict[str, dict[str, int]],
    actual_rows: int,
) -> None:
    if actual_rows != expected_rows:
        raise ValueError(
            f'chunk {ordinal} row count mismatch: expected {expected_rows}, got {actual_rows}'
        )
    for key, histogram in histograms.items():
        if sum(histogram.values()) != actual_rows:
            raise ValueError(f'chunk {ordinal} {key} tier total mismatch')
        for tier in TIERS:
            checkpoint['tier_histograms'][key][tier] += histogram[tier]
    checkpoint['per_chunk'].append({
        'chunk_ordinal': ordinal,
        'row_count': actual_rows,
        'per_archetype': {
            key: {'tier_histogram': histogram}
            for key, histogram in histograms.items()
        },
    })
    checkpoint['system_count'] += actual_rows
    checkpoint['next_chunk_index'] += 1


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
    per_archetype: dict[str, Any] = {}
    for key in model.ARCHETYPE_KEYS:
        histogram = checkpoint['tier_histograms'][key]
        if sum(histogram.values()) != system_count:
            raise ValueError(f'{key} tier total does not equal system_count')
        per_archetype[key] = {
            'tier_histogram': histogram,
            'per_chunk': [
                {
                    'chunk_ordinal': chunk['chunk_ordinal'],
                    'row_count': chunk['row_count'],
                    'tier_histogram': chunk['per_archetype'][key]['tier_histogram'],
                }
                for chunk in checkpoint['per_chunk']
            ],
        }

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
            'chunks': chunk_plan,
            'sha256': chunk_plan_sha256,
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


def run_complete(
    connection: Any,
    args: argparse.Namespace,
    *,
    f2d_identity: str,
    model_file_sha256: str | None = None,
) -> tuple[int, dict[str, Any] | None]:
    connection.read_only = True
    connection.execute(
        "SELECT set_config('default_transaction_read_only','on',false)",
    )
    connection.execute(
        "SELECT set_config('statement_timeout',%s,false)",
        (f'{args.statement_timeout_ms}ms',),
    )
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

    next_index = _validate_checkpoint_state(
        checkpoint,
        chunk_plan=chunk_plan,
        keys=tuple(model.ARCHETYPE_KEYS),
    )
    processed_this_run = 0
    for index in range(next_index, len(chunk_plan)):
        chunk = chunk_plan[index]
        raw_rows = probe._read_chunk_rows(
            connection, generation_id, chunk['chunk_ordinal'],
        )
        histograms, actual_rows = _score_chunk(raw_rows, model)
        connection.commit()
        _apply_chunk(
            checkpoint,
            ordinal=chunk['chunk_ordinal'],
            expected_rows=chunk['row_count'],
            histograms=histograms,
            actual_rows=actual_rows,
        )
        _atomic_json(checkpoint_path, checkpoint)
        processed_this_run += 1
        if (
            args.stop_after_chunks is not None
            and processed_this_run >= args.stop_after_chunks
            and checkpoint['next_chunk_index'] < len(chunk_plan)
        ):
            return 75, None

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


def _failure_receipt(state_dir: Path, reason: str, identity: str) -> None:
    body = {
        'schema_version': RECEIPT_SCHEMA,
        'mode': 'complete',
        'status': 'failed',
        'failures': [reason],
        'f2d_operator_code_sha256': identity,
        'read_only': True,
        'db_writes_performed': False,
    }
    try:
        _atomic_json(state_dir / 'failure-receipt.json', seal_receipt(body))
    except OSError:
        pass


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
        model_file_sha256 = require_image_model_match(args.image_model_file)
        import psycopg

        with psycopg.connect(dsn, autocommit=False) as connection:
            exit_code, receipt = run_complete(
                connection,
                args,
                f2d_identity=f2d_identity,
                model_file_sha256=model_file_sha256,
            )
    except (ValueError, OSError) as exc:
        _failure_receipt(args.state_dir, str(exc), f2d_identity)
        print(f'complete calibration refused: {exc}', file=sys.stderr)
        return 3
    except psycopg.Error as exc:
        _failure_receipt(args.state_dir, f'database error: {type(exc).__name__}', f2d_identity)
        print(f'database error: {type(exc).__name__}', file=sys.stderr)
        return 4

    if receipt is not None:
        print(canonical_json(receipt))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
