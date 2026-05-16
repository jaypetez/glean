<script lang="ts">
  import { CaretDown, CaretRight } from "@phosphor-icons/svelte";
  import DOMPurify from "dompurify";
  import { onMount } from "svelte";
  import { listDigests, listFeedConfigs, listFeedDigests } from "../api";
  import { subscribeEvents, type AppEvent, type EventSubscription } from "../sse";
  import type { Digest } from "../types";

  const DIGEST_PAGE_SIZE = 50;

  const pendingLiveFeeds = new Set<string>();

  let digests: Digest[] = $state([]);
  let feedNames: string[] = $state([]);
  let selectedFeed = $state("");
  let loading = $state(true);
  let loadingMore = $state(false);
  let liveRefreshCount = $state(0);
  let error: string | null = $state(null);
  let hasMore = $state(false);
  let sseConnected = $state(false);
  let expandedIds: Set<number> = $state(new Set());

  const liveRefreshing = $derived(liveRefreshCount > 0);

  onMount(() => {
    void initialize();
    const subscription: EventSubscription = subscribeEvents({
      onEvent: handleEvent,
      onConnectionChange: (connected) => {
        sseConnected = connected;
      },
    });

    return () => subscription.close();
  });

  async function initialize(): Promise<void> {
    loading = true;
    error = null;
    try {
      const [feeds, page] = await Promise.all([
        loadFeedNames().then((names) => {
          feedNames = names;
          return names;
        }),
        fetchDigestPage(),
      ]);
      feedNames = feeds;
      digests = sortAndDedupe(page);
      hasMore = page.length === DIGEST_PAGE_SIZE;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }

    if (!error) {
      await drainPendingLiveFeeds();
    }
  }

  async function loadFeedNames(): Promise<string[]> {
    const feeds = await listFeedConfigs();
    return feeds.map((feed) => feed.name).sort((left, right) => left.localeCompare(right));
  }

  async function fetchDigestPage(opts?: {
    feedName?: string;
    before?: number;
  }): Promise<Digest[]> {
    const feedName = opts?.feedName ?? selectedFeed;
    if (feedName) {
      return listFeedDigests(feedName, { limit: DIGEST_PAGE_SIZE, before: opts?.before });
    }
    return listDigests({ limit: DIGEST_PAGE_SIZE, before: opts?.before });
  }

  function compareDigests(left: Digest, right: Digest): number {
    const sentAtDiff = Date.parse(right.sent_at) - Date.parse(left.sent_at);
    if (sentAtDiff !== 0) return sentAtDiff;
    return right.id - left.id;
  }

  function sortAndDedupe(items: Digest[]): Digest[] {
    const byId = new Map<number, Digest>();
    for (const item of items) {
      byId.set(item.id, item);
    }
    return [...byId.values()].sort(compareDigests);
  }

  function lastDigestId(): number | undefined {
    return digests.at(-1)?.id;
  }

  async function applyFilter(): Promise<void> {
    expandedIds = new Set();
    await initialize();
  }

  async function loadMore(): Promise<void> {
    if (loadingMore || !hasMore) return;
    loadingMore = true;
    error = null;
    try {
      const page = await fetchDigestPage({ before: lastDigestId() });
      digests = sortAndDedupe([...digests, ...page]);
      hasMore = page.length === DIGEST_PAGE_SIZE;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loadingMore = false;
    }
  }

  function liveDigestsForCurrentView(page: Digest[]): Digest[] {
    if (selectedFeed) return page;
    const currentHead = digests[0];
    if (!currentHead) return page;
    return page.filter((digest) => compareDigests(digest, currentHead) < 0);
  }

  async function prependLatestFeed(feedName: string): Promise<void> {
    liveRefreshCount += 1;
    try {
      const page = await fetchDigestPage({ feedName });
      const incoming = liveDigestsForCurrentView(page);
      if (incoming.length === 0) return;
      digests = sortAndDedupe([...incoming, ...digests]);
    } catch (e) {
      console.warn("digest live refresh failed", e);
    } finally {
      liveRefreshCount = Math.max(0, liveRefreshCount - 1);
    }
  }

  async function drainPendingLiveFeeds(): Promise<void> {
    if (pendingLiveFeeds.size === 0) return;
    const feeds = [...pendingLiveFeeds];
    pendingLiveFeeds.clear();
    for (const feedName of feeds) {
      if (selectedFeed && selectedFeed !== feedName) {
        continue;
      }
      await prependLatestFeed(feedName);
    }
  }

  function handleEvent(event: AppEvent): void {
    if (event.type !== "digest.persisted") return;
    if (selectedFeed && selectedFeed !== event.feed_name) return;
    if (loading) {
      pendingLiveFeeds.add(event.feed_name);
      return;
    }
    void prependLatestFeed(event.feed_name);
  }

  function toggleExpanded(id: number): void {
    const next = new Set(expandedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    expandedIds = next;
  }

  function plainText(value: string): string {
    return value.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  }

  function previewText(digest: Digest): string {
    const source = digest.intro ?? digest.body;
    const preview = plainText(source);
    if (!preview) return "No preview available";
    return preview.length > 80 ? `${preview.slice(0, 80)}…` : preview;
  }

  function formatSentAt(value: string): string {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  }

  function sanitizeHtml(value: string): string {
    return DOMPurify.sanitize(value, { USE_PROFILES: { html: true } });
  }
</script>

<div class="mx-auto max-w-6xl px-6 py-6">
  <header class="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
    <div>
      <h1 class="text-2xl font-semibold text-primary">Digests</h1>
      <p class="text-sm text-tertiary">Stored digest history with live updates from the dashboard sink.</p>
    </div>

    <label class="flex min-w-56 flex-col gap-1 text-xs text-tertiary">
      <span>Feed filter</span>
      <select
        aria-label="Feed filter"
        bind:value={selectedFeed}
        onchange={() => void applyFilter()}
        class="density-control rounded-md border border-border bg-surface px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
      >
        <option value="">All feeds</option>
        {#each feedNames as feedName}
          <option value={feedName}>{feedName}</option>
        {/each}
      </select>
    </label>
  </header>

  <div class="mb-4 rounded-lg border border-border bg-surface px-4 py-3 text-sm" aria-live="polite">
    <div class="flex flex-wrap items-center gap-2 text-tertiary">
      <span class={`h-2.5 w-2.5 rounded-full ${sseConnected ? "bg-cyan" : "bg-status-warn"}`}></span>
      <span>{sseConnected ? "Connected" : "Reconnecting..."}</span>
      {#if liveRefreshing}
        <span class="text-faint">Updating digest history...</span>
      {/if}
    </div>
  </div>

  {#if error}
    <div class="mb-4 rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error">
      {error}
    </div>
  {/if}

  {#if loading}
    <p class="text-tertiary">Loading digest history...</p>
  {:else if digests.length === 0}
    <div class="rounded-xl border border-border bg-surface p-8 text-center">
      <h2 class="text-lg font-semibold text-primary">No digests yet</h2>
      <p class="mt-2 text-sm text-tertiary">
        {#if selectedFeed}
          {selectedFeed} has not persisted any dashboard digests yet.
        {:else}
          Run a feed with the dashboard sink enabled to start building digest history.
        {/if}
      </p>
    </div>
  {:else}
    <ul class="space-y-3" aria-label="Digest history">
      {#each digests as digest (digest.id)}
        <li class="rounded-xl border border-border bg-surface p-4 shadow-sm">
          <div class="flex items-start gap-3">
            <button
              type="button"
              aria-label={`${expandedIds.has(digest.id) ? "Collapse" : "Expand"} digest ${digest.id}`}
              class="mt-0.5 rounded-md border border-border bg-elevated p-2 text-tertiary hover:border-cyan/40 hover:text-primary"
              onclick={() => toggleExpanded(digest.id)}
            >
              {#if expandedIds.has(digest.id)}
                <CaretDown size={16} aria-hidden="true" />
              {:else}
                <CaretRight size={16} aria-hidden="true" />
              {/if}
            </button>

            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full bg-cyan/10 px-2 py-0.5 font-mono text-xs text-cyan">
                  {digest.feed_name}
                </span>
                <time class="text-xs text-tertiary" datetime={digest.sent_at} title={digest.sent_at}>
                  {formatSentAt(digest.sent_at)}
                </time>
                <span class="rounded-full bg-muted px-2 py-0.5 text-xs text-tertiary">
                  {digest.item_count} item{digest.item_count === 1 ? "" : "s"}
                </span>
                {#if digest.fragment_index > 0}
                  <span class="rounded-full bg-muted px-2 py-0.5 text-xs text-tertiary">
                    Fragment {digest.fragment_index + 1}
                  </span>
                {/if}
              </div>

              <p class="mt-2 text-sm leading-6 text-secondary">{previewText(digest)}</p>
            </div>
          </div>

          {#if expandedIds.has(digest.id)}
            <div class="mt-4 rounded-lg border border-border bg-base/30 p-4">
              {#if digest.intro}
                <p class="mb-3 text-sm font-medium text-primary">{plainText(digest.intro)}</p>
              {/if}

              {#if digest.style === "html"}
                <div class="break-words text-sm leading-6 text-secondary [&_a]:text-cyan [&_code]:font-mono [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-elevated [&_pre]:p-3" >
                  {@html sanitizeHtml(digest.body)}
                </div>
              {:else}
                <pre class="overflow-x-auto whitespace-pre-wrap rounded-md bg-elevated p-3 font-mono text-sm text-secondary">{digest.body}</pre>
              {/if}

              {#if digest.trace_id}
                <p class="mt-3 font-mono text-xs text-faint">trace {digest.trace_id}</p>
              {/if}
            </div>
          {/if}
        </li>
      {/each}
    </ul>

    {#if hasMore}
      <div class="mt-6 flex justify-center">
        <button
          type="button"
          onclick={() => void loadMore()}
          disabled={loadingMore}
          class="density-control rounded-md border border-cyan/30 bg-cyan/10 px-4 py-2 text-sm font-medium text-cyan hover:bg-cyan/20 disabled:cursor-not-allowed disabled:border-border disabled:bg-muted disabled:text-tertiary"
        >
          {loadingMore ? "Loading..." : "Load more"}
        </button>
      </div>
    {/if}
  {/if}
</div>
