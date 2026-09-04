<script lang="ts">
  import { adminToken } from '$lib/persistence/stores';

  let draft = $state('');
  let message = $state<string | null>(null);
  let error = $state<string | null>(null);

  function save() {
    const token = draft.trim();
    message = null;
    error = null;
    if (!token) {
      error = 'Enter an admin token before saving it for this browser session.';
      return;
    }
    if (!adminToken.set(token)) {
      error = 'The session token could not be stored in this browser.';
      return;
    }
    draft = '';
    message = 'Session admin token saved.';
  }

  function clear() {
    message = null;
    error = null;
    if (!adminToken.clear()) {
      error = 'The session token could not be cleared in this browser.';
      return;
    }
    draft = '';
    message = 'Session admin token cleared.';
  }
</script>

<section class="panel" aria-labelledby="session-admin-token-heading">
  <p class="eyebrow">Compatibility credential</p>
  <h2 id="session-admin-token-heading">Session admin token</h2>
  <p>
    Use this only for bounded API operations that still accept
    <code>X-Admin-Token</code>. It is stored in session storage, is not included
    in profile sync, and is cleared when the browser session ends.
  </p>
  <p aria-live="polite" data-testid="session-admin-token-status">
    {$adminToken.value ? 'A session token is configured.' : 'No session token is configured.'}
  </p>
  <form
    onsubmit={(event) => {
      event.preventDefault();
      save();
    }}
  >
    <label for="session-admin-token">Admin token for this session</label>
    <input
      id="session-admin-token"
      type="password"
      bind:value={draft}
      autocomplete="off"
      data-testid="session-admin-token-input"
    />
    <button
      type="submit"
      disabled={!draft.trim()}
      data-testid="session-admin-token-save">Save for this session</button
    >
    <button
      type="button"
      disabled={!$adminToken.value}
      onclick={clear}
      data-testid="session-admin-token-clear">Clear session token</button
    >
  </form>
  {#if message}<p role="status">{message}</p>{/if}
  {#if error}<p role="alert">{error}</p>{/if}
</section>
