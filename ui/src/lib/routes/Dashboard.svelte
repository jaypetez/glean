<script lang="ts">
  import { onMount } from "svelte";
  import { Link } from "svelte-routing";
  import { listFeedConfigs, listFeedStatuses, runFeedNow } from "../api";
  import { subscribeEvents, type EventSubscription, type RunEvent } from "../sse";
  import type { FeedListItem, FeedStatus } from "../types";
  import Logo from "../components/Logo.svelte";

  type StatusKind = "running" | "ok" | "warning" | "error";

  interface FeedCard extends FeedListItem {
    last_success_at: string | null;
    last_attempt_at: string | null;
    last_error: string | null;
    consecutive_failures: number;
    alert_active: boolean;
    bootstrapped: boolean;
  }

  let feeds: FeedCard[] = $state([]);
  let loading = $state(true);
  let error: string | null = $state(null);
  let sseConnected = $state(false);
  let runningFeeds: Set<string> = $state(new Set());

  onMount(() => {
    void loadFeeds();
    const subscription: EventSubscription = subscribeEvents({
      onEvent: applyRunEvent,
      onConnectionChange: (connected) => {
        sseConnected = connected;
      },
    });

    return () => subscription.close();
  });

  async function loadFeeds(): Promise<void> {
    loading = true;
    error = null;
    try {
      const [configs, statuses] = await Promise.all([listFeedConfigs(), listFeedStatuses()]);
      feeds = mergeFeeds(configs, statuses);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  function mergeFeeds(configs: FeedListItem[], statuses: FeedStatus[]): FeedCard[] {
    const statusByName = new Map(statuses.map((status) => [status.name, status]));
    return configs.map((feed) => withStatus(feed, statusByName.get(feed.name)));
  }

  function withStatus(feed: FeedListItem, status?: FeedStatus): FeedCard {
    return {
      ...feed,
      last_success_at: status?.last_success_at ?? null,
      last_attempt_at: status?.last_attempt_at ?? null,
      last_error: status?.last_error ?? null,
      consecutive_failures: status?.consecutive_failures ?? 0,
      alert_active: status?.alert_active ?? false,
      bootstrapped: status?.bootstrapped ?? false,
    };
  }

  async function refreshStatuses(): Promise<void> {
    const statuses = await listFeedStatuses();
    const statusByName = new Map(statuses.map((status) => [status.name, status]));
    feeds = feeds.map((feed) => ({ ...feed, ...statusByName.get(feed.name) }));
  }

  function updateFeed(feedName: string, update: (feed: FeedCard) => FeedCard): void {
    feeds = feeds.map((feed) => (feed.name === feedName ? update(feed) : feed));
  }

  function setRunning(feedName: string, running: boolean): void {
    const next = new Set(runningFeeds);
    if (running) {
      next.add(feedName);
    } else {
      next.delete(feedName);
    }
    runningFeeds = next;
  }

  function applyRunEvent(event: RunEvent): void {
    if (!feeds.some((feed) => feed.name === event.feed)) return;

    if (event.type === "run_started") {
      setRunning(event.feed, true);
      updateFeed(event.feed, (feed) => ({
        ...feed,
        last_attempt_at: event.timestamp,
      }));
      return;
    }

    setRunning(event.feed, false);
    if (event.type === "run_completed") {
      updateFeed(event.feed, (feed) => ({
        ...feed,
        last_success_at: event.timestamp,
        last_attempt_at: event.timestamp,
        last_error: null,
        consecutive_failures: 0,
        alert_active: false,
      }));
    } else {
      updateFeed(event.feed, (feed) => ({
        ...feed,
        last_attempt_at: event.timestamp,
        last_error: event.error ?? "Run failed",
        consecutive_failures: Math.max(feed.consecutive_failures + 1, 1),
      }));
    }
    void refreshStatuses();
  }

  async function onRunNow(feedName: string): Promise<void> {
    setRunning(feedName, true);
    updateFeed(feedName, (feed) => ({ ...feed, last_error: null }));
    try {
      await runFeedNow(feedName);
      await refreshStatuses();
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      updateFeed(feedName, (feed) => ({
        ...feed,
        last_error: message,
        consecutive_failures: Math.max(feed.consecutive_failures + 1, 1),
      }));
    } finally {
      setRunning(feedName, false);
    }
  }

  function statusKind(feed: FeedCard): StatusKind {
    if (runningFeeds.has(feed.name)) return "running";
    if (feed.alert_active) return "error";
    if (feed.consecutive_failures > 0) return "warning";
    return "ok";
  }

  function statusPillClass(feed: FeedCard): string {
    const base = "rounded-full border px-2 py-0.5 text-xs font-medium capitalize";
    switch (statusKind(feed)) {
      case "running":
        return `${base} border-cyan/30 bg-cyan/15 text-cyan motion-safe:animate-pulse`;
      case "error":
        return `${base} border-status-error/40 bg-status-error/15 text-status-error`;
      case "warning":
        return `${base} border-status-warn/40 bg-status-warn/15 text-status-warn`;
      case "ok":
        return `${base} border-status-ok/40 bg-status-ok/15 text-status-ok`;
    }
  }

  function formatDate(value: string | null): string {
    if (!value) return "Never";
    return new Date(value).toLocaleString();
  }

  function runningCount(): number {
    return runningFeeds.size;
  }

  function healthyCount(): number {
    return feeds.filter((feed) => statusKind(feed) === "ok").length;
  }

  function alertCount(): number {
    return feeds.filter((feed) => feed.alert_active).length;
  }
</script>

<div class="mx-auto max-w-6xl px-6 py-6">
  <header class="mb-6 flex items-center justify-between gap-4">
    <div>
      <h1 class="text-2xl font-semibold text-primary">Feeds</h1>
      <p class="text-sm text-tertiary">Configured feeds and live run status</p>
    </div>
    <Link
      to="/feeds/new"
      class="rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-base hover:bg-cyan-light"
    >
      New feed
    </Link>
  </header>

  <section class="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Feed summary">
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Total feeds</p>
      <p class="mt-1 text-2xl font-semibold text-primary">{feeds.length}</p>
    </div>
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Running</p>
      <p class="mt-1 text-2xl font-semibold text-cyan">{runningCount()}</p>
    </div>
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Healthy</p>
      <p class="mt-1 text-2xl font-semibold text-status-ok">{healthyCount()}</p>
    </div>
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Alerts</p>
      <p class="mt-1 text-2xl font-semibold text-status-error">{alertCount()}</p>
    </div>
  </section>

  {#if loading}
    <p class="text-tertiary">Loading...</p>
  {:else if error}
    <div
      class="rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error"
    >
      {error}
    </div>
  {:else if feeds.length === 0}
    <div class="flex flex-col items-center justify-center gap-6 py-16 text-center">
      <Logo variant="vertical" class="h-32 w-32 text-cyan" />
      <div class="max-w-md space-y-2">
        <h2 class="text-lg font-semibold text-primary">No feeds yet</h2>
        <p class="text-sm text-tertiary">
          Configure your first feed to start gleaning signal from RSS, scraping, or web search.
        </p>
      </div>
      <Link
        to="/feeds/new"
        class="rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-base hover:bg-cyan-light"
      >
        Create your first feed
      </Link>
    </div>
  {:else}
    <ul class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
      {#each feeds as feed (feed.name)}
        <li class="rounded-lg border border-border bg-surface p-4 hover:border-cyan/40 transition">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <Link to={`/feeds/${encodeURIComponent(feed.name)}`} class="block">
                <h2 class="truncate font-mono text-base font-medium text-primary">{feed.name}</h2>
              </Link>
              <p class="mt-1 font-mono text-xs text-tertiary">{feed.schedule}</p>
            </div>
            <span class={statusPillClass(feed)}>{statusKind(feed)}</span>
          </div>

          <div class="mt-3 flex flex-wrap gap-1.5 text-xs">
            {#each feed.pipeline_stages as stage}
              <span class="rounded-full bg-muted px-2 py-0.5 font-mono text-tertiary">{stage}</span>
            {/each}
          </div>

          <dl class="mt-4 space-y-2 text-xs">
            <div class="flex justify-between gap-3">
              <dt class="text-faint">Last success</dt>
              <dd class="text-right text-tertiary">{formatDate(feed.last_success_at)}</dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-faint">Failures</dt>
              <dd class="text-tertiary">{feed.consecutive_failures}</dd>
            </div>
            {#if feed.last_error}
              <div>
                <dt class="text-faint">Last error</dt>
                <dd class="mt-1 line-clamp-2 text-status-error">{feed.last_error}</dd>
              </div>
            {/if}
          </dl>

          <div class="mt-4 flex items-center justify-between gap-3 text-xs text-faint">
            <div class="flex gap-3">
              <span>{feed.sources_count} source{feed.sources_count === 1 ? "" : "s"}</span>
              <span>{feed.sinks_count} sink{feed.sinks_count === 1 ? "" : "s"}</span>
            </div>
            <button
              type="button"
              onclick={() => onRunNow(feed.name)}
              disabled={runningFeeds.has(feed.name)}
              class="rounded-md border border-cyan/30 bg-cyan/10 px-3 py-1.5 text-sm font-medium text-cyan hover:bg-cyan/20 disabled:cursor-not-allowed disabled:border-border disabled:bg-muted disabled:text-tertiary"
            >
              {runningFeeds.has(feed.name) ? "Running..." : "Run now"}
            </button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}

  <div class="mt-6 rounded-lg border border-border bg-surface px-4 py-3 text-sm" aria-live="polite">
    <div class="flex items-center gap-2 text-tertiary">
      <span class={`h-2.5 w-2.5 rounded-full ${sseConnected ? "bg-cyan" : "bg-status-warn"}`}
      ></span>
      <span>{sseConnected ? "Connected" : "Reconnecting..."}</span>
    </div>
  </div>
</div>
