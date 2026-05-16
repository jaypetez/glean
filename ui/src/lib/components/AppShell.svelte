<script lang="ts">
  import { Gear } from "@phosphor-icons/svelte";
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
        <svg viewBox="0 0 64 64" class="h-7 w-7 text-cyan" aria-hidden="true">
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
          href="/digests"
        >
          Digests
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
          class="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-tertiary hover:bg-elevated hover:text-primary"
          href="/settings"
        >
          <Gear size={16} aria-hidden="true" />
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
