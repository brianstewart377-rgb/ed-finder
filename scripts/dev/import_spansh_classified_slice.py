#!/usr/bin/env python3
"""Dry-run a small Spansh slice or COPY it into a fresh disposable V3 candidate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/importer/src"))

from v3_spansh.pipeline import ArtifactRegistration  # noqa: E402
from v3_spansh_classified.pipeline import (  # noqa: E402
    ClassifiedImportConfig, ClassifiedSpanshPipeline, dry_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--generation-key", default="spansh_classified_slice")
    parser.add_argument("--max-systems", type=int, default=1000)
    parser.add_argument("--chunk-systems", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    artifact = ArtifactRegistration.load(args.artifact, args.artifact_metadata)
    if args.dry_run:
        result = dry_run(artifact, max_systems=args.max_systems)
    else:
        dsn = os.environ.get("SPANSH_CLASSIFIED_TEST_DSN")
        if not dsn:
            parser.error("set SPANSH_CLASSIFIED_TEST_DSN to a disposable local database")
        config = ClassifiedImportConfig(generation_key=args.generation_key,
                                        target_systems=args.max_systems, max_systems=args.max_systems,
                                        chunk_systems=args.chunk_systems)
        result = ClassifiedSpanshPipeline(dsn, artifact, config).run()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
