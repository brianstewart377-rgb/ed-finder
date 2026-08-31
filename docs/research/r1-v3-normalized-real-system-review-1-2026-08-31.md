# ED-Finder R1 — V3 Normalized Real-System Validation
## Review 1 — Stage Definition

Date: 2026-08-31
Status: read-only validation stage; no Finder/ratings changes.

## Goal

Run bounded real-system validation directly against the full normalized V3 canonical generation `v3_gen_phase4c_full_20260827_r5` now that its schema and vocabularies have been inspected.

The stage measures what real R1 facts the normalized 598M-body store can support today and where it must return Unknown.

## Critical known limitation

No inspected normalized/generated/source/identity/meta relation retains planet/star subtype/classification beyond generic `body_type_id` = Star / Planet / Barycentre / Belt Cluster.

Therefore this stage must not claim HMC, Metal-Rich, Rocky, Icy, WW, ELW, Ammonia World, gas-giant subtype, black-hole/neutron identity, or any other subtype-dependent mechanic from this normalized store alone.

## Allowed real facts

For up to 20 exact systems per run, read only:

- system identity and source/loaded body counts;
- body generic type, name, source IDs, physical fields;
- explicit Terraforming vocab state;
- explicit atmosphere classification;
- explicit volcanism type;
- landable/tidal stored state, preserving caveats where negative provenance is uncertain;
- `signals_complete` and current Biological/Geological signal rows;
- current/non-retired ring rows and ring/reserve vocab labels;
- source/run/freshness/lifecycle metadata needed for provenance diagnostics.

## Output purpose

Produce per-system and aggregate coverage metrics across the named real systems:

- body completeness;
- generic body count;
- landable positive count;
- explicit Terraformable / not-Terraformable counts;
- unknown Terraforming count;
- atmosphere known/unknown;
- volcanism known/unknown;
- signals-complete rate;
- known Biological/Geological presence and known-negative where completeness permits;
- active ring-body count;
- physical-field coverage (radius, gravity, temp, distance);
- number of bodies blocked from exact R1 surface-slot prediction specifically because body subtype/HMC status is unavailable.

## Safety

- max 20 exact systems per run;
- explicit read-only PostgreSQL transaction; verify `transaction_read_only=on`;
- static parameterized SELECT only;
- no writes/migrations;
- no legacy ratings/archetype reads;
- no Plan Fit or plan-resilience calculation;
- no Finder/UI changes.

## Test corpus

Run the already-defined three batches of 20 real systems (60 total) if each preceding run succeeds safely.
