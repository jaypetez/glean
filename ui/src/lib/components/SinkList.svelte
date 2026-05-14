<script lang="ts">
  import XIcon from "@phosphor-icons/svelte/lib/XIcon";

  interface Props {
    sinks: Array<Record<string, unknown>> | null | undefined;
  }
  let { sinks = $bindable() }: Props = $props();

  const SINK_TYPES = ["telegram", "discord", "slack", "ntfy", "webhook", "file"] as const;

  function addSink(type: string) {
    const defaults: Record<string, Record<string, unknown>> = {
      telegram: { type: "telegram", chat_id: "" },
      discord: { type: "discord", webhook_url: "" },
      slack: { type: "slack", webhook_url: "" },
      ntfy: { type: "ntfy", topic: "" },
      webhook: { type: "webhook", url: "" },
      file: { type: "file", path: "/data/glean.jsonl", format: "jsonl" },
    };
    const arr = sinks ?? [];
    sinks = [...arr, defaults[type]];
  }

  function removeSink(i: number) {
    if (!sinks) return;
    sinks = sinks.filter((_, idx) => idx !== i);
    if (sinks.length === 0) sinks = null;
  }

  function updateField(i: number, key: string, value: string) {
    if (!sinks) return;
    const next = [...sinks];
    next[i] = { ...next[i], [key]: value };
    sinks = next;
  }

  function fieldsForType(s: Record<string, unknown>): string[] {
    const t = s.type as string;
    return (
      {
        telegram: ["chat_id"],
        discord: ["webhook_url"],
        slack: ["webhook_url"],
        ntfy: ["topic"],
        webhook: ["url"],
        file: ["path", "format"],
      }[t] ?? []
    );
  }
</script>

<div class="rounded-lg border border-border bg-surface p-5">
  <header class="mb-3 flex items-center justify-between">
    <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Sinks (fan-out)</h2>
    <div class="flex items-center gap-2 text-xs">
      <label class="text-tertiary" for="add-sink">Add</label>
      <select
        id="add-sink"
        class="rounded-md border border-border bg-elevated px-2 py-1 text-secondary focus:outline-none focus:ring-2 focus:ring-cyan"
        onchange={(e) => {
          const target = e.currentTarget as HTMLSelectElement;
          if (target.value) {
            addSink(target.value);
            target.value = "";
          }
        }}
      >
        <option value="">+ sink...</option>
        {#each SINK_TYPES as s}
          <option value={s}>{s}</option>
        {/each}
      </select>
    </div>
  </header>

  {#if !sinks || sinks.length === 0}
    <p class="text-sm text-faint">
      No sinks yet. Add one above, or use the legacy <code class="font-mono text-tertiary"
        >chat_id</code
      > field for a single Telegram sink.
    </p>
  {:else}
    <ul class="space-y-3">
      {#each sinks as sink, i}
        <li class="rounded-md border border-border bg-elevated p-3">
          <div class="mb-2 flex items-center justify-between">
            <span
              class="rounded-full bg-cyan/15 border border-cyan/30 px-2 py-0.5 text-xs font-mono text-cyan"
            >
              {sink.type}
            </span>
            <button
              type="button"
              class="rounded p-1 text-tertiary hover:bg-status-error/20 hover:text-status-error"
              onclick={() => removeSink(i)}
              aria-label="Remove sink"><XIcon size={14} aria-hidden="true" /></button
            >
          </div>
          {#each fieldsForType(sink) as field}
            <label class="mb-2 block">
              <span class="block text-xs text-tertiary mb-1">{field}</span>
              <input
                type="text"
                value={(sink[field] ?? "") as string}
                oninput={(e) => updateField(i, field, (e.currentTarget as HTMLInputElement).value)}
                class="w-full rounded-md border border-border bg-base px-2 py-1.5 font-mono text-xs text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan"
              />
            </label>
          {/each}
        </li>
      {/each}
    </ul>
  {/if}
</div>
