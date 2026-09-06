#!/usr/bin/env python3
"""External, credential-free verification of the fixed non-production checkpoint."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from v3_checkpoint_deploy import (
    DeploymentError,
    TARGET_FQDN,
    smoke_origin,
    wait_for_origin_ready,
)


def verify_public_checkpoint(source_sha: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise DeploymentError("invalid expected public checkpoint source")
    origin = "http://" + TARGET_FQDN
    wait_for_origin_ready(origin, source_sha)
    outcomes = smoke_origin(origin, source_sha)
    return {
        "schema_version": "ed-finder/v3-live-checkpoint-public-smoke/v1",
        "status": "accepted", "origin": origin, "source_sha": source_sha,
        "checks": outcomes, "production": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = verify_public_checkpoint(os.environ.get("EXPECTED_SOURCE_SHA", ""))
        result = 0
    except DeploymentError as exc:
        receipt = {"status": "stopped", "production": False, "failures": [str(exc)]}
        result = 78
    document = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    args.receipt.write_text(document, encoding="utf-8")
    print(document, end="")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
