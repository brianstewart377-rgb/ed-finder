"""Time-balanced Finder sharding and measured-duration refresh contracts."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts/ci"
REFRESH = SCRIPTS / "finder_derived_data_weights.py"


def _load_plugin():
    spec = importlib.util.spec_from_file_location(
        "finder_derived_data_shards_contract", SCRIPTS / "finder_derived_data_shards.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def plugin():
    return _load_plugin()


def _write_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _weights(plugin, seconds: dict[str, float]) -> dict:
    return {"measured": "synthetic run", "schema": plugin.WEIGHTS_SCHEMA, "seconds": seconds}


def _nodeids(module: str, count: int) -> list[str]:
    return [f"{module}::test_item[{number:02d}]" for number in range(count)]


def test_schema_constants_and_maximum_shards(plugin) -> None:
    assert plugin.WEIGHTS_SCHEMA == "finder-derived-data-weights/v1"
    assert plugin.DURATIONS_SCHEMA == "finder-derived-data-durations/v1"
    assert plugin.MAX_SHARDS == 8
    ids = _nodeids("tests/test_big.py", 8)
    planned = plugin.plan(ids, {}, 8, lambda _: 8)
    assert planned.totals == (1.0,) * 8
    assert planned.assignment == dict(zip(ids, range(1, 9), strict=True))


def test_plan_is_deterministic_with_weight_key_and_shard_tie_breaking(plugin) -> None:
    big, small_a, small_b = (f"tests/test_{name}.py" for name in ("big", "small_a", "small_b"))
    ids = _nodeids(big, 6) + _nodeids(small_a, 2) + _nodeids(small_b, 2)
    weights = {big: 60.0, small_a: 20.0, small_b: 20.0}
    planned = plugin.plan(ids, weights, 2, lambda _: 100)
    assert planned == plugin.plan(list(reversed(ids)), dict(reversed(list(weights.items()))), 2, lambda _: 100)
    assert planned.shards == 2
    assert planned.totals == (50.0, 50.0)
    assert planned.split_modules == (big,)
    assert planned.assignment == {
        **{node: 1 for node in _nodeids(small_a, 2)},
        **{node: 2 for node in _nodeids(small_b, 2)},
        **{node: 1 + index % 2 for index, node in enumerate(_nodeids(big, 6))},
    }
    with pytest.raises(FrozenInstanceError):
        planned.shards = 3


def test_only_modules_strictly_above_half_a_shard_share_are_split(plugin) -> None:
    small_a, small_b, big = (f"tests/test_{name}.py" for name in ("small_a", "small_b", "big"))
    weights = {small_a: 30.0, small_b: 30.0, big: 120.0}
    ids = _nodeids(small_a, 3) + _nodeids(small_b, 3) + _nodeids(big, 12)
    planned = plugin.plan(ids, weights, 3, lambda _: 1)
    assert planned.split_modules == (big,)
    assert {planned.assignment[node] for node in _nodeids(big, 12)} == {1, 2, 3}
    for module in (small_a, small_b):
        assert len({planned.assignment[node] for node in _nodeids(module, 3)}) == 1
    assert planned.totals == (60.0, 60.0, 60.0)


def test_unlisted_module_uses_present_measured_seconds_per_byte(plugin) -> None:
    listed, new, removed = (f"tests/test_{name}.py" for name in ("listed", "new", "removed"))
    sizes = {listed: 30, new: 20}
    planned = plugin.plan(
        _nodeids(listed, 2) + _nodeids(new, 2),
        {listed: 60.0, removed: 99999.0}, 1, sizes.__getitem__,
    )
    assert planned.totals == (100.0,)
    assert planned.split_modules == (listed,)
    assert len(planned.assignment) == 4


def test_all_unlisted_modules_use_file_sizes_and_bare_nodeid_is_its_module(plugin) -> None:
    sizes = {"tests/test_a.py": 6, "tests/test_b.py": 4, "tests/test_c.py": 2}
    ids = _nodeids("tests/test_a.py", 3) + _nodeids("tests/test_b.py", 2) + ["tests/test_c.py"]
    planned = plugin.plan(ids, {"tests/test_removed.py": 10000.0}, 2, sizes.__getitem__)
    assert planned.totals == (6.0, 6.0)
    assert set(planned.assignment) == set(ids)
    assert planned.split_modules == ("tests/test_a.py", "tests/test_b.py")


@pytest.mark.parametrize(
    ("nodeids", "shards"),
    [(["tests/test_a.py::test_a"], 0), (["tests/test_a.py::test_a"], 9),
     ([], 1), (["tests/test_a.py::test_a"] * 2, 1), (["tests/test_a.py::test_a"], 2)],
    ids=["zero-shards", "too-many-shards", "empty-input", "duplicate-test", "empty-shard"],
)
def test_plan_refuses_invalid_inputs_with_one_line(plugin, nodeids, shards) -> None:
    with pytest.raises(ValueError) as refused:
        plugin.plan(nodeids, {}, shards, lambda _: 10)
    assert len(str(refused.value).splitlines()) == 1


def test_load_weights_accepts_integer_and_float_seconds(plugin, tmp_path) -> None:
    data = _weights(plugin, {"tests/test_a.py": 1, "tests/test_b_2.py": 2.5})
    path = _write_json(tmp_path / "weights.json", data)
    assert plugin.load_weights(path) == data["seconds"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("measured", ""), ("measured", None), ("schema", "wrong/v1"),
     ("seconds", []), ("seconds", None), ("extra", True)],
)
def test_load_weights_rejects_invalid_envelope(plugin, tmp_path, field, value) -> None:
    data = _weights(plugin, {"tests/test_a.py": 1.0})
    data[field] = value
    with pytest.raises(ValueError) as refused:
        plugin.load_weights(_write_json(tmp_path / "weights.json", data))
    assert len(str(refused.value).splitlines()) == 1


@pytest.mark.parametrize("field", ["measured", "schema", "seconds"])
def test_load_weights_requires_all_envelope_keys(plugin, tmp_path, field) -> None:
    data = _weights(plugin, {})
    del data[field]
    with pytest.raises(ValueError):
        plugin.load_weights(_write_json(tmp_path / "weights.json", data))


@pytest.mark.parametrize(
    "module", ["test_a.py", "tests/test_a-b.py", "tests/nested/test_a.py", "tests/test_.py",
               "/tests/test_a.py", "tests/test_a.py::test_a", "tests/test_a.py\n"],
)
def test_load_weights_rejects_non_module_paths(plugin, tmp_path, module) -> None:
    with pytest.raises(ValueError):
        plugin.load_weights(_write_json(tmp_path / "weights.json", _weights(plugin, {module: 1.0})))


@pytest.mark.parametrize("seconds", [0, -1, True, "1", None, [], {}, float("nan"), float("inf"), -float("inf")])
def test_load_weights_rejects_nonpositive_or_nonfinite_numbers(plugin, tmp_path, seconds) -> None:
    with pytest.raises(ValueError):
        plugin.load_weights(_write_json(tmp_path / "weights.json", _weights(plugin, {"tests/test_a.py": seconds})))


@pytest.mark.parametrize("contents", ["not json", "[]", "null", "1", b"\xff"])
def test_load_weights_rejects_invalid_json_document(plugin, tmp_path, contents) -> None:
    path = tmp_path / "weights.json"
    path.write_bytes(contents if isinstance(contents, bytes) else contents.encode())
    with pytest.raises(ValueError) as refused:
        plugin.load_weights(path)
    assert len(str(refused.value).splitlines()) == 1


def test_load_weights_refuses_missing_and_unreadable_files(plugin, tmp_path) -> None:
    for path in (tmp_path / "absent.json", tmp_path):
        with pytest.raises(ValueError) as refused:
            plugin.load_weights(path)
        assert len(str(refused.value).splitlines()) == 1


@pytest.fixture
def synthetic_tree(plugin, tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    for name, count in (("small_a", 3), ("small_b", 2)):
        (tests / f"test_{name}.py").write_text(
            "\n\n".join(f"def test_{index}():\n    assert True" for index in range(count)) + "\n",
            encoding="utf-8",
        )
    (tests / "test_big.py").write_text(
        'import pytest\n\n@pytest.mark.parametrize("number", range(30))\n'
        "def test_number(number):\n    assert number >= 0\n", encoding="utf-8",
    )
    weights = _write_json(tmp_path / "weights.json", _weights(plugin, {
        "tests/test_small_a.py": 30.0, "tests/test_small_b.py": 20.0, "tests/test_big.py": 300.0,
    }))
    return tmp_path, weights


def _pytest(tree: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "-p", "finder_derived_data_shards", *args],
        cwd=tree, capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONPATH": str(SCRIPTS), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTEST_ADDOPTS": ""},
    )


def _collected(completed: subprocess.CompletedProcess) -> list[str]:
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return [line for line in completed.stdout.splitlines() if line.startswith("tests/") and "::" in line]


def _options(weights: Path, shard: int) -> tuple[str, ...]:
    return ("--finder-shard", str(shard), "--finder-shards", "3", "--finder-weights", str(weights))


def test_real_pytest_shards_partition_collection_and_preserve_order(synthetic_tree) -> None:
    tree, weights = synthetic_tree
    unsharded = _collected(_pytest(tree, "--collect-only"))
    assert len(unsharded) == 35
    selections = []
    for shard in range(1, 4):
        completed = _pytest(tree, "--collect-only", *_options(weights, shard))
        selected = _collected(completed)
        selections.append(set(selected))
        assert selected == [node for node in unsharded if node in set(selected)]
        assert f"finder-derived-data shard {shard}/3: {len(selected)} of 35 tests, predicted " in completed.stdout
        assert "(shard totals " in completed.stdout
        assert "  split: tests/test_big.py (" in completed.stdout
        assert "deselected" in completed.stdout
        for module in ("tests/test_small_a.py", "tests/test_small_b.py"):
            present = [node for node in selected if node.split("::", 1)[0] == module]
            assert (f"  whole: {module}" in completed.stdout) == bool(present)
    assert set.union(*selections) == set(unsharded)
    assert sum(map(len, selections)) == len(unsharded)
    for module in ("tests/test_small_a.py", "tests/test_small_b.py"):
        assert sum(any(node.startswith(module + "::") for node in selection) for selection in selections) == 1
    assert all(any(node.startswith("tests/test_big.py::") for node in selection) for selection in selections)


@pytest.mark.parametrize(
    "case", ["shard-zero", "shard-four", "shards-nine", "missing-weights", "wrong-schema", "partial-options"],
)
def test_bad_pytest_options_fail_before_collection(synthetic_tree, case) -> None:
    tree, weights = synthetic_tree
    # Importing this test would fail if invalid options were checked after collection.
    (tree / "tests/test_no_collection.py").write_text("raise AssertionError('collection must not happen')\n", encoding="utf-8")
    args = list(_options(weights, 1))
    if case == "shard-zero":
        args[1] = "0"
    elif case == "shard-four":
        args[1] = "4"
    elif case == "shards-nine":
        args[3] = "9"
    elif case == "missing-weights":
        args[5] = str(tree / "missing.json")
    elif case == "wrong-schema":
        data = json.loads(weights.read_text(encoding="utf-8"))
        data["schema"] = "wrong/v1"
        _write_json(weights, data)
    else:
        args = ["--finder-shard", "1"]
    completed = _pytest(tree, "--collect-only", *args)
    assert completed.returncode == 4, completed.stdout + completed.stderr
    assert len([line for line in completed.stderr.splitlines() if line.strip()]) == 1, completed.stderr
    assert "collection must not happen" not in completed.stdout + completed.stderr


@pytest.mark.parametrize("sharded", [True, False], ids=["sharded", "unsharded"])
def test_real_run_writes_exact_executed_nodes_and_all_phase_durations(plugin, synthetic_tree, sharded) -> None:
    tree, weights = synthetic_tree
    (tree / "conftest.py").write_text(
        "import pytest\n\n@pytest.hookimpl(hookwrapper=True)\n"
        "def pytest_runtest_makereport():\n"
        "    outcome = yield\n"
        "    report = outcome.get_result()\n"
        '    report.duration = {"setup": 0.1234, "call": 0.2344, "teardown": 0.3454}[report.when]\n',
        encoding="utf-8",
    )
    options = _options(weights, 2) if sharded else ()
    collected = _collected(_pytest(tree, "--collect-only", *options))
    output = tree / "nested/durations.json"
    completed = _pytest(tree, *options, "--finder-durations-out", str(output))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data == {
        "exitstatus": 0, "schema": plugin.DURATIONS_SCHEMA,
        "seconds": dict.fromkeys(collected, 0.703), "shard": 2 if sharded else None,
        "shards": 3 if sharded else None,
    }
    assert output.read_text(encoding="utf-8") == json.dumps(data, indent=2, sort_keys=True) + "\n"


def _durations(plugin, shard=1, shards=1, seconds=None) -> dict:
    return {
        "exitstatus": 0, "schema": plugin.DURATIONS_SCHEMA, "shard": shard, "shards": shards,
        "seconds": {"tests/test_a.py::test_a": 1.0} if seconds is None else seconds,
    }


def _refresh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REFRESH), *args], cwd=ROOT,
        capture_output=True, text=True, timeout=30,
    )


def _assert_refresh_refused(completed: subprocess.CompletedProcess) -> None:
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert completed.stdout == ""
    assert len(completed.stderr.splitlines()) == 1, completed.stderr
    assert completed.stderr.strip()


def test_refresh_sums_modules_rounds_and_writes_canonical_weights(plugin, tmp_path) -> None:
    first = _write_json(tmp_path / "one.json", _durations(plugin, 1, 2, {
        "tests/test_big.py::test_a": 1.234, "tests/test_tiny.py::test_a": 0.004,
        "tests/test_whole.py": 2.66,
    }))
    second = _write_json(tmp_path / "two.json", _durations(plugin, 2, 2, {
        "tests/test_big.py::TestGroup::test_b": 2.234, "tests/test_zero.py::test_a": 0.0,
    }))
    completed = _refresh("--measured", "fresh green run", str(second), str(first))
    assert completed.returncode == 0, completed.stderr
    expected = {"measured": "fresh green run", "schema": plugin.WEIGHTS_SCHEMA, "seconds": {
        "tests/test_big.py": 3.5, "tests/test_tiny.py": 0.1, "tests/test_whole.py": 2.7, "tests/test_zero.py": 0.1,
    }}
    assert completed.stdout == json.dumps(expected, indent=2, sort_keys=True) + "\n"
    assert completed.stderr == ""
    output = tmp_path / "weights.json"
    output.write_text(completed.stdout, encoding="utf-8")
    assert plugin.load_weights(output) == expected["seconds"]


@pytest.mark.parametrize("measured_args", [[], ["--measured", ""]], ids=["missing", "empty"])
def test_refresh_requires_measured_text(plugin, tmp_path, measured_args) -> None:
    path = _write_json(tmp_path / "duration.json", _durations(plugin))
    _assert_refresh_refused(_refresh(*measured_args, str(path)))


@pytest.mark.parametrize("kind", ["missing", "directory", "invalid-json", "invalid-encoding", "not-object"])
def test_refresh_requires_readable_json_files(tmp_path, kind) -> None:
    path = tmp_path / "duration.json"
    if kind == "directory":
        path.mkdir()
    elif kind == "invalid-json":
        path.write_text("not json\n", encoding="utf-8")
    elif kind == "invalid-encoding":
        path.write_bytes(b"\xff")
    elif kind == "not-object":
        _write_json(path, [])
    _assert_refresh_refused(_refresh("--measured", "run", str(path)))


@pytest.mark.parametrize(
    ("field", "value"),
    [("schema", "wrong/v1"), ("exitstatus", 1), ("exitstatus", "0"), ("exitstatus", False),
     ("shard", None), ("shard", True), ("shard", "1"), ("shard", 1.0),
     ("shards", None), ("shards", True), ("shards", "1"), ("shards", 1.0),
     ("shard", 0), ("shard", 2), ("shards", 0)],
)
def test_refresh_refuses_invalid_duration_metadata(plugin, tmp_path, field, value) -> None:
    data = _durations(plugin)
    data[field] = value
    path = _write_json(tmp_path / "duration.json", data)
    _assert_refresh_refused(_refresh("--measured", "run", str(path)))


@pytest.mark.parametrize("field", ["schema", "exitstatus", "shard", "shards"])
def test_refresh_requires_duration_metadata(plugin, tmp_path, field) -> None:
    data = _durations(plugin)
    del data[field]
    path = _write_json(tmp_path / "duration.json", data)
    _assert_refresh_refused(_refresh("--measured", "run", str(path)))


@pytest.mark.parametrize("case", ["inconsistent-total", "missing-shard", "duplicate-shard", "duplicate-node", "no-nodes"])
def test_refresh_refuses_incomplete_or_overlapping_runs(plugin, tmp_path, case) -> None:
    first = _durations(plugin, 1, 2, {"tests/test_a.py::test_a": 1.0})
    second = _durations(plugin, 2, 2, {"tests/test_a.py::test_b": 2.0})
    data = [first, second]
    if case == "inconsistent-total":
        second["shards"] = 3
    elif case == "missing-shard":
        data = [first]
    elif case == "duplicate-shard":
        second["shard"] = 1
    elif case == "duplicate-node":
        second["seconds"] = first["seconds"]
    else:
        first["seconds"] = {}
        second["seconds"] = {}
    files = [_write_json(tmp_path / f"duration-{index}.json", item) for index, item in enumerate(data)]
    _assert_refresh_refused(_refresh("--measured", "run", *map(str, files)))


@pytest.mark.parametrize("seconds", [None, [], {"tests/test_a.py::test_a": -1}, {"tests/test_a.py::test_a": True},
                                    {"tests/test_a.py::test_a": float("nan")}, {"tests/test_a.py::test_a": float("inf")}])
def test_refresh_refuses_invalid_duration_seconds(plugin, tmp_path, seconds) -> None:
    data = _durations(plugin)
    data["seconds"] = seconds
    path = _write_json(tmp_path / "duration.json", data)
    _assert_refresh_refused(_refresh("--measured", "run", str(path)))
