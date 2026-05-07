"""Preview-environment EDDN ticker simulator.

The real EDDN listener (`eddn_listener.py`) connects to an external WebSocket
feed and ingests ~10-30 events/sec. Running it in the preview pod would
need outbound websocket access and a constant trickle of compute, so for
preview purposes we ship a tiny *simulator* instead: every ~3 seconds it
inserts one synthetic row into `eddn_log` from the 40 seeded sample systems
(round-robin), choosing a plausible event type ('Scan', 'FSDJump',
'Docked', 'Location', 'CarrierJump').

This gives the new bottom-bar live-feed ticker something realistic to show
without any external dependency. Idempotent on insert (eddn_log has a
serial id), and the simulator is supervised so it auto-restarts.
"""
import asyncio
import logging
import os
import random
import sys

import asyncpg

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:edfinder@localhost:5432/edfinder')

EVENT_TYPES = [
    ('FSDJump',     0.35),
    ('Scan',        0.30),
    ('Docked',      0.12),
    ('Location',    0.10),
    ('CarrierJump', 0.05),
    ('Touchdown',   0.04),
    ('FSSDiscoveryScan', 0.04),
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', stream=sys.stdout)
log = logging.getLogger('eddn_simulator')


def _weighted_choice(weighted: list[tuple[str, float]]) -> str:
    r = random.random()
    cum = 0.0
    for v, w in weighted:
        cum += w
        if r <= cum:
            return v
    return weighted[-1][0]


async def main() -> None:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id64, name FROM systems ORDER BY id64")
        if not rows:
            log.warning('No systems seeded; ticker has nothing to publish.')
            return
        systems = [(r['id64'], r['name']) for r in rows]
        log.info('eddn_simulator starting — %d systems available, %d event types', len(systems), len(EVENT_TYPES))

        # Seed a handful of historical events so the ticker has content
        # immediately on first paint.
        async with pool.acquire() as conn:
            existing = await conn.fetchval("SELECT COUNT(*) FROM eddn_log")
            if existing < 30:
                pre = random.sample(systems, min(30, len(systems)))
                async with conn.transaction():
                    for i, (sid, name) in enumerate(pre):
                        ev = _weighted_choice(EVENT_TYPES)
                        await conn.execute(
                            """
                            INSERT INTO eddn_log (event_type, system_id64, system_name, processed, received_at)
                            VALUES ($1, $2, $3, true, NOW() - ($4 || ' seconds')::interval)
                            """,
                            ev, sid, name, str((30 - i) * random.randint(2, 8)),
                        )
                log.info('seeded %d historical events', len(pre))

        # Tick loop
        while True:
            sid, name = random.choice(systems)
            ev = _weighted_choice(EVENT_TYPES)
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO eddn_log (event_type, system_id64, system_name, processed)
                        VALUES ($1, $2, $3, true)
                        """,
                        ev, sid, name,
                    )
                log.info('tick: %s @ %s', ev, name)
            except Exception as e:  # pragma: no cover
                log.warning('insert failed: %s', e)
            # 2-5 second jitter
            await asyncio.sleep(random.uniform(2.0, 5.0))
    finally:
        await pool.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
