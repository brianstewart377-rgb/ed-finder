from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest


pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "scripts/v3_plan_probe_statements.py"
PLACEHOLDER = re.compile(r"\$(\d+)")


def _generate() -> tuple[bytes, dict]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "apps/api/src")
    result = subprocess.run(
        [
            sys.executable,
            str(PROGRAM),
            "--dense-anchor",
            "123.5",
            "-456.25",
            "789.0",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=True,
    )
    return result.stdout, json.loads(result.stdout)


def test_generator_is_deterministic_and_emits_exact_matrix() -> None:
    first_bytes, first = _generate()
    second_bytes, second = _generate()

    assert first_bytes == second_bytes
    assert first == second
    assert len(first["statements"]) == 80
    assert Counter(statement["kind"] for statement in first["statements"]) == {
        "picked_page": 48,
        "picked_count": 24,
        "galaxy_page": 1,
        "galaxy_count": 1,
        "anchored_knn_page": 2,
        "anchored_knn_count": 2,
        "anchored_filtered_page": 1,
        "anchored_score_page": 1,
    }
    assert first_bytes == (
        json.dumps(
            first,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode()


def test_every_statement_has_exact_contiguous_asyncpg_parameters() -> None:
    _, document = _generate()
    allowed_types = {"bigint", "double precision", "text"}
    for statement in document["statements"]:
        placeholders = sorted(
            {int(value) for value in PLACEHOLDER.findall(statement["sql"])}
        )
        assert placeholders == list(range(1, len(statement["params"]) + 1))
        assert len(statement["params"]) == len(statement["param_sql_types"])
        assert set(statement["param_sql_types"]) <= allowed_types


@pytest.mark.parametrize("floor,suffix", [(60, "b"), (76, "a"), (88, "s")])
def test_picked_statements_bind_literal_floor_and_expected_order(
    floor: int, suffix: str
) -> None:
    _, document = _generate()
    statements = document["statements"]
    pages = [
        statement
        for statement in statements
        if statement["kind"] == "picked_page"
        and statement["expectations"]["floor"] == floor
    ]
    counts = [
        statement
        for statement in statements
        if statement["kind"] == "picked_count"
        and statement["expectations"]["floor"] == floor
    ]
    assert len(pages) == 16
    assert len(counts) == 8
    for statement in [*pages, *counts]:
        archetype = statement["expectations"]["archetype"]
        assert f"ar.{archetype}_score >= {floor}" in statement["sql"]
        assert statement["expectations"]["expected_index"] == (
            f"system_archetype_{archetype}_{suffix}_weighted"
        )
    for statement in pages:
        archetype = statement["expectations"]["archetype"]
        assert (
            f"ORDER BY ar.{archetype}_weighted_e4 DESC, ar.system_id64 ASC"
            in statement["sql"]
        )


def test_live_and_unbounded_request_arguments_match_route_contract() -> None:
    _, document = _generate()
    by_name = {statement["name"]: statement for statement in document["statements"]}

    assert by_name["galaxy_wide_development_page_24"]["params"] == [24, 0]
    assert by_name["galaxy_wide_development_count"]["params"] == [10_001]
    assert by_name["anchored_nearest_sol_page_24"]["params"] == [
        0.0,
        0.0,
        0.0,
        500.0,
        24,
        24,
        0,
    ]
    filtered = by_name["anchored_filtered_o_star_dense_page_24"]
    assert filtered["expectations"]["hard_filter"] == "main_star_class_in"
    assert filtered["params"][4] == "O"
    assert filtered["param_sql_types"][4] == "text"
