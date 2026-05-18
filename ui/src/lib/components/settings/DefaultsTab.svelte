<script lang="ts">
  import { onMount } from "svelte";
  import { getDefaults } from "../../api";
  import type { Defaults } from "../../types";

  let loading = $state(true);
  let error = $state<string | null>(null);
  let defaults = $state<Defaults | null>(null);

  function displayValue(value: string | number | null | undefined): string {
    if (value === null || value === undefined || value === "") return "Not set";
    return String(value);
  }

  function boolLabel(value: boolean | undefined): string {
    return value ? "Enabled" : "Disabled";
  }

  async function loadDefaults(): Promise<void> {
    loading = true;
    error = null;
    try {
      defaults = await getDefaults();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    void loadDefaults();
  });
</script>

<div class="space-y-4">
  {#if loading}
    <p class="text-tertiary">Loading defaults…</p>
  {:else if error}
    <div class="rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error">
      {error}
    </div>
  {:else if defaults}
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <section class="rounded-lg border border-border bg-surface p-5">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">LLM defaults</h2>
        <dl class="mt-4 space-y-3 text-sm">
          <div>
            <dt class="text-tertiary">Provider</dt>
            <dd class="mt-1 font-mono text-primary">{displayValue(defaults.llm.provider)}</dd>
          </div>
          <div>
            <dt class="text-tertiary">Model</dt>
            <dd class="mt-1 font-mono text-primary">{displayValue(defaults.llm.model)}</dd>
          </div>
          <div>
            <dt class="text-tertiary">Base URL</dt>
            <dd class="mt-1 break-all font-mono text-primary">{displayValue(defaults.llm.base_url)}</dd>
          </div>
        </dl>
      </section>

      <section class="rounded-lg border border-border bg-surface p-5">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Render defaults</h2>
        <dl class="mt-4 space-y-3 text-sm">
          <div>
            <dt class="text-tertiary">Style</dt>
            <dd class="mt-1 font-mono text-primary">{displayValue(defaults.render.style ?? "html")}</dd>
          </div>
          <div>
            <dt class="text-tertiary">Max items</dt>
            <dd class="mt-1 font-mono text-primary">{displayValue(defaults.render.max_items ?? 10)}</dd>
          </div>
          <div>
            <dt class="text-tertiary">Link previews</dt>
            <dd class="mt-1 text-primary">{boolLabel(defaults.render.link_preview)}</dd>
          </div>
        </dl>
      </section>

      <section class="rounded-lg border border-border bg-surface p-5">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Feed behavior</h2>
        <dl class="mt-4 space-y-3 text-sm">
          <div>
            <dt class="text-tertiary">Bootstrap mode</dt>
            <dd class="mt-1 font-mono text-primary">{displayValue(defaults.bootstrap)}</dd>
          </div>
          <div>
            <dt class="text-tertiary">Bootstrap count</dt>
            <dd class="mt-1 font-mono text-primary">{displayValue(defaults.bootstrap_count)}</dd>
          </div>
          <div>
            <dt class="text-tertiary">Failure threshold</dt>
            <dd class="mt-1 font-mono text-primary">{displayValue(defaults.failure.alert_after ?? 3)}</dd>
          </div>
        </dl>
      </section>
    </div>

    <p class="rounded-lg border border-border bg-surface px-4 py-3 text-sm text-tertiary">
      Defaults are read-only here for now — edit <code class="rounded bg-elevated px-1 py-0.5 font-mono text-xs text-secondary">feeds.yaml</code>
      directly.
    </p>
  {/if}
</div>
