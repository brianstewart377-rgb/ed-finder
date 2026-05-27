"""
ED Finder — Ingest: EDDN Async Client for API Process
=======================================================
Lightweight async background task that ingests EDDN events relevant to
the simulation engine (Scan, FSSBodySignals, SAASignalsFound) and writes
them into journal_events + body_scan_facts.

Design rules:
  • Runs as a background asyncio.Task inside the FastAPI lifespan.
  • Does NOT block any request handler.
  • Uses the existing asyncpg pool — no separate connection.
  • Reconnects automatically on ZMQ disconnect.
  • Batches DB writes every FLUSH_INTERVAL seconds.
  • All errors are logged and swallowed — never crashes the API process.

NOTE: The existing apps/eddn/eddn_listener.py handles the full event
spectrum (systems, bodies, stations, dirty flags). This client handles
ONLY the simulation-relevant event types for body_scan_facts ingestion.
They can run side-by-side without conflict — this client writes to
different tables (journal_events, body_scan_facts).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import zlib
from typing import Optional, TYPE_CHECKING

from ring_facts import ring_rows_for_body

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger('ed_finder')

EDDN_RELAY       = 'tcp://eddn.edcd.io:9500'
FLUSH_INTERVAL   = 15    # seconds between DB batch flushes
MAX_BATCH_SIZE   = 200   # flush early if batch exceeds this
RECONNECT_DELAY  = 5     # seconds between reconnect attempts

# Event types we process for the simulation engine
SIMULATION_EVENT_TYPES = {'Scan', 'FSSBodySignals', 'SAASignalsFound'}


async def run_eddn_simulation_ingest(pool: 'asyncpg.Pool') -> None:
    """
    Async entry point. Call as:
        asyncio.create_task(run_eddn_simulation_ingest(pool))

    Runs indefinitely — handles reconnects internally.
    Catches all exceptions to prevent crashing the API process.
    """
    log.info('EDDN simulation ingest task started')
    while True:
        try:
            await _run_ingest_loop(pool)
        except asyncio.CancelledError:
            log.info('EDDN simulation ingest task cancelled — shutting down')
            raise
        except Exception as e:
            log.warning(f'EDDN simulation ingest loop error: {e} — reconnecting in {RECONNECT_DELAY}s')
            await asyncio.sleep(RECONNECT_DELAY)


async def _run_ingest_loop(pool: 'asyncpg.Pool') -> None:
    """Single connection lifetime. Reconnects on exception."""
    try:
        import zmq
        import zmq.asyncio as azmq
    except ImportError:
        log.warning('pyzmq not available — EDDN simulation ingest disabled')
        # Sleep forever rather than fast-loop on ImportError
        await asyncio.sleep(86400)
        return

    ctx    = azmq.Context()
    socket = ctx.socket(zmq.SUB)
    socket.setsockopt(zmq.SUBSCRIBE, b'')
    socket.setsockopt(zmq.RCVTIMEO, 30_000)
    socket.connect(EDDN_RELAY)

    log.info(f'EDDN simulation ingest connected to {EDDN_RELAY}')

    # Pending batch accumulator
    pending_journal: list[dict] = []
    pending_facts:   list[dict] = []
    last_flush = time.monotonic()

    try:
        while True:
            # ── Receive ───────────────────────────────────────────────────
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=35.0)
            except (asyncio.TimeoutError, Exception):
                # Timeout or ZMQ error — flush what we have and reconnect
                break

            # ── Decode ────────────────────────────────────────────────────
            try:
                data  = zlib.decompress(raw)
                frame = json.loads(data)
            except Exception:
                continue

            schema = frame.get('$schemaRef', '')
            if 'journal' not in schema.lower():
                continue

            message    = frame.get('message', {})
            event_type = message.get('event', '')

            if event_type not in SIMULATION_EVENT_TYPES:
                continue

            # ── Normalise ─────────────────────────────────────────────────
            try:
                from ingest.journal_normaliser import (
                    build_journal_event_row,
                    event_type_to_normaliser,
                )
                journal_row = build_journal_event_row(message, event_type, source='eddn')
                pending_journal.append(journal_row)

                normaliser = event_type_to_normaliser(event_type)
                if normaliser:
                    fact = normaliser(message)
                    if fact:
                        pending_facts.append(fact)

            except Exception as e:
                log.debug(f'EDDN normalise error ({event_type}): {e}')
                continue

            # ── Flush check ───────────────────────────────────────────────
            now = time.monotonic()
            if (now - last_flush >= FLUSH_INTERVAL
                    or len(pending_journal) >= MAX_BATCH_SIZE):
                await _flush_batch(pool, pending_journal, pending_facts)
                pending_journal.clear()
                pending_facts.clear()
                last_flush = now

    finally:
        # Final flush before reconnect
        if pending_journal or pending_facts:
            try:
                await _flush_batch(pool, pending_journal, pending_facts)
            except Exception as e:
                log.warning(f'EDDN final flush error: {e}')
        socket.close()
        ctx.term()


async def _flush_batch(
    pool: 'asyncpg.Pool',
    journal_rows: list[dict],
    fact_rows: list[dict],
) -> None:
    """
    Write a batch of journal events and body_scan_facts to DB.
    Errors are logged but do not propagate — we never crash on a flush failure.
    """
    if not journal_rows and not fact_rows:
        return

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # ── journal_events ─────────────────────────────────────────
                if journal_rows:
                    await conn.executemany("""
                        INSERT INTO journal_events
                            (system_address, system_name, body_id, body_name,
                             event_type, event_timestamp, source, raw_event)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """, [
                        (
                            r.get('system_address'),
                            r.get('system_name'),
                            r.get('body_id'),
                            r.get('body_name'),
                            r['event_type'],
                            r.get('event_timestamp'),
                            r['source'],
                            json.dumps(r['raw_event']),
                        )
                        for r in journal_rows
                    ])

                # ── body_scan_facts ────────────────────────────────────────
                if fact_rows:
                    source_ring_rows = _ring_rows_from_scan_facts(fact_rows)
                    ring_rows, unresolved_ring_rows = await _resolve_eddn_ring_rows(conn, source_ring_rows)
                    if unresolved_ring_rows:
                        log.debug(
                            'EDDN flush skipped %d unresolved ring rows without an exact local body match',
                            len(unresolved_ring_rows),
                        )
                    await conn.executemany("""
                        INSERT INTO body_scan_facts (
                            system_address, body_id, body_name,
                            radius, mass_em, gravity,
                            surface_temp, surface_pressure,
                            planet_class, terraform_state,
                            atmosphere, volcanism,
                            semi_major_axis, orbital_period, parents,
                            has_geo, has_bio,
                            geo_signal_count, bio_signal_count,
                            is_landable, is_terraformable, is_ringed,
                            data_sources, confidence, updated_at
                        ) VALUES (
                            $1, $2, $3,
                            $4, $5, $6,
                            $7, $8,
                            $9, $10,
                            $11, $12,
                            $13, $14, $15,
                            $16, $17,
                            $18, $19,
                            $20, $21, $22,
                            $23, $24, now()
                        )
                        ON CONFLICT (system_address, body_id) DO UPDATE SET
                            body_name        = COALESCE(EXCLUDED.body_name, body_scan_facts.body_name),
                            radius           = COALESCE(EXCLUDED.radius, body_scan_facts.radius),
                            mass_em          = COALESCE(EXCLUDED.mass_em, body_scan_facts.mass_em),
                            gravity          = COALESCE(EXCLUDED.gravity, body_scan_facts.gravity),
                            surface_temp     = COALESCE(EXCLUDED.surface_temp, body_scan_facts.surface_temp),
                            surface_pressure = COALESCE(EXCLUDED.surface_pressure, body_scan_facts.surface_pressure),
                            planet_class     = COALESCE(EXCLUDED.planet_class, body_scan_facts.planet_class),
                            terraform_state  = COALESCE(EXCLUDED.terraform_state, body_scan_facts.terraform_state),
                            atmosphere       = COALESCE(EXCLUDED.atmosphere, body_scan_facts.atmosphere),
                            volcanism        = COALESCE(EXCLUDED.volcanism, body_scan_facts.volcanism),
                            semi_major_axis  = COALESCE(EXCLUDED.semi_major_axis, body_scan_facts.semi_major_axis),
                            orbital_period   = COALESCE(EXCLUDED.orbital_period, body_scan_facts.orbital_period),
                            parents          = COALESCE(EXCLUDED.parents, body_scan_facts.parents),
                            has_geo          = GREATEST(EXCLUDED.has_geo, body_scan_facts.has_geo),
                            has_bio          = GREATEST(EXCLUDED.has_bio, body_scan_facts.has_bio),
                            geo_signal_count = GREATEST(EXCLUDED.geo_signal_count, body_scan_facts.geo_signal_count),
                            bio_signal_count = GREATEST(EXCLUDED.bio_signal_count, body_scan_facts.bio_signal_count),
                            is_landable      = COALESCE(EXCLUDED.is_landable, body_scan_facts.is_landable),
                            is_terraformable = COALESCE(EXCLUDED.is_terraformable, body_scan_facts.is_terraformable),
                            is_ringed        = CASE
                                WHEN body_scan_facts.is_ringed IS TRUE OR EXCLUDED.is_ringed IS TRUE THEN TRUE
                                WHEN EXCLUDED.is_ringed IS FALSE THEN FALSE
                                ELSE body_scan_facts.is_ringed
                            END,
                            -- Take higher confidence value, merge sources
                            confidence       = GREATEST(EXCLUDED.confidence, body_scan_facts.confidence),
                            data_sources     = (
                                SELECT ARRAY(
                                    SELECT DISTINCT unnest(
                                        body_scan_facts.data_sources || EXCLUDED.data_sources
                                    )
                                )
                            ),
                            updated_at       = now()
                    """, [
                        (
                            r['system_address'], r['body_id'],
                            r.get('body_name'),
                            r.get('radius'), r.get('mass_em'), r.get('gravity'),
                            r.get('surface_temp'), r.get('surface_pressure'),
                            r.get('planet_class'), r.get('terraform_state'),
                            r.get('atmosphere'), r.get('volcanism'),
                            r.get('semi_major_axis'), r.get('orbital_period'),
                            json.dumps(r['parents']) if r.get('parents') else None,
                            r.get('has_geo', False), r.get('has_bio', False),
                            r.get('geo_signal_count', 0), r.get('bio_signal_count', 0),
                            r.get('is_landable', False), r.get('is_terraformable', False),
                            r.get('is_ringed'),
                            r.get('data_sources', []),
                            r.get('confidence', 0.4),
                        )
                        for r in fact_rows
                    ])
                    if ring_rows:
                        await conn.executemany("""
                            INSERT INTO body_rings (
                                system_id64, body_id, source_body_id, body_name,
                                ring_name, ring_type, ring_class,
                                mass_mt, inner_radius, outer_radius,
                                source, confidence, updated_at
                            ) VALUES (
                                $1, $2, $3, $4,
                                $5, $6, $7,
                                $8, $9, $10,
                                $11, $12, now()
                            )
                            ON CONFLICT (system_id64, body_id, ring_name, source) DO UPDATE SET
                                source_body_id = COALESCE(EXCLUDED.source_body_id, body_rings.source_body_id),
                                body_name    = COALESCE(EXCLUDED.body_name, body_rings.body_name),
                                ring_type    = COALESCE(EXCLUDED.ring_type, body_rings.ring_type),
                                ring_class   = COALESCE(EXCLUDED.ring_class, body_rings.ring_class),
                                mass_mt      = COALESCE(EXCLUDED.mass_mt, body_rings.mass_mt),
                                inner_radius = COALESCE(EXCLUDED.inner_radius, body_rings.inner_radius),
                                outer_radius = COALESCE(EXCLUDED.outer_radius, body_rings.outer_radius),
                                confidence   = EXCLUDED.confidence,
                                updated_at   = now()
                        """, [_ring_row_tuple(row) for row in ring_rows])

                    dirty_system_ids = sorted({
                        int(r['system_address'])
                        for r in fact_rows
                        if r.get('is_ringed') is not None or r.get('rings')
                    })
                    if dirty_system_ids:
                        await conn.execute("""
                            UPDATE systems
                               SET rating_dirty = TRUE,
                                   cluster_dirty = TRUE,
                                   updated_at = NOW()
                             WHERE id64 = ANY($1::bigint[])
                        """, dirty_system_ids)

        log.debug(
            f'EDDN flush: {len(journal_rows)} journal events, '
            f'{len(fact_rows)} body_scan_facts'
        )

    except Exception as e:
        log.warning(f'EDDN flush failed: {e}')


def _ring_rows_from_scan_facts(fact_rows: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for fact in fact_rows:
        source_body_id = int(fact['body_id']) if fact.get('body_id') is not None else None
        source_rows, _explicit_no_rings = ring_rows_for_body(
            {'rings': fact.get('rings') or []},
            system_id64=int(fact['system_address']),
            body_id=None,
            body_name=fact.get('body_name'),
            source='eddn_scan',
            source_body_id=source_body_id,
            trusted_empty_means_no_rings=False,
        )
        rows.extend(source_rows)
    return rows


async def _resolve_eddn_ring_rows(conn: 'asyncpg.Connection', rows: list[dict]) -> tuple[list[dict], list[dict]]:
    if not rows:
        return [], []

    system_ids = sorted({int(row['system_id64']) for row in rows if row.get('system_id64') is not None})
    body_names = sorted({str(row['body_name']) for row in rows if row.get('body_name')})
    if not system_ids or not body_names:
        return _resolve_ring_rows_with_local_bodies(rows, [])

    local_bodies = await conn.fetch("""
        SELECT system_id64, id, name
          FROM bodies
         WHERE system_id64 = ANY($1::bigint[])
           AND name = ANY($2::text[])
    """, system_ids, body_names)
    return _resolve_ring_rows_with_local_bodies(rows, local_bodies)


def _resolve_ring_rows_with_local_bodies(
    rows: list[dict],
    local_bodies,
) -> tuple[list[dict], list[dict]]:
    local_by_name: dict[tuple[int, str], list[dict]] = {}
    for body in local_bodies:
        system_id64 = body.get('system_id64') if isinstance(body, dict) else body['system_id64']
        body_name = body.get('name') if isinstance(body, dict) else body['name']
        body_id = body.get('id') if isinstance(body, dict) else body['id']
        if system_id64 is None or not body_name or body_id is None:
            continue
        key = (int(system_id64), str(body_name))
        local_by_name.setdefault(key, []).append({
            'system_id64': int(system_id64),
            'id': int(body_id),
            'name': str(body_name),
        })

    resolved: list[dict] = []
    skipped: list[dict] = []
    for row in rows:
        body_name = row.get('body_name')
        if row.get('system_id64') is None or not body_name:
            skipped.append({**row, 'reason': 'missing_system_or_body_name'})
            continue
        matches = local_by_name.get((int(row['system_id64']), str(body_name)), [])
        if len(matches) != 1:
            skipped.append({
                **row,
                'reason': 'local_body_not_found_by_name' if not matches else 'local_body_name_not_unique',
            })
            continue
        match = matches[0]
        resolved.append({
            **row,
            'body_id': match['id'],
            'body_name': match['name'],
        })
    return resolved, skipped


def _ring_row_tuple(row: dict) -> tuple:
    return (
        row.get('system_id64'),
        row.get('body_id'),
        row.get('source_body_id'),
        row.get('body_name'),
        row.get('ring_name'),
        row.get('ring_type'),
        row.get('ring_class'),
        row.get('mass_mt'),
        row.get('inner_radius'),
        row.get('outer_radius'),
        row.get('source'),
        row.get('confidence'),
    )
