"""Fail CI if the browser-journey systems drift between the legacy ``systems``
table and the published ``v3_app.system_search`` projection.

After F3, autocomplete + system detail still read legacy ``public.systems``
while search reads the V3 projection -- the two MUST agree on the journey
id64s, or the Cypress product-journey (search -> detail) breaks silently.
Both relations expose a ``name`` column (``v3_derived.system_search.name``,
exposed via ``v3_app.system_search`` = ``SELECT s.*``).
"""
from __future__ import annotations

import os
import sys

JOURNEY_SYSTEMS = {10477373803000: 'Achenar', 9007199254740993: 'V3 Lossless Reach'}

# Legacy coords are stored as numeric(.2); V3 x_ly/y_ly/z_ly are double. Compare
# with a small tolerance so representation differences do not false-positive.
_COORD_TOLERANCE_LY = 0.01

# A journey record is (name, x, y, z). Legacy reads x/y/z from `systems`; V3 reads
# x_ly/y_ly/z_ly from `v3_app.system_search`. Both must agree, or the browser
# search->detail handoff renders the same system at two different positions.
Record = tuple


def _coords_match(a: Record, b: Record) -> bool:
    return all(
        x is not None and y is not None and abs(float(x) - float(y)) <= _COORD_TOLERANCE_LY
        for x, y in zip(a[1:4], b[1:4], strict=True)
    )


def diff_journey_systems(legacy: dict[int, Record], v3: dict[int, Record]) -> list[str]:
    problems = []
    for id64, name in JOURNEY_SYSTEMS.items():
        lrec, vrec = legacy.get(id64), v3.get(id64)
        if lrec is None or lrec[0] != name:
            problems.append(
                f'legacy systems missing/mismatched {id64} (want {name!r}, got {lrec!r})')
        if vrec is None or vrec[0] != name:
            problems.append(
                f'v3_app.system_search missing/mismatched {id64} (want {name!r}, got {vrec!r})')
        if lrec is not None and vrec is not None and not _coords_match(lrec, vrec):
            problems.append(
                f'{id64} coordinates differ: legacy {tuple(lrec[1:4])} vs v3 {tuple(vrec[1:4])}')
    return problems


def main() -> int:
    import psycopg

    ids = list(JOURNEY_SYSTEMS)
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as conn:
        legacy = {r[0]: (r[1], r[2], r[3], r[4]) for r in conn.execute(
            'SELECT id64, name, x, y, z FROM systems WHERE id64 = ANY(%s)', (ids,)).fetchall()}
        v3 = {r[0]: (r[1], r[2], r[3], r[4]) for r in conn.execute(
            'SELECT system_id64, name, x_ly, y_ly, z_ly FROM v3_app.system_search '
            'WHERE system_id64 = ANY(%s)', (ids,)).fetchall()}
    problems = diff_journey_systems(legacy, v3)
    if problems:
        print('legacy/V3 journey-system drift:', *problems, sep='\n  ')
        return 1
    print('legacy/V3 journey systems consistent:', ids)
    return 0


if __name__ == '__main__':
    sys.exit(main())
