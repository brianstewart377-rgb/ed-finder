<script lang="ts">
  import { createQuery } from '@tanstack/svelte-query';
  import { getAuthSession, getHealth } from '$lib/api/client';

  const health = createQuery(() => ({
    queryKey: ['bootstrap', 'health'],
    queryFn: ({ signal }) => getHealth(signal),
  }));
  const session = createQuery(() => ({
    queryKey: ['bootstrap', 'session'],
    queryFn: ({ signal }) => getAuthSession(signal),
  }));
</script>

<section class="status-panel" aria-labelledby="connection-title">
  <div>
    <p class="eyebrow">Foundation status</p>
    <h2 id="connection-title">Application connection</h2>
  </div>
  <dl>
    <div>
      <dt>API</dt>
      <dd aria-live="polite">
        {#if health.isPending}Checking…{:else if health.isError}Unavailable{:else}{health
            .data.database === 'connected'
            ? 'Connected'
            : health.data.status}{/if}
      </dd>
    </div>
    <div>
      <dt>Session</dt>
      <dd aria-live="polite">
        {#if session.isPending}Checking…{:else if session.isError}Unavailable{:else if session.data.authenticated}{session
            .data.user?.commander_name ?? 'Signed in'}{:else}Guest{/if}
      </dd>
    </div>
  </dl>
</section>
