#!/usr/bin/env python3
"""Fail closed unless V3 application validation uses CPython 3.14."""

from __future__ import annotations

import platform
import sys


EXPECTED_IMPLEMENTATION = "CPython"
EXPECTED_VERSION = (3, 14)


def main() -> int:
    implementation = platform.python_implementation()
    version = sys.version_info[:2]
    print(
        "V3 application runtime: "
        f"{implementation} {platform.python_version()} ({sys.executable})"
    )
    if implementation != EXPECTED_IMPLEMENTATION or version != EXPECTED_VERSION:
        print(
            "V3 application validation requires CPython 3.14; "
            f"received {implementation} {platform.python_version()}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
