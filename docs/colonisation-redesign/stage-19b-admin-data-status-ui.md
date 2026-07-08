# Stage 19B — Admin data-status UI

## Result

Stage 19B adds frontend visibility for the Stage 19A read-only admin data-status endpoint.

The existing Admin tab now fetches:

`GET /api/admin/data-status`

and renders a token-gated Data Status panel.

## Scope

The panel shows:

- total station rows;
- unknown station rows;
- Coriolis and Dodec station counts;
- external identity counts;
- remaining Unknown station-type evidence by source station type;
- recent station-type updates;
- safety summary flags.

## Safety boundary

This stage is frontend-only.

It does not add:

- DB writes;
- migrations;
- station-type writes;
- canonical writes;
- canonical apply.

The API endpoint consumed by the panel runs in a read-only transaction and is admin-token gated.

