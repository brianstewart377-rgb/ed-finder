#!/usr/bin/env python3
"""Transport-corrected launcher for the one-shot normalized-V3 R1 apply."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

CORE_PATH = Path(__file__).with_name("r1_v3_normalized_live_structural_apply.py")
SPEC = importlib.util.spec_from_file_location("r1_v3_apply_core", CORE_PATH)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("STOP: could not load R1 apply core")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


def apply_atomic_with_stdin(base: list[str], atomic_sql: str) -> None:
    # docker exec must keep stdin open (-i) so psql receives the reviewed SQL.
    apply_base = base[:2] + ["-i"] + base[2:]
    proc = subprocess.run(
        apply_base,
        input=atomic_sql.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        output = proc.stdout.decode("utf-8", "replace")
        print(output)
        core.fail(f"atomic migration failed with exit code {proc.returncode}; transaction rolled back")
    print("atomic_apply_psql_result: success")


core.apply_atomic = apply_atomic_with_stdin
raise SystemExit(core.main())
