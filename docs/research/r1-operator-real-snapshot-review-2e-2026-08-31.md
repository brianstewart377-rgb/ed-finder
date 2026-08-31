# ED-Finder R1 — Operator Real-System Snapshot
## Review 2E — V3 Vocabulary Mapping Amendment

Date: 2026-08-31
Status: bounded read-only reference-data amendment.

## Triggering evidence

Metadata-only schema inventory found the full retained body store in normalized schema:

`v3_gen_phase4c_full_20260827_r5`

with approximately:

- 198.5M systems
- 598.7M bodies
- 93.6M rings
- 25.0M body-signal rows

Body rows use normalized IDs such as `body_type_id`, `atmosphere_classification_id`, `terraforming_state_id`, and `volcanism_type_id`, so R1 must not guess their semantic labels.

## Goal

Read only the small static/reference vocabulary relations required to translate normalized body/ring/signal IDs into canonical labels before any real-system row projection.

## Allowed source

Schema `v3_vocab` and other small normalized reference schemas where a foreign-key target is required to decode body/ring/signal fields.

First inspect catalog metadata to identify the exact relevant relations and columns. Then SELECT their reference rows only.

Expected categories include, if present:

- body type
- atmosphere classification
- terraforming state
- volcanism type
- signal type
- ring type
- reserve type
- source identity/run metadata needed only for provenance labels

## Safety

- SELECT/catalog reads only;
- reference/vocabulary tables only, not gameplay system/body rows;
- no writes/migrations;
- no user/private schemas;
- no credentials logged;
- output may include vocabulary IDs, public codes, display names and active flags.

## Adapter rule

The future V3 normalized snapshot adapter must join IDs to these explicit vocabulary values. Unknown/unmapped IDs remain Unknown and are surfaced as caveats; they are never mapped by numeric position or guessed string convention.

Exact Ammonia identity, HMC, Metal-Rich, rocky/icy, atmosphere, Terraformable, volcanism and signal semantics must derive from the actual vocabulary labels.
