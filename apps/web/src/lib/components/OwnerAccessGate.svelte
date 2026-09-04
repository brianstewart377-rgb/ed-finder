<script lang="ts">
  import { authState } from '$lib/stores/auth.svelte';
  let { children } = $props();
  let token = $state('');
  let error = $state('');
  let claiming = $state(false);
  async function claim() {
    claiming = true;
    error = '';
    try {
      await authState.claim(token.trim());
      token = '';
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      claiming = false;
    }
  }
</script>

{#if authState.loading}<section
    class="panel"
    data-testid="owner-access-loading"
  >
    Checking owner access…
  </section>
{:else if !authState.session.authenticated}<section
    class="panel"
    data-testid="owner-sign-in-required"
  >
    <h2>Owner sign-in required</h2>
    <p>Operational dashboards and health information are private.</p>
    <button onclick={() => authState.signIn()}>Sign in with Frontier</button>
  </section>
{:else if !authState.session.user?.is_owner}<section
    class="panel"
    data-testid="owner-access-denied"
  >
    <h2>Owner access only</h2>
    <p>This Frontier account is not linked as ED-Finder’s owner.</p>
    {#if authState.session.owner_claim_available}<label
        >Existing admin token<input
          type="password"
          bind:value={token}
          data-testid="owner-claim-token"
          autocomplete="off"
        /></label
      ><button
        disabled={!token.trim() || claiming}
        data-testid="owner-claim-submit"
        onclick={claim}>{claiming ? 'Linking…' : 'Link owner account'}</button
      >{/if}{#if error}<p role="alert">{error}</p>{/if}
  </section>
{:else}{@render children()}{/if}
