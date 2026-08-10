# Stage 19A — Admin data-status API

## Result

Stage 19A adds a read-only admin data-status endpoint:

`GET /api/admin/data-status`

The endpoint is admin-token gated and returns database status counts useful for operator/data visibility.

## Scope

The endpoint reports:

- station row counts;
- station type counts;
- station type source counts;
- external identity counts;
- external identity source/status counts;
- remaining `Unknown` station-type evidence by source station type;
- recent station-type updates.

## Safety boundary

The endpoint runs inside a read-only database transaction.

It does not perform:

- imports;
- migrations;
- station-type writes;
- canonical writes;
- canonical apply;
- artifact generation.

## Roadmap context

This is the backend foundation for Stage 19 operator/data visibility. A later stage can add UI cards that consume this endpoint.

