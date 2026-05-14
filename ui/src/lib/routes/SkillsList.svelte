<script lang="ts">
  import { onMount } from "svelte";
  import { Link } from "svelte-routing";
  import { listSkills } from "../api";
  import type { SkillConfig } from "../types";

  let skills: SkillConfig[] = $state([]);
  let loading = $state(true);
  let error: string | null = $state(null);

  onMount(async () => {
    try {
      skills = await listSkills();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  });

  function fieldCount(skill: SkillConfig): number {
    return Object.keys(skill.output_schema).length;
  }
</script>

<div class="mx-auto max-w-6xl px-6 py-6">
  <header class="mb-6 flex items-center justify-between">
    <div>
      <h1 class="text-2xl font-semibold text-primary">Skills</h1>
      <p class="text-sm text-tertiary">Reusable structured extraction templates</p>
    </div>
    <Link
      to="/skills/new"
      class="rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-base hover:bg-cyan-light"
    >
      New skill
    </Link>
  </header>

  {#if loading}
    <p class="text-tertiary">Loading…</p>
  {:else if error}
    <div
      class="rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error"
    >
      {error}
    </div>
  {:else if skills.length === 0}
    <div class="rounded-lg border border-border bg-surface p-8 text-center">
      <p class="text-tertiary">No skills defined yet.</p>
      <p class="mt-2 text-xs text-faint">
        Skills are reusable extraction templates you can apply via the
        <code class="font-mono text-secondary">apply_skill</code> pipeline stage.
      </p>
      <Link
        to="/skills/new"
        class="mt-4 inline-block rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-base hover:bg-cyan-light"
      >
        Create your first skill
      </Link>
    </div>
  {:else}
    <ul class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
      {#each skills as skill}
        <li
          class="rounded-lg border border-border bg-surface p-4 hover:border-violet/40 transition"
        >
          <Link to={`/skills/${encodeURIComponent(skill.name)}`} class="block">
            <h2 class="font-mono text-base font-medium text-primary">{skill.name}</h2>
            {#if skill.description}
              <p class="mt-1 text-xs text-tertiary line-clamp-2">{skill.description}</p>
            {/if}
            <div class="mt-3 flex gap-3 text-xs text-faint">
              <span>{fieldCount(skill)} field{fieldCount(skill) === 1 ? "" : "s"}</span>
              {#if skill.llm}
                <span class="font-mono">{skill.llm.provider}:{skill.llm.model}</span>
              {/if}
            </div>
          </Link>
        </li>
      {/each}
    </ul>
  {/if}
</div>
