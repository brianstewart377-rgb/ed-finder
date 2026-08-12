# Bulk database write safety

Every bulk write that can update `systems`, `bodies`, `cluster_summary` /
cluster-derived rows, or `ratings` must use
`shared_contracts.bulk_update_helper.bulk_update_replica_mode` when suppressing
referential-integrity triggers is safe. The helper is mandatory for bulk
`UPDATE systems` statements that do not modify `id64`.

The helper is fail-closed: it sets and verifies `session_replication_role` on
the exact connection passed by the caller before yielding, rolls back failed
work, and restores and verifies the original role in a `finally` block. The
successful write must be committed inside the context. Do not set replica mode
on a monitoring connection while writing through another connection, and do
not use it through a transaction-pooled connection. The helper rejects
autocommit connections because their failed writes cannot be rolled back.

Replica mode suppresses ordinary application and foreign-key triggers. Do not
wrap writes that change primary/foreign-key identities, and keep replica-mode
scope as narrow as practical when a batch includes writes whose triggers must
remain active. A bulk path that intentionally does not use the helper must carry
an adjacent code comment explaining why trigger enforcement is required or why
the statement is not an update of these canonical tables.

Current audited exceptions:

- `build_archetype_scores.py` writes only `system_archetype_scores` and
  `system_archetype_traits`; it does not update `systems`, `bodies`, clusters,
  or `ratings`.
- `build_regional_analysis.py` writes only `system_regional_analysis`.
- `build_topology.py` writes only `system_slot_topology`,
  `system_archetype_scores`, and `economy_pair_synergy`.
- `build_grid.py` predates the helper and has specialized parallel reconnect,
  autocommit, and `ALTER TABLE ... DISABLE TRIGGER` fallback behavior. Its
  connection-specific replica-mode handling remains an explicitly documented
  legacy exception pending a separately reviewed migration.
