"""Refresh Finder module weights from all durations artifacts of a green run."""

import argparse
from collections import defaultdict
from collections.abc import Sequence
import json
import math
from pathlib import Path
import sys

from finder_derived_data_shards import DURATIONS_SCHEMA, format_weights


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, f"{self.prog}: {message}\n")


def refresh(measured: str, paths: Sequence[str | Path]) -> str:
    """Validate one complete set of shard artifacts and total seconds by module."""
    if not measured.strip():
        raise ValueError("--measured must be a non-empty string")
    seconds_by_module: dict[str, float] = defaultdict(float)
    seen_nodeids: set[str] = set()
    seen_shards: list[int] = []
    expected_shards = None
    for path in paths:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            raise ValueError(f"cannot read durations file: {str(path)!r}") from None
        except ValueError:
            raise ValueError(f"invalid JSON in durations file: {str(path)!r}") from None
        if not isinstance(data, dict) or data.get("schema") != DURATIONS_SCHEMA:
            raise ValueError(f"durations schema must be {DURATIONS_SCHEMA}")
        if type(data.get("exitstatus")) is not int or data["exitstatus"] != 0:
            raise ValueError("durations exitstatus must be 0 for every shard")
        shard, shards = data.get("shard"), data.get("shards")
        if type(shard) is not int or type(shards) is not int:
            raise ValueError("durations shard and shards must be integers")
        if shards < 1 or not 1 <= shard <= shards:
            raise ValueError("durations shard must be between 1 and shards")
        if expected_shards is None:
            expected_shards = shards
        elif expected_shards != shards:
            raise ValueError("all durations files must have the same shards count")
        seen_shards.append(shard)
        seconds = data.get("seconds")
        if not isinstance(seconds, dict):
            raise ValueError("durations seconds must be an object")
        for nodeid, duration in seconds.items():
            if not isinstance(nodeid, str) or not nodeid:
                raise ValueError("durations node ids must be non-empty strings")
            if nodeid in seen_nodeids:
                raise ValueError(f"duplicate node id across durations files: {nodeid!r}")
            try:
                valid = (
                    isinstance(duration, (int, float))
                    and not isinstance(duration, bool)
                    and math.isfinite(duration)
                    and duration >= 0
                )
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"durations seconds must be finite and non-negative: {nodeid!r}")
            seen_nodeids.add(nodeid)
            seconds_by_module[nodeid.split("::", 1)[0]] += duration

    if (
        expected_shards is None
        or len(seen_shards) != expected_shards
        or sorted(seen_shards) != list(range(1, expected_shards + 1))
    ):
        raise ValueError("durations files must contain shards 1..K exactly once each")
    if not seen_nodeids:
        raise ValueError("durations files contain no node ids")
    rounded = {
        module: round(seconds, 1) or 0.1 for module, seconds in seconds_by_module.items()
    }
    return format_weights(measured, rounded)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("--measured", required=True, help="Description and date of the green run")
    parser.add_argument("durations", nargs="+", metavar="DURATIONS.json")
    args = parser.parse_args(argv)
    try:
        output = refresh(args.measured, args.durations)
    except ValueError as error:
        parser.error(str(error))
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
