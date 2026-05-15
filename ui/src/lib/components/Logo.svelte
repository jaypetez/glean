<script lang="ts">
  interface Props {
    variant?: "mark" | "horizontal" | "vertical";
    /** Tailwind size class — e.g. 'h-8' for the mark, 'h-12' for horizontal */
    class?: string;
    /** Override aria-label; defaults to "glean" */
    label?: string;
  }

  let { variant = "mark", class: cls = "h-8", label = "glean" }: Props = $props();
</script>

{#if variant === "mark"}
  <svg viewBox="0 0 64 64" class={cls} role="img" aria-label={label}>
    <title>{label}</title>
    <path
      d="M 32 10 A 22 22 0 1 0 54 32"
      fill="none"
      stroke="currentColor"
      stroke-width="6"
      stroke-linecap="round"
    />
    <path
      d="M 54 32 L 40 32"
      fill="none"
      stroke="currentColor"
      stroke-width="6"
      stroke-linecap="round"
    />
    <circle cx="28" cy="28" r="4" fill="currentColor" />
  </svg>
{:else if variant === "horizontal"}
  <svg viewBox="0 0 240 64" class={cls} role="img" aria-label={label}>
    <title>{label}</title>
    <g class="text-cyan">
      <path
        d="M 32 10 A 22 22 0 1 0 54 32"
        fill="none"
        stroke="currentColor"
        stroke-width="6"
        stroke-linecap="round"
      />
      <path
        d="M 54 32 L 40 32"
        fill="none"
        stroke="currentColor"
        stroke-width="6"
        stroke-linecap="round"
      />
      <circle cx="28" cy="28" r="4" fill="currentColor" />
    </g>
    <text
      x="76"
      y="44"
      font-family="Inter, 'Inter Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
      font-size="36"
      font-weight="600"
      letter-spacing="-0.02em"
      fill="currentColor"
      class="text-primary">glean</text
    >
  </svg>
{:else}
  <svg viewBox="0 0 200 200" class={cls} role="img" aria-label={label}>
    <title>{label}</title>
    <g class="text-cyan" transform="translate(52 28) scale(1.5)">
      <path
        d="M 32 10 A 22 22 0 1 0 54 32"
        fill="none"
        stroke="currentColor"
        stroke-width="6"
        stroke-linecap="round"
      />
      <path
        d="M 54 32 L 40 32"
        fill="none"
        stroke="currentColor"
        stroke-width="6"
        stroke-linecap="round"
      />
      <circle cx="28" cy="28" r="4" fill="currentColor" />
    </g>
    <text
      x="100"
      y="178"
      text-anchor="middle"
      font-family="Inter, 'Inter Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
      font-size="32"
      font-weight="600"
      letter-spacing="-0.02em"
      fill="currentColor"
      class="text-primary">glean</text
    >
  </svg>
{/if}
