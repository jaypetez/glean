<script lang="ts">
  import { onMount } from "svelte";
  import { navigate } from "svelte-routing";
  import { getFeedStatus, runFeedNow } from "../api";
  import Breadcrumbs from "../components/Breadcrumbs.svelte";
  import DigestsTab from "../components/feed-detail/DigestsTab.svelte";
  import EditTab from "../components/feed-detail/EditTab.svelte";
  import OverviewTab from "../components/feed-detail/OverviewTab.svelte";
  import RunsTab from "../components/feed-detail/RunsTab.svelte";
  import { subscribeEvents, type AppEvent, type EventSubscription } from "../sse";
  import type { FeedStatus } from "../types";

  type Tab = "overview" | "digests" | "runs" | "edit";

  interface Props {
    name: string;
    defaultTab?: Tab;
  }

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "digests", label: "Digests" },
    { id: "runs", label: "Runs" },
    { id: "edit", label: "Edit" },
  ];

  let { name, defaultTab = "overview" }: Props = $props();
  let status: FeedStatus | null = $state(null);
  let loading = $state(true);
  let running = $state(false);
  let error: string | null = $state(null);
  let hashTab: Tab | null = $state(typeof window === "undefined" ? null : readHashTab());

  const activeTab = $derived(hashTab ?? defaultTab);

  onMount(() => {
    void loadStatus();
    hashTab = readHashTab();
    const onHashChange = () => {
      hashTab = readHashTab();
    };
    window.addEventListener("hashchange", onHashChange);

    const subscription: EventSubscription = subscribeEvents({
      onEvent: applyRunEvent,
    });

    return () => {
      window.removeEventListener("hashchange", onHashChange);
      subscription.close();
    };
  });

  async function loadStatus(): Promise<void> {
    loading = true;
    error = null;
    try {
      status = await getFeedStatus(name);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  function isTab(value: string): value is Tab {
    return tabs.some((tab) => tab.id === value);
  }

  function readHashTab(): Tab | null {
    const value = window.location.hash.replace(/^#/, "").trim();
    return isTab(value) ? value : null;
  }

  function selectTab(tab: Tab): void {
    hashTab = tab;
    const encodedName = encodeURIComponent(name);
    if (tab === "overview") {
      navigate(`/feeds/${encodedName}`);
      return;
    }
    if (tab === "edit") {
      navigate(`/feeds/${encodedName}/edit`);
      return;
    }
    navigate(`/feeds/${encodedName}#${tab}`);
  }

  function tabLabel(tab: Tab): string {
    return tabs.find((candidate) => candidate.id === tab)?.label ?? tab;
  }

  function breadcrumbItems(): Array<{ label: string; href?: string }> {
    const items: Array<{ label: string; href?: string }> = [
      { label: "Home", href: "/" },
      { label: "Feeds", href: "/feeds" },
      { label: name },
    ];
    if (activeTab !== "overview") {
      items.push({ label: tabLabel(activeTab) });
    }
    return items;
  }

  function applyRunEvent(event: AppEvent): void {
    if (event.type === "digest.persisted" || event.feed !== name) return;

    if (event.type === "run_started") {
      running = true;
      if (status) {
        status = {
          ...status,
          last_attempt_at: event.timestamp,
        };
      }
      return;
    }

    running = false;
    if (!status) {
      void loadStatus();
      return;
    }

    if (event.type === "run_completed") {
      status = {
        ...status,
        last_success_at: event.timestamp,
        last_attempt_at: event.timestamp,
        last_error: null,
        consecutive_failures: 0,
        alert_active: false,
      };
      void loadStatus();
      return;
    }

    if (event.type === "run_failed") {
      status = {
        ...status,
        last_attempt_at: event.timestamp,
        last_error: event.error ?? "Run failed",
        consecutive_failures: Math.max(status.consecutive_failures + 1, 1),
      };
      void loadStatus();
    }
  }

  async function onRunNow(): Promise<void> {
    running = true;
    error = null;
    try {
      await runFeedNow(name);
      await loadStatus();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      await loadStatus();
    } finally {
      running = false;
    }
  }

  function statusLabel(): string {
    if (running) return "Running";
    if (loading) return "Loading";
    if (!status) return "Unavailable";
    if (status.alert_active) return "Failure";
    if (status.consecutive_failures > 0) return "Warning";
    return "Healthy";
  }

  function statusPillClass(): string {
    const base = "rounded-full border px-2.5 py-0.5 text-xs font-medium";
    if (running) return `${base} border-cyan/30 bg-cyan/15 text-cyan motion-safe:animate-pulse`;
    if (loading || !status) return `${base} border-border bg-muted text-tertiary`;
    if (status.alert_active)
      return `${base} border-status-error/40 bg-status-error/15 text-status-error`;
    if (status.consecutive_failures > 0) {
      return `${base} border-status-warn/40 bg-status-warn/15 text-status-warn`;
    }
    return `${base} border-status-ok/40 bg-status-ok/15 text-status-ok`;
  }
</script>

<div class="mx-auto max-w-6xl px-6 py-6">
  <Breadcrumbs items={breadcrumbItems()} />

  <header class="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
    <div>
      <div class="flex flex-wrap items-center gap-3">
        <h1 class="text-3xl font-semibold text-primary">{name}</h1>
        <span class={statusPillClass()}>{statusLabel()}</span>
      </div>
      <p class="mt-2 text-sm text-tertiary">
        Review feed health, digest history, run history, and editor tabs from one place.
      </p>
    </div>

    <button
      type="button"
      onclick={() => void onRunNow()}
      disabled={running}
      class="rounded-md border border-cyan/30 bg-cyan/10 px-4 py-2 text-sm font-medium text-cyan hover:bg-cyan/20 disabled:cursor-not-allowed disabled:border-border disabled:bg-muted disabled:text-tertiary"
    >
      {running ? "Running..." : "Run now"}
    </button>
  </header>

  {#if error}
    <div
      class="mb-6 rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error"
    >
      {error}
    </div>
  {/if}

  <div class="mb-6 border-b border-border" role="tablist" aria-label={`${name} sections`}>
    <div class="flex flex-wrap gap-1">
      {#each tabs as tab}
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === tab.id}
          tabindex={activeTab === tab.id ? 0 : -1}
          onclick={() => selectTab(tab.id)}
          class={activeTab === tab.id
            ? "border-b-2 border-cyan px-3 py-2 text-sm font-medium text-primary"
            : "border-b-2 border-transparent px-3 py-2 text-sm text-tertiary hover:bg-elevated hover:text-primary"}
        >
          {tab.label}
        </button>
      {/each}
    </div>
  </div>

  {#if activeTab === "overview"}
    <OverviewTab {name} {status} />
  {:else if activeTab === "digests"}
    <DigestsTab {name} />
  {:else if activeTab === "runs"}
    <RunsTab {name} />
  {:else}
    <EditTab {name} />
  {/if}
</div>
