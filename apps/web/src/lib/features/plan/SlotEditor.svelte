<script lang="ts">
  import { tick } from 'svelte';

  type Props = {
    label: string;
    kind: 'orbital' | 'surface';
    used: number;
    value: number | null;
    disabled?: boolean;
    onchange: (value: number | null) => void;
  };
  let {
    label,
    kind,
    used,
    value,
    disabled = false,
    onchange,
  }: Props = $props();

  const id = $props.id();
  let open = $state(false);
  let draft = $state<number | null>(null);
  let editorLeft = $state(0);
  let editorTop = $state(0);
  let trigger: HTMLButtonElement;
  let editor = $state<HTMLDivElement>();
  let container: HTMLDivElement;
  const overCapacity = $derived(value !== null && used > value);
  const slotLabel = $derived(kind === 'orbital' ? 'Orbital' : 'Surface');

  async function toggle() {
    if (disabled) return;
    if (open) {
      close();
      return;
    }
    draft = value;
    open = true;
    await tick();
    if (!editor) return;
    const anchor = trigger.getBoundingClientRect();
    const bounds = editor.getBoundingClientRect();
    editorLeft = Math.max(
      8,
      Math.min(
        anchor.right - bounds.width,
        window.innerWidth - bounds.width - 8,
      ),
    );
    editorTop = Math.max(
      8,
      Math.min(anchor.bottom + 6, window.innerHeight - bounds.height - 8),
    );
    editor?.focus();
  }

  function close() {
    open = false;
    trigger?.focus({ preventScroll: true });
  }

  function change(next: number | null) {
    draft = next === null ? null : Math.min(64, Math.max(0, next));
    onchange(draft);
  }

  function keydown(event: KeyboardEvent) {
    if (!open || !editor) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }
    if (event.key !== 'Tab') return;
    const controls = Array.from(
      editor.querySelectorAll<HTMLButtonElement>('button:not([disabled])'),
    );
    const first = controls[0];
    const last = controls.at(-1);
    const active = document.activeElement;
    if (active === editor || !editor.contains(active)) {
      event.preventDefault();
      (event.shiftKey ? last : first)?.focus();
    } else if (event.shiftKey && active === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first?.focus();
    }
  }

  function pointerdown(event: PointerEvent) {
    if (
      open &&
      event.target instanceof Node &&
      !container.contains(event.target)
    ) {
      // Pointer users retain focus on the control they clicked outside.
      open = false;
    }
  }
</script>

<svelte:window onkeydown={keydown} onpointerdown={pointerdown} />

<div class="slot-container" bind:this={container}>
  <button
    bind:this={trigger}
    type="button"
    class="slot-box"
    class:over-capacity={overCapacity && !disabled}
    {disabled}
    aria-label={disabled
      ? `${slotLabel} slots on ${label}: not available`
      : `${slotLabel} slots on ${label}: ${used} used, ${value ?? 'unknown'} total${overCapacity ? ', over capacity' : ''}`}
    aria-haspopup="dialog"
    aria-expanded={open}
    aria-controls={open ? `${id}-editor` : undefined}
    onclick={toggle}
  >
    <span>{slotLabel}</span>
    <strong>{disabled ? '–' : `${used}/${value ?? '?'}`}</strong>
    {#if overCapacity && !disabled}<span class="warning">Over capacity</span
      >{/if}
  </button>
  {#if open}
    <div
      bind:this={editor}
      class="slot-editor"
      style:left={`${editorLeft}px`}
      style:top={`${editorTop}px`}
      id={`${id}-editor`}
      role="dialog"
      tabindex="-1"
      aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-help`}
    >
      <h4 id={`${id}-title`}>{slotLabel} slots on {label}</h4>
      <p id={`${id}-help`}>
        This value is entered by the commander.
        {#if kind === 'orbital'}Copy orbital slots from Architect Mode.{/if}
        Enter 0–64, or leave it unknown.
      </p>
      <div class="stepper">
        <button
          type="button"
          aria-label={`Decrease ${kind} slots`}
          disabled={draft === 0}
          onclick={() => change((draft ?? 1) - 1)}>−</button
        >
        <output aria-live="polite" aria-label={`${slotLabel} slot total`}
          >{draft ?? 'Unknown'}</output
        >
        <button
          type="button"
          aria-label={`Increase ${kind} slots`}
          disabled={draft === 64}
          onclick={() => change((draft ?? 0) + 1)}>+</button
        >
      </div>
      <div class="editor-actions">
        <button type="button" onclick={() => change(null)}>Unknown</button>
        <button type="button" onclick={close}>Done</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .slot-container {
    position: relative;
  }
  button {
    border: 1px solid var(--line);
    border-radius: 0.35rem;
    background: var(--panel-raised);
    color: inherit;
    cursor: pointer;
    font: inherit;
  }
  button:disabled {
    cursor: default;
    opacity: 0.6;
  }
  .slot-box {
    display: grid;
    gap: 0.15rem;
    min-width: 4.3rem;
    min-height: 2.75rem;
    padding: 0.3rem 0.45rem;
    text-align: center;
    font-size: 0.72rem;
  }
  .slot-box strong {
    font-size: 0.85rem;
    font-variant-numeric: tabular-nums;
  }
  .over-capacity {
    border-color: var(--color-signal);
    border-width: 2px;
    background: color-mix(in srgb, var(--color-signal) 12%, var(--color-panel));
  }
  .warning {
    font-size: 0.65rem;
    font-weight: 650;
  }
  .slot-editor {
    position: fixed;
    z-index: 20;
    width: min(17rem, calc(100vw - 3rem));
    max-height: calc(100dvh - 1rem);
    overflow-y: auto;
    border: 1px solid var(--line);
    border-radius: 0.6rem;
    padding: 0.9rem;
    background: var(--color-panel);
    box-shadow: 0 0.6rem 2rem #0006;
  }
  h4 {
    margin: 0;
    font-size: 0.9rem;
  }
  p {
    font-size: 0.8rem;
    line-height: 1.5;
    color: var(--muted);
  }
  .stepper,
  .editor-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .stepper button {
    min-width: 2.75rem;
    min-height: 2.75rem;
    font-size: 1.15rem;
  }
  .stepper output {
    font-variant-numeric: tabular-nums;
  }
  .editor-actions {
    margin-top: 0.75rem;
  }
  .editor-actions button {
    min-height: 2.75rem;
    padding: 0.4rem 0.65rem;
    font-size: 0.85rem;
  }
</style>
