<script lang="ts">
  import { createQuery, useQueryClient } from '@tanstack/svelte-query';
  import {
    ApiError,
    getSystemRatingExplanation,
    getSystemRatings,
    type EconomyRatingExplanation,
    type SystemDetailBody,
  } from '$lib/api/client';
  import { queryKeys } from '$lib/api/query';
  import type { Id64 } from '$lib/domain/id64';
  import RatingExplanation from './RatingExplanation.svelte';
  import {
    byPotential,
    percent,
    ratingEconomyLabel,
  } from './system-detail-format';

  let { id64, bodies, headingId } = $props<{
    id64: Id64;
    bodies: readonly SystemDetailBody[];
    headingId: string;
  }>();

  const queryClient = useQueryClient();

  /** The economy whose explanation is open; one at a time. */
  let open = $state<string | null>(null);

  // 404: not in the published ratings generation. 422: an id64 beyond the
  // signed 64-bit key space, which therefore cannot be rated.
  const isAbsent = (error: unknown): boolean =>
    error instanceof ApiError && (error.status === 404 || error.status === 422);

  const ratings = createQuery(() => ({
    queryKey: queryKeys.systemRatings(id64),
    queryFn: ({ signal }) => getSystemRatings(id64, signal),
    retry: (failureCount, error) => !isAbsent(error) && failureCount < 1,
  }));
  const identity = $derived(ratings.data?.identity ?? null);
  // Lazy: nothing is fetched until a "Why?" is opened, and the key carries the
  // identity of the ratings on screen so a republish never reuses it.
  const explanation = createQuery(() => ({
    queryKey: queryKeys.systemRatingExplanation(id64, identity),
    queryFn: ({ signal }) => {
      if (!identity)
        throw new Error('Ratings must load before their explanation');
      return getSystemRatingExplanation(id64, identity, signal);
    },
    enabled: open !== null && identity !== null,
    retry: (failureCount, error) => !isAbsent(error) && failureCount < 1,
  }));

  const ordered = $derived(
    ratings.data ? byPotential(ratings.data.ratings) : [],
  );
  const bodyNames = $derived(
    new Map(bodies.map((body) => [body.bodyKey, body.name])),
  );
  const explained = $derived.by((): EconomyRatingExplanation | null => {
    const data = explanation.data;
    if (open === null || data?.kind !== 'explained') return null;
    return data.economies.find((economy) => economy.economy === open) ?? null;
  });

  function toggle(economy: string): void {
    open = open === economy ? null : economy;
  }

  /**
   * After a republish, reload the ratings and the open explanation together.
   * The explanation key is under the ratings key, so one prefix covers both,
   * even when the reloaded ratings come back with the same identity.
   */
  function reloadRatings(): void {
    void queryClient.invalidateQueries({
      queryKey: queryKeys.systemRatings(id64),
    });
  }

  const regionId = (economy: string) => `${headingId}-rating-${economy}`;
</script>

<section
  class="system-ratings"
  aria-labelledby={`${headingId}-ratings`}
  aria-busy={ratings.isPending}
>
  <p class="eyebrow">Ratings V4</p>
  <h2 id={`${headingId}-ratings`}>Economy potential</h2>
  {#if ratings.isPending}
    <p class="state-copy" role="status">Loading economy ratings…</p>
  {:else if ratings.isError}
    {#if isAbsent(ratings.error)}
      <p class="state-copy">
        This system is not in the published ratings yet.
      </p>
    {:else}
      <div class="system-ratings-error" role="alert">
        <p class="state-copy">Economy ratings could not be loaded.</p>
        <button
          class="secondary-button"
          type="button"
          onclick={() => ratings.refetch()}
        >
          Try again
        </button>
      </div>
    {/if}
  {:else if ratings.data}
    <p class="system-ratings-note">
      Seven independent potentials, each 0–100. Confidence shows how much of a
      rating's evidence the catalogue knows; it is not a measured probability.
    </p>
    <div class="rating-table-scroll">
      <table class="rating-table" aria-labelledby={`${headingId}-ratings`}>
        <thead>
          <tr>
            <th scope="col">Economy</th>
            <th scope="col">Potential</th>
            <th scope="col">Confidence</th>
            <th scope="col">
              <span class="rating-column-label">Explanation</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {#each ordered as rating (rating.economy)}
            {@const label = ratingEconomyLabel(rating.economy)}
            <tr data-rating-economy={rating.economy}>
              <th scope="row">{label}</th>
              <td>
                <div class="rating-potential">
                  <div class="rating-meter" aria-hidden="true">
                    <div style:width={`${rating.potential}%`}></div>
                  </div>
                  <div>{rating.potential}</div>
                </div>
              </td>
              <td>{percent(rating.confidence)}</td>
              <td>
                <button
                  type="button"
                  class="rating-why"
                  aria-label={`Why? ${label}`}
                  aria-expanded={open === rating.economy}
                  aria-controls={regionId(rating.economy)}
                  onclick={() => toggle(rating.economy)}
                >
                  Why?
                </button>
              </td>
            </tr>
            <tr class="rating-explanation-row" hidden={open !== rating.economy}>
              <td colspan={4}>
                <div
                  id={regionId(rating.economy)}
                  class="rating-explanation"
                  role="region"
                  aria-label={`Why ${label} scores ${rating.potential}`}
                >
                  {#if open !== rating.economy}
                    <!-- Collapsed: nothing is fetched or rendered. -->
                  {:else if explanation.isPending}
                    <p role="status">Loading the explanation…</p>
                  {:else if explanation.isError}
                    <p role="alert">The explanation could not be loaded.</p>
                    <button
                      class="quiet-button"
                      type="button"
                      onclick={() => explanation.refetch()}
                    >
                      Try again
                    </button>
                  {:else if explanation.data?.kind === 'republished'}
                    <p role="alert">
                      The ratings were republished while this page was open.
                    </p>
                    <button
                      class="quiet-button"
                      type="button"
                      onclick={reloadRatings}
                    >
                      Reload ratings
                    </button>
                  {:else if explained && explanation.data}
                    <RatingExplanation
                      {explained}
                      identity={explanation.data.identity}
                      {bodyNames}
                    />
                  {/if}
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>
