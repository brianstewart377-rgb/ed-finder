#!/usr/bin/env python3
"""Plan by default; apply reviewed facts only to an unpublished canonical build.

Development/build integration utility, not a production operator authority.
Run with the frozen API test environment (Psycopg 3) and a disposable test DSN.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/api/src'))
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation-id', type=uuid.UUID, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--contribution-ids-file', type=Path,
                        help='JSON array of reviewed contribution UUIDs, maximum 500')
    selection.add_argument('--all-eligible', action='store_true',
                           help='Apply all eligible observations reviewed before build creation, in bounded batches')
    parser.add_argument('--expected-manifest-sha256')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    import psycopg
    from shared_contracts.journal_canonical import reconcile_all_eligible, reconcile_generation
    from tests.helpers.db_isolation import target_from_env

    if args.all_eligible and not args.apply:
        parser.error('--all-eligible requires --apply; inspect selected IDs for a read-only plan')
    ids = json.loads(args.contribution_ids_file.read_text()) if args.contribution_ids_file else []
    if not isinstance(ids, list):
        parser.error('Contribution IDs must be a JSON array')
    # Secrets are read from the environment and never included in a receipt.
    target = target_from_env(os.environ)
    with psycopg.connect(target.dsn, autocommit=True) as conn:
        if not args.apply:
            conn.read_only = True
        result = reconcile_all_eligible(conn, generation_id=args.generation_id) if args.all_eligible else reconcile_generation(
            conn, generation_id=args.generation_id,
            contribution_ids=[uuid.UUID(value) for value in ids], apply=args.apply,
            expected_manifest_sha256=args.expected_manifest_sha256,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
