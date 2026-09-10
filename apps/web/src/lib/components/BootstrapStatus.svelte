<script lang="ts">
  import { createQuery } from '@tanstack/svelte-query';
  import { getHealth } from '$lib/api/client';
  import { auth } from '$lib/auth/auth';

  const health = createQuery(() => ({
    queryKey: ['bootstrap', 'health'],
    queryFn: ({ signal }) => getHealth(signal),
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
        {#if $auth.loading}Checking…{:else if $auth.error}Unavailable{:else if $auth.authenticated}{$auth
            .user?.commander_name ?? 'Signed in'}{:else}Guest{/if}
      </dd>
    </div>
  </dl>
</section>
