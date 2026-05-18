<script lang="ts">
  import SystemHealthCard from "../SystemHealthCard.svelte";
  import { formatDateTime, formatUptime, type HealthStatus } from "./health";

  interface HealthCardHandle {
    refresh: () => Promise<HealthStatus | null>;
    getSnapshot: () => HealthStatus | null;
    getError: () => string | null;
    getLastRefreshed: () => Date | null;
  }

  let healthCard: HealthCardHandle | null = $state(null);
  let health = $state<HealthStatus | null>(null);
  let error = $state<string | null>(null);
  let lastRefreshed = $state<Date | null>(null);
  let refreshing = $state(false);

  function syncFromCard(): void {
    health = healthCard?.getSnapshot() ?? null;
    error = healthCard?.getError() ?? null;
    lastRefreshed = healthCard?.getLastRefreshed() ?? null;
  }

  async function refreshDetails(): Promise<void> {
    if (!healthCard) return;
    refreshing = true;
    try {
      await healthCard.refresh();
    } finally {
      syncFromCard();
      refreshing = false;
    }
  }

  $effect(() => {
    if (!healthCard || typeof window === "undefined") return;
    void refreshDetails();
    const interval = window.setInterval(() => {
      void refreshDetails();
    }, 5000);
    return () => window.clearInterval(interval);
  });
</script>

<div class="space-y-4">
  <SystemHealthCard bind:this={healthCard} />

  <div class="rounded-lg border border-border bg-surface p-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Health details</h2>
        <p class="mt-1 text-sm text-tertiary">
          Live snapshot of the daemon's unauthenticated
          <code class="rounded bg-elevated px-1 py-0.5 font-mono text-xs text-secondary">/healthz</code>
          endpoint.
        </p>
      </div>
      <button
        type="button"
        onclick={() => void refreshDetails()}
        disabled={refreshing}
        class="density-control rounded-md border border-border px-3 py-2 text-sm text-secondary hover:bg-elevated disabled:opacity-50"
      >
        {refreshing ? "Refreshing" : "Refresh now"}
      </button>
    </div>

    {#if error && !health}
      <div class="mt-4 rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error">
        {error}
      </div>
    {/if}

    <div class="mt-4 overflow-x-auto">
      <table class="min-w-full border-separate border-spacing-y-2 text-sm">
        <tbody>
          <tr>
            <th class="w-48 rounded-l-md bg-elevated px-3 py-2 text-left font-medium text-tertiary">
              Daemon status
            </th>
            <td class="rounded-r-md bg-elevated px-3 py-2 text-primary">
              {#if health}
                {health.status === "ok" ? "Healthy" : "Degraded"}
              {:else if error}
                Unreachable
              {:else}
                Checking…
              {/if}
            </td>
          </tr>
          <tr>
            <th class="rounded-l-md bg-elevated px-3 py-2 text-left font-medium text-tertiary">
              Uptime
            </th>
            <td class="rounded-r-md bg-elevated px-3 py-2 font-mono text-primary">
              {health ? formatUptime(health.uptime_seconds) : "Unavailable"}
            </td>
          </tr>
          <tr>
            <th class="rounded-l-md bg-elevated px-3 py-2 text-left font-medium text-tertiary">
              Feed count
            </th>
            <td class="rounded-r-md bg-elevated px-3 py-2 font-mono text-primary">
              {health?.feed_count ?? "Unavailable"}
            </td>
          </tr>
          <tr>
            <th class="rounded-l-md bg-elevated px-3 py-2 text-left font-medium text-tertiary">
              Alert-active feeds
            </th>
            <td class="rounded-r-md bg-elevated px-3 py-2 text-primary">
              {#if health && health.alert_active_feeds.length > 0}
                <ul class="flex flex-wrap gap-2">
                  {#each health.alert_active_feeds as feed (feed)}
                    <li class="rounded-full border border-status-warn/40 bg-status-warn/10 px-2 py-0.5 font-mono text-xs text-status-warn">
                      {feed}
                    </li>
                  {/each}
                </ul>
              {:else}
                None
              {/if}
            </td>
          </tr>
          <tr>
            <th class="rounded-l-md bg-elevated px-3 py-2 text-left font-medium text-tertiary">
              Version
            </th>
            <td class="rounded-r-md bg-elevated px-3 py-2 font-mono text-primary">
              {health?.version ?? "Unavailable"}
            </td>
          </tr>
          <tr>
            <th class="rounded-l-md bg-elevated px-3 py-2 text-left font-medium text-tertiary">
              DB status
            </th>
            <td class="rounded-r-md bg-elevated px-3 py-2 font-mono text-primary">
              {health?.db ?? "Unavailable"}
            </td>
          </tr>
          <tr>
            <th class="rounded-l-md bg-elevated px-3 py-2 text-left font-medium text-tertiary">
              Scheduler status
            </th>
            <td class="rounded-r-md bg-elevated px-3 py-2 font-mono text-primary">
              {health?.scheduler ?? "Unavailable"}
            </td>
          </tr>
          <tr>
            <th class="rounded-l-md bg-elevated px-3 py-2 text-left font-medium text-tertiary">
              Last refreshed
            </th>
            <td class="rounded-r-md bg-elevated px-3 py-2 text-primary">
              {formatDateTime(lastRefreshed)}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</div>
