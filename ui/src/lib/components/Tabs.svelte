<script lang="ts" generics="T extends string">
  interface Props {
    tabs: Array<{ id: T; label: string }>;
    active: T;
    onChange: (id: T) => void;
    ariaLabel?: string;
  }

  let { tabs, active, onChange, ariaLabel = "Tabs" }: Props = $props();
</script>

<div class="border-b border-border">
  <nav aria-label={ariaLabel}>
    <div class="flex gap-1 px-6" role="tablist">
      {#each tabs as tab (tab.id)}
        <button
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          tabindex={active === tab.id ? 0 : -1}
          class={`border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
            active === tab.id
              ? "border-cyan text-primary"
              : "border-transparent text-tertiary hover:border-border hover:text-secondary"
          }`}
          onclick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      {/each}
    </div>
  </nav>
</div>
