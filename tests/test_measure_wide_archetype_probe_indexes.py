"""The probe-index measurement script's timing summary."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dev" / "measure_wide_archetype_probe_indexes.py"


def _load():
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec = importlib.util.spec_from_file_location("measure_wide_archetype_probe_indexes", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPT.parent))


def test_warm_median_averages_the_two_middle_runs_for_an_even_count():
    module = _load()
    # First run is excluded; the four warm totals are 2, 4, 6 and 8 ms.
    timings = [(50.0, 50.0), (1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (4.0, 4.0)]
    assert module.warm_median_ms(timings) == 5.0


def test_warm_median_takes_the_middle_run_for_an_odd_count():
    module = _load()
    timings = [(50.0, 50.0), (1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]
    assert module.warm_median_ms(timings) == 4.0
