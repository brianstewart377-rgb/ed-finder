#!/usr/bin/env python3
"""Seed normal account/import browser journeys in an isolated CI database.

No auth bypass is added to the application. The fixture invokes the normal
post-provider account/session transaction, then uses its opaque session cookie.
This proves application behavior, not a live Frontier provider exchange.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import asyncpg
import psycopg

from scripts.operator.v3_schema_identity import derive_entries
from tests.helpers.db_isolation import validate_test_db_target

ROOT = Path(__file__).resolve().parents[2]


async def seed(output: Path) -> None:
    if os.environ.get('EDFINDER_ACCOUNT_BROWSER_DATABASE') != 'yes':
        raise RuntimeError('Explicit disposable account browser database confirmation required')
    target = validate_test_db_target(os.environ['DATABASE_URL'])
    with psycopg.connect(target.dsn, autocommit=True) as conn:
        if int(conn.execute('SHOW server_version_num').fetchone()[0]) // 10000 != 18:
            raise RuntimeError('Account browser acceptance requires PostgreSQL 18')
        if conn.execute("SELECT to_regnamespace('v3_identity')").fetchone()[0] is not None:
            raise RuntimeError('Account acceptance requires a fresh V3 namespace')
        for entry in derive_entries(ROOT):
            conn.execute((ROOT / entry['path']).read_text())

    from edfinder_api.routers.auth import (
        FRONTIER_ISSUER,
        FrontierIdentity,
        _upsert_account_and_session,
    )

    pool = await asyncpg.create_pool(target.dsn, min_size=1, max_size=2)
    try:
        sessions = {}
        for width in (1280, 390):
            _, token, _ = await _upsert_account_and_session(
                pool,
                FrontierIdentity(
                    issuer=FRONTIER_ISSUER,
                    subject=f'account-browser-fixture-{width}',
                    journal_fid=f'F991{width}',
                    commander_name=f'Browser commander {width}',
                ),
            )
            sessions[str(width)] = token
        # The caller keeps this test-only opaque-cookie fixture out of artifacts.
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as handle:
            json.dump({'sessions': sessions, 'cookie_name': 'edfinder_account_e2e'}, handle)
    finally:
        await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(seed(parser.parse_args().output))
