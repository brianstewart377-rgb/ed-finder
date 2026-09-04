# Legacy Data Inventory

> **Inventory only — not a V3 production recovery or migration runbook.** This
> document and its manifest do not authorize database access, restoration,
> extraction, or production changes. V3 database recovery remains fail-closed
> under [infrastructure-status.md](infrastructure-status.md).

## Purpose

The retained V2 dump may be used only as evidence for a future, reviewed
selective migration of data that cannot be rebuilt from public sources. The
machine-readable companion,
[`legacy-data-inventory-manifest.json`](legacy-data-inventory-manifest.json),
records the initial table-level classification and is the template for adding
measured evidence after an explicitly approved offline inspection.

This inventory makes no claim that the retained dump has been fully inspected,
that every historical table is represented, or that any data has been migrated.
An entry is a candidate, not an extraction decision.

## Retained dump identity

The only dump covered by this inventory is the offsite custom-format dump whose
identity is recorded in `infrastructure-status.md`:

| Field | Value |
|---|---|
| Filename | `edfinder_20260823T021001Z.dump` |
| Size | `75,931,356,521` bytes |
| SHA-256 | `20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1` |
| Offsite sync recorded | `2026-08-23T05:32:41Z` |

The dump is not the operating database and must never be restored wholesale
into V3 production. Its identity must be reverified before any future offline
inspection.

## Classification

- `public_reconstructable`: galaxy/source facts or derived products expected to
  be reproducible through current public import and calculation paths. Rebuild;
  do not migrate merely because a copy exists in the dump.
- `irreplaceable_private_manual_history`: commander/private, manually curated,
  or historical records that may merit selective migration. Inclusion still
  requires purpose, minimisation, ownership, privacy, and integrity evidence.
- `transient_or_operational`: cache, staging, sessions, job, and transport-like
  state that is not canonical domain truth and should normally be discarded.
- `unresolved_requires_evidence`: provenance or semantics are too ambiguous to
  decide safely from the checked-in schema. It is excluded unless an approved
  inspection supplies evidence and a reviewer reclassifies it.

The manifest's table list is based on checked-in migrations, not on a dump
catalogue. Tables absent from the list default to
`unresolved_requires_evidence`; they must not be silently extracted.

## Evidence gate before selective extraction

Before a table can be approved, a future authorized process must work only from
an explicitly confirmed disposable/offline restore, never production, and must
record in the manifest:

1. verified dump filename, byte size, and SHA-256;
2. restored schema/table identity and measured source table and record counts;
3. the proposed selective row count and selection predicate or artifact ID;
4. primary-key/uniqueness, referential-integrity, and domain validation results;
5. privacy/ownership review and the reason public reconstruction is inadequate;
6. target table and pre/post-load counts, reconciliation result, reviewer, and
   immutable evidence references.

Unknown, estimated, or blank counts do not pass the gate. Validation must be
`passed`, not merely attempted. Differences require an explained and reviewed
reconciliation. No production credentials, DSNs, personal values, or extracted
records belong in this repository.

## Completion rule

Migration completeness remains explicitly `false` until all dump tables have an
evidence-backed disposition, every approved selective dataset has reconciled
source/selection/target counts and validations, and a separate reviewed
authority records completion. Neither this document nor a populated manifest is
that authority.
