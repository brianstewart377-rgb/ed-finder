# RETIRED — V1/V2 production storage recovery runbook

**Historical date:** 2026-07-12  
**Status:** retired after the 2026-09-02 V3 cutover. **Do not execute this file.**

This document previously described destructive storage-recovery work for the
former Hetzner/V2 PostgreSQL environment, including index drops, ratings-data
rewrites, backup assumptions, and `pg_repack` operations tied to the retired
container/storage layout.

It is retained only as historical evidence explaining the July 2026 storage
incident and the changes that were made to that former database. It is **not** a
PostgreSQL 18/V3 production runbook and does not authorize adapting its commands
to the replacement host.

## Current V3 boundary

Use `docs/operations/infrastructure-status.md` as the current infrastructure and
recovery authority.

The repository does not currently contain an executable PostgreSQL 18
backup/restore/PITR recovery runbook. Therefore repository-driven V3 production
backup restoration, PITR, destructive storage recovery, index removal,
repacking, or disaster-recovery commands remain unauthorized unless a later
explicitly reviewed V3 runbook opens that action.

Issue #573 tracks the required PostgreSQL 18-native recovery/runbook/rehearsal
work. Do not fill that gap by reviving this procedure or by inferring V3 topology
from retired V2 Compose, maintenance, backup, or host paths.

## Historical evidence

The complete executable historical version remains available through Git history
before the V3 decommission re-baseline, including commit
`1dcc6531f61c2ac6ac6f1cc774f53cdee760b1fd` and the dated storage-recovery
receipts under `artifacts/storage-recovery/`.

Those receipts may explain what happened on V2; they do not establish the
current PostgreSQL 18 database size, indexes, free-space posture, backup state,
or maintenance requirements.
