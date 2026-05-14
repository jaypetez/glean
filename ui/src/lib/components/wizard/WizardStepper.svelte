<script lang="ts">
  interface Props {
    steps: string[];
    current: number;
  }

  let { steps, current }: Props = $props();
</script>

<nav aria-label="Setup progress" class="mb-8">
  <ol class="flex items-center gap-2">
    {#each steps as step, index}
      <li class="flex flex-1 items-center gap-2">
        <div
          class={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-sm font-semibold ${
            index <= current
              ? "border-cyan bg-cyan text-base"
              : "border-border bg-elevated text-tertiary"
          }`}
          aria-current={index === current ? "step" : undefined}
        >
          {index + 1}
        </div>
        <span class={`hidden text-sm sm:inline ${index === current ? "text-primary" : "text-tertiary"}`}>
          {step}
        </span>
        {#if index < steps.length - 1}
          <span class="h-px flex-1 bg-border" aria-hidden="true"></span>
        {/if}
      </li>
    {/each}
  </ol>
</nav>
