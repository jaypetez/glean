<script lang="ts">
  import XIcon from "@phosphor-icons/svelte/lib/XIcon";

  interface Props {
    sources: Array<Record<string, unknown>>;
  }
  let { sources = $bindable() }: Props = $props();

  const SOURCE_TYPES = ["rss", "scraper", "hn", "reddit", "search"] as const;

  function addSource(type: string) {
    const defaults: Record<string, Record<string, unknown>> = {
      rss: { type: "rss", url: "" },
      scraper: { type: "scraper", urls: [] },
      hn: { type: "hn", query: "" },
      reddit: { type: "reddit", subreddit: "" },
      search: { type: "search", query: "", engine: "searxng" },
    };
    sources = [...sources, defaults[type]];
  }

  function removeSource(i: number) {
    sources = sources.filter((_, idx) => idx !== i);
  }

  function updateField(i: number, key: string, value: string | string[]) {
    const next = [...sources];
    next[i] = { ...next[i], [key]: value };
    sources = next;
  }

  function arrayText(value: unknown): string {
    return Array.isArray(value) ? value.map(String).join("\n") : String(value ?? "");
  }

  function parseLines(value: string): string[] {
    return value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
  }

  function fieldsForType(s: Record<string, unknown>): string[] {
    const t = s.type as string;
    return (
      {
        rss: ["url"],
        scraper: ["urls"],
        hn: ["query"],
        reddit: ["subreddit", "sort", "timeframe"],
        search: ["query", "engine"],
      }[t] ?? []
    );
  }
</script>

<div class="rounded-lg border border-border bg-surface p-5">
  <header class="mb-3 flex items-center justify-between">
    <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Sources</h2>
    <div class="flex items-center gap-2 text-xs">
      <label class="text-tertiary" for="add-source">Add</label>
      <select
        id="add-source"
        class="rounded-md border border-border bg-elevated px-2 py-1 text-secondary focus:outline-none focus:ring-2 focus:ring-cyan"
        onchange={(e) => {
          const target = e.currentTarget as HTMLSelectElement;
          if (target.value) {
            addSource(target.value);
            target.value = "";
          }
        }}
      >
        <option value="">+ source...</option>
        {#each SOURCE_TYPES as s}
          <option value={s}>{s}</option>
        {/each}
      </select>
    </div>
  </header>

  {#if sources.length === 0}
    <p class="text-sm text-faint">No sources yet. Add one above.</p>
  {:else}
    <ul class="space-y-3">
      {#each sources as source, i}
        <li class="rounded-md border border-border bg-elevated p-3">
          <div class="mb-2 flex items-center justify-between">
            <span
              class="rounded-full bg-violet/15 border border-violet/30 px-2 py-0.5 text-xs font-mono text-violet"
            >
              {source.type}
            </span>
            <button
              type="button"
              class="rounded p-1 text-tertiary hover:bg-status-error/20 hover:text-status-error"
              onclick={() => removeSource(i)}
              aria-label="Remove source"><XIcon size={14} /></button
            >
          </div>
          {#each fieldsForType(source) as field}
            <label class="mb-2 block">
              <span class="block text-xs text-tertiary mb-1">{field}</span>
              {#if field === "urls"}
                <textarea
                  value={arrayText(source[field])}
                  rows="3"
                  oninput={(e) =>
                    updateField(
                      i,
                      field,
                      parseLines((e.currentTarget as HTMLTextAreaElement).value),
                    )}
                  class="w-full rounded-md border border-border bg-base px-2 py-1.5 font-mono text-xs text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan"
                ></textarea>
                <span class="mt-1 block text-[11px] text-faint">One URL per line</span>
              {:else}
                <input
                  type="text"
                  value={(source[field] ?? "") as string}
                  oninput={(e) =>
                    updateField(i, field, (e.currentTarget as HTMLInputElement).value)}
                  class="w-full rounded-md border border-border bg-base px-2 py-1.5 font-mono text-xs text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan"
                />
              {/if}
            </label>
          {/each}
        </li>
      {/each}
    </ul>
  {/if}
</div>
