def canonical_body_provenance(body): return f'canonical_body:{body.id}:{body.updated_at or "unknown"}'
def canonical_system_provenance(system): return f'canonical_system:{system.id64}:{system.updated_at or "unknown"}'
def ring_provenance(ring): return f'ring:{ring.source}:{ring.body_id or ring.source_body_id or ring.body_name or "unknown"}:{ring.ring_name or "unknown"}:{ring.updated_at or "unknown"}'
def sorted_ids(*groups): return tuple(sorted({x for g in groups for x in g if x}))
