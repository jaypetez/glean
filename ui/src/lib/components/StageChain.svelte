<script lang="ts">
  import CaretDownIcon from "@phosphor-icons/svelte/lib/CaretDownIcon";
  import CaretUpIcon from "@phosphor-icons/svelte/lib/CaretUpIcon";
  import XIcon from "@phosphor-icons/svelte/lib/XIcon";
  import type { StageSpecYaml } from "../types";

  interface Props {
    pipeline: StageSpecYaml[];
  }
  let { pipeline = $bindable() }: Props = $props();

  const KNOWN_STAGES = ["dedup", "rank", "summarize", "apply_skill", "digest"] as const;

  function stageLabel(spec: StageSpecYaml): string {
    return typeof spec === "string" ? spec : Object.keys(spec)[0];
  }

  function moveUp(i: number) {
    if (i === 0) return;
    const next = [...pipeline];
    [next[i - 1], next[i]] = [next[i], next[i - 1]];
    pipeline = next;
  }

  function moveDown(i: number) {
    if (i === pipeline.length - 1) return;
    const next = [...pipeline];
    [next[i], next[i + 1]] = [next[i + 1], next[i]];
    pipeline = next;
  }

  function removeStage(i: number) {
    pipeline = pipeline.filter((_, idx) => idx !== i);
  }

  function addStage(stageName: string) {
    if (stageName === "dedup") {
      pipeline = [...pipeline, "dedup"];
    } else {
      pipeline = [...pipeline, { [stageName]: {} }];
    }
  }
</script>

<div class="rounded-lg border border-border bg-surface p-5">
  <header class="mb-3 flex items-center justify-between">
    <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Pipeline</h2>
    <div class="flex items-center gap-2 text-xs">
      <label class="text-tertiary" for="add-stage">Add</label>
      <select
        id="add-stage"
        class="rounded-md border border-border bg-elevated px-2 py-1 text-secondary focus:outline-none focus:ring-2 focus:ring-cyan"
        onchange={(e) => {
          const target = e.currentTarget as HTMLSelectElement;
          if (target.value) {
            addStage(target.value);
            target.value = "";
          }
        }}
      >
        <option value="">+ stage...</option>
        {#each KNOWN_STAGES as s}
          <option value={s}>{s}</option>
        {/each}
      </select>
    </div>
  </header>

  {#if pipeline.length === 0}
    <p class="text-sm text-faint">No stages yet. Add one above.</p>
  {:else}
    <ol class="space-y-2">
      {#each pipeline as stage, i}
        <li class="flex items-center gap-2 rounded-md border border-border bg-elevated px-3 py-2">
          <span class="font-mono text-xs text-faint w-6">{i + 1}.</span>
          <span class="flex-1 font-mono text-sm text-secondary">{stageLabel(stage)}</span>
          <button
            type="button"
            class="rounded p-1 text-tertiary hover:bg-muted hover:text-primary disabled:opacity-30"
            disabled={i === 0}
            onclick={() => moveUp(i)}
            aria-label="Move stage up"><CaretUpIcon size={14} /></button
          >
          <button
            type="button"
            class="rounded p-1 text-tertiary hover:bg-muted hover:text-primary disabled:opacity-30"
            disabled={i === pipeline.length - 1}
            onclick={() => moveDown(i)}
            aria-label="Move stage down"><CaretDownIcon size={14} /></button
          >
          <button
            type="button"
            class="rounded p-1 text-tertiary hover:bg-status-error/20 hover:text-status-error"
            onclick={() => removeStage(i)}
            aria-label="Remove stage"><XIcon size={14} /></button
          >
        </li>
      {/each}
    </ol>
  {/if}
</div>
