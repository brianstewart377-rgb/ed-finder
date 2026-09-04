<script lang="ts">
  import { authState } from '$lib/stores/auth.svelte';
</script>

{#if authState.loading}<span>Account…</span>
{:else if !authState.session.authenticated}<button
    data-testid="frontier-sign-in"
    onclick={() => authState.signIn()}>Sign in</button
  >
{:else}<div class="account">
    <span data-testid="frontier-account-name"
      >{authState.session.user?.commander_name
        ? `CMDR ${authState.session.user.commander_name}`
        : 'Frontier account'}</span
    >{#if authState.session.user?.is_owner}<a
        href="/admin"
        data-testid="owner-open-ops">Ops</a
      >{/if}<button
      data-testid="frontier-sign-out"
      onclick={() => authState.signOut()}>Sign out</button
    >
  </div>{/if}
