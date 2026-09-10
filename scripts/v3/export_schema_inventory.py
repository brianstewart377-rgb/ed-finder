"""Export the stable V3 post-migration structural inventory as JSON."""
from __future__ import annotations

import argparse
import asyncio
import os
import re
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUERY = (
    ROOT / 'sql' / 'v3' / 'introspection' / 'post_migration_schema_inventory.sql'
)


async def export_inventory(*, dsn: str, query_path: Path, output: Path) -> None:
    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        version = str(await conn.fetchval('SHOW server_version_num'))
        if not re.fullmatch(r'18\d{4}', version):
            raise RuntimeError(f'V3 inventory requires PostgreSQL 18, got {version}')
        ledger = await conn.fetch(
            """
            SELECT migration_name
            FROM v3_meta.schema_migration
            ORDER BY migration_name
            """
        )
        if [str(row['migration_name']) for row in ledger] != [
            '001_v3_baseline.sql',
            '002_v3_accounts_identity.sql',
        ]:
            raise RuntimeError('V3 identity inventory requires the complete two-file ledger')
        rendered = await conn.fetchval(query_path.read_text(encoding='utf-8'))
    finally:
        await conn.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(str(rendered).rstrip() + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--database-url-env', default='EDFINDER_V3_DATABASE_URL')
    parser.add_argument('--query', type=Path, default=DEFAULT_QUERY)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    dsn = os.environ.get(args.database_url_env, '').strip()
    if not dsn:
        raise SystemExit(f'missing database URL environment variable: {args.database_url_env}')
    asyncio.run(export_inventory(dsn=dsn, query_path=args.query, output=args.output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
