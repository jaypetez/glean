<script lang="ts">
  import { onMount } from "svelte";
  import { navigate } from "svelte-routing";
  import { stringify as yamlStringify } from "yaml";
  import {
    createFeedConfig,
    deleteFeedConfig,
    getFeedConfig,
    updateFeedConfig,
    validateFeedConfig,
  } from "../api";
  import type { FeedConfig, StageSpecYaml } from "../types";
  import StageChain from "../components/StageChain.svelte";
  import SinkList from "../components/SinkList.svelte";
  import SourceList from "../components/SourceList.svelte";

  interface Props {
    mode: "create" | "edit";
    name?: string;
    embedded?: boolean;
    returnTo?: string;
  }
  let { mode, name, embedded = false, returnTo }: Props = $props();

  let feed: FeedConfig = $state({
    name: "",
    schedule: "every 1h",
    chat_id: "",
    sources: [],
    pipeline: ["dedup"],
  });

  let loading = $state(true);
  let saving = $state(false);
  let deleting = $state(false);
  let error: string | null = $state(null);
  let validationErrors: string[] = $state([]);

  const nameError = $derived(validateName(feed.name));
  const scheduleError = $derived(feed.schedule.trim() ? null : "Schedule is required");
  const sourcesError = $derived(feed.sources.length > 0 ? null : "At least one source is required");
  const pipelineError = $derived(
    feed.pipeline.length > 0 ? null : "At least one pipeline stage is required",
  );
  const destinationError = $derived(
    hasDestination(feed) ? null : "Add a chat ID or at least one sink",
  );
  const hasInlineErrors = $derived(
    Boolean(nameError || scheduleError || sourcesError || pipelineError || destinationError),
  );
  const yamlPreview = $derived(yamlStringify({ feeds: [stripEmpty(feed)] }));

  function validateName(value: string): string | null {
    if (!value.trim()) return "Feed name is required";
    if (!/^[a-z0-9][a-z0-9._-]*$/.test(value)) {
      return "Use lowercase letters, numbers, dots, underscores, or hyphens; start with a letter or number";
    }
    return null;
  }

  function hasDestination(f: FeedConfig): boolean {
    const hasChatId = String(f.chat_id ?? "").trim().length > 0;
    return hasChatId || Boolean(f.sinks && f.sinks.length > 0);
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function toYamlStage(spec: unknown): StageSpecYaml {
    if (typeof spec === "string") return spec;
    if (!isRecord(spec)) return "dedup";
    if (typeof spec.name === "string") {
      const params = isRecord(spec.params) ? spec.params : {};
      return Object.keys(params).length > 0 ? { [spec.name]: params } : spec.name;
    }
    return spec as StageSpecYaml;
  }

  function normalizeLoadedFeed(loaded: FeedConfig): FeedConfig {
    return {
      ...loaded,
      chat_id: loaded.chat_id == null ? "" : String(loaded.chat_id),
      pipeline: (loaded.pipeline as unknown[]).map(toYamlStage),
    };
  }

  function stripEmpty(f: FeedConfig): FeedConfig {
    const out: FeedConfig = {
      ...f,
      pipeline: (f.pipeline as unknown[]).map(toYamlStage),
    };
    if (!String(out.chat_id ?? "").trim()) delete out.chat_id;
    if (!out.sinks || out.sinks.length === 0) delete out.sinks;
    if (out.llm === null) delete out.llm;
    if (out.render === null) delete out.render;
    if (out.bootstrap === null) delete out.bootstrap;
    if (out.bootstrap_count === null) delete out.bootstrap_count;
    if (out.failure === null) delete out.failure;
    return out;
  }

  onMount(async () => {
    if (mode === "create") {
      loading = false;
      return;
    }
    if (!name) {
      error = "Feed name is required";
      loading = false;
      return;
    }
    try {
      feed = normalizeLoadedFeed(await getFeedConfig(name));
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  });

  async function onValidate() {
    validationErrors = [];
    error = null;
    try {
      const result = await validateFeedConfig(stripEmpty(feed));
      if (!result.valid) {
        validationErrors = result.errors;
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  function feedPath(feedName: string): string {
    return `/feeds/${encodeURIComponent(feedName)}`;
  }

  function cancelPath(): string {
    if (returnTo) return returnTo;
    if (mode === "create") return "/feeds";
    return name ? feedPath(name) : "/feeds";
  }

  async function onSave() {
    if (hasInlineErrors) {
      error = "Resolve the highlighted fields before saving";
      return;
    }
    saving = true;
    error = null;
    validationErrors = [];
    try {
      const prepared = stripEmpty(feed);
      if (mode === "create") {
        await createFeedConfig(prepared);
        navigate(feedPath(prepared.name));
      } else {
        await updateFeedConfig(name!, prepared);
        navigate(cancelPath());
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }

  async function onDelete() {
    if (!name || !window.confirm(`Delete feed ${name}?`)) return;
    deleting = true;
    error = null;
    validationErrors = [];
    try {
      await deleteFeedConfig(name);
      navigate("/feeds");
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      deleting = false;
    }
  }

  function onCancel() {
    navigate(cancelPath());
  }
</script>

<div class={embedded ? "space-y-6" : "mx-auto max-w-7xl px-6 py-6"}>
  <header
    class={`mb-6 flex items-center justify-between gap-4 ${embedded ? "rounded-lg border border-border bg-surface p-4" : ""}`}
  >
    {#if embedded}
      <p class="text-sm text-tertiary">
        Editing <span class="font-mono text-primary">{name}</span>
      </p>
    {:else}
      <div>
        <h1 class="text-2xl font-semibold text-primary">
          {mode === "create" ? "New feed" : "Edit feed"}
        </h1>
        {#if mode === "edit" && name}
          <p class="font-mono text-sm text-tertiary">{name}</p>
        {/if}
      </div>
    {/if}
    <div class="flex flex-wrap justify-end gap-2">
      {#if mode === "edit"}
        <button
          type="button"
          onclick={onDelete}
          class="rounded-md border border-status-error/40 bg-status-error/10 px-3 py-1.5 text-sm text-status-error hover:bg-status-error/20"
          disabled={saving || deleting}>{deleting ? "Deleting..." : "Delete"}</button
        >
      {/if}
      <button
        type="button"
        onclick={onCancel}
        class="rounded-md border border-border px-3 py-1.5 text-sm text-secondary hover:bg-elevated"
        disabled={saving || deleting}>Cancel</button
      >
      <button
        type="button"
        onclick={onValidate}
        class="rounded-md border border-cyan/30 bg-cyan/10 px-3 py-1.5 text-sm text-cyan hover:bg-cyan/20"
        disabled={saving || deleting}>Validate</button
      >
      <button
        type="button"
        onclick={onSave}
        class="rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-base hover:bg-cyan-light disabled:cursor-not-allowed disabled:opacity-50"
        disabled={saving || deleting || hasInlineErrors}
      >
        {saving ? "Saving..." : mode === "create" ? "Create feed" : "Save changes"}
      </button>
    </div>
  </header>

  {#if loading}
    <div class="rounded-lg border border-border bg-surface p-6 text-tertiary">Loading feed...</div>
  {:else}
    <div class="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
      <div class="space-y-4">
        <div class="rounded-lg border border-border bg-surface p-5">
          <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-tertiary">Basics</h2>
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label class="block">
              <span class="mb-1 block text-xs text-tertiary">Name</span>
              <input
                type="text"
                bind:value={feed.name}
                disabled={mode === "edit"}
                placeholder="ai-news-daily"
                aria-invalid={Boolean(nameError)}
                class="w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan disabled:opacity-50 aria-invalid:border-status-error/60"
              />
              {#if nameError}
                <p class="mt-1 text-xs text-status-error">{nameError}</p>
              {/if}
            </label>
            <label class="block">
              <span class="mb-1 block text-xs text-tertiary">Schedule</span>
              <input
                type="text"
                bind:value={feed.schedule}
                placeholder="every 1h"
                aria-invalid={Boolean(scheduleError)}
                class="w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan aria-invalid:border-status-error/60"
              />
              {#if scheduleError}
                <p class="mt-1 text-xs text-status-error">{scheduleError}</p>
              {/if}
            </label>
            <label class="block sm:col-span-2">
              <span class="mb-1 block text-xs text-tertiary">
                Chat ID <span class="text-faint"
                  >(legacy shorthand for a single Telegram sink — leave blank if using sinks below)</span
                >
              </span>
              <input
                type="text"
                bind:value={feed.chat_id}
                placeholder={"${TELEGRAM_CHAT_AI}"}
                aria-invalid={Boolean(destinationError)}
                class="w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan aria-invalid:border-status-error/60"
              />
              {#if destinationError}
                <p class="mt-1 text-xs text-status-error">{destinationError}</p>
              {/if}
            </label>
          </div>
        </div>

        <SourceList bind:sources={feed.sources} />
        {#if sourcesError}
          <p
            class="-mt-2 rounded-md border border-status-error/40 bg-status-error/10 px-3 py-2 text-xs text-status-error"
          >
            {sourcesError}
          </p>
        {/if}

        <StageChain bind:pipeline={feed.pipeline} />
        {#if pipelineError}
          <p
            class="-mt-2 rounded-md border border-status-error/40 bg-status-error/10 px-3 py-2 text-xs text-status-error"
          >
            {pipelineError}
          </p>
        {/if}

        <SinkList bind:sinks={feed.sinks} />

        {#if validationErrors.length > 0}
          <div class="rounded-lg border border-status-error/50 bg-status-error/10 p-4">
            <h3 class="text-sm font-semibold text-status-error">Validation errors</h3>
            <ul class="mt-2 space-y-1 text-sm text-status-error">
              {#each validationErrors as err}
                <li class="font-mono">{err}</li>
              {/each}
            </ul>
          </div>
        {/if}

        {#if error}
          <div
            class="rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error"
          >
            {error}
          </div>
        {/if}
      </div>

      <aside class="sticky top-6 self-start">
        <div class="rounded-lg border border-border bg-surface">
          <header class="flex items-center justify-between border-b border-border px-4 py-2.5">
            <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">
              YAML preview
            </h2>
            <span class="font-mono text-xs text-faint">live</span>
          </header>
          <pre class="overflow-x-auto p-4 font-mono text-xs leading-relaxed text-secondary"><code
              >{yamlPreview}</code
            ></pre>
        </div>
      </aside>
    </div>
  {/if}
</div>
