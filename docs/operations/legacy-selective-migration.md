# Legacy selective-migration contract

This document describes the review boundary for selectively assessing legacy
data. It is **not a production recovery runbook** and does not authorize access
to the retained dump, offsite storage, secrets, DNS, or a live database.

Phase 1 was developed from repository schema and importer evidence plus tiny,
synthetic local dumps. **No retained dump was inspected.** Consequently Phase 1
cannot certify which records exist, whether relationships are complete, or
whether all irreplaceable records can be recovered. Data completeness remains
unproven until Phase 2 uses the validated dump with explicit owner
authorization.

## Fixed retained-vault identity

The sole retained-vault artifact recognized by the inventory tooling is:

| Field | Required value |
|---|---|
| Filename | `edfinder_20260823T021001Z.dump` |
| Size | `75,931,356,521` bytes |
| SHA-256 | `20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1` |

Those values identify a candidate source; they do not approve inspection or
migration. Retained-vault verification is used only when the operator explicitly
selects retained-vault mode. A synthetic/test acknowledgement is separate
evidence and must never be represented as validation of the retained artifact.

## Data classes

Every dump object must match an exact registry entry or a narrow, reviewed
family. Unknown objects fail closed as unclassified blockers.

| Class | Meaning | Required disposition |
|---|---|---|
| Public/reconstructable source data | Public galaxy or source records recoverable through an authoritative importer/source path | Reimport from the named source; do not migrate from the vault |
| Derived/rebuildable state | Indexes, materialized views, caches, summaries, and transport state derived from authoritative records | Rebuild; never treat it as canonical evidence |
| Private/manual/user/history candidates | Potentially irreplaceable records that may justify narrow, owner-approved migration | Inventory first; inspect or extract only through an exact validated manifest |
| Credentials/operational/security state | Authentication material, tokens, operational state, security state, or similarly sensitive objects | Never migrate |

The versioned machine-readable registry records rationale, authoritative source
or rebuild path, candidate keys and relationships, and whether row-content
inspection is permitted. Classification is not extraction permission.

## Three phases

### Phase 1 — offline inventory and proposal

Phase 1 accepts only an explicitly supplied local regular custom-format dump.
It uses `pg_restore --list` read-only, joins object names and types to the
classification registry, and writes sanitized deterministic JSON and Markdown
receipts. Receipts contain no table rows, SQL bodies, secrets, DSNs, hostnames,
or credential-like values. Only the input dump and generated receipts are
hashed; object content is not hashed.

Phase 1 may validate or generate a blank extraction-manifest proposal and may
print an isolated-inspection command plan. It does not execute SQL, restore a
database, or extract data. It rejects symlinks, non-regular inputs, unsafe
output locations, URLs, production-looking connection details, incompatible
PostgreSQL client relationships, broad restore flags, wildcards, unbounded
tables, arbitrary SQL, shell fragments, and unclassified objects.

The CLI authority is its checked-in `--help` output. A synthetic inventory is
requested explicitly, for example:

```bash
python scripts/migration/legacy_data_inventory.py inventory \
  --dump /absolute/path/to/tiny-synthetic.dump \
  --output-dir /absolute/path/to/new-receipt-directory \
  --synthetic-or-test-dump \
  --proposal-template
```

Use `--retained-vault` instead only under a later explicit authorization to
inspect the retained artifact; the two acknowledgements are mutually exclusive.

### Phase 2 — owner-authorized disposable inspection

Phase 2 is future work. It requires the actual identity-validated dump, an
explicit repository-owner authorization, a reviewed extraction manifest, and
a disposable PostgreSQL instance bound only to a local Unix socket or loopback.
Inspection must begin schema-only, use a generated non-production database
name, and constrain any later data operation to the manifest's exact table and
column allowlists. The Phase 1 plan generator prints commands for review; it
does not execute them.

Phase 2 must validate candidate keys, relationships, source counts, and bounded
tolerances recorded in the manifest. It is the first phase capable of producing
evidence about record completeness; it still does not authorize production
writes.

After a manifest is reviewed, Phase 1 can print (but cannot execute) a future
local inspection plan. Consult the exact interface before preparing it:

```bash
python scripts/migration/legacy_data_inventory.py inspection-plan --help
```

The command requires `--manifest`, one explicit dump acknowledgement, and an
explicit loopback-only `--host`; its generated commands retain the schema-first
and exact-table-allowlist constraints above.

### Phase 3 — separately reviewed selective migration

Phase 3 requires a separate approved change and operator procedure. It may move
only approved candidate private/manual/user/history records through an exact
manifest with destination mapping, idempotency/conflict policy, relationship
validation, count/tolerance checks, and tested abort and rollback conditions.
No credentials/operational/security state, public/reconstructable data, or
derived state may be carried forward.

There is no wholesale-restore path in any phase. Never use the retained dump as
a production database, run a broad restore, attach an older PostgreSQL physical
directory to PostgreSQL 18, or use `pg_restore --clean`, `--create`, or a
user-supplied/network database target as a shortcut.

## Decisions the owner must record

Before Phase 2, the repository owner must record:

- authorization to access the retained artifact and confirmation of its exact
  filename, size, and SHA-256;
- the precise candidate tables and columns whose content may be inspected;
- the business justification and authoritative owner for each candidate;
- allowed key filters and required relationship validation;
- expected source and target counts or explicit bounded tolerances; and
- approval/rejection criteria, abort conditions, evidence retention, and safe
  disposal requirements for the isolated environment.

Before Phase 3, the owner must additionally approve the destination mapping,
idempotency and conflict behavior, rollback conditions, target environment, and
the separately reviewed execution procedure. An inventory receipt or valid
manifest alone is not approval.

## Synthetic local validation

Repository tests may create tiny synthetic custom-format dumps in disposable
local PostgreSQL only. They must use invented, non-sensitive rows and must not
use retained-vault mode. Run the focused suite with:

```bash
pytest -q tests/test_legacy_data_inventory.py tests/test_legacy_selective_migration_docs.py
```

The custom-format integration case skips clearly when the required PostgreSQL
client binaries are unavailable. Its success proves parser and safety behavior
against synthetic input only. It is not retained-vault evidence and does not
prove legacy-data completeness.

For current production and recovery authority, return to
[`infrastructure-status.md`](infrastructure-status.md). For bulk-write safety,
see [`bulk-database-write-safety.md`](../development/bulk-database-write-safety.md).
