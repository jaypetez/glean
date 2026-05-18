<script lang="ts">
  import { CaretRight } from "@phosphor-icons/svelte";
  import { Link } from "svelte-routing";

  interface BreadcrumbItem {
    label: string;
    href?: string;
  }

  interface Props {
    items: BreadcrumbItem[];
  }

  let { items }: Props = $props();
</script>

<nav aria-label="Breadcrumb" class="mb-4">
  <ol class="flex flex-wrap items-center gap-1.5 text-sm text-tertiary">
    {#each items as item, index}
      {#if index > 0}
        <li aria-hidden="true" class="text-faint">
          <CaretRight size={14} />
        </li>
      {/if}
      <li>
        {#if item.href}
          <Link to={item.href} class="transition hover:text-primary">{item.label}</Link>
        {:else}
          <span class="font-medium text-primary">{item.label}</span>
        {/if}
      </li>
    {/each}
  </ol>
</nav>
