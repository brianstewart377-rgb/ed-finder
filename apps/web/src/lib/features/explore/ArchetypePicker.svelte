<script lang="ts">
  import {
    ANY_ARCHETYPE,
    ANY_ARCHETYPE_DESCRIPTION,
    ANY_ARCHETYPE_LABEL,
    ARCHETYPES,
    DEFAULT_MINIMUM_TIER,
    isSelectedMinimumTier,
    type ArchetypeKey,
    type SelectedMinimumTier,
  } from './archetypes';

  let {
    archetype,
    minimumTier,
    onArchetypeChange,
    onMinimumTierChange,
    disabled = false,
  }: {
    archetype: typeof ANY_ARCHETYPE | ArchetypeKey;
    minimumTier: SelectedMinimumTier | null;
    onArchetypeChange: (archetype: typeof ANY_ARCHETYPE | ArchetypeKey) => void;
    onMinimumTierChange: (tier: SelectedMinimumTier) => void;
    disabled?: boolean;
  } = $props();

  const id = $props.id();
  const choices = [
    {
      key: ANY_ARCHETYPE,
      label: ANY_ARCHETYPE_LABEL,
      description: ANY_ARCHETYPE_DESCRIPTION,
    },
    ...ARCHETYPES,
  ];
</script>

<div class="archetype-controls">
  <fieldset {disabled}>
    <legend>Colony archetype</legend>
    <div class="archetype-choices">
      {#each choices as choice (choice.key)}
        <div class="archetype-choice">
          <input
            id={`${id}-${choice.key}`}
            name={`${id}-archetype`}
            type="radio"
            value={choice.key}
            checked={archetype === choice.key}
            aria-describedby={`${id}-${choice.key}-description`}
            onchange={() => onArchetypeChange(choice.key)}
          />
          <label for={`${id}-${choice.key}`}>{choice.label}</label>
          <p id={`${id}-${choice.key}-description`}>{choice.description}</p>
        </div>
      {/each}
    </div>
  </fieldset>
  {#if archetype !== ANY_ARCHETYPE}
    <label class="minimum-tier" for={`${id}-minimum-tier`}>
      Minimum tier
      <select
        id={`${id}-minimum-tier`}
        {disabled}
        value={minimumTier ?? DEFAULT_MINIMUM_TIER}
        onchange={(event) => {
          const value = event.currentTarget.value;
          if (isSelectedMinimumTier(value)) onMinimumTierChange(value);
        }}
      >
        <option value="B">Tier B</option>
        <option value="A">Tier A</option>
        <option value="S">Tier S</option>
      </select>
    </label>
  {/if}
  <!-- Reserved for the later weight pop-out; no unavailable control is shown. -->
  <div class="ranking-tools"></div>
</div>

<style>
  .archetype-controls {
    display: grid;
    gap: 1rem;
    margin-block: 1.5rem;
  }
  fieldset {
    min-width: 0;
    margin: 0;
    padding: 1rem;
    border: 1px solid var(--line);
    border-radius: 0.75rem;
    background: var(--color-panel);
  }
  legend {
    padding-inline: 0.4rem;
    font-weight: 650;
  }
  .archetype-choices {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr));
    gap: 0.75rem;
  }
  .archetype-choice {
    display: grid;
    grid-template-columns: auto 1fr;
    align-content: start;
    gap: 0.4rem 0.65rem;
    padding: 0.7rem;
    border: 1px solid var(--line);
    border-radius: 0.5rem;
  }
  .archetype-choice:has(input:checked) {
    border-color: var(--color-cyan);
    background: var(--panel-raised);
  }
  input {
    accent-color: var(--color-cyan);
  }
  label,
  input {
    cursor: pointer;
  }
  .archetype-choice p {
    grid-column: 2;
    margin: 0;
    color: var(--muted);
    font-size: 0.8rem;
    line-height: 1.45;
  }
  .minimum-tier {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.75rem;
  }
  select {
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--line);
    border-radius: 0.4rem;
    background: var(--panel-raised);
    color: inherit;
    font: inherit;
  }
  .ranking-tools {
    justify-self: end;
    align-self: start;
  }
  .ranking-tools:empty {
    display: none;
  }
  @media (min-width: 48rem) {
    .archetype-controls:has(.ranking-tools:not(:empty)) {
      grid-template-columns: minmax(0, 1fr) auto;
    }
    .ranking-tools {
      grid-column: 2;
      grid-row: 1;
    }
  }
</style>
