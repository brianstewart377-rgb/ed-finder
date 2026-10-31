"""Deterministic, measured-time sharding for the Finder PostgreSQL test lane."""

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re

import pytest


WEIGHTS_SCHEMA = "finder-derived-data-weights/v1"
DURATIONS_SCHEMA = "finder-derived-data-durations/v1"
MAX_SHARDS = 8

_MODULE_PATTERN = re.compile(r"tests/test_[A-Za-z0-9_]+\.py")


def _validate_weights(data: object) -> dict[str, float]:
    if not isinstance(data, dict) or set(data) != {"measured", "schema", "seconds"}:
        raise ValueError("weights must have exactly measured, schema and seconds keys")
    if data["schema"] != WEIGHTS_SCHEMA:
        raise ValueError(f"weights schema must be {WEIGHTS_SCHEMA}")
    if not isinstance(data["measured"], str) or not data["measured"].strip():
        raise ValueError("weights measured must be a non-empty string")
    if not isinstance(data["seconds"], dict):
        raise ValueError("weights seconds must be an object")
    weights = {}
    for module, seconds in data["seconds"].items():
        if not isinstance(module, str) or _MODULE_PATTERN.fullmatch(module) is None:
            raise ValueError(f"invalid weights module: {module!r}")
        try:
            valid = (
                isinstance(seconds, (int, float))
                and not isinstance(seconds, bool)
                and math.isfinite(seconds)
                and seconds > 0
            )
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f"weights seconds must be finite and positive: {module!r}")
        weights[module] = float(seconds)
    return weights


def load_weights(path: str | Path) -> dict[str, float]:
    """Read the strict, versioned module weights format."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        raise ValueError(f"cannot read weights file: {str(path)!r}") from None
    except ValueError:
        raise ValueError(f"invalid JSON in weights file: {str(path)!r}") from None
    return _validate_weights(data)


def format_weights(measured: str, seconds: Mapping[str, float]) -> str:
    """Produce the validated canonical format used by the refresh tool."""
    data = {"measured": measured, "schema": WEIGHTS_SCHEMA, "seconds": dict(seconds)}
    _validate_weights(data)
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True)
class ShardPlan:
    shards: int
    assignment: dict[str, int]
    totals: tuple[float, ...]
    split_modules: tuple[str, ...]


def plan(
    nodeids: Sequence[str],
    weights: Mapping[str, float],
    shards: int,
    size_of: Callable[[str], int],
) -> ShardPlan:
    """Assign whole modules and dominant-module tests with deterministic LPT."""
    if type(shards) is not int or not 1 <= shards <= MAX_SHARDS:
        raise ValueError(f"finder shards must be between 1 and {MAX_SHARDS}")
    if not nodeids:
        raise ValueError("cannot shard an empty collection")
    if len(set(nodeids)) != len(nodeids):
        raise ValueError("cannot shard duplicate node ids")

    modules: dict[str, list[str]] = defaultdict(list)
    for nodeid in nodeids:
        modules[nodeid.split("::", 1)[0]].append(nodeid)
    measured_modules = sorted(module for module in modules if module in weights)
    if measured_modules:
        measured_size = sum(size_of(module) for module in measured_modules)
        if measured_size <= 0:
            raise ValueError("measured modules must have a positive total byte size")
        rate = sum(weights[module] for module in measured_modules) / measured_size
    else:
        rate = 1.0
    module_weights = {
        module: weights[module] if module in weights else size_of(module) * rate
        for module in sorted(modules)
    }
    threshold = sum(module_weights.values()) / (2 * shards)
    split_modules = tuple(
        module for module, weight in module_weights.items() if weight > threshold
    )
    units: list[tuple[float, str, Sequence[str]]] = []
    for module, weight in module_weights.items():
        members = modules[module]
        if module in split_modules:
            units.extend((weight / len(members), nodeid, [nodeid]) for nodeid in members)
        else:
            units.append((weight, module, members))

    totals = [0.0] * shards
    unit_counts = [0] * shards
    assignment = {}
    for weight, _key, members in sorted(units, key=lambda unit: (-unit[0], unit[1])):
        shard = min(range(shards), key=lambda index: (totals[index], index))
        totals[shard] += weight
        unit_counts[shard] += 1
        assignment.update((nodeid, shard + 1) for nodeid in members)
    if 0 in unit_counts:
        raise ValueError("every finder shard must receive at least one unit")
    return ShardPlan(shards, assignment, tuple(totals), split_modules)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("finder-derived-data", "Finder derived-data CI sharding")
    group.addoption("--finder-shard", type=int, help="This shard's number (1-based)")
    group.addoption("--finder-shards", type=int, help="Total number of shards")
    group.addoption("--finder-weights", help="Measured module weights JSON path")
    group.addoption("--finder-durations-out", help="Write per-test phase durations JSON")


def pytest_configure(config: pytest.Config) -> None:
    shard = config.getoption("finder_shard")
    shards = config.getoption("finder_shards")
    weights_path = config.getoption("finder_weights")
    durations_out = config.getoption("finder_durations_out")
    supplied = (shard is not None, shards is not None, weights_path is not None)
    weights = None
    if any(supplied):
        if not all(supplied):
            raise pytest.UsageError(
                "--finder-shard, --finder-shards and --finder-weights must be given together"
            )
        if not 1 <= shards <= MAX_SHARDS:
            raise pytest.UsageError(f"finder shards must be between 1 and {MAX_SHARDS}")
        if not 1 <= shard <= shards:
            raise pytest.UsageError("finder shard must be between 1 and finder shards")
        try:
            weights = load_weights(weights_path)
        except ValueError as error:
            raise pytest.UsageError(str(error)) from None
    if any(supplied) or durations_out is not None:
        config.pluginmanager.register(
            _FinderPlugin(config, shard, shards, weights, durations_out),
            "finder-derived-data-session",
        )


class _FinderPlugin:
    """Keep report and sharding state scoped to one pytest configuration."""

    def __init__(
        self,
        config: pytest.Config,
        shard: int | None,
        shards: int | None,
        weights: dict[str, float] | None,
        durations_out: str | None,
    ) -> None:
        self.config = config
        self.shard = shard
        self.shards = shards
        self.weights = weights
        self.durations_out = durations_out
        self.seconds: dict[str, float] = defaultdict(float)

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        if self.weights is None:
            return
        nodeids = [item.nodeid for item in items]
        try:
            shard_plan = plan(
                nodeids,
                self.weights,
                self.shards,
                lambda module: (self.config.rootpath / module).stat().st_size,
            )
        except ValueError as error:
            raise pytest.UsageError(str(error)) from None
        except OSError:
            raise pytest.UsageError("cannot read a collected Finder test module's byte size") from None
        kept = []
        deselected = []
        for item in items:
            (kept if shard_plan.assignment[item.nodeid] == self.shard else deselected).append(item)
        self.config.hook.pytest_deselected(items=deselected)
        items[:] = kept

        reporter = self.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is None:
            return
        totals = " / ".join(f"{total:.1f}" for total in shard_plan.totals)
        reporter.write_line(
            f"finder-derived-data shard {self.shard}/{self.shards}: "
            f"{len(kept)} of {len(nodeids)} tests, "
            f"predicted {shard_plan.totals[self.shard - 1]:.1f} s "
            f"(shard totals {totals} s)"
        )
        module_counts: dict[str, int] = defaultdict(int)
        kept_counts: dict[str, int] = defaultdict(int)
        for nodeid in nodeids:
            module_counts[nodeid.split("::", 1)[0]] += 1
        for item in kept:
            kept_counts[item.nodeid.split("::", 1)[0]] += 1
        for module in sorted(kept_counts):
            if module not in shard_plan.split_modules:
                reporter.write_line(f"  whole: {module}")
        for module in shard_plan.split_modules:
            reporter.write_line(
                f"  split: {module} ({kept_counts[module]} of {module_counts[module]} tests)"
            )

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if self.durations_out is not None:
            self.seconds[report.nodeid] += report.duration

    def pytest_sessionfinish(self, exitstatus: int) -> None:
        if self.durations_out is None:
            return
        data = {
            "exitstatus": int(exitstatus),
            "schema": DURATIONS_SCHEMA,
            "seconds": {nodeid: round(seconds, 3) for nodeid, seconds in self.seconds.items()},
            "shard": self.shard,
            "shards": self.shards,
        }
        path = Path(self.durations_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
