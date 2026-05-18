<script lang="ts">
  import { onMount } from "svelte";
  import { Link } from "svelte-routing";
  import { listDigests, listFeedStatuses } from "../api";
  import type { Digest, FeedStatus } from "../types";

  interface HealthResponse {
    status: string;
    db: string;
    scheduler: string;
    version: string;
    uptime_s?: number;
    uptime_seconds: number;
    feed_count: number;
    alert_active_feeds: string[];
  }

  const DAY_IN_MS = 24 * 60 * 60 * 1000;
  const DIGEST_COUNT_PAGE_SIZE = 100;

  let health: HealthResponse | null = $state(null);
  let feedStatuses: FeedStatus[] = $state([]);
  let recentDigests: Digest[] = $state([]);
  let digestsLast24h: number | null = $state(null);
  let loading = $state(true);
  let error: string | null = $state(null);

  onMount(() => {
    void loadHome();
  });

  async function loadHome(): Promise<void> {
    loading = true;
    error = null;
    try {
      const [nextHealth, statuses, digestSummary] = await Promise.all([
        fetchHealth(),
        listFeedStatuses(),
        loadDigestSummary(),
      ]);
      health = nextHealth;
      feedStatuses = statuses;
      recentDigests = digestSummary.recentDigests;
      digestsLast24h = digestSummary.last24hCount;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  async function fetchHealth(): Promise<HealthResponse> {
    const resp = await fetch("/healthz");
    if (!resp.ok) throw new Error(`GET /healthz -> ${resp.status}`);
    return (await resp.json()) as HealthResponse;
  }

  async function loadDigestSummary(): Promise<{
    recentDigests: Digest[];
    last24hCount: number;
  }> {
    const cutoff = Date.now() - DAY_IN_MS;
    let before: number | undefined;
    let last24hCount = 0;
    let firstPage: Digest[] = [];

    while (true) {
      const page = await listDigests({ limit: DIGEST_COUNT_PAGE_SIZE, before });
      if (firstPage.length === 0) {
        firstPage = page.slice(0, 5);
      }
      if (page.length === 0) break;

      for (const digest of page) {
        if (Date.parse(digest.sent_at) >= cutoff) {
          last24hCount += 1;
        } else {
          return { recentDigests: firstPage.slice(0, 5), last24hCount };
        }
      }

      if (page.length < DIGEST_COUNT_PAGE_SIZE) break;
      before = page.at(-1)?.id;
      if (before === undefined) break;
    }

    return { recentDigests: firstPage.slice(0, 5), last24hCount };
  }

  function plainText(value: string): string {
    return value
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function previewText(digest: Digest): string {
    const preview = plainText(digest.intro ?? digest.body);
    if (!preview) return "No preview available";
    return preview.length > 120 ? `${preview.slice(0, 120)}…` : preview;
  }

  function formatSentAt(value: string): string {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  }

  function formatUptime(totalSeconds: number | undefined): string {
    if (totalSeconds === undefined) return "—";
    const days = Math.floor(totalSeconds / 86_400);
    const hours = Math.floor((totalSeconds % 86_400) / 3_600);
    const minutes = Math.floor((totalSeconds % 3_600) / 60);
    const parts: string[] = [];
    if (days > 0) parts.push(`${days}d`);
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0 || parts.length === 0) parts.push(`${minutes}m`);
    return parts.slice(0, 2).join(" ");
  }

  function daemonBadgeClass(): string {
    const base = "rounded-full border px-2.5 py-1 text-xs font-medium uppercase tracking-wide";
    if (!health) return `${base} border-border bg-muted text-tertiary`;
    if (health.status === "ok") return `${base} border-status-ok/40 bg-status-ok/15 text-status-ok`;
    return `${base} border-status-warn/40 bg-status-warn/15 text-status-warn`;
  }

  function daemonLabel(): string {
    if (!health) return "Loading";
    return health.status === "ok" ? "Healthy" : "Degraded";
  }

  function activeFeedsCount(): number | string {
    return loading ? "—" : feedStatuses.length;
  }

  function alertCount(): number | string {
    return loading ? "—" : feedStatuses.filter((feed) => feed.alert_active).length;
  }
</script>

<div class="mx-auto max-w-6xl px-6 py-6">
  <header class="mb-6 rounded-xl border border-border bg-surface p-6 shadow-sm">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <div class="flex flex-wrap items-center gap-3">
          <h1 class="text-3xl font-semibold text-primary">Glean is running</h1>
          <span class={daemonBadgeClass()}>{daemonLabel()}</span>
        </div>
        <p class="mt-2 text-sm text-tertiary">
          Daemon status from <code class="rounded bg-elevated px-1.5 py-0.5 font-mono text-xs"
            >/healthz</code
          >
          with live service health, alert state, and uptime.
        </p>
      </div>
      <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        <div>
          <dt class="text-faint">Scheduler</dt>
          <dd class="font-medium text-primary">{health?.scheduler ?? "—"}</dd>
        </div>
        <div>
          <dt class="text-faint">Database</dt>
          <dd class="font-medium text-primary">{health?.db ?? "—"}</dd>
        </div>
        <div>
          <dt class="text-faint">Version</dt>
          <dd class="font-medium text-primary">{health?.version ?? "—"}</dd>
        </div>
        <div>
          <dt class="text-faint">Configured feeds</dt>
          <dd class="font-medium text-primary">{health?.feed_count ?? "—"}</dd>
        </div>
      </dl>
    </div>
  </header>

  {#if error}
    <div
      class="mb-6 rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error"
    >
      {error}
    </div>
  {/if}

  <section class="mb-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4" aria-label="Overview stats">
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Active feeds</p>
      <p class="mt-1 text-2xl font-semibold text-primary">{activeFeedsCount()}</p>
    </div>
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Feeds with alerts</p>
      <p class="mt-1 text-2xl font-semibold text-status-error">{alertCount()}</p>
    </div>
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Digests in last 24h</p>
      <p class="mt-1 text-2xl font-semibold text-primary">{digestsLast24h ?? "—"}</p>
    </div>
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Uptime</p>
      <p class="mt-1 text-2xl font-semibold text-primary">{formatUptime(health?.uptime_seconds)}</p>
    </div>
  </section>

  <div class="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
    <section class="rounded-xl border border-border bg-surface p-6 shadow-sm">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 class="text-lg font-semibold text-primary">Recent digests</h2>
          <p class="mt-1 text-sm text-tertiary">The newest persisted digests across every feed.</p>
        </div>
        <Link
          to="/digests"
          class="inline-flex items-center rounded-md border border-cyan/30 bg-cyan/10 px-3 py-1.5 text-sm font-medium text-cyan hover:bg-cyan/20"
        >
          View all digests
        </Link>
      </div>

      {#if loading}
        <p class="mt-4 text-sm text-tertiary">Loading recent digests...</p>
      {:else if recentDigests.length === 0}
        <div class="mt-4 rounded-lg border border-dashed border-border bg-base/30 p-6 text-center">
          <h3 class="text-base font-semibold text-primary">No digests yet</h3>
          <p class="mt-2 text-sm text-tertiary">
            Run a feed with the dashboard sink enabled to start building history.
          </p>
        </div>
      {:else}
        <ul class="mt-4 space-y-3">
          {#each recentDigests as digest (digest.id)}
            <li class="rounded-lg border border-border bg-base/30 p-4">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full bg-cyan/10 px-2 py-0.5 font-mono text-xs text-cyan">
                  {digest.feed_name}
                </span>
                <time
                  class="text-xs text-tertiary"
                  datetime={digest.sent_at}
                  title={digest.sent_at}
                >
                  {formatSentAt(digest.sent_at)}
                </time>
              </div>
              <p class="mt-2 text-sm leading-6 text-secondary">{previewText(digest)}</p>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <aside class="rounded-xl border border-border bg-surface p-6 shadow-sm">
      <h2 class="text-lg font-semibold text-primary">Quick actions</h2>
      <p class="mt-1 text-sm text-tertiary">Jump to the most common setup and review tasks.</p>

      <div class="mt-4 grid gap-3">
        <Link
          to="/feeds/new"
          class="rounded-lg border border-border bg-base/30 p-4 transition hover:border-cyan/40 hover:bg-elevated"
        >
          <p class="font-medium text-primary">Add a feed</p>
          <p class="mt-1 text-sm text-tertiary">Create a new feed and start monitoring a source.</p>
        </Link>
        <Link
          to="/digests"
          class="rounded-lg border border-border bg-base/30 p-4 transition hover:border-cyan/40 hover:bg-elevated"
        >
          <p class="font-medium text-primary">View digests</p>
          <p class="mt-1 text-sm text-tertiary">
            Browse digest history across every configured feed.
          </p>
        </Link>
        <Link
          to="/settings"
          class="rounded-lg border border-border bg-base/30 p-4 transition hover:border-cyan/40 hover:bg-elevated"
        >
          <p class="font-medium text-primary">Open settings</p>
          <p class="mt-1 text-sm text-tertiary">
            Adjust defaults, API access, and appearance preferences.
          </p>
        </Link>
      </div>
    </aside>
  </div>
</div>
