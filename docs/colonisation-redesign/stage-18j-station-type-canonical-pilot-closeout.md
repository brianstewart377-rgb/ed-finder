# Stage 18J — Station Type Canonical Pilot Closeout

## Result

Stage 18J is complete as the first narrow canonical write pilot.

The delivered path is intentionally small:

- target table: `stations`
- target field: `station_type`
- existing canonical row only
- exact identity proof required
- deterministic dry-run artifact required
- guarded apply path required
- rollback pre-image and post-apply verification required

This does **not** turn the warehouse into a general warehouse-to-canonical
bridge. It proves one bounded, auditable, reversible path only.

## Delivered Implementation

The repo already contains the Stage 18J pilot implementation:

- `apps/importer/src/station_type_canonical_pilot.py`
- `tests/test_station_type_canonical_pilot.py`
- `tests/test_station_type_canonical_pilot_postgres.py`

That module provides:

1. deterministic station-type-only dry-run artifact generation
2. explicit approval-parameter validation
3. guarded apply helpers that update only `stations.station_type`
4. rollback pre-image emission
5. post-apply verification
6. fail-closed CLI wiring for dry-run and guarded apply modes

## Boundaries Preserved

Stage 18J still does **not** authorize:

- broad canonical backfill
- planner, scoring, CP, role, optimiser, or Simulation Preview mutation
- station/body link writes
- ring writes
- distance writes
- services/economies/faction/government/allegiance writes
- unrestricted production apply
- scheduler or UI/API apply controls

Production apply remains unauthorized unless a separate future instruction
approves the exact artifact checksum, candidate count, source run/file, table,
field, max row count, and apply DSN context.

## Artifact Chain

The bounded station-type write chain is documented in:

- `docs/colonisation-redesign/stage-18j-p18m-dodec-and-bounded-station-type-write-closeout.md`

That closeout records the bounded reviewed station-type write result and keeps
the post-closeout policy conservative.

## Next Roadmap Position

The next meaningful follow-on is Stage 18T — Canonical Safety Test
Environment, which hardens repeatable CI/local safety coverage around the
canonical-write-capable Stage 18J path without authorizing further production
apply.
