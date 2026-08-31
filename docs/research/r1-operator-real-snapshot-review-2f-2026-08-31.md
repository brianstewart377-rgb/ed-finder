# ED-Finder R1 — Operator Real-System Snapshot
## Review 2F — Missing Body Classification Source Discovery

Date: 2026-08-31
Status: metadata-only source-tracing amendment.

## Triggering evidence

The normalized full V3 body table `v3_gen_phase4c_full_20260827_r5.bodies` contains generic `body_type_id` (Star / Planet / Barycentre / Belt Cluster) plus physical/environmental fields, but **does not contain a planet/star subtype/classification field**.

The `v3_vocab.body_type` reference confirms `body_type_id` cannot distinguish HMC, Metal-Rich, Rocky, Icy, Water World, Earth-like World, Ammonia World, gas-giant classes, black holes, neutron stars, etc.

This means the generated body table alone is insufficient for R1 economy/body-identity reasoning.

## Goal

Locate the retained authoritative/source-backed body subtype/classification without guessing it from atmosphere, mass, composition, star spectral class or other proxies.

## Allowed metadata discovery

Inspect relation names and column lists only in:

- `v3_source`
- `v3_identity`
- `v3_meta`
- `v3_async`
- all remaining relations in `v3_gen_phase4c_full_20260827_r5` not already inspected

Search specifically for fields/relations representing:

- planet class / subtype / body class / star type
- raw source payload or normalized source observation
- source body records keyed by source_body_id64/body_pk/system_id64
- source run provenance needed to join such classification safely.

No gameplay rows are read in this metadata step.

## Rule

Do not derive canonical body identity from atmosphere, signals, composition percentages, landability, radius, or mass if the actual source classification is absent.

If no retained classification exists anywhere in V3, record it as a schema gap that must be corrected before R1 can use this generated dataset for economy-role ranking.
