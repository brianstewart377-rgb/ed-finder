# Ratings V4 chunk re-read plan

Ratings V4 replay re-reads every stored chunk before it can seal or publish a
generation. `_read_chunk` in `scripts/ratings_v4/production_generation.py`
selected chunk membership with a semi-join:

```sql
SELECT ... FROM v3_derived.body_mechanics t
 WHERE t.derived_generation_id = $1
   AND t.system_id64 IN (SELECT system_id64 FROM v3_derived.system_rating_vector
                          WHERE derived_generation_id = $2 AND chunk_ordinal = $3)
 ORDER BY t.system_id64, t.body_pk
```

On the retained production relation (602,267,906 rows, ~110 GB) PostgreSQL prices
that semi-join against a parallel sequential scan of `body_mechanics` as a
near-tie and then chooses the scan, so every replayed chunk read the whole table
and sorted it.

## Measured on the retained production database

Chunk 19058, same rows, default planner settings:

| read | time | shared buffers |
| --- | --- | --- |
| semi-join (previous) | 13,594 ms | 8,000,718 |
| plain join (adopted) | 69 ms | 5,117 |

`SET enable_seqscan=off` gave 75.8 ms and `random_page_cost=1.1` gave 93 ms, so
both flip the same plan, but the join rewrite needs no session or server setting
change and is therefore the fix.

Cumulative evidence for the same misplan elsewhere: `body_mechanics.seq_tup_read`
had reached ~939 billion rows (about 1,560 complete passes) while the larger
`economy_opportunity` relation had been sequentially scanned 31 times ever. Live
sampling on 2026-09-13 showed one complete `body_mechanics` pass (602,267,906
rows, ~65 GB of buffers) for every chunk committed by the concurrently running
Search follower, at ~20 s per chunk.

## The fix

Chunk rows are joined to their own chunk receipt:

```sql
SELECT ... FROM v3_derived.<table> t
  JOIN v3_derived.system_rating_vector v
    ON v.derived_generation_id = t.derived_generation_id AND v.system_id64 = t.system_id64
 WHERE v.derived_generation_id = $1 AND v.chunk_ordinal = $2
 ORDER BY ...
```

`system_rating_vector` is unique on `(derived_generation_id, system_id64)`, so the
joined form returns exactly the receipt rows, resolves to the keyed
`body_mechanics_pkey` nested loop, and binds the receipt filter once instead of
three times. Every read keeps its explicit `ORDER BY`, so replayed row order and
therefore the sealed chunk digest and the recorded content seal are unchanged.
Equivalence was checked on the retained database for chunk 19058 across all three
reads (`bodies` 4,586 rows, `vectors` 1,000, `opportunities` 6,081; membership
digests identical) and is asserted by
`tests/test_ratings_v4_chunk_read_plan.py` wherever a validation database is
available.

The validation fixture cannot catch this regression. It holds a few hundred rows,
so every candidate plan is an index lookup there and a plan assertion would pass
against the defective query too. The regression guard is therefore the query
shape the planner cannot degrade, and the guard is additionally shown to reject
the previous query verbatim.

## Scope

This changes the replay read path only. It does not change what is stored, what
is hashed, the scorer, the manifest, or any publication behaviour, and it does
not make validation faster for a generation that is already `VALIDATING`: the
running validator holds its original bundle and the manifest pins the code
identity of the generation being replayed, so an in-flight replay must finish
under the code that wrote it. The saving applies to generations built or
validated after this change.