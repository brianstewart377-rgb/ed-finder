<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import { auth } from '$lib/auth/auth';
  import {
    getVerifiedCommanders,
    importVerifiedJournals,
    offerGalaxyFacts,
    getGalaxyContributions,
    withdrawGalaxyContribution,
    type VerifiedCommanderResponse,
    type V3VerifiedImportReceipt,
    type ContributionRow,
  } from '$lib/api/client';
  import { parseJournals } from '$lib/journal/parse';

  let commanders = $state<VerifiedCommanderResponse[]>([]);
  let selected = $state<FileList | undefined>();
  let sharing = $state(false);
  let busy = $state(false);
  let status = $state('Checking linked commanders…');
  let error = $state('');
  let receipt = $state<V3VerifiedImportReceipt | null>(null);
  let warnings = $state<Array<{ name: string; reason: string }>>([]);
  let contributions = $state<ContributionRow[]>([]);
  let page = $state(0);
  let sharingPending = $state<Array<{ id: string; hashes: string[] }>>([]);
  const lifetime = new AbortController();
  let operation = $state<AbortController | null>(null);
  let refreshGeneration = 0;

  async function refresh() {
    const generation = ++refreshGeneration;
    error = '';
    try {
      const [linked, rows] = await Promise.allSettled([
        getVerifiedCommanders(lifetime.signal),
        getGalaxyContributions(page * 50, lifetime.signal),
      ]);
      if (lifetime.signal.aborted || generation !== refreshGeneration) return;
      if (linked.status === 'fulfilled') commanders = linked.value;
      if (rows.status === 'fulfilled') contributions = rows.value;
      if (linked.status === 'rejected' || rows.status === 'rejected')
        error = 'Some account data could not be loaded. Retry to refresh it.';
      status = commanders.length
        ? 'Ready to import your journals'
        : 'Sign in again to verify your commander with Frontier';
    } catch (cause) {
      if (!lifetime.signal.aborted && generation === refreshGeneration)
        error =
          cause instanceof Error
            ? cause.message
            : 'Could not load journal account';
    }
  }

  async function shareSavedImports() {
    if (!sharingPending.length) return;
    busy = true;
    error = '';
    operation ??= new AbortController();
    try {
      let offered = 0;
      for (const pending of [...sharingPending]) {
        const result = await offerGalaxyFacts(
          pending.id,
          pending.hashes,
          operation.signal,
        );
        if (lifetime.signal.aborted) return;
        offered += result.new_offers;
        sharingPending = sharingPending.filter(
          (item) => item.id !== pending.id,
        );
        for (const [reason, count] of Object.entries(result.skipped)) {
          if (count)
            warnings = [
              ...warnings,
              {
                name: 'Galaxy sharing',
                reason: `${count} records excluded: ${reason.replaceAll('_', ' ')}`,
              },
            ];
        }
      }
      await refresh();
      if (!lifetime.signal.aborted)
        status = `Journal saved. ${offered} new galaxy observations offered for review`;
    } catch (cause) {
      if (!lifetime.signal.aborted)
        error = `Your Journal is saved. Sharing needs a retry: ${cause instanceof Error ? cause.message : 'request failed'}`;
    } finally {
      if (!lifetime.signal.aborted) busy = false;
      operation = null;
    }
  }

  async function upload() {
    if (busy || !selected?.length) return;
    busy = true;
    error = '';
    receipt = null;
    warnings = [];
    const contributeThisImport = sharing;
    operation = new AbortController();
    try {
      status = 'Reading selected files…';
      const parsed = await parseJournals(
        Array.from(selected),
        operation.signal,
        (count) => {
          if (!lifetime.signal.aborted) status = `Read ${count} files`;
        },
      );
      if (lifetime.signal.aborted) return;
      warnings = parsed.held;
      if (!parsed.body.files.length) {
        status = 'No files ready to import';
        return;
      }
      status = 'Saving journal events…';
      const saved = await importVerifiedJournals(parsed.body, operation.signal);
      if (lifetime.signal.aborted) return;
      receipt = saved;
      status = 'Import finished';
      if (contributeThisImport) {
        const pending = new SvelteMap(
          sharingPending.map((item) => [item.id, item.hashes]),
        );
        for (const id of saved.import_ids)
          pending.set(id, [
            ...new Set([
              ...(pending.get(id) ?? []),
              ...parsed.body.files.map((file) => file.content_sha256),
            ]),
          ]);
        sharingPending = [...pending].map(([id, hashes]) => ({ id, hashes }));
        await shareSavedImports();
      } else {
        await refresh();
        if (!lifetime.signal.aborted) status = 'Import finished';
      }
    } catch (cause) {
      if (!lifetime.signal.aborted)
        error = operation?.signal.aborted
          ? 'Import stopped. Any events already committed remain saved; retrying is safe.'
          : cause instanceof Error
            ? cause.message
            : 'Import failed; retrying is safe';
    } finally {
      if (!lifetime.signal.aborted) busy = false;
      operation = null;
    }
  }

  async function withdraw(id: string) {
    busy = true;
    error = '';
    try {
      await withdrawGalaxyContribution(id, lifetime.signal);
      await refresh();
    } catch (cause) {
      if (!lifetime.signal.aborted)
        error = cause instanceof Error ? cause.message : 'Withdrawal failed';
    } finally {
      if (!lifetime.signal.aborted) busy = false;
    }
  }

  async function changePage(delta: number) {
    page += delta;
    await refresh();
  }
  onMount(() => {
    void refresh();
  });
  onDestroy(() => {
    lifetime.abort();
    operation?.abort();
  });
</script>

<section class="identity-panel" aria-labelledby="journal-account-title">
  <p class="eyebrow">Your exploration</p>
  <h2 id="journal-account-title">Commanders and journals</h2>
  {#if commanders.length}
    <ul>
      {#each commanders as commander (commander.commander_id)}
        <li>
          {commander.commander_name} · {commander.journal_fid} · Verified with Frontier
        </li>
      {/each}
    </ul>
  {:else}
    <p>
      Re-authenticate to link your journal identity. A commander name alone is
      not used to match logs.
    </p>
    <button class="secondary-button" type="button" onclick={() => auth.signIn()}
      >Verify with Frontier</button
    >
  {/if}
  <p>
    Files from unlinked commanders are held for review while your valid files
    continue. Files with multiple commanders are held intact.
  </p>
  <label for="journal-files">Select journal logs</label>
  <input
    id="journal-files"
    type="file"
    multiple
    accept=".log,.jsonl"
    bind:files={selected}
    disabled={busy}
  />
  <p class="state-copy">
    Up to 200 files, 16 MiB per file, 64 MiB total and 50,000 events per import.
    Larger files remain available for a later import.
  </p>
  <label class="journal-sharing-choice">
    <input type="checkbox" bind:checked={sharing} disabled={busy} />
    Share eligible physical galaxy facts from this import on ED-Finder and its API
  </label>
  <p class="state-copy">
    Optional and separate from research sharing. Names, credits and your private
    history stay private. Contributions need review before publication.
    Withdrawal stops future use; removing published effects requires a
    replacement catalogue build.
  </p>
  <div class="identity-panel-heading">
    <button
      class="primary-button"
      type="button"
      disabled={busy || !selected?.length || !commanders.length}
      onclick={() => void upload()}>Import journals</button
    >
    {#if busy && operation}<button
        class="quiet-button"
        type="button"
        onclick={() => operation?.abort()}>Stop import</button
      >{/if}
    {#if sharingPending.length && !busy}<button
        class="secondary-button"
        type="button"
        onclick={() => void shareSavedImports()}
        >Retry sharing saved import</button
      >{/if}
  </div>
  <p role="status">{status}</p>
  {#if error}<p role="alert">{error}</p>
    <button
      type="button"
      class="quiet-button"
      disabled={busy}
      onclick={() => void refresh()}>Refresh account</button
    >
  {/if}
  {#if receipt}
    <p>
      {receipt.events_inserted} events saved · {receipt.duplicates_skipped} duplicate
      events · {receipt.files_skipped} previously imported files
    </p>
    <ul>
      {#each receipt.held_files as file, index (index)}<li>
          {file.name}: {file.reason.replaceAll('_', ' ')}
        </li>{/each}
    </ul>
  {/if}
  {#if warnings.length}<ul>
      {#each warnings as warning, index (index)}<li>
          {warning.name}: {warning.reason}
        </li>{/each}
    </ul>{/if}
</section>

<section class="identity-panel" aria-labelledby="contribution-title">
  <h2 id="contribution-title">Your galaxy contributions</h2>
  {#if !contributions.length}<p>
      No contributions on this page. Personal imports do not enable sharing
      automatically.
    </p>{/if}
  <ul>
    {#each contributions as contribution (contribution.contribution_id)}
      <li>
        System {String(contribution.observation.system_id64)} · Body {String(
          contribution.observation.frontier_body_id,
        )} · {contribution.contribution_state.toLowerCase()}
        {#if contribution.used_in_generation}
          · Included in a catalogue build{/if}
        {#if contribution.contribution_state !== 'WITHDRAWN'}
          <button
            class="quiet-button"
            type="button"
            disabled={busy}
            onclick={() => void withdraw(contribution.contribution_id)}
            >Withdraw sharing</button
          >
        {/if}
      </li>
    {/each}
  </ul>
  <button
    class="quiet-button"
    type="button"
    disabled={busy || page === 0}
    onclick={() => void changePage(-1)}>Previous</button
  >
  <button
    class="quiet-button"
    type="button"
    disabled={busy || contributions.length < 50}
    onclick={() => void changePage(1)}>Next</button
  >
</section>
