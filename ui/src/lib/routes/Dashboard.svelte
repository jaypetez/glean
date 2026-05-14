<script lang="ts">
  import { onMount } from "svelte";
  import { Link } from "svelte-routing";
  import { listFeedConfigs } from "../api";
  import type { FeedListItem } from "../types";

  let feeds: FeedListItem[] = $state([]);
  let loading = $state(true);
  let error: string | null = $state(null);

  onMount(async () => {
    try {
      feeds = await listFeedConfigs();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  });
</script>

<div class="mx-auto max-w-6xl px-6 py-6">
  <header class="mb-6 flex items-center justify-between">
    <div>
      <h1 class="text-2xl font-semibold text-primary">Feeds</h1>
      <p class="text-sm text-tertiary">Configured feeds and their pipeline stages</p>
    </div>
    <Link
      to="/feeds/new"
      class="rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-base hover:bg-cyan-light"
    >
      New feed
    </Link>
  </header>

  {#if loading}
    <p class="text-tertiary">Loading...</p>
  {:else if error}
    <div
      class="rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error"
    >
      {error}
    </div>
  {:else if feeds.length === 0}
    <div class="rounded-lg border border-border bg-surface p-8 text-center">
      <p class="text-tertiary">No feeds configured yet.</p>
      <Link
        to="/feeds/new"
        class="mt-4 inline-block rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-base hover:bg-cyan-light"
      >
        Create your first feed
      </Link>
    </div>
  {:else}
    <ul class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
      {#each feeds as feed}
        <li class="rounded-lg border border-border bg-surface p-4 hover:border-cyan/40 transition">
          <Link to={`/feeds/${encodeURIComponent(feed.name)}`} class="block">
            <h2 class="font-mono text-base font-medium text-primary">{feed.name}</h2>
            <p class="mt-1 font-mono text-xs text-tertiary">{feed.schedule}</p>
            <div class="mt-3 flex flex-wrap gap-1.5 text-xs">
              {#each feed.pipeline_stages as stage}
                <span class="rounded-full bg-muted px-2 py-0.5 font-mono text-tertiary"
                  >{stage}</span
                >
              {/each}
            </div>
            <div class="mt-3 flex gap-3 text-xs text-faint">
              <span>{feed.sources_count} source{feed.sources_count === 1 ? "" : "s"}</span>
              <span>{feed.sinks_count} sink{feed.sinks_count === 1 ? "" : "s"}</span>
            </div>
          </Link>
        </li>
      {/each}
    </ul>
  {/if}
</div>
