#!/usr/bin/env python3
"""Build a Spansh candidate and reconcile reviewed journal facts, without publication.

Disposable development/rehearsal command only, not production authority. The
recovered v3_spansh files remain byte-for-byte pinned to their original source.
If enrichment stops after baseline validation, resume using
reconcile_journal_galaxy.py --all-eligible against the saved READY candidate.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/importer/src'))
sys.path.insert(0, str(ROOT))


def main() -> None:
    import psycopg
    from v3_spansh.cli import parser
    from v3_spansh.pipeline import ArtifactRegistration, ImportConfig, SpanshV3Pipeline
    from shared_contracts.journal_canonical import reconcile_all_eligible
    from tests.helpers.db_isolation import validate_test_db_target

    arguments = parser()
    arguments.description = __doc__
    args = arguments.parse_args()
    if args.publish or args.publish_only:
        arguments.error('This development build command cannot publish')
    target = validate_test_db_target(args.dsn, env=os.environ, source='journal-galaxy-development-build')
    with psycopg.connect(target.dsn, autocommit=True) as conn:
        if conn.execute("SELECT to_regclass('v3_private.eligible_journal_galaxy_contribution')").fetchone()[0] is None:
            arguments.error('Journal contribution migrations must be applied to the disposable DB first')
    artifact = ArtifactRegistration.load(args.artifact, args.artifact_metadata)
    config = ImportConfig(generation_key=args.generation_key, target_systems=args.target_systems,
                          max_systems=args.max_systems, chunk_systems=args.chunk_systems,
                          require_macmillan=args.require_macmillan, execution_phase=args.execution_phase)
    pipeline = SpanshV3Pipeline(target.dsn, artifact, config)
    result = pipeline.run(crash_before_chunk=args.crash_before_chunk,
                          pause_before_chunk=args.pause_before_chunk, pause_seconds=args.pause_seconds).as_dict()
    with psycopg.connect(target.dsn, autocommit=True) as conn:
        result['journal_reconciliation'] = reconcile_all_eligible(conn, generation_id=pipeline.generation_id)
    result['published'] = False
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
