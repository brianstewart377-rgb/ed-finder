<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import type { Id64 } from '$lib/domain/id64';
  let { id64 } = $props<{ id64: Id64 }>();
  let dialog: HTMLDivElement;
  let returnFocus: HTMLElement | null = null;

  function close() {
    const url = new URL(page.url);
    url.searchParams.delete('system');
    // eslint-disable-next-line svelte/no-navigation-without-resolve -- current URL is already resolved
    void goto(`${url.pathname}${url.search}${url.hash}`, {
      replaceState: true,
      noScroll: true,
    }).then(() => returnFocus?.focus());
  }
  function keydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  }
  $effect(() => {
    returnFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    queueMicrotask(() => dialog?.focus());
    return () => {
      document.body.style.overflow = previous;
    };
  });
</script>

<svelte:window onkeydown={keydown} />
<div
  class="overlay"
  role="presentation"
  onclick={(event) => {
    if (event.target === event.currentTarget) close();
  }}
>
  <div
    class="dialog panel"
    role="dialog"
    aria-modal="true"
    aria-labelledby="system-detail-title"
    tabindex="-1"
    bind:this={dialog}
    data-testid="system-detail-modal"
  >
    <button
      class="dialog-close"
      type="button"
      onclick={close}
      aria-label="Close system detail">×</button
    >
    <p class="eyebrow">Inspect</p>
    <h1 id="system-detail-title">System Detail</h1>
    <p>System <code>{id64}</code></p>
    <p>
      This feature body has not been ported yet. The route, identifier, and
      overlay lifecycle are active platform contracts.
    </p>
  </div>
</div>
