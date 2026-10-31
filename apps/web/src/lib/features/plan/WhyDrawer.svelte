<script lang="ts">
  import type { PlanEvaluationV1, PlanFacilityV1, PlanStepV1 } from '$lib/api';

  type Props = {
    step: PlanStepV1;
    index: number;
    name: string;
    evaluation: PlanEvaluationV1;
    facilities: PlanFacilityV1[];
    onclose: () => void;
    oninsert: (facilityId: string) => void;
    canInsert?: boolean;
    stale?: boolean;
  };
  let {
    step,
    index,
    name,
    evaluation,
    facilities,
    onclose,
    oninsert,
    canInsert = true,
    stale = false,
  }: Props = $props();

  const id = $props.id();
  let dialog: HTMLDivElement;
  let returnFocus: HTMLElement | null = null;
  const labels: Record<PlanStepV1['result'], string> = {
    OK: '✓ OK',
    BLOCKED: '✕ Blocked',
    NEEDS_INFO: '? Needs info',
    COUNTED: '● Counted',
    IGNORED: '– Ignored',
  };
  const focusableSelector =
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  const reasonLabels: Record<string, string> = {
    INSUFFICIENT_T2:
      'There are not enough Tier 2 construction points for this step.',
    INSUFFICIENT_T3:
      'There are not enough Tier 3 construction points for this step.',
    PREREQUISITE_MISSING:
      'A required facility must be completed earlier in the build order.',
    NOT_PLACED: 'Choose a body or belt for this build.',
    SLOTS_UNKNOWN: 'Enter the available slot count for this location.',
    NO_FREE_SLOT: 'No slot of the required kind is free at this location.',
    NOT_LANDABLE: 'This surface facility needs a landable body.',
    LANDABLE_UNKNOWN: 'It is not yet known whether this body is landable.',
    NOT_RINGED:
      'This facility needs a location with rings or an asteroid belt.',
    RINGED_UNKNOWN: 'It is not yet known whether this location has rings.',
  };

  function reasonText(reason: string): string {
    if (reasonLabels[reason]) return reasonLabels[reason];
    if (!/^[A-Z][A-Z0-9_]+$/.test(reason)) return reason;
    const words = reason.toLowerCase().replaceAll('_', ' ');
    return `${words[0].toUpperCase()}${words.slice(1)}.`;
  }

  function restoreFocus() {
    const target = returnFocus;
    returnFocus = null;
    if (target?.isConnected) target.focus({ preventScroll: true });
  }

  function close() {
    onclose();
    restoreFocus();
  }

  function keydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }
    if (event.key !== 'Tab') return;
    const controls = Array.from(
      dialog.querySelectorAll<HTMLElement>(focusableSelector),
    ).filter(
      (element) =>
        !element.hasAttribute('hidden') &&
        element.getAttribute('aria-hidden') !== 'true',
    );
    const first = controls[0];
    const last = controls.at(-1);
    const active = document.activeElement;
    if (!first || !last) {
      event.preventDefault();
      dialog.focus();
    } else if (!controls.includes(active as HTMLElement)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    } else if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  $effect(() => {
    returnFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    queueMicrotask(() => dialog?.focus());
    return () => {
      document.body.style.overflow = previousOverflow;
      restoreFocus();
    };
  });
</script>

<svelte:window onkeydown={keydown} />

<div
  class="why-backdrop"
  role="presentation"
  onclick={(event) => {
    if (event.target === event.currentTarget) close();
  }}
>
  <div
    bind:this={dialog}
    class="why-drawer"
    role="dialog"
    aria-modal="true"
    aria-labelledby={`${id}-title`}
    tabindex="-1"
  >
    <header>
      <div>
        <p class="eyebrow">Why this step?</p>
        <h2 id={`${id}-title`}>Step {index + 1}: {name}</h2>
      </div>
      <button type="button" aria-label="Close why panel" onclick={close}
        >Close</button
      >
    </header>
    {#if stale}<p class="muted">
        Last good evaluation — awaiting a valid current result.
      </p>{/if}
    <p class="result" class:stale class:blocked={step.result === 'BLOCKED'}>
      {labels[step.result]}
    </p>
    {#if step.reasons.length > 0}
      <ul class="reasons" class:stale aria-label="Reasons">
        {#each step.reasons as reason, reasonIndex (reasonIndex)}
          <li>{reasonText(reason)}</li>
        {/each}
      </ul>
    {/if}
    <table class:stale aria-label="Construction points for this step">
      <thead>
        <tr
          ><th scope="col">Points</th><th scope="col">Tier 2</th><th scope="col"
            >Tier 3</th
          ></tr
        >
      </thead>
      <tbody>
        <tr
          ><th scope="row">Before</th><td>{step.t2_before}</td><td
            >{step.t3_before}</td
          ></tr
        >
        <tr
          ><th scope="row">Cost</th><td>{step.cost_t2}</td><td
            >{step.cost_t3}</td
          ></tr
        >
        <tr
          ><th scope="row">After</th><td>{step.t2_after}</td><td
            >{step.t3_after}</td
          ></tr
        >
        <tr
          ><th scope="row">Earns</th><td>{step.reward_t2}</td><td
            >{step.reward_t3}</td
          ></tr
        >
      </tbody>
    </table>
    {#if step.counted_port_number !== null}
      <p class:stale>Port #{step.counted_port_number}</p>
    {/if}

    {#if step.payers.length > 0}
      <section class:stale aria-labelledby={`${id}-payers`}>
        <h3 id={`${id}-payers`}>Payer suggestions</h3>
        <p class="muted">
          These suggestions come from the evaluation. A new build uses a free
          suitable slot, or stays unplaced until you choose a location.
        </p>
        <ul class="payers">
          {#each step.payers as facilityId (facilityId)}
            {@const facilityName =
              facilities.find((facility) => facility.id === facilityId)?.name ??
              facilityId}
            <li>
              <span>{facilityName}</span>
              <button
                type="button"
                disabled={!canInsert}
                aria-label={`Add ${facilityName} before this step`}
                onclick={() => oninsert(facilityId)}
                >Add before this step</button
              >
            </li>
          {/each}
        </ul>
        {#if !canInsert}
          <p class="muted">
            Adding a payer is unavailable while the evaluation is out of date,
            before the Primary Port, or when the plan has 300 sites.
          </p>
        {/if}
      </section>
    {/if}

    <section class:stale aria-labelledby={`${id}-rules`}>
      <h3 id={`${id}-rules`}>Rules behind this step</h3>
      <p class="muted">Rulebook: {evaluation.rulebook_release}</p>
      {#each step.rule_ids as ruleId (ruleId)}
        {@const rule = evaluation.explanations[ruleId]}
        {#if rule}
          <article class="rule">
            <h4>{rule.id} · {rule.title}</h4>
            <p class="rule-status">Status: {rule.status}</p>
            <p>{rule.statement}</p>
            <blockquote>{rule.quote}</blockquote>
            <p class="muted">
              {rule.page === null ? 'Page not supplied' : `Page ${rule.page}`}
            </p>
          </article>
        {:else}
          <p>{ruleId}: explanation not supplied by the evaluation.</p>
        {/if}
      {/each}
      {#if step.rule_ids.length === 0}
        <p class="muted">No rule explanations were returned for this step.</p>
      {/if}
    </section>
  </div>
</div>

<style>
  .why-backdrop {
    position: fixed;
    z-index: 90;
    inset: 0;
    display: flex;
    justify-content: flex-end;
    background: #0009;
  }
  .why-drawer {
    width: min(34rem, 100%);
    height: 100%;
    overflow-y: auto;
    overflow-wrap: anywhere;
    padding: 1.25rem;
    border-left: 1px solid var(--line);
    background: var(--color-panel);
    box-shadow: -1rem 0 3rem #0005;
    animation: drawer-in 140ms ease-out;
  }
  header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }
  h2 {
    margin: 0.5rem 0;
    font-size: 1.35rem;
    line-height: 1.35;
  }
  h3 {
    margin: 0 0 0.75rem;
    font-size: 1rem;
  }
  h4 {
    margin: 0;
    font-size: 0.95rem;
  }
  p,
  li {
    font-size: 0.87rem;
    line-height: 1.55;
  }
  button {
    flex-shrink: 0;
    min-height: 2.75rem;
    border: 1px solid var(--line);
    border-radius: 0.35rem;
    padding: 0.45rem 0.7rem;
    background: var(--panel-raised);
    color: inherit;
    font: inherit;
    font-size: 0.82rem;
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .result {
    display: inline-block;
    margin: 1rem 0 0;
    padding: 0.35rem 0.6rem;
    border: 1px solid var(--line);
    border-radius: 0.3rem;
    font-weight: 650;
  }
  .blocked {
    border-color: var(--color-signal);
    background: color-mix(in srgb, var(--color-signal) 12%, var(--color-panel));
  }
  .reasons {
    padding-left: 1.25rem;
  }
  .reasons li + li {
    margin-top: 0.45rem;
  }
  table {
    width: 100%;
    margin-top: 1rem;
    border-collapse: collapse;
    font-size: 0.85rem;
  }
  th,
  td {
    padding: 0.6rem;
    text-align: left;
    border-bottom: 1px solid var(--line);
    font-variant-numeric: tabular-nums;
  }
  section {
    margin-top: 1.5rem;
    padding-top: 1rem;
    border-top: 1px solid var(--line);
  }
  .muted,
  .rule-status {
    color: var(--muted);
  }
  .stale {
    opacity: 0.55;
    filter: grayscale(1);
  }
  .payers {
    display: grid;
    gap: 0.65rem;
    padding: 0;
    list-style: none;
  }
  .payers li {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
  }
  .rule {
    margin-top: 1rem;
    padding: 0.85rem;
    border: 1px solid var(--line);
    border-radius: 0.35rem;
    background: var(--panel-raised);
  }
  .rule p:last-child {
    margin-bottom: 0;
  }
  blockquote {
    margin: 0.75rem 0;
    padding-left: 0.75rem;
    border-left: 2px solid var(--color-signal);
    font-size: 0.85rem;
    line-height: 1.55;
  }
  @keyframes drawer-in {
    from {
      transform: translateX(1rem);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .why-drawer {
      animation: none;
    }
  }
</style>
