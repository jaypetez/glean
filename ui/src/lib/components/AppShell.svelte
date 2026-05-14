<script lang="ts">
  import type { Snippet } from "svelte";
  interface Props {
    children: Snippet;
  }
  let { children }: Props = $props();
</script>

<div class="flex min-h-full flex-col">
  <header class="border-b border-border bg-surface">
    <div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
      <a href="/" class="flex items-center gap-2">
        <svg viewBox="0 0 64 64" class="h-7 w-7" aria-hidden="true">
          <rect width="64" height="64" rx="12" fill="#0e1730" />
          <circle cx="32" cy="32" r="14" fill="none" stroke="#22d3ee" stroke-width="2" />
          <circle cx="32" cy="32" r="6" fill="#22d3ee" />
        </svg>
        <span class="text-lg font-semibold text-primary tracking-tight">glean</span>
      </a>
      <nav class="hidden items-center gap-1 text-sm md:flex" aria-label="Primary">
        <a
          class="rounded-md px-3 py-1.5 text-secondary hover:bg-elevated hover:text-primary"
          href="/"
        >
          Dashboard
        </a>
        <a
          class="rounded-md px-3 py-1.5 text-tertiary hover:bg-elevated hover:text-primary"
          href="/feeds"
        >
          Feeds
        </a>
        <a
          class="rounded-md px-3 py-1.5 text-tertiary hover:bg-elevated hover:text-primary"
          href="/skills"
        >
          Skills
        </a>
        <a
          class="rounded-md px-3 py-1.5 text-tertiary hover:bg-elevated hover:text-primary"
          href="/settings"
        >
          Settings
        </a>
      </nav>
    </div>
  </header>
  <main class="flex-1">
    {@render children()}
  </main>
  <footer class="border-t border-border bg-base/50 py-4">
    <div class="mx-auto max-w-6xl px-6 text-xs text-faint">
      glean — self-hosted content aggregator
    </div>
  </footer>
</div>
