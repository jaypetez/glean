<script lang="ts">
  import { Copy } from "@phosphor-icons/svelte";
  import { onMount } from "svelte";
  import { listFeedSuppressed, type FeedSuppression } from "../../api";

  const SUPPRESSED_PAGE_SIZE = 50;
  const SEMANTIC_DEDUP_DOCS_URL =
    "https://github.com/jaypetez/glean/blob/main/docs/concepts/semantic-dedup.md";

  interface Props {
    name: string;
  }

  let { name }: Props = $props();
  let suppressions: FeedSuppression[] = $state([]);
  let loading = $state(true);
  let loadingMore = $state(false);
  let hasMore = $state(false);
  let error: string | null = $state(null);
  let copyMessage: string | null = $state(null);

  onMount(() => {
    void loadSuppressions(true);
  });

  async function loadSuppressions(reset: boolean): Promise<void> {
    if (reset) {
      loading = true;
    } else {
      loadingMore = true;
    }
    error = null;

    try {
      const page = await listFeedSuppressed(name, {
        limit: SUPPRESSED_PAGE_SIZE,
        // Cursor uses the last row id; backend sorts by suppressed_at DESC, id DESC.
        before: reset ? undefined : suppressions.at(-1)?.id,
      });
      suppressions = reset ? page : [...suppressions, ...page];
      hasMore = page.length === SUPPRESSED_PAGE_SIZE;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
      loadingMore = false;
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

  function similarityBadgeClass(similarity: number): string {
    const base = "rounded-full border px-2 py-0.5 text-xs font-medium";
    if (similarity >= 0.95) {
      return `${base} border-status-ok/40 bg-status-ok/15 text-status-ok`;
    }
    if (similarity >= 0.85) {
      return `${base} border-status-warn/40 bg-status-warn/15 text-status-warn`;
    }
    return `${base} border-orange-500/40 bg-orange-500/15 text-orange-400`;
  }

  function formatSimilarity(value: number): string {
    return value.toFixed(2);
  }

  function displayTitle(title: string | null, url: string): string {
    const trimmed = title?.trim();
    return trimmed && trimmed.length > 0 ? trimmed : url;
  }

  function safeExternalUrl(value: string): string | null {
    try {
      const parsed = new URL(value);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") {
        return parsed.toString();
      }
    } catch {
      return null;
    }
    return null;
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
  <div>
    <h2 class="text-lg font-semibold text-primary">Suppressed by semantic dedup</h2>
    <p class="text-sm text-tertiary">
      Recent items this feed skipped because they closely matched an earlier item.
    </p>
  </div>

  {#if copyMessage}
    <div class="rounded-md border border-status-ok/40 bg-status-ok/10 px-3 py-2 text-sm text-status-ok">
      {copyMessage}
    </div>
  {/if}

  {#if error}
    <div class="rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error">
      {error}
    </div>
  {/if}

  {#if loading}
    <p class="text-sm text-tertiary">Loading suppressions...</p>
  {:else if suppressions.length === 0}
    <div class="rounded-xl border border-dashed border-border bg-surface p-8 text-center">
      <h3 class="text-lg font-semibold text-primary">Nothing suppressed yet</h3>
      <p class="mt-2 text-sm text-tertiary">
        No suppressions yet for this feed. Either no near-duplicates have appeared, or the
        <code class="rounded bg-elevated px-1 py-0.5 font-mono text-xs text-secondary"
          >semantic_dedup</code
        >
        stage isn't in this feed's pipeline. See
        <a
          class="text-cyan hover:underline"
          href={SEMANTIC_DEDUP_DOCS_URL}
          target="_blank"
          rel="noreferrer">docs/concepts/semantic-dedup.md</a
        >.
      </p>
    </div>
  {:else}
    <div class="overflow-x-auto rounded-xl border border-border bg-surface shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-base/60 text-left text-xs uppercase tracking-wide text-tertiary">
          <tr>
            <th class="px-4 py-3 font-medium">When</th>
            <th class="px-4 py-3 font-medium">Suppressed</th>
            <th class="px-4 py-3 font-medium">Matched</th>
            <th class="px-4 py-3 font-medium">Similarity</th>
            <th class="px-4 py-3 font-medium">trace_id</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border">
          {#each suppressions as suppression (suppression.id)}
            {@const suppressedHref = safeExternalUrl(suppression.suppressed_url)}
            {@const matchedHref = safeExternalUrl(suppression.matched_url)}
            <tr class="align-top">
              <td class="px-4 py-3 text-secondary">
                <time
                  datetime={suppression.suppressed_at}
                  title={formatAbsoluteTime(suppression.suppressed_at)}
                >
                  {formatRelativeTime(suppression.suppressed_at)}
                </time>
              </td>
              <td class="px-4 py-3">
                <div class="max-w-sm space-y-1">
                  {#if suppressedHref}
                    <a
                      href={suppressedHref}
                      target="_blank"
                      rel="noreferrer"
                      class="font-medium text-primary hover:text-cyan hover:underline"
                    >
                      {displayTitle(suppression.suppressed_title, suppression.suppressed_url)}
                    </a>
                  {:else}
                    <span class="font-medium text-primary">
                      {displayTitle(suppression.suppressed_title, suppression.suppressed_url)}
                    </span>
                  {/if}
                  <div
                    class="max-w-sm truncate font-mono text-xs text-tertiary"
                    title={suppression.suppressed_url}
                  >
                    {suppression.suppressed_url}
                  </div>
                </div>
              </td>
              <td class="px-4 py-3">
                <div class="max-w-sm space-y-1">
                  {#if matchedHref}
                    <a
                      href={matchedHref}
                      target="_blank"
                      rel="noreferrer"
                      class="font-medium text-primary hover:text-cyan hover:underline"
                    >
                      {displayTitle(suppression.matched_title, suppression.matched_url)}
                    </a>
                  {:else}
                    <span class="font-medium text-primary">
                      {displayTitle(suppression.matched_title, suppression.matched_url)}
                    </span>
                  {/if}
                  <div
                    class="max-w-sm truncate font-mono text-xs text-tertiary"
                    title={suppression.matched_url}
                  >
                    {suppression.matched_url}
                  </div>
                </div>
              </td>
              <td class="px-4 py-3">
                <span class={similarityBadgeClass(suppression.similarity)}>
                  {formatSimilarity(suppression.similarity)}
                </span>
              </td>
              <td class="px-4 py-3">
                {#if suppression.trace_id}
                  <button
                    type="button"
                    class="flex items-center gap-2 rounded-md border border-border bg-elevated px-2 py-1 text-left hover:border-cyan/40 hover:text-primary"
                    onclick={() => void copyTraceId(suppression.trace_id!)}
                    aria-label="Copy trace ID"
                  >
                    <code class="font-mono text-xs text-secondary">{suppression.trace_id}</code>
                    <Copy size={14} aria-hidden="true" />
                  </button>
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
          onclick={() => void loadSuppressions(false)}
          disabled={loadingMore}
          class="rounded-md border border-cyan/30 bg-cyan/10 px-4 py-2 text-sm font-medium text-cyan hover:bg-cyan/20 disabled:cursor-not-allowed disabled:border-border disabled:bg-muted disabled:text-tertiary"
        >
          {loadingMore ? "Loading..." : "Load more"}
        </button>
      </div>
    {/if}
  {/if}
</div>
