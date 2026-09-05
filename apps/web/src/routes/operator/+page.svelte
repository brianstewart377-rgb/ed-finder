<script lang="ts">
  import { auth } from '$lib/auth/auth';
  import OwnerAccessGate from '$lib/components/OwnerAccessGate.svelte';
</script>

<main class="placeholder">
  <OwnerAccessGate
    authState={$auth}
    signIn={auth.signIn}
    signOut={auth.signOut}
    claimOwner={auth.claimOwner}
    ><section data-testid="operator-tab">
      <p class="eyebrow">Separate owner mode</p>
      <h1>Operator</h1>
      <p>Operator features have not been ported yet.</p>
    </section></OwnerAccessGate
  >
</main>
