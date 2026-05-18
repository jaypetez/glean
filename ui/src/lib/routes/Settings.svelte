<script lang="ts">
  import Tabs from "../components/Tabs.svelte";
  import Breadcrumbs from "../components/Breadcrumbs.svelte";
  import ApiAuthTab from "../components/settings/ApiAuthTab.svelte";
  import AppearanceTab from "../components/settings/AppearanceTab.svelte";
  import DefaultsTab from "../components/settings/DefaultsTab.svelte";
  import HealthTab from "../components/settings/HealthTab.svelte";

  type SettingsTab = "api-auth" | "defaults" | "appearance" | "health";

  const DEFAULT_TAB: SettingsTab = "api-auth";
  const tabs: Array<{ id: SettingsTab; label: string }> = [
    { id: "api-auth", label: "API & auth" },
    { id: "defaults", label: "Defaults" },
    { id: "appearance", label: "Appearance" },
    { id: "health", label: "Health" },
  ];

  let activeTab: SettingsTab = $state(DEFAULT_TAB);

  function isSettingsTab(value: string): value is SettingsTab {
    return tabs.some((tab) => tab.id === value);
  }

  function parseHash(hash: string): SettingsTab {
    const value = hash.replace(/^#/, "").trim();
    return isSettingsTab(value) ? value : DEFAULT_TAB;
  }

  function syncFromHash(): void {
    if (typeof window === "undefined") return;
    activeTab = parseHash(window.location.hash);
  }

  function changeTab(tab: SettingsTab): void {
    activeTab = tab;
    if (typeof window === "undefined") return;
    if (window.location.hash !== `#${tab}`) {
      window.location.hash = tab;
    }
  }

  function activeLabel(): string {
    return tabs.find((tab) => tab.id === activeTab)?.label ?? "Settings";
  }

  function breadcrumbItems(): Array<{ label: string; href?: string }> {
    const items: Array<{ label: string; href?: string }> = [
      { label: "Home", href: "/" },
      { label: "Settings" },
    ];
    if (activeTab !== DEFAULT_TAB) {
      items.push({ label: activeLabel() });
    }
    return items;
  }

  $effect(() => {
    if (typeof window === "undefined") return;
    syncFromHash();
    const onHashChange = () => syncFromHash();
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  });
</script>

<div class="mx-auto max-w-6xl px-6 py-6">
  <Breadcrumbs items={breadcrumbItems()} />

  <header class="mb-6">
    <h1 class="text-2xl font-semibold text-primary">Settings</h1>
    <p class="mt-2 text-sm text-tertiary">
      Manage API access, defaults, appearance, and daemon health in focused, deep-linkable tabs.
    </p>
  </header>

  <div class="-mx-6 mb-6">
    <Tabs tabs={tabs} active={activeTab} onChange={changeTab} ariaLabel="Settings sections" />
  </div>

  {#if activeTab === "api-auth"}
    <ApiAuthTab />
  {:else if activeTab === "defaults"}
    <DefaultsTab />
  {:else if activeTab === "appearance"}
    <AppearanceTab />
  {:else}
    <HealthTab />
  {/if}
</div>
