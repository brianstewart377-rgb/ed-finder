#!/usr/bin/env python3
"""Generate the F2d plan-probe SQL from the deployed API image.

This file is intentionally self-contained: the operator pipes it to
``/app/.venv/bin/python -`` in the running API container.  Its only imports
outside the standard library are the ranking modules shipped in that image.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from edfinder_api.ranking.profile import (
    ACCEPTED_ARCHETYPE_SCORE_FLOORS,
    PROFILE_SPEC,
    RANKING_COUNT_SENTINEL,
    RANKING_VERSION,
    ranking_sha256,
)
from edfinder_api.ranking.ranking_sql import (
    ARCHETYPE_COLUMNS,
    SORT_DISTANCE,
    SORT_SCORE,
    build_count_query,
    build_ranked_query,
)


STATEMENT_COUNT = 80
COUNT_CAP = RANKING_COUNT_SENTINEL - 1
RADIUS_LY = 500.0
SOL = (0.0, 0.0, 0.0)


def _statement(
    *,
    name: str,
    kind: str,
    sql: str,
    params: list[Any],
    param_sql_types: list[str],
    expectations: dict[str, Any],
) -> dict[str, Any]:
    if len(params) != len(param_sql_types):
        raise ValueError(f"{name}: parameter/type count mismatch")
    return {
        "name": name,
        "kind": kind,
        "sql": sql,
        "params": params,
        "param_sql_types": param_sql_types,
        "expectations": expectations,
    }


def _page(
    *,
    name: str,
    kind: str,
    picked_archetype: str | None,
    hard_filters: dict[str, Any],
    reference_coords: tuple[float, float, float] | None,
    limit: int,
    sort: str,
    param_sql_types: list[str],
    expectations: dict[str, Any],
    min_score: int | None = None,
) -> dict[str, Any]:
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=picked_archetype,
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=reference_coords,
        limit=limit,
        offset=0,
        sort=sort,
        min_score=min_score,
    )
    return _statement(
        name=name,
        kind=kind,
        sql=sql,
        params=params,
        param_sql_types=param_sql_types,
        expectations=expectations,
    )


def _count(
    *,
    name: str,
    kind: str,
    picked_archetype: str | None,
    hard_filters: dict[str, Any],
    reference_coords: tuple[float, float, float] | None,
    sort: str,
    param_sql_types: list[str],
    expectations: dict[str, Any],
    min_score: int | None = None,
    cap: int | None = None,
) -> dict[str, Any]:
    sql, params = build_count_query(
        PROFILE_SPEC,
        picked_archetype=picked_archetype,
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=reference_coords,
        cap=cap,
        sort=sort,
        min_score=min_score,
    )
    return _statement(
        name=name,
        kind=kind,
        sql=sql,
        params=params,
        param_sql_types=param_sql_types,
        expectations=expectations,
    )


def build_statements_document(
    dense_anchor: tuple[float, float, float],
) -> dict[str, Any]:
    """Build the exact statement document consumed by the plan probe."""

    statements: list[dict[str, Any]] = []
    suffix_for_floor = {60: "b", 76: "a", 88: "s"}
    for archetype in ARCHETYPE_COLUMNS:
        for floor in ACCEPTED_ARCHETYPE_SCORE_FLOORS:
            index_name = (
                f"system_archetype_{archetype}_"
                f"{suffix_for_floor[floor]}_weighted"
            )
            common = {
                "archetype": archetype,
                "floor": floor,
                "expected_index": index_name,
            }
            for page_size in (50, 500):
                statements.append(
                    _page(
                        name=f"picked_{archetype}_{floor}_page_{page_size}",
                        kind="picked_page",
                        picked_archetype=archetype,
                        hard_filters={},
                        reference_coords=None,
                        limit=page_size,
                        sort=SORT_SCORE,
                        min_score=floor,
                        param_sql_types=["bigint", "bigint"],
                        expectations={**common, "page_size": page_size},
                    )
                )
            # This mirrors routers/archetypes.py exactly: picked counts pass no
            # cap because the builder owns the literal 10,001 sentinel.
            statements.append(
                _count(
                    name=f"picked_{archetype}_{floor}_count",
                    kind="picked_count",
                    picked_archetype=archetype,
                    hard_filters={},
                    reference_coords=None,
                    sort=SORT_SCORE,
                    min_score=floor,
                    cap=None,
                    param_sql_types=[],
                    expectations=common,
                )
            )

    statements.append(
        _page(
            name="galaxy_wide_development_page_24",
            kind="galaxy_page",
            picked_archetype=None,
            hard_filters={},
            reference_coords=None,
            limit=24,
            sort=SORT_SCORE,
            param_sql_types=["bigint", "bigint"],
            expectations={
                "page_size": 24,
                "expected_index": "system_archetype_summary_weighted",
            },
        )
    )
    statements.append(
        _count(
            name="galaxy_wide_development_count",
            kind="galaxy_count",
            picked_archetype=None,
            hard_filters={},
            reference_coords=None,
            sort=SORT_SCORE,
            cap=COUNT_CAP,
            param_sql_types=["bigint"],
            expectations={"sentinel": RANKING_COUNT_SENTINEL},
        )
    )

    for anchor_name, anchor in (("sol", SOL), ("dense", dense_anchor)):
        filters = {"max_distance_ly": RADIUS_LY}
        statements.append(
            _page(
                name=f"anchored_nearest_{anchor_name}_page_24",
                kind="anchored_knn_page",
                picked_archetype=None,
                hard_filters=filters,
                reference_coords=anchor,
                limit=24,
                sort=SORT_DISTANCE,
                param_sql_types=[
                    "double precision",
                    "double precision",
                    "double precision",
                    "double precision",
                    "bigint",
                    "bigint",
                    "bigint",
                ],
                expectations={
                    "anchor": anchor_name,
                    "inner_limit": 24,
                    "page_size": 24,
                    "radius_ly": RADIUS_LY,
                },
            )
        )
        statements.append(
            _count(
                name=f"anchored_nearest_{anchor_name}_count",
                kind="anchored_knn_count",
                picked_archetype=None,
                hard_filters=filters,
                reference_coords=anchor,
                sort=SORT_DISTANCE,
                cap=COUNT_CAP,
                param_sql_types=[
                    "double precision",
                    "double precision",
                    "double precision",
                    "double precision",
                    "bigint",
                ],
                expectations={
                    "anchor": anchor_name,
                    "inner_limit": RANKING_COUNT_SENTINEL,
                    "radius_ly": RADIUS_LY,
                },
            )
        )

    # O-class main stars are the most selective accepted live classification
    # filter. It is deliberately named (and typed as text) in the receipt.
    selective_filter = "main_star_class_in"
    statements.append(
        _page(
            name="anchored_filtered_o_star_dense_page_24",
            kind="anchored_filtered_page",
            picked_archetype=None,
            hard_filters={
                "max_distance_ly": RADIUS_LY,
                selective_filter: ["O"],
            },
            reference_coords=dense_anchor,
            limit=24,
            sort=SORT_DISTANCE,
            param_sql_types=[
                "double precision",
                "double precision",
                "double precision",
                "double precision",
                "text",
                "bigint",
                "bigint",
                "bigint",
            ],
            expectations={
                "anchor": "dense",
                "candidate_bound": True,
                "hard_filter": selective_filter,
                "hard_filter_value": ["O"],
                "page_size": 24,
                "radius_ly": RADIUS_LY,
            },
        )
    )
    statements.append(
        _page(
            name="anchored_development_dense_page_24",
            kind="anchored_score_page",
            picked_archetype=None,
            hard_filters={"max_distance_ly": RADIUS_LY},
            reference_coords=dense_anchor,
            limit=24,
            sort=SORT_SCORE,
            param_sql_types=[
                "double precision",
                "double precision",
                "double precision",
                "double precision",
                "bigint",
                "bigint",
            ],
            expectations={
                "anchor": "dense",
                "candidate_bound": True,
                "page_size": 24,
                "radius_ly": RADIUS_LY,
            },
        )
    )

    if len(statements) != STATEMENT_COUNT:
        raise RuntimeError(
            f"statement matrix drifted: expected {STATEMENT_COUNT}, got {len(statements)}"
        )
    return {
        "ranking_version": RANKING_VERSION,
        "ranking_sha256": ranking_sha256(),
        "statements": statements,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dense-anchor",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        required=True,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    document = build_statements_document(tuple(args.dense_anchor))
    print(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
