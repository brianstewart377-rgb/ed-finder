<script lang="ts">
  import type { AuthState } from '$lib/auth/auth';
  let { authState, signIn, signOut, claimOwner, children } = $props<{
    authState: AuthState;
    signIn: () => void;
    signOut: () => Promise<void>;
    claimOwner: (token: string) => Promise<void>;
    children: import('svelte').Snippet;
  }>();
  let token = $state('');
  let claiming = $state(false);
  let claimError = $state<string | null>(null);
  async function claim() {
    claiming = true;
    claimError = null;
    try {
      await claimOwner(token);
      token = '';
    } catch (error) {
      claimError = error instanceof Error ? error.message : String(error);
    } finally {
      claiming = false;
    }
  }
</script>

{#if authState.loading}
  <section class="panel gate" data-testid="owner-access-loading">
    <p aria-live="polite">Checking owner access…</p>
  </section>
{:else if !authState.authenticated}
  <section class="panel gate" data-testid="owner-sign-in-required">
    <h1>Owner sign-in required</h1>
    <p>
      Operational dashboards and health information are private. Sign in with
      the Frontier account linked to ED-Finder.
    </p>
    <button type="button" onclick={signIn}>Sign in with Frontier</button>
  </section>
{:else if !authState.user?.is_owner}
  <section class="panel gate" data-testid="owner-access-denied">
    <h1>Owner access only</h1>
    <p>
      This Frontier account is signed in, but it is not linked as ED-Finder’s
      owner.
    </p>
    {#if authState.ownerClaimAvailable}
      <form
        onsubmit={(event) => {
          event.preventDefault();
          void claim();
        }}
      >
        <label for="owner-token">Existing ED-Finder admin token</label>
        <input
          id="owner-token"
          type="password"
          bind:value={token}
          autocomplete="off"
          data-testid="owner-claim-token"
        />
        <button
          type="submit"
          disabled={!token.trim() || claiming}
          data-testid="owner-claim-submit"
          >{claiming ? 'Linking…' : 'Link owner account'}</button
        >
      </form>
      {#if claimError}<p role="alert">{claimError}</p>{/if}
    {/if}
    <button type="button" onclick={() => void signOut()}>Sign out</button>
  </section>
{:else}
  {@render children()}
{/if}
