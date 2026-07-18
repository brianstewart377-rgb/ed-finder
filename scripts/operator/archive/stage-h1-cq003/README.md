# scripts/operator/archive/stage-h1-cq003

## Historical — not current operator surface

This directory contains the CQ-003 archival move of
scripts/repair_ratings_score_breakdown_null.py, a one-shot repair
script that targeted the retired score_breakdown column.

The script was unreferenced (zero callers in tests/, scripts/, or
Makefile) and is preserved here for historical reference only.
It is NOT part of any active operator surface and MUST NOT be
scheduled, invoked, or imported by any live automation path.

Archived: 2026-07-18 · CQ-003 · commit TBD
