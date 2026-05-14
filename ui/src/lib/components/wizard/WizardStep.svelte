<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    title: string;
    description?: string;
    children: Snippet;
  }

  let { title, description, children }: Props = $props();
</script>

<section class="rounded-xl border border-border bg-surface p-6 shadow-sm">
  <header class="mb-6">
    <h1 class="text-2xl font-semibold text-primary">{title}</h1>
    {#if description}
      <p class="mt-2 max-w-3xl text-sm leading-6 text-tertiary">{description}</p>
    {/if}
  </header>
  {@render children()}
</section>
