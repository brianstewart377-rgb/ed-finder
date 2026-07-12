# Storage Recovery Phase A — Receipt
**Date:** 2026-07-12
**Operation:** Drop dead/fossil indexes (Phase A)
**Operator:** brianstewart377-rgb

## Starting state
- Database size: 960 GB
- Disk free: 525 GB (71% used)

## Indexes dropped
### Invalid reindex debris (0 bytes)
- idx_sys_name_lower_pattern_ccnew (x9 variants)
- All confirmed indisvalid=false before dropping

### Retired per-economy scoring model (~55 GB)
- idx_ratings_confidence_high
- idx_rat_econ_score, idx_rat_score, idx_rat_body_quality
- idx_rat_agriculture, idx_rat_military, idx_rat_slots
- idx_rat_refinery, idx_rat_industrial, idx_rat_hightech
- idx_rat_tourism, idx_rat_gas_giant, idx_rat_terraformable
- idx_rat_neutron, idx_rat_ammonia, idx_rat_bio, idx_rat_elw, idx_rat_geo
- Justification: ratings table joined by primary key only;
  no query in codebase filters/sorts on these columns as
  driving predicate. Verified by code analysis 2026-07-12.

### Redundant coordinate singles (~32 GB)
- idx_sys_x, idx_sys_y, idx_sys_z
- Justification: idx_sys_coords (composite) confirmed chosen
  by planner for all 3D bounding box queries.

### Redundant name btree (~14 GB)
- idx_sys_name
- Justification: idx_sys_name_trgm serves all name search paths.

## Ending state
- Database size: 871 GB
- Disk free: 615 GB (66% used)
- Recovered: 89 GB

## Verification
Both critical indexes confirmed working post-drop:
- idx_sys_coords: Index Scan on 3D bounding box query ✓
- idx_sys_name_trgm: Bitmap Index Scan on similarity query ✓

## Remaining index questions (deferred)
- idx_sys_name_lower_pattern (14 GB): needs EXPLAIN against
  autocomplete query shape before deciding
- idx_rat_dirty (8 GB): needs grep confirmation no pipeline
  references by name

## Next
Phase B: score_breakdown removal (~180 GB)
Requires code change to build_ratings.py first.
See docs/operations/storage-recovery-runbook-2026-07-12.md
