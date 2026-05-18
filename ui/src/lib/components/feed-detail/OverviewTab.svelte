<script lang="ts">
  import { onMount } from "svelte";
  import { getFeedConfig, listFeedDigests } from "../../api";
  import type { FeedConfig, FeedStatus, Digest, StageSpec, StageSpecYaml } from "../../types";

  interface Props {
    name: string;
    status: FeedStatus | null;
  }

  let { name, status }: Props = $props();
  let config: FeedConfig | null = $state(null);
  let digests: Digest[] = $state([]);
  let loading = $state(true);
  let error: string | null = $state(null);

  onMount(() => {
    void loadOverview();
  });

  async function loadOverview(): Promise<void> {
    loading = true;
    error = null;
    try {
      const [nextConfig, nextDigests] = await Promise.all([
        getFeedConfig(name),
        listFeedDigests(name, { limit: 3 }),
      ]);
      config = nextConfig;
      digests = nextDigests;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  function formatDate(value: string | null): string {
    if (!value) return "Never";
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  }

  function stageLabel(stage: StageSpec | StageSpecYaml): string {
    if (typeof stage === "string") return stage;
    if ("name" in stage && typeof stage.name === "string") return stage.name;
    const [firstKey] = Object.keys(stage);
    return firstKey ?? "unknown";
  }

  function pluginLabel(spec: Record<string, unknown>): string {
    if (typeof spec.type === "string") return spec.type;
    if (typeof spec.provider === "string") return spec.provider;
    if (typeof spec.name === "string") return spec.name;
    return "custom";
  }

  function summarizeValue(value: unknown): string {
    if (Array.isArray(value)) {
      return value.map((item) => summarizeValue(item)).join(", ");
    }
    if (value && typeof value === "object") {
      return JSON.stringify(value);
    }
    if (value === null || value === undefined) return "null";
    return String(value);
  }

  function pluginDetails(spec: Record<string, unknown>): string {
    const fields = Object.entries(spec).filter(
      ([key]) => !["type", "provider", "name"].includes(key),
    );
    if (fields.length === 0) return "No additional settings";
    return fields.map(([key, value]) => `${key}: ${summarizeValue(value)}`).join(" · ");
  }

  function plainText(value: string): string {
    return value
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function digestPreview(digest: Digest): string {
    const preview = plainText(digest.intro ?? digest.body);
    if (!preview) return "No preview available";
    return preview.length > 120 ? `${preview.slice(0, 120)}…` : preview;
  }
</script>

<div class="space-y-6">
  <section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Last success</p>
      <p class="mt-1 text-sm font-medium text-primary">
        {formatDate(status?.last_success_at ?? null)}
      </p>
    </div>
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Last attempt</p>
      <p class="mt-1 text-sm font-medium text-primary">
        {formatDate(status?.last_attempt_at ?? null)}
      </p>
    </div>
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Consecutive failures</p>
      <p class="mt-1 text-sm font-medium text-primary">{status?.consecutive_failures ?? "—"}</p>
    </div>
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Alert active</p>
      <p class="mt-1 text-sm font-medium text-primary">
        {status ? (status.alert_active ? "Yes" : "No") : "—"}
      </p>
    </div>
    <div class="rounded-lg border border-border bg-surface p-4">
      <p class="text-xs uppercase tracking-wide text-tertiary">Bootstrapped</p>
      <p class="mt-1 text-sm font-medium text-primary">
        {status ? (status.bootstrapped ? "Yes" : "No") : "—"}
      </p>
    </div>
  </section>

  {#if error}
    <div
      class="rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error"
    >
      {error}
    </div>
  {:else if loading}
    <p class="text-sm text-tertiary">Loading feed overview...</p>
  {:else if config}
    <div class="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <div class="grid gap-4 lg:grid-cols-2">
        <section class="rounded-xl border border-border bg-surface p-5 shadow-sm lg:col-span-2">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Schedule</h2>
          <p class="mt-3 font-mono text-sm text-primary">{config.schedule}</p>
        </section>

        <section class="rounded-xl border border-border bg-surface p-5 shadow-sm">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Sources</h2>
          {#if config.sources.length === 0}
            <p class="mt-3 text-sm text-tertiary">No sources configured.</p>
          {:else}
            <ul class="mt-3 space-y-3">
              {#each config.sources as source, index}
                <li class="rounded-lg border border-border bg-base/30 p-3">
                  <p class="font-mono text-sm text-primary">{index + 1}. {pluginLabel(source)}</p>
                  <p class="mt-1 text-xs leading-5 text-tertiary">{pluginDetails(source)}</p>
                </li>
              {/each}
            </ul>
          {/if}
        </section>

        <section class="rounded-xl border border-border bg-surface p-5 shadow-sm">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Pipeline</h2>
          <div class="mt-3 flex flex-wrap gap-2">
            {#each config.pipeline as stage}
              <span class="rounded-full bg-muted px-2 py-1 font-mono text-xs text-tertiary">
                {stageLabel(stage)}
              </span>
            {/each}
          </div>
        </section>

        <section class="rounded-xl border border-border bg-surface p-5 shadow-sm lg:col-span-2">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Sinks</h2>
          {#if (!config.sinks || config.sinks.length === 0) && !config.chat_id}
            <p class="mt-3 text-sm text-tertiary">No sinks configured.</p>
          {:else}
            <ul class="mt-3 space-y-3">
              {#if config.chat_id}
                <li class="rounded-lg border border-border bg-base/30 p-3">
                  <p class="font-mono text-sm text-primary">telegram</p>
                  <p class="mt-1 text-xs leading-5 text-tertiary">
                    chat_id: {String(config.chat_id)}
                  </p>
                </li>
              {/if}
              {#each config.sinks ?? [] as sink, index}
                <li class="rounded-lg border border-border bg-base/30 p-3">
                  <p class="font-mono text-sm text-primary">{index + 1}. {pluginLabel(sink)}</p>
                  <p class="mt-1 text-xs leading-5 text-tertiary">{pluginDetails(sink)}</p>
                </li>
              {/each}
            </ul>
          {/if}
        </section>
      </div>

      <section class="rounded-xl border border-border bg-surface p-5 shadow-sm">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">
              Latest digests
            </h2>
            <p class="mt-1 text-sm text-tertiary">
              Recent persisted digest previews for this feed.
            </p>
          </div>
          <a href="#digests" class="text-sm font-medium text-cyan hover:underline"
            >See all digests →</a
          >
        </div>

        {#if digests.length === 0}
          <div
            class="mt-4 rounded-lg border border-dashed border-border bg-base/30 p-4 text-sm text-tertiary"
          >
            No digests yet for this feed.
          </div>
        {:else}
          <ul class="mt-4 space-y-3">
            {#each digests as digest (digest.id)}
              <li class="rounded-lg border border-border bg-base/30 p-4">
                <div class="flex flex-wrap items-center gap-2">
                  <time
                    class="text-xs text-tertiary"
                    datetime={digest.sent_at}
                    title={digest.sent_at}
                  >
                    {formatDate(digest.sent_at)}
                  </time>
                  <span class="rounded-full bg-muted px-2 py-0.5 text-xs text-tertiary">
                    {digest.item_count} item{digest.item_count === 1 ? "" : "s"}
                  </span>
                </div>
                <p class="mt-2 text-sm leading-6 text-secondary">{digestPreview(digest)}</p>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    </div>
  {/if}
</div>
