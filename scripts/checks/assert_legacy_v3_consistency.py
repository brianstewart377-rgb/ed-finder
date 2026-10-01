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


def diff_journey_systems(legacy: dict[int, str], v3: dict[int, str]) -> list[str]:
    problems = []
    for id64, name in JOURNEY_SYSTEMS.items():
        if legacy.get(id64) != name:
            problems.append(
                f'legacy systems missing/mismatched {id64} '
                f'(want {name!r}, got {legacy.get(id64)!r})')
        if v3.get(id64) != name:
            problems.append(
                f'v3_app.system_search missing/mismatched {id64} '
                f'(want {name!r}, got {v3.get(id64)!r})')
    return problems


def main() -> int:
    import psycopg

    ids = list(JOURNEY_SYSTEMS)
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as conn:
        legacy = dict(conn.execute(
            'SELECT id64, name FROM systems WHERE id64 = ANY(%s)', (ids,)).fetchall())
        v3 = dict(conn.execute(
            'SELECT system_id64, name FROM v3_app.system_search WHERE system_id64 = ANY(%s)',
            (ids,)).fetchall())
    problems = diff_journey_systems(legacy, v3)
    if problems:
        print('legacy/V3 journey-system drift:', *problems, sep='\n  ')
        return 1
    print('legacy/V3 journey systems consistent:', ids)
    return 0


if __name__ == '__main__':
    sys.exit(main())
