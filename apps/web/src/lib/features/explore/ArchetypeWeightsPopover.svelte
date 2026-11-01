<script lang="ts">
  import { tick } from 'svelte';
  import { ARCHETYPE_KEYS, archetypeLabel } from './archetypes';
  import { DEFAULT_ARCHETYPE_WEIGHTS, normalizeWeights } from './ranking-state';

  let {
    weights = {},
    profiles = [],
    profilesLoading = false,
    profilesError = false,
    onapply,
    onopen,
  }: {
    weights?: Readonly<Record<string, number>>;
    profiles?: readonly {
      id: string;
      label: string;
      description: string;
      weights: Readonly<Record<string, number>>;
    }[];
    profilesLoading?: boolean;
    profilesError?: boolean;
    onapply: (weights: Readonly<Record<string, number>>) => void;
    onopen?: () => void;
  } = $props();

  const id = $props.id();
  let open = $state(false);
  let draft = $state<Record<string, number>>({ ...DEFAULT_ARCHETYPE_WEIGHTS });
  let trigger: HTMLButtonElement;
  let container: HTMLDivElement;
  let panel = $state<HTMLDivElement>();
  let left = $state(0);
  let top = $state(0);
  const hasWeights = $derived(
    Object.keys(normalizeWeights(weights)).length > 0,
  );
  const validDraft = $derived(normalizeWeights(draft));
  const canApply = $derived(Object.keys(validDraft).length > 0);

  // Presets arrive after opening and can make the panel taller. Keep its
  // desktop placement inside the viewport as the content changes.
  $effect(() => {
    if (!open || !panel || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(position);
    observer.observe(panel);
    return () => observer.disconnect();
  });

  function position() {
    if (!open || !panel) return;
    const anchor = trigger.getBoundingClientRect();
    const bounds = panel.getBoundingClientRect();
    left = Math.max(
      8,
      Math.min(
        anchor.right - bounds.width,
        window.innerWidth - bounds.width - 8,
      ),
    );
    top = Math.max(
      8,
      Math.min(anchor.bottom + 8, window.innerHeight - bounds.height - 8),
    );
  }

  async function toggle() {
    if (open) {
      close();
      return;
    }
    draft = { ...(hasWeights ? weights : DEFAULT_ARCHETYPE_WEIGHTS) };
    open = true;
    onopen?.();
    await tick();
    position();
    panel?.focus({ preventScroll: true });
  }

  function close() {
    open = false;
    trigger?.focus({ preventScroll: true });
  }

  function keydown(event: KeyboardEvent) {
    if (open && event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  }

  function outsideClick(event: MouseEvent) {
    if (
      open &&
      event.target instanceof Node &&
      !container.contains(event.target)
    )
      close();
  }

  function apply() {
    if (!canApply) return;
    onapply(validDraft);
    close();
  }
</script>

<svelte:window onkeydown={keydown} onclick={outsideClick} onresize={position} />

<div class="weights-control" bind:this={container}>
  <button
    bind:this={trigger}
    type="button"
    class="weights-trigger"
    class:custom={hasWeights}
    aria-haspopup="dialog"
    aria-expanded={open}
    aria-controls={open ? `${id}-dialog` : undefined}
    onclick={toggle}>{hasWeights ? 'Custom weights' : 'Weights'}</button
  >

  {#if open}
    <div
      bind:this={panel}
      class="weights-popover"
      style:--popover-left={`${left}px`}
      style:--popover-top={`${top}px`}
      id={`${id}-dialog`}
      data-testid="archetype-weights-dialog"
      role="dialog"
      aria-modal="false"
      aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-help`}
      tabindex="-1"
    >
      <div class="popover-heading">
        <h3 id={`${id}-title`}>Custom archetype weights</h3>
        <button type="button" aria-label="Close weights" onclick={close}
          >Close</button
        >
      </div>
      <p id={`${id}-help`}>
        Blend the archetypes to reorder this page. Higher weights give an
        archetype more influence. Changes take effect when you apply them and
        are saved only in this link.
      </p>

      <fieldset class="presets">
        <legend>Presets</legend>
        {#if profilesLoading}<p role="status">Loading presets…</p>{/if}
        {#if profilesError}<p role="status">
            Presets are unavailable. You can still adjust the sliders.
          </p>{/if}
        <div class="preset-buttons">
          {#each profiles as profile (profile.id)}
            <button
              type="button"
              title={profile.description}
              onclick={() => {
                draft = { ...profile.weights };
              }}>{profile.label}</button
            >
          {/each}
        </div>
      </fieldset>

      <div class="sliders">
        {#each ARCHETYPE_KEYS as key (key)}
          <div class="weight-slider">
            <label for={`${id}-${key}`}>{archetypeLabel(key)}</label>
            <output for={`${id}-${key}`}>{draft[key]}%</output>
            <input
              id={`${id}-${key}`}
              type="range"
              min="0"
              max="100"
              step="5"
              value={draft[key]}
              aria-valuetext={`${draft[key]}%`}
              oninput={(event) => {
                draft = { ...draft, [key]: Number(event.currentTarget.value) };
              }}
            />
          </div>
        {/each}
      </div>

      {#if !canApply}
        <p class="weight-notice" id={`${id}-invalid`} role="status">
          Set at least one weight above 0% to apply.
        </p>
      {/if}
      <div class="popover-actions">
        <button
          type="button"
          onclick={() => {
            draft = { ...DEFAULT_ARCHETYPE_WEIGHTS };
          }}>Reset to default</button
        >
        <button type="button" onclick={close}>Cancel</button>
        <button
          type="button"
          class="apply"
          disabled={!canApply}
          aria-describedby={!canApply ? `${id}-invalid` : undefined}
          onclick={apply}>Apply</button
        >
      </div>
    </div>
  {/if}
</div>

<style>
  .weights-control {
    position: relative;
  }
  button {
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--line);
    border-radius: 0.5rem;
    background: var(--panel-raised);
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  .custom,
  .apply {
    border-color: var(--color-cyan);
  }
  .weights-popover {
    position: fixed;
    z-index: 50;
    left: var(--popover-left);
    top: var(--popover-top);
    width: min(28rem, calc(100vw - 2rem));
    max-height: calc(100dvh - 2rem);
    overflow-y: auto;
    box-sizing: border-box;
    padding: 1rem;
    border: 1px solid var(--line);
    border-radius: 0.75rem;
    background: var(--color-panel);
    box-shadow: 0 1rem 3rem rgb(0 0 0 / 35%);
  }
  .popover-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }
  h3 {
    margin: 0;
    font-size: 1.1rem;
  }
  p {
    color: var(--muted);
    font-size: 0.85rem;
    line-height: 1.5;
  }
  fieldset {
    border: 0;
    margin: 0 0 1rem;
    padding: 0;
    min-width: 0;
  }
  legend {
    margin-bottom: 0.5rem;
    font-weight: 600;
  }
  .preset-buttons,
  .popover-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .preset-buttons button {
    font-size: 0.8rem;
  }
  .sliders {
    display: grid;
    gap: 0.8rem;
  }
  .weight-slider {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 0.25rem 0.5rem;
  }
  .weight-slider label {
    font-size: 0.9rem;
  }
  output {
    font-variant-numeric: tabular-nums;
  }
  input {
    grid-column: 1 / -1;
    width: 100%;
    margin: 0;
    accent-color: var(--color-cyan);
  }
  .popover-actions {
    justify-content: flex-end;
    margin-top: 1rem;
  }
  @media (max-width: 639px) {
    .weights-popover {
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
    }
  }
</style>
