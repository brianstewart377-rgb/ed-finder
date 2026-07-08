# Stage 18J-Q4c — Read-Only Warehouse DSN Provisioning Plan

## Purpose

Stage 18J-Q4c explains how an operator should create or provide the
read-only/report-only database connection that Stage 18J-Q3 needs before it can
generate a reconciliation report.

This is a documentation and operations plan only. It does not run
reconciliation, generate artifacts, create users, grant permissions, change
deployment config, create a station-type dry-run, approve an artifact, apply
canonical data, start Stage 18J-P, start Stage 18K, or begin broader canonical
work.

## Current Blocker

Stage 18J-Q3 is blocked because `EDFINDER_WAREHOUSE_READ_DSN` is not available
in the current shell and the repository does not already define a usable
read-only warehouse/report DSN.

Recent inspection found:

- The current machine was `DAVE2`.
- The checkout path was a local/dev-looking repo under a user home directory.
- `DATABASE_URL` was not set in that shell.
- `EDFINDER_WAREHOUSE_READ_DSN` was not set in that shell.
- The deployed path expected for this environment was not present.
- Docker could not be inspected without elevated local access.
- A local Postgres listener existed, but no database query was run.
- `docker-compose.yml` defines the normal app database path, not a separate
  `edfinder_enrichment` warehouse database.

This means the missing action is operator provisioning: someone with approved
database administration access must create or provide a read-only/report-only
credential outside Git.

Current repo support status:

| Item | Status |
|---|---|
| Separate `edfinder_enrichment` database | No. Stage 18I.5 recommends it, but it is design-only here. |
| `EDFINDER_WAREHOUSE_READ_DSN` deployment config | No. The name is documented for operator use, but no secret value is defined in repo config. |
| Production operator access packet | Yes. Stage 18J-Q4 provides docs/checklists only; it does not provision access. |

## Where This Must Be Run

Run provisioning from one of these approved operator locations:

- the actual deployment server, in an operator shell with approved database
  administration access;
- the approved production secret manager or deployment secret UI;
- an approved database administration console for the deployment database;
- a controlled operations workstation that is already authorized to administer
  the deployment database.

Do not assume a local checkout is enough. A path such as a user home directory
checkout on `DAVE2` is suitable for editing docs and running local tests, but it
is not enough to prove production database roles or create production-safe
credentials unless the operator has separately approved that machine and shell.

Beginner rule: if you are not sure whether the shell has approved production
database administration access, stop and ask the deployment operator before
running any database command.

## What Must Not Be Run On DAVE2

Do not run any of these from `DAVE2` or any local/dev checkout unless an
operator explicitly confirms it is the approved database administration
environment:

- production-connected reconciliation;
- the Stage 18J-Q3 report command;
- station-type dry-run generation;
- production apply or guarded apply;
- role creation or permission grants;
- Docker, scheduler, UI/API, or live API wiring;
- commands that print real DSNs, passwords, hostnames, tokens, or private
  paths.

Local/dev checkouts may be used for docs, tests, and redacted command review
only.

## Required Database Role

The operator must provide one dedicated read-only/report-only database role for
Stage 18J-Q3. The role should be easy to recognize as a reporting role and must
not be shared with the app, warehouse loader, maintenance scripts, apply tools,
or superuser/admin workflows.

Required role properties:

- login allowed only through the approved operator secret path;
- read/report purpose only;
- no ownership of schemas, tables, functions, or databases;
- no superuser/admin attributes;
- no write permissions;
- no DDL permissions;
- no canonical apply permissions;
- default session read-only behavior where the database supports it.

Stage 18I.5 recommends a future separate `edfinder_enrichment` warehouse
database. That database is design-only in the current repo. Until that boundary
is implemented, the operator must be extra careful if the warehouse staging
tables and canonical comparison tables live in the same app database.

## Required Permissions

The exact database, schemas, and table names must be confirmed by the operator
before any grants are applied. Do not guess. Use placeholders until the
operator has confirmed the deployment layout.

The role needs read access to:

- the warehouse source-run metadata needed by reconciliation;
- the warehouse source-file metadata needed by reconciliation;
- the warehouse raw-record metadata needed by reconciliation;
- the staged station evidence needed by the approved source run/file;
- controlled canonical comparison rows, views, snapshots, or exports needed by
  the read-only reconciliation query.

Known warehouse table names used by the current loader are:

- `enrichment_source_runs`;
- `enrichment_source_files`;
- `enrichment_raw_records`;
- `staging_edsm_stations`;
- `staging_edsm_bodies`;
- `staging_body_rings`.

Stage 18J-Q3 currently targets the station source scope, so the operator must
confirm the required station evidence path and any canonical comparison objects
before granting access.

## Forbidden Permissions

Do not grant the read/report role any of these:

- `INSERT`;
- `UPDATE`;
- `DELETE`;
- `MERGE`;
- `TRUNCATE`;
- `DROP`;
- `ALTER`;
- `CREATE`;
- schema ownership;
- table ownership;
- database ownership;
- superuser/admin privileges;
- app write privileges;
- warehouse loader/write privileges;
- canonical apply privileges.

Do not grant write access to canonical tables such as:

- `systems`;
- `stations`;
- `bodies`;
- `station_body_links`;
- `body_rings`;
- `body_scan_facts`.

Do not use any role that can bypass normal permissions or change grants for
itself.

## Required Private Environment Variables

Before a later Stage 18J-Q3 retry, the operator must set these in the approved
operator shell or deployment secret injection mechanism:

```sh
export PGOPTIONS='-c default_transaction_read_only=on'
export EDFINDER_WAREHOUSE_READ_DSN='<redacted-read-only-report-dsn>'
export SOURCE_RUN_KEY='<redacted-approved-source-run-key>'
export SOURCE_FILE_KEY='<redacted-approved-source-file-key>'
export SAFE_ARTIFACT_DIR='<redacted-operator-managed-path-outside-git>'
```

`SOURCE_RUN_KEY` and `SOURCE_FILE_KEY` must identify an approved staged
`edsm_nightly_stations` source scope. `SAFE_ARTIFACT_DIR` must be outside Git,
operator-managed, private, and not a path that triggers UI/API, scheduler, or
automation behavior.

## Secret Handling

The real DSN, password, host, username, source keys, private artifact paths,
and generated artifacts must stay outside Git.

Never place real values in:

- committed docs;
- tracked `.env` files;
- PR descriptions;
- issue comments;
- screenshots;
- copied terminal output;
- test fixtures;
- generated artifacts that will be committed.

Use only redacted examples in docs and chats. If a command prints a real DSN or
password, stop and treat that output as sensitive.

## Example Redacted DSN Shape

The real value is a database connection string supplied by the operator. Do not
copy a real value into this repo.

Example shape, with every sensitive part redacted:

```text
<db-scheme>://<read-report-user>:<redacted-password>@<redacted-host>:<port>/<operator-confirmed-database>
```

The database might be a future dedicated warehouse database, or it might be the
current transitional database with stricter read-only permissions. The operator
must confirm which layout is actually deployed before using the DSN.

## Operator Steps To Provision Access

These steps are examples only. Do not run them from a local/dev checkout. Do
not run them until the operator has confirmed the deployment database, schema
names, table names, and approved administration environment.

1. Confirm the database layout:
   - Is there a separate warehouse database?
   - If not, are the warehouse tables in the normal app database?
   - Which schemas contain the warehouse tables?
   - Which objects provide controlled canonical comparison access?

2. Choose or create a dedicated read/report role:
   - It must not be the app role.
   - It must not be the warehouse loader role.
   - It must not be the canonical apply role.
   - It must not be an owner or superuser.

3. Store the credential in the approved secret manager or private operator
   shell only.

4. Grant only the minimum read permissions.

5. Set default read-only transaction behavior where supported.

6. Record the role/grant review outside Git.

Example SQL template only:

```sql
-- Example only. Operator must confirm names before running.
-- Do not paste real passwords, hostnames, or private paths into this repo.

CREATE ROLE <readonly_report_role> LOGIN;

GRANT CONNECT ON DATABASE <operator_confirmed_database>
  TO <readonly_report_role>;

GRANT USAGE ON SCHEMA <operator_confirmed_warehouse_schema>
  TO <readonly_report_role>;

GRANT SELECT ON TABLE
  <operator_confirmed_warehouse_schema>.enrichment_source_runs,
  <operator_confirmed_warehouse_schema>.enrichment_source_files,
  <operator_confirmed_warehouse_schema>.enrichment_raw_records,
  <operator_confirmed_warehouse_schema>.staging_edsm_stations
  TO <readonly_report_role>;

-- Add only the operator-confirmed canonical comparison views, snapshots, or
-- tables required for read-only reconciliation.
GRANT USAGE ON SCHEMA <operator_confirmed_comparison_schema>
  TO <readonly_report_role>;

GRANT SELECT ON TABLE
  <operator_confirmed_comparison_schema>.<operator_confirmed_comparison_object>
  TO <readonly_report_role>;

ALTER ROLE <readonly_report_role>
  SET default_transaction_read_only = on;
```

Do not include `GRANT INSERT`, `GRANT UPDATE`, `GRANT DELETE`, `GRANT CREATE`,
`GRANT ALL`, ownership changes, superuser changes, or broad schema default
privileges for this role.

## Operator Steps To Verify Access

These verification steps are examples only. They should be run by the operator
in the approved environment without printing real DSNs or passwords.

1. Confirm the private variables are present without printing values:

```sh
test "$PGOPTIONS" = "-c default_transaction_read_only=on" || {
  echo "STOP: PGOPTIONS is not the required read-only value"
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
```

2. Confirm the DSN role and grants outside Git:
   - role is dedicated read/report;
   - role is not app/write/apply/owner/superuser;
   - role has only required read permissions;
   - role cannot write warehouse tables;
   - role cannot write canonical tables;
   - role cannot create, alter, drop, or truncate objects;
   - session read-only enforcement is active.

3. Confirm the source scope outside Git:
   - source is `edsm_nightly_stations`;
   - source run key is approved;
   - source file key is approved;
   - staged source run/file exists;
   - no live API crawl is required.

4. Confirm the artifact directory:
   - outside Git;
   - private/operator-managed;
   - not UI/API mounted;
   - not a scheduler trigger path.

Do not run the Stage 18J-Q3 reconciliation command during provisioning. That
command belongs to the later Q3 retry after every gate is confirmed.

## Stage 18J-Q3 Retry Criteria

Stage 18J-Q3 can be retried only when all of these are true:

- `EDFINDER_WAREHOUSE_READ_DSN` is set privately;
- the DSN has been proven read-only/report-only outside Git;
- the DSN is not `DATABASE_URL`;
- the DSN is not the app write DSN;
- the DSN is not the warehouse loader/write DSN;
- the DSN is not the canonical apply DSN;
- the DSN has no write or DDL permissions;
- `PGOPTIONS` is exactly `-c default_transaction_read_only=on`;
- `SOURCE_RUN_KEY` is approved;
- `SOURCE_FILE_KEY` is approved;
- `SAFE_ARTIFACT_DIR` is outside Git and operator-managed;
- the exact Q3 command is printed only in redacted form before execution;
- no apply, write, commit, confirmation, rollback, scheduler, Docker/UI/API, or
  live API command is present.

Passing these criteria does not start Stage 18J-P. Stage 18J-P still needs a
separate explicit task after the reconciliation artifact exists and passes its
contract checks.

## Stop Conditions

Stop immediately if any of these happen:

- the shell is a local/dev checkout and not the approved operator environment;
- the operator cannot identify the actual deployment database layout;
- the read/report DSN does not exist;
- the DSN is the app/runtime DSN;
- the DSN is a write, loader, apply, owner, superuser, or staging/test DSN;
- the role can write canonical tables;
- the role can create, alter, drop, truncate, insert, update, delete, or merge;
- the source run/file is not approved;
- the artifact directory is inside Git or unsafe;
- a command would print a real DSN or password;
- a command would run reconciliation, station-type dry-run, apply, scheduler,
  Docker/UI/API, or live API work during this provisioning stage.

## Final Recommendation

Do not retry Stage 18J-Q3 from `DAVE2` or a local/dev checkout unless the
operator explicitly confirms that shell has approved deployment database
administration access.

Provision a dedicated read-only/report-only DSN through the approved operator
path first. Keep the credential out of Git. After the role and variables are
verified, rerun the Stage 18J-Q3 pre-run gate in a separate task. Until then,
Stage 18J-Q3 remains blocked, Stage 18J-P remains blocked, and no production
artifact or production apply is authorized.

