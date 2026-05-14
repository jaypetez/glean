<script lang="ts">
  import { onMount } from "svelte";
  import { navigate } from "svelte-routing";
  import { createSkill, deleteSkill, getSkill, updateSkill } from "../api";
  import type { SkillConfig, SkillFieldType } from "../types";
  import { SKILL_FIELD_TYPES } from "../types";

  interface Props {
    mode: "create" | "edit";
    name?: string;
  }
  let { mode, name }: Props = $props();

  let skill: SkillConfig = $state({
    name: "",
    version: "1",
    prompt: "Extract from:\nTITLE: {title}\nBODY: {body}",
    output_schema: { summary: "str" },
  });

  let loading = $state(true);
  let saving = $state(false);
  let error: string | null = $state(null);

  type SchemaRow = { field: string; type: SkillFieldType };
  let schemaRows: SchemaRow[] = $state([]);

  function schemaRowsFromSkill(value: SkillConfig): SchemaRow[] {
    return Object.entries(value.output_schema).map(([field, def]) => ({
      field,
      type: typeof def === "string" ? def : def.type,
    }));
  }

  onMount(async () => {
    if (mode === "edit" && name) {
      try {
        skill = await getSkill(name);
        schemaRows = schemaRowsFromSkill(skill);
      } catch (e) {
        error = e instanceof Error ? e.message : String(e);
      } finally {
        loading = false;
      }
    } else {
      skill.name = name ?? "";
      schemaRows = schemaRowsFromSkill(skill);
      loading = false;
    }
  });

  function addField() {
    schemaRows = [...schemaRows, { field: "", type: "str" }];
  }

  function removeField(i: number) {
    schemaRows = schemaRows.filter((_, idx) => idx !== i);
  }

  function buildOutputSchema(): Record<string, SkillFieldType> {
    const out: Record<string, SkillFieldType> = {};
    for (const row of schemaRows) {
      const key = row.field.trim();
      if (key) out[key] = row.type;
    }
    return out;
  }

  async function onSave() {
    if (!skill.name.trim()) {
      error = "Skill name is required";
      return;
    }
    if (!skill.prompt.trim()) {
      error = "Prompt is required";
      return;
    }
    const output_schema = buildOutputSchema();
    if (Object.keys(output_schema).length === 0) {
      error = "Output schema must have at least one field";
      return;
    }
    saving = true;
    error = null;
    try {
      const payload: SkillConfig = { ...skill, output_schema };
      if (mode === "create") {
        await createSkill(payload);
      } else {
        await updateSkill(name!, payload);
      }
      navigate("/skills");
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }

  async function onDelete() {
    if (mode !== "edit" || !name) return;
    if (!confirm(`Delete skill ${name}? This cannot be undone.`)) return;
    saving = true;
    try {
      await deleteSkill(name);
      navigate("/skills");
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }
</script>

<div class="mx-auto max-w-4xl px-6 py-6">
  <header class="mb-6 flex items-center justify-between">
    <div>
      <h1 class="text-2xl font-semibold text-primary">
        {mode === "create" ? "New skill" : "Edit skill"}
      </h1>
      {#if mode === "edit" && name}
        <p class="font-mono text-sm text-tertiary">{name}</p>
      {/if}
    </div>
    <div class="flex gap-2">
      {#if mode === "edit"}
        <button
          type="button"
          onclick={onDelete}
          class="rounded-md border border-status-error/40 px-3 py-1.5 text-sm text-status-error hover:bg-status-error/10"
          disabled={saving}>Delete</button
        >
      {/if}
      <button
        type="button"
        onclick={() => navigate("/skills")}
        class="rounded-md border border-border px-3 py-1.5 text-sm text-secondary hover:bg-elevated"
        disabled={saving}>Cancel</button
      >
      <button
        type="button"
        onclick={onSave}
        class="rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-base hover:bg-cyan-light disabled:opacity-50"
        disabled={saving}
      >
        {saving ? "Saving…" : mode === "create" ? "Create skill" : "Save changes"}
      </button>
    </div>
  </header>

  {#if loading}
    <p class="text-tertiary">Loading…</p>
  {:else}
    <div class="space-y-4">
      <div class="rounded-lg border border-border bg-surface p-5">
        <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-tertiary">Basics</h2>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label class="block">
            <span class="block text-xs text-tertiary mb-1">Name</span>
            <input
              type="text"
              bind:value={skill.name}
              disabled={mode === "edit"}
              placeholder="deal-finder"
              class="w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan disabled:opacity-50"
            />
          </label>
          <label class="block">
            <span class="block text-xs text-tertiary mb-1">Version</span>
            <input
              type="text"
              bind:value={skill.version}
              placeholder="1"
              class="w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
            />
          </label>
          <label class="block sm:col-span-2">
            <span class="block text-xs text-tertiary mb-1">Description</span>
            <input
              type="text"
              value={skill.description ?? ""}
              oninput={(e) => (skill.description = (e.currentTarget as HTMLInputElement).value)}
              placeholder="Extract structured deal information"
              class="w-full rounded-md border border-border bg-elevated px-3 py-2 text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan"
            />
          </label>
        </div>
      </div>

      <div class="rounded-lg border border-border bg-surface p-5">
        <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-tertiary">Prompts</h2>
        <label class="block mb-3">
          <span class="block text-xs text-tertiary mb-1">System prompt (optional)</span>
          <textarea
            value={skill.system_prompt ?? ""}
            oninput={(e) => (skill.system_prompt = (e.currentTarget as HTMLTextAreaElement).value)}
            rows="3"
            placeholder="You are a structured-extraction assistant…"
            class="w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-xs text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan"
          ></textarea>
        </label>
        <label class="block">
          <span class="block text-xs text-tertiary mb-1">
            Prompt template <span class="text-faint"
              >(use {`{title} {body} {url} {source_name} {summary} {source_type}`} variables)</span
            >
          </span>
          <textarea
            bind:value={skill.prompt}
            rows="6"
            class="w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-xs text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
          ></textarea>
        </label>
      </div>

      <div class="rounded-lg border border-border bg-surface p-5">
        <header class="mb-3 flex items-center justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Output schema</h2>
          <button
            type="button"
            onclick={addField}
            class="rounded-md border border-cyan/30 bg-cyan/10 px-2 py-1 text-xs text-cyan hover:bg-cyan/20"
          >
            + field
          </button>
        </header>
        {#if schemaRows.length === 0}
          <p class="text-sm text-faint">Add at least one output field.</p>
        {:else}
          <table class="w-full text-sm">
            <thead>
              <tr class="text-xs uppercase text-tertiary">
                <th class="text-left pb-2 pr-2" scope="col">Field name</th>
                <th class="text-left pb-2 pr-2" scope="col">Type</th>
                <th class="w-8" scope="col">Remove</th>
              </tr>
            </thead>
            <tbody>
              {#each schemaRows as row, i}
                <tr>
                  <td class="py-1 pr-2">
                    <label class="block">
                      <span class="mb-1 block text-xs text-tertiary">Field name</span>
                      <input
                        type="text"
                        bind:value={row.field}
                        placeholder="summary"
                        class="w-full rounded-md border border-border bg-elevated px-2 py-1.5 font-mono text-xs text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
                      />
                    </label>
                  </td>
                  <td class="py-1 pr-2">
                    <label class="block">
                      <span class="mb-1 block text-xs text-tertiary">Type</span>
                      <select
                        bind:value={row.type}
                        class="rounded-md border border-border bg-elevated px-2 py-1.5 font-mono text-xs text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
                      >
                        {#each SKILL_FIELD_TYPES as type}
                          <option value={type}>{type}</option>
                        {/each}
                      </select>
                    </label>
                  </td>
                  <td>
                    <button
                      type="button"
                      onclick={() => removeField(i)}
                      class="rounded p-1 text-tertiary hover:bg-status-error/20 hover:text-status-error"
                      aria-label="Remove field">×</button
                    >
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>

      {#if error}
        <div
          class="rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error"
        >
          {error}
        </div>
      {/if}
    </div>
  {/if}
</div>
