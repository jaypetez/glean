<script lang="ts">
  import { CaretDown, CaretRight, Copy } from "@phosphor-icons/svelte";
  import { onMount } from "svelte";
  import { listFeedRuns, type FeedRun } from "../../api";

  type RunFilter = "all" | FeedRun["status"];

  const RUN_PAGE_SIZE = 50;

  interface Props {
    name: string;
  }

  let { name }: Props = $props();
  let runs: FeedRun[] = $state([]);
  let selectedStatus: RunFilter = $state("all");
  let loading = $state(true);
  let loadingMore = $state(false);
  let hasMore = $state(false);
  let error: string | null = $state(null);
  let expandedIds: Set<number> = $state(new Set());
  let copyMessage: string | null = $state(null);

  onMount(() => {
    void loadRuns(true);
  });

  async function loadRuns(reset: boolean): Promise<void> {
    if (reset) {
      loading = true;
    } else {
      loadingMore = true;
    }
    error = null;

    try {
      const page = await listFeedRuns(name, {
        limit: RUN_PAGE_SIZE,
        before: reset ? undefined : runs.at(-1)?.id,
        status: selectedStatus === "all" ? undefined : selectedStatus,
      });
      runs = reset ? page : [...runs, ...page];
      hasMore = page.length === RUN_PAGE_SIZE;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
      loadingMore = false;
    }
  }

  async function applyFilter(): Promise<void> {
    expandedIds = new Set();
    await loadRuns(true);
  }

  function statusBadgeClass(status: FeedRun["status"]): string {
    const base = "rounded-full border px-2 py-0.5 text-xs font-medium capitalize";
    switch (status) {
      case "success":
        return `${base} border-status-ok/40 bg-status-ok/15 text-status-ok`;
      case "skip":
        return `${base} border-status-warn/40 bg-status-warn/15 text-status-warn`;
      case "failure":
        return `${base} border-status-error/40 bg-status-error/15 text-status-error`;
    }
  }

  function formatAbsoluteTime(value: string): string {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  }

  function formatRelativeTime(value: string): string {
    const seconds = Math.round((Date.now() - Date.parse(value)) / 1_000);
    const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

    if (Math.abs(seconds) < 60) return formatter.format(-seconds, "second");
    const minutes = Math.round(seconds / 60);
    if (Math.abs(minutes) < 60) return formatter.format(-minutes, "minute");
    const hours = Math.round(minutes / 60);
    if (Math.abs(hours) < 24) return formatter.format(-hours, "hour");
    const days = Math.round(hours / 24);
    return formatter.format(-days, "day");
  }

  function errorPreview(value: string): string {
    return value.length > 90 ? `${value.slice(0, 90)}…` : value;
  }

  function formatMetric(value: number): string {
    return value.toLocaleString();
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

  async function copyTraceId(traceId: string): Promise<void> {
    if (!navigator.clipboard) {
      copyMessage = "Clipboard unavailable";
      return;
    }
    try {
      await navigator.clipboard.writeText(traceId);
      copyMessage = `Copied ${traceId}`;
    } catch {
      copyMessage = "Copy failed";
    }
    window.setTimeout(() => {
      if (copyMessage === `Copied ${traceId}` || copyMessage === "Copy failed") {
        copyMessage = null;
      }
    }, 2_000);
  }
</script>

<div class="space-y-4">
  <div class="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
    <div>
      <h2 class="text-lg font-semibold text-primary">Recent runs</h2>
      <p class="text-sm text-tertiary">
        Last 50 recorded runs for this feed, with status and counters.
      </p>
    </div>

    <label class="flex min-w-52 flex-col gap-1 text-xs text-tertiary">
      <span>Status filter</span>
      <select
        bind:value={selectedStatus}
        onchange={() => void applyFilter()}
        class="rounded-md border border-border bg-surface px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
      >
        <option value="all">All</option>
        <option value="success">Success</option>
        <option value="skip">Skip</option>
        <option value="failure">Failure</option>
      </select>
    </label>
  </div>

  {#if copyMessage}
    <div
      class="rounded-md border border-status-ok/40 bg-status-ok/10 px-3 py-2 text-sm text-status-ok"
    >
      {copyMessage}
    </div>
  {/if}

  {#if error}
    <div
      class="rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error"
    >
      {error}
    </div>
  {/if}

  {#if loading}
    <p class="text-sm text-tertiary">Loading runs...</p>
  {:else if runs.length === 0}
    <div class="rounded-xl border border-dashed border-border bg-surface p-8 text-center">
      <h3 class="text-lg font-semibold text-primary">No runs yet</h3>
      <p class="mt-2 text-sm text-tertiary">
        Use Run now above to create the first recorded run for this feed.
      </p>
    </div>
  {:else}
    <div class="overflow-x-auto rounded-xl border border-border bg-surface shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-base/60 text-left text-xs uppercase tracking-wide text-tertiary">
          <tr>
            <th class="px-4 py-3 font-medium">Started</th>
            <th class="px-4 py-3 font-medium">Duration</th>
            <th class="px-4 py-3 font-medium">Status</th>
            <th class="px-4 py-3 font-medium">Fetched</th>
            <th class="px-4 py-3 font-medium">After dedup</th>
            <th class="px-4 py-3 font-medium">Dropped</th>
            <th class="px-4 py-3 font-medium">Sent</th>
            <th class="px-4 py-3 font-medium">Overflow</th>
            <th class="px-4 py-3 font-medium">Error</th>
            <th class="px-4 py-3 font-medium">Trace ID</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border">
          {#each runs as run (run.id)}
            <tr class="align-top">
              <td class="px-4 py-3 text-secondary">
                <time datetime={run.started_at} title={formatAbsoluteTime(run.started_at)}>
                  {formatRelativeTime(run.started_at)}
                </time>
              </td>
              <td class="px-4 py-3 text-secondary">{formatMetric(run.duration_ms)} ms</td>
              <td class="px-4 py-3">
                <div class="flex flex-wrap items-center gap-2">
                  <span class={statusBadgeClass(run.status)}>{run.status}</span>
                  {#if run.dry_run}
                    <span class="rounded-full bg-muted px-2 py-0.5 text-xs text-tertiary"
                      >dry run</span
                    >
                  {/if}
                </div>
              </td>
              <td class="px-4 py-3 text-secondary">{formatMetric(run.fetched)}</td>
              <td class="px-4 py-3 text-secondary">{formatMetric(run.after_dedup)}</td>
              <td class="px-4 py-3 text-secondary">{formatMetric(run.dropped)}</td>
              <td class="px-4 py-3 text-secondary">{formatMetric(run.sent)}</td>
              <td class="px-4 py-3 text-secondary">{formatMetric(run.overflow)}</td>
              <td class="px-4 py-3">
                {#if run.error}
                  <div class="max-w-sm space-y-2">
                    <div class="flex items-start gap-2">
                      <span class="text-status-error">{errorPreview(run.error)}</span>
                      {#if run.error.length > 90}
                        <button
                          type="button"
                          class="rounded-md border border-border bg-elevated p-1 text-tertiary hover:border-cyan/40 hover:text-primary"
                          onclick={() => toggleExpanded(run.id)}
                          aria-label={expandedIds.has(run.id) ? "Collapse error" : "Expand error"}
                        >
                          {#if expandedIds.has(run.id)}
                            <CaretDown size={14} />
                          {:else}
                            <CaretRight size={14} />
                          {/if}
                        </button>
                      {/if}
                    </div>
                    {#if expandedIds.has(run.id)}
                      <pre
                        class="overflow-x-auto whitespace-pre-wrap rounded-md bg-base/60 p-3 font-mono text-xs text-status-error">{run.error}</pre>
                    {/if}
                  </div>
                {:else}
                  <span class="text-faint">—</span>
                {/if}
              </td>
              <td class="px-4 py-3">
                {#if run.trace_id}
                  <div class="flex items-center gap-2">
                    <code class="font-mono text-xs text-secondary">{run.trace_id}</code>
                    <button
                      type="button"
                      class="rounded-md border border-border bg-elevated p-1 text-tertiary hover:border-cyan/40 hover:text-primary"
                      onclick={() => void copyTraceId(run.trace_id!)}
                      aria-label="Copy trace ID"
                    >
                      <Copy size={14} />
                    </button>
                  </div>
                {:else}
                  <span class="text-faint">—</span>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    {#if hasMore}
      <div class="flex justify-center">
        <button
          type="button"
          onclick={() => void loadRuns(false)}
          disabled={loadingMore}
          class="rounded-md border border-cyan/30 bg-cyan/10 px-4 py-2 text-sm font-medium text-cyan hover:bg-cyan/20 disabled:cursor-not-allowed disabled:border-border disabled:bg-muted disabled:text-tertiary"
        >
          {loadingMore ? "Loading..." : "Load more"}
        </button>
      </div>
    {/if}
  {/if}
</div>
