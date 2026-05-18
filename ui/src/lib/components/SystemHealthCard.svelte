<script lang="ts">
  import {
    fetchHealthStatus,
    formatDateTime,
    formatUptime,
    type HealthStatus,
  } from "./settings/health";

  interface Props {
    pollIntervalMs?: number;
  }

  let { pollIntervalMs = 0 }: Props = $props();

  let health = $state<HealthStatus | null>(null);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let lastRefreshed = $state<Date | null>(null);

  export async function refresh(): Promise<HealthStatus | null> {
    if (loading) return health;

    loading = true;
    try {
      const next = await fetchHealthStatus();
      health = next;
      error = null;
      return next;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      health = null;
      return null;
    } finally {
      lastRefreshed = new Date();
      loading = false;
    }
  }

  export function getSnapshot(): HealthStatus | null {
    return health;
  }

  export function getError(): string | null {
    return error;
  }

  export function getLastRefreshed(): Date | null {
    return lastRefreshed;
  }

  function badgeMeta(): { label: string; className: string } | null {
    if (error) {
      return {
        label: "Unreachable",
        className: "border-status-error/40 bg-status-error/15 text-status-error",
      };
    }
    if (health?.status === "degraded") {
      return {
        label: "Degraded",
        className: "border-status-warn/40 bg-status-warn/15 text-status-warn",
      };
    }
    if (health) {
      return {
        label: "Healthy",
        className: "border-status-ok/40 bg-status-ok/15 text-status-ok",
      };
    }
    return null;
  }

  function alertCount(): number {
    return health?.alert_active_feeds.length ?? 0;
  }

  $effect(() => {
    if (typeof window === "undefined" || pollIntervalMs <= 0) return;
    void refresh();
    const interval = window.setInterval(() => {
      void refresh();
    }, pollIntervalMs);
    return () => window.clearInterval(interval);
  });
</script>

<div class="rounded-lg border border-border bg-surface p-5">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <p class="text-xs uppercase tracking-wide text-tertiary">Daemon health</p>
      {#if badgeMeta()}
        {@const badge = badgeMeta()}
        <span
          class={`mt-2 inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${badge.className}`}
        >
          {badge.label}
        </span>
      {:else}
        <span
          class="mt-2 inline-flex rounded-full border border-border px-2 py-0.5 text-xs font-medium text-tertiary"
        >
          Checking…
        </span>
      {/if}
    </div>
    <div class="text-right">
      <p class="text-xs uppercase tracking-wide text-tertiary">Last refreshed</p>
      <p class="mt-1 text-sm text-secondary">{formatDateTime(lastRefreshed)}</p>
    </div>
  </div>

  {#if error}
    <p class="mt-3 text-sm text-status-error">{error}</p>
  {/if}

  <div class="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
    <div class="rounded-md border border-border bg-elevated p-3">
      <p class="text-xs uppercase tracking-wide text-tertiary">Feeds</p>
      <p class="mt-1 text-2xl font-semibold text-primary">{health?.feed_count ?? "—"}</p>
    </div>
    <div class="rounded-md border border-border bg-elevated p-3">
      <p class="text-xs uppercase tracking-wide text-tertiary">Uptime</p>
      <p class="mt-1 text-2xl font-semibold text-primary">{formatUptime(health?.uptime_seconds)}</p>
    </div>
    <div class="rounded-md border border-border bg-elevated p-3">
      <p class="text-xs uppercase tracking-wide text-tertiary">Alert feeds</p>
      <p class="mt-1 text-2xl font-semibold text-status-warn">{alertCount()}</p>
    </div>
    <div class="rounded-md border border-border bg-elevated p-3">
      <p class="text-xs uppercase tracking-wide text-tertiary">Version</p>
      <p class="mt-1 text-lg font-semibold text-primary">{health?.version ?? "—"}</p>
    </div>
  </div>
</div>
