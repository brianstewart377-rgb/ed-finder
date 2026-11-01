<script lang="ts">
  import { QueryClientProvider } from '@tanstack/svelte-query';
  import { untrack } from 'svelte';
  import { queryClient } from '$lib/api/query';
  import { providePersistenceContext } from '$lib/persistence/context';
  import ExploreWorkspace from './ExploreWorkspace.svelte';

  type TestPage = { url: URL; state: App.PageState };
  let { installPage } = $props<{
    installPage: (page: TestPage) => void;
  }>();
  const reactivePage = $state<TestPage>({
    url: new URL('http://localhost/explore'),
    state: {},
  });
  untrack(() => installPage(reactivePage));
  providePersistenceContext();
</script>

<QueryClientProvider client={queryClient}>
  <ExploreWorkspace />
</QueryClientProvider>
