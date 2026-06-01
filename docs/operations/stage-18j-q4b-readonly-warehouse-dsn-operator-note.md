# Stage 18J-Q4b - Read-Only Warehouse DSN Operator Note

## Purpose

Stage 18J-Q3 remains blocked because the required
`EDFINDER_WAREHOUSE_READ_DSN` was not present in the operator shell. This note
summarizes where that value should come from and how operators should provide
it safely for a later retry.

This note is docs/ops only. It does not authorize production reconciliation,
station-type dry-run generation, artifact approval, production apply, guarded
apply, database mutation, scheduler wiring, UI/API controls, live API crawling,
Stage 18J-P, Stage 18K, or broader canonical work.

## Current Configuration Finding

The repository documents `EDFINDER_WAREHOUSE_READ_DSN` as the required
read-only/report-only DSN variable for Stage 18J-Q3. The importer CLI itself
does not read that environment variable directly; it accepts a caller-supplied
`--dsn` and Stage 18J-Q3 passes `"$EDFINDER_WAREHOUSE_READ_DSN"` to that flag.

`env.example` does not define `EDFINDER_WAREHOUSE_READ_DSN`,
`EDFINDER_WAREHOUSE_DSN`, `EDFINDER_CANONICAL_READ_DSN`, or
`EDFINDER_CANONICAL_APPLY_DSN`. It includes the warehouse status artifact path
variable, which is for a prepublished JSON artifact read by the API, not a
database DSN.

`docker-compose.yml` defines the normal app Postgres service and app/runtime
`DATABASE_URL` usage. It does not define a separate `edfinder_enrichment`
warehouse database, a warehouse read/report role, or
`EDFINDER_WAREHOUSE_READ_DSN`.

Stage 18I.5 recommends a future separate `edfinder_enrichment` warehouse
database and names `EDFINDER_WAREHOUSE_READ_DSN` as the read/report DSN for
warehouse reporting processes. Stage 18I.5 explicitly does not implement that
database, user, permission model, migration path, or deployment configuration.

## Required Operator Action

The operator must create or provide a real read-only/report-only warehouse DSN
outside Git before Stage 18J-Q3 can be retried. The DSN must come from the
operator secret manager, deployment secret store, or private operator shell. It
must not be written to committed docs, tracked `.env` files, PRs, issue
comments, screenshots, or copied logs.

If no read-only/report-only warehouse credential exists yet, the follow-up
provisioning plan is:

```text
Stage 18J-Q4c - Read-Only Warehouse DSN Provisioning Plan
```

See
[`stage-18j-q4c-readonly-warehouse-dsn-provisioning-plan.md`](./stage-18j-q4c-readonly-warehouse-dsn-provisioning-plan.md).
That plan defines how to provision a dedicated read/report role and validate
its grants before any production-connected reconciliation command is run.

## Required Variables For A Later Q3 Retry

Operators must export these values in the approved shell or secret-injected
environment before rerunning Stage 18J-Q3:

```sh
export PGOPTIONS='-c default_transaction_read_only=on'
export EDFINDER_WAREHOUSE_READ_DSN='<redacted-read-only-report-dsn>'
export SOURCE_RUN_KEY='<redacted-approved-source-run-key>'
export SOURCE_FILE_KEY='<redacted-approved-source-file-key>'
export SAFE_ARTIFACT_DIR='<redacted-operator-managed-path-outside-git>'
```

The source run and source file must identify an approved staged
`edsm_nightly_stations` source scope. `SAFE_ARTIFACT_DIR` must be outside Git,
operator-managed, private, and not mounted into UI/API or scheduler trigger
paths.

## Forbidden DSN Types

Do not use any of these as `EDFINDER_WAREHOUSE_READ_DSN`:

- the app/runtime `DATABASE_URL`;
- the application write DSN;
- a warehouse loader or staging write DSN;
- a test-only or disposable staging smoke-test DSN;
- `EDFINDER_CANONICAL_APPLY_DSN`;
- a canonical apply user;
- a database owner or superuser credential;
- any role with canonical table write access;
- any role with broad DDL privileges;
- any credential that can insert, update, delete, truncate, create, alter,
  drop, or merge warehouse or canonical tables.

The read/report role must be able to read the staged warehouse evidence needed
for reconciliation and the controlled canonical comparison data or snapshots.
It must not be able to write canonical tables such as `systems`, `stations`,
`bodies`, `station_body_links`, `body_rings`, or `body_scan_facts`.

## Redacted Verification Command

Run this from the operator shell after injecting the real values. It verifies
presence and the read-only session option without printing secrets:

```sh
export PGOPTIONS='-c default_transaction_read_only=on'

test "$PGOPTIONS" = "-c default_transaction_read_only=on" || {
  echo "STOP: PGOPTIONS is not set to the required read-only value"
  exit 1
}

for name in EDFINDER_WAREHOUSE_READ_DSN SOURCE_RUN_KEY SOURCE_FILE_KEY SAFE_ARTIFACT_DIR; do
  eval "is_set=\${$name:+set}"
  if [ "$is_set" != "set" ]; then
    echo "STOP: $name is not set"
    exit 1
  fi
  echo "$name: set (redacted)"
done

case "$SAFE_ARTIFACT_DIR" in
  *"/.git"*|*"Documents/GitHub"*|*"ed-finder"*)
    echo "STOP: SAFE_ARTIFACT_DIR appears to be inside or near the repo"
    exit 1
    ;;
esac

echo "PGOPTIONS: set to required read-only value"
echo "Stage 18J-Q3 variables are present; complete operator DSN grant review before running any production-connected command"
```

This check only proves that variables are present. It does not prove the DSN
grant model. Before any Stage 18J-Q3 command runs, the operator must separately
confirm outside Git that the DSN is read-only/report-only, is not the app write
DSN, is not the canonical apply DSN, has no canonical write access, and points
at the intended warehouse/report source.

## Stage 18J-Q3 Status

Stage 18J-Q3 cannot proceed until `EDFINDER_WAREHOUSE_READ_DSN` is provided and
verified by the operator. Stage 18J-P remains blocked until a valid
`enrichment_staging_reconciliation/v1` production reconciliation artifact is
generated through the approved read-only/report-only path and passes contract
validation.

No production command is run by this note.
