import type { UseAdmin } from '../useAdmin';
import { Flag, Stat } from './AdminMetrics';

export function AdminLiveStatusPanel({
  status,
  cache,
  metaError,
  metaLoading,
}: {
  status: UseAdmin['status'];
  cache: UseAdmin['cache'];
  metaError: UseAdmin['metaError'];
  metaLoading: UseAdmin['metaLoading'];
}) {
  return (
    <section className="panel p-5 space-y-3">
      <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
        2. Live status
      </h3>

      {metaError && (
        <div className="panel-thin border-red/50 p-2 font-mono text-xs text-red" style={{ background: 'rgba(248,113,113,0.10)' }}>
          {metaError}
        </div>
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs font-mono">
        {status && (
          <>
            <Stat label="Systems" value={status.systems_count.toLocaleString()} />
            <Stat label="Bodies" value={status.body_count.toLocaleString()} />
            <Stat label="Rated" value={status.rated_count.toLocaleString()} />
            <Stat label="Clustered" value={status.clustered_count.toLocaleString()} />
            <Stat label="Schema version" value={status.schema_version} />
            <Stat label="App version" value={status.version} />
            <Stat label="Last nightly" value={status.last_nightly_update} highlight={status.last_nightly_update === 'never'} />
            <Flag label="Import complete" value={status.import_complete} />
            <Flag label="Ratings built" value={status.ratings_built} />
            <Flag label="Grid built" value={status.grid_built} />
            <Flag label="Clusters built" value={status.clusters_built} />
            <Flag label="EDDN enabled" value={status.eddn_enabled} />
          </>
        )}
        {cache && (
          <>
            <Stat label="Mem cache hits" value={cache.cache_hits.toLocaleString()} />
            <Stat label="Mem cache misses" value={cache.cache_misses.toLocaleString()} />
            {cache.redis_hits != null && (
              <Stat label="Redis hits" value={cache.redis_hits.toLocaleString()} />
            )}
            {cache.redis_misses != null && (
              <Stat label="Redis misses" value={cache.redis_misses.toLocaleString()} />
            )}
            {cache.redis_memory_mb != null && (
              <Stat label="Redis memory" value={`${cache.redis_memory_mb} MB`} />
            )}
            <Stat label="DB cache rows" value={cache.db_cache_rows.toLocaleString()} />
          </>
        )}
      </div>

      <p className="text-[10px] text-silver-dk font-mono">
        Auto-refreshes every 30s.
        {metaLoading && <span className="text-orange-lt ml-2">⟳ refreshing…</span>}
      </p>
    </section>
  );
}
