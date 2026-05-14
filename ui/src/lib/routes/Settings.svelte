<script lang="ts">
  import { ArrowClockwise, Copy, Eye, EyeSlash } from "@phosphor-icons/svelte";
  import { onMount } from "svelte";
  import {
    getDefaults,
    getInitialize,
    getStoredApiKey,
    getSystemInfo,
    rotateApiKey,
    setApiKey,
    updateDefaults,
    type InitializeResponse,
  } from "../api";
  import type { Defaults, DensityChoice, SystemInfo, ThemeChoice } from "../types";
  import Dialog from "../components/Dialog.svelte";
  import { loadAppearance, saveDensity, saveTheme } from "../theme";

  type Tab = "defaults" | "api" | "appearance" | "about";
  type Provider = string;
  type RenderStyle = "html" | "markdown_v2" | "plain";

  interface SettingsForm {
    telegram: { bot_token: string; chat_id: string; ops_chat_id: string };
    llm: { provider: Provider; model: string; base_url: string; api_key: string };
    render: { style: RenderStyle; link_preview: boolean; max_items: number };
    failure: { alert_after: number };
  }

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "defaults", label: "Defaults" },
    { id: "api", label: "API Key" },
    { id: "appearance", label: "Appearance" },
    { id: "about", label: "About" },
  ];
  const providers = ["ollama", "openai", "anthropic", "openrouter"];
  const renderStyles: RenderStyle[] = ["html", "markdown_v2", "plain"];

  let activeTab: Tab = $state("defaults");
  let loading = $state(true);
  let saving = $state(false);
  let rotating = $state(false);
  let error: string | null = $state(null);
  let saveError: string | null = $state(null);
  let toast: string | null = $state(null);
  let defaults: Defaults | null = $state(null);
  let initialize: InitializeResponse | null = $state(null);
  let systemInfo: SystemInfo | null = $state(null);
  let fieldErrors: Record<string, string> = $state({});
  let advanced = $state(false);
  let showTelegramToken = $state(false);
  let showLlmKey = $state(false);
  let showCurrentApiKey = $state(false);
  let showRotateDialog = $state(false);
  let rotatedKey: string | null = $state(null);
  let currentApiKey: string | null = $state(null);
  let themeChoice: ThemeChoice = $state("system");
  let densityChoice: DensityChoice = $state("comfortable");

  let form: SettingsForm = $state({
    telegram: { bot_token: "", chat_id: "", ops_chat_id: "" },
    llm: { provider: "ollama", model: "", base_url: "", api_key: "" },
    render: { style: "html", link_preview: false, max_items: 10 },
    failure: { alert_after: 3 },
  });

  function asText(value: string | number | null | undefined): string {
    return value === null || value === undefined ? "" : String(value);
  }

  function nullableText(value: string): string | null {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }

  function providerOptions(current: string): string[] {
    if (current && !providers.includes(current)) return [current, ...providers];
    return [...providers];
  }

  function isRenderStyle(value: string): value is RenderStyle {
    return renderStyles.includes(value as RenderStyle);
  }

  function formFromDefaults(value: Defaults): SettingsForm {
    const provider = value.llm.provider;
    const style = isRenderStyle(value.render.style ?? "html") ? value.render.style ?? "html" : "html";
    return {
      telegram: {
        bot_token: asText(value.telegram?.bot_token),
        chat_id: asText(value.telegram?.chat_id),
        ops_chat_id: asText(value.failure.ops_chat_id),
      },
      llm: {
        provider,
        model: value.llm.model,
        base_url: asText(value.llm.base_url),
        api_key: asText(value.llm.api_key),
      },
      render: {
        style,
        link_preview: value.render.link_preview ?? false,
        max_items: value.render.max_items ?? 10,
      },
      failure: { alert_after: value.failure.alert_after ?? 3 },
    };
  }

  function tabId(tab: Tab): string {
    return `settings-tab-${tab}`;
  }

  function panelId(tab: Tab): string {
    return `settings-panel-${tab}`;
  }

  function fieldError(path: string): string | null {
    return fieldErrors[path] ?? null;
  }

  function showToast(message: string): void {
    toast = message;
    window.setTimeout(() => {
      if (toast === message) toast = null;
    }, 2500);
  }

  function validateDefaults(): boolean {
    const errors: Record<string, string> = {};
    if (!form.llm.provider) errors["llm.provider"] = "Choose a provider.";
    if (!form.llm.model.trim()) errors["llm.model"] = "Model name is required.";
    if (form.render.max_items < 1 || form.render.max_items > 50) {
      errors["render.max_items"] = "Enter a number from 1 to 50.";
    }
    if (form.failure.alert_after < 1) {
      errors["failure.alert_after"] = "Enter a number of 1 or greater.";
    }
    fieldErrors = errors;
    return Object.keys(errors).length === 0;
  }

  function buildDefaultsPayload(): Defaults {
    return {
      telegram: {
        bot_token: nullableText(form.telegram.bot_token),
        chat_id: nullableText(form.telegram.chat_id),
      },
      llm: {
        provider: form.llm.provider,
        model: form.llm.model.trim(),
        base_url: nullableText(form.llm.base_url),
        api_key: nullableText(form.llm.api_key),
        timeout_s: defaults?.llm.timeout_s ?? 60,
      },
      render: {
        style: form.render.style,
        link_preview: form.render.link_preview,
        max_items: Number(form.render.max_items),
      },
      bootstrap: defaults?.bootstrap ?? "skip-and-mark",
      bootstrap_count: defaults?.bootstrap_count ?? 5,
      failure: {
        alert_after: Number(form.failure.alert_after),
        ops_chat_id: nullableText(form.telegram.ops_chat_id),
      },
    };
  }

  async function saveDefaults(): Promise<void> {
    saveError = null;
    if (!validateDefaults()) return;
    saving = true;
    try {
      const payload = buildDefaultsPayload();
      await updateDefaults(payload);
      defaults = payload;
      showToast("Defaults saved.");
    } catch (e) {
      saveError = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }

  async function copyText(value: string, message: string): Promise<void> {
    await navigator.clipboard.writeText(value);
    showToast(message);
  }

  async function confirmRotate(): Promise<void> {
    if (rotating) return;
    saveError = null;
    rotating = true;
    try {
      const response = await rotateApiKey();
      setApiKey(response.api_key);
      initialize = initialize
        ? { ...initialize, api_key: response.api_key }
        : { version: "", api_key: response.api_key, auth_disabled: false };
      currentApiKey = response.api_key;
      rotatedKey = response.api_key;
      showRotateDialog = false;
      showCurrentApiKey = true;
      showToast("API key rotated.");
    } catch (e) {
      saveError = e instanceof Error ? e.message : String(e);
    } finally {
      rotating = false;
    }
  }

  async function copyRotatedAndContinue(): Promise<void> {
    if (!rotatedKey) return;
    try {
      await copyText(rotatedKey, "New API key copied.");
      rotatedKey = null;
    } catch {
      saveError = "Clipboard copy failed. Select and copy the new key manually.";
    }
  }

  function selectTheme(theme: ThemeChoice): void {
    themeChoice = theme;
    saveTheme(theme);
  }

  function selectDensity(density: DensityChoice): void {
    densityChoice = density;
    saveDensity(density);
  }

  function formatDateTime(value: string | undefined): string {
    if (!value) return "Unavailable";
    return new Date(value).toLocaleString();
  }

  function formatUptime(seconds: number | undefined): string {
    const total = Math.max(0, Math.floor(seconds ?? 0));
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    const parts = [
      days ? `${days}d` : null,
      hours ? `${hours}h` : null,
      minutes ? `${minutes}m` : null,
      `${secs}s`,
    ].filter(Boolean);
    return parts.join(" ");
  }

  onMount(async () => {
    const appearance = loadAppearance();
    themeChoice = appearance.theme;
    densityChoice = appearance.density;
    try {
      const [loadedDefaults, loadedInitialize, loadedSystemInfo] = await Promise.all([
        getDefaults(),
        getInitialize(),
        getSystemInfo(),
      ]);
      defaults = loadedDefaults;
      form = formFromDefaults(loadedDefaults);
      initialize = loadedInitialize;
      currentApiKey = loadedInitialize.api_key ?? getStoredApiKey();
      systemInfo = loadedSystemInfo;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  });
</script>

<div class="mx-auto max-w-6xl px-6 py-6">
  <header class="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
    <div>
      <h1 class="text-2xl font-semibold text-primary">Settings</h1>
      <p class="text-sm text-tertiary">Manage defaults, authentication, appearance, and runtime info.</p>
    </div>
    {#if toast}
      <div class="rounded-md border border-status-ok/40 bg-status-ok/10 px-3 py-2 text-sm text-status-ok">
        {toast}
      </div>
    {/if}
  </header>

  <div class="mb-6 border-b border-border" role="tablist" aria-label="Settings sections">
    <div class="flex flex-wrap gap-1">
      {#each tabs as tab}
        <button
          id={tabId(tab.id)}
          role="tab"
          type="button"
          aria-selected={activeTab === tab.id}
          aria-controls={panelId(tab.id)}
          tabindex={activeTab === tab.id ? 0 : -1}
          onclick={() => (activeTab = tab.id)}
          class={activeTab === tab.id
            ? "rounded-t-md border border-border border-b-surface bg-surface px-3 py-2 text-sm font-medium text-primary"
            : "rounded-t-md border border-transparent px-3 py-2 text-sm text-tertiary hover:bg-elevated hover:text-primary"}
        >
          {tab.label}
        </button>
      {/each}
    </div>
  </div>

  {#if loading}
    <p class="text-tertiary">Loading settings</p>
  {:else if error}
    <div class="rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error">
      {error}
    </div>
  {:else if activeTab === "defaults"}
    <div id={panelId("defaults")} role="tabpanel" aria-labelledby={tabId("defaults")} class="space-y-4">
      <div class="density-section rounded-lg border border-border bg-surface p-5">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Telegram defaults</h2>
        <div class="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
          <label class="block">
            <span class="mb-1 block text-xs text-tertiary">Bot token</span>
            <span class="flex rounded-md border border-border bg-elevated focus-within:ring-2 focus-within:ring-cyan">
              <input
                type={showTelegramToken ? "text" : "password"}
                bind:value={form.telegram.bot_token}
                autocomplete="off"
                class="density-control min-w-0 flex-1 bg-transparent px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none"
              />
              <button
                type="button"
                class="px-3 text-tertiary hover:text-primary"
                aria-label={showTelegramToken ? "Hide Telegram bot token" : "Show Telegram bot token"}
                onclick={() => (showTelegramToken = !showTelegramToken)}
              >
                {#if showTelegramToken}<EyeSlash size={16} aria-hidden="true" />{:else}<Eye size={16} aria-hidden="true" />{/if}
              </button>
            </span>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-tertiary">Default chat ID</span>
            <input
              type="text"
              bind:value={form.telegram.chat_id}
              placeholder="-1001234567890"
              class="density-control w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan"
            />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-tertiary">Ops chat ID</span>
            <input
              type="text"
              bind:value={form.telegram.ops_chat_id}
              placeholder="-1001234567890"
              class="density-control w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan"
            />
          </label>
        </div>
      </div>

      <div class="density-section rounded-lg border border-border bg-surface p-5">
        <div class="flex items-center justify-between gap-4">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">LLM defaults</h2>
          <label class="flex items-center gap-2 text-xs text-tertiary">
            <input type="checkbox" bind:checked={advanced} class="accent-cyan" />
            Advanced
          </label>
        </div>
        <div class="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <label class="block">
            <span class="mb-1 block text-xs text-tertiary">Provider</span>
            <select
              bind:value={form.llm.provider}
              class="density-control w-full rounded-md border border-border bg-elevated px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
            >
              {#each providerOptions(form.llm.provider) as provider}
                <option value={provider}>{provider}</option>
              {/each}
            </select>
            {#if fieldError("llm.provider")}
              <p class="mt-1 text-xs text-status-error">{fieldError("llm.provider")}</p>
            {/if}
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-tertiary">Model name</span>
            <input
              type="text"
              bind:value={form.llm.model}
              class="density-control w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan"
            />
            {#if fieldError("llm.model")}
              <p class="mt-1 text-xs text-status-error">{fieldError("llm.model")}</p>
            {/if}
          </label>
          {#if form.llm.provider === "ollama" || advanced}
            <label class="block">
              <span class="mb-1 block text-xs text-tertiary">Base URL</span>
              <input
                type="text"
                bind:value={form.llm.base_url}
                placeholder="http://ollama:11434"
                class="density-control w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan"
              />
            </label>
          {/if}
          <label class="block">
            <span class="mb-1 block text-xs text-tertiary">API key</span>
            <span class="flex rounded-md border border-border bg-elevated focus-within:ring-2 focus-within:ring-cyan">
              <input
                type={showLlmKey ? "text" : "password"}
                bind:value={form.llm.api_key}
                autocomplete="off"
                class="density-control min-w-0 flex-1 bg-transparent px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none"
              />
              <button
                type="button"
                class="px-3 text-tertiary hover:text-primary"
                aria-label={showLlmKey ? "Hide LLM API key" : "Show LLM API key"}
                onclick={() => (showLlmKey = !showLlmKey)}
              >
                {#if showLlmKey}<EyeSlash size={16} aria-hidden="true" />{:else}<Eye size={16} aria-hidden="true" />{/if}
              </button>
            </span>
          </label>
        </div>
      </div>

      <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div class="density-section rounded-lg border border-border bg-surface p-5">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Render defaults</h2>
          <div class="mt-4 space-y-4">
            <label class="block">
              <span class="mb-1 block text-xs text-tertiary">Style</span>
              <select
                bind:value={form.render.style}
                class="density-control w-full rounded-md border border-border bg-elevated px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
              >
                {#each renderStyles as style}
                  <option value={style}>{style}</option>
                {/each}
              </select>
            </label>
            <label class="flex items-center justify-between gap-4 rounded-md border border-border bg-elevated px-3 py-2">
              <span class="text-sm text-secondary">Enable link previews</span>
              <input type="checkbox" bind:checked={form.render.link_preview} class="accent-cyan" />
            </label>
            <label class="block">
              <span class="mb-1 block text-xs text-tertiary">Max items per digest</span>
              <input
                type="number"
                min="1"
                max="50"
                bind:value={form.render.max_items}
                class="density-control w-full rounded-md border border-border bg-elevated px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
              />
              {#if fieldError("render.max_items")}
                <p class="mt-1 text-xs text-status-error">{fieldError("render.max_items")}</p>
              {/if}
            </label>
          </div>
        </div>

        <div class="density-section rounded-lg border border-border bg-surface p-5">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Failure defaults</h2>
          <label class="mt-4 block">
            <span class="mb-1 block text-xs text-tertiary">Alert after consecutive failures</span>
            <input
              type="number"
              min="1"
              bind:value={form.failure.alert_after}
              class="density-control w-full rounded-md border border-border bg-elevated px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
            />
            {#if fieldError("failure.alert_after")}
              <p class="mt-1 text-xs text-status-error">{fieldError("failure.alert_after")}</p>
            {/if}
          </label>
        </div>
      </div>

      {#if saveError}
        <div class="rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error">
          {saveError}
        </div>
      {/if}
      <div class="flex justify-end">
        <button
          type="button"
          onclick={saveDefaults}
          disabled={saving}
          class="density-control rounded-md bg-cyan px-4 py-2 text-sm font-medium text-base hover:bg-cyan-light disabled:opacity-50"
        >
          {saving ? "Saving" : "Save defaults"}
        </button>
      </div>
    </div>
  {:else if activeTab === "api"}
    <div id={panelId("api")} role="tabpanel" aria-labelledby={tabId("api")} class="space-y-4">
      <div class="density-section rounded-lg border border-border bg-surface p-5">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">API key management</h2>
        <div class="mt-4 rounded-md border border-border bg-elevated p-4">
          <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p class="text-xs text-tertiary">Current API key</p>
              <p class="mt-1 break-all font-mono text-sm text-primary">
                {#if currentApiKey && showCurrentApiKey}
                  {currentApiKey}
                {:else if currentApiKey}
                  {"•".repeat(32)}
                {:else}
                  Unavailable in this browser
                {/if}
              </p>
            </div>
            <div class="flex gap-2">
              <button
                type="button"
                onclick={() => (showCurrentApiKey = !showCurrentApiKey)}
                disabled={!currentApiKey}
                class="density-control inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-secondary hover:bg-surface disabled:opacity-50"
              >
                {#if showCurrentApiKey}<EyeSlash size={16} aria-hidden="true" /> Hide{:else}<Eye size={16} aria-hidden="true" /> Show{/if}
              </button>
              <button
                type="button"
                onclick={() => currentApiKey && copyText(currentApiKey, "API key copied.")}
                disabled={!currentApiKey}
                class="density-control inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-secondary hover:bg-surface disabled:opacity-50"
              >
                <Copy size={16} aria-hidden="true" /> Copy
              </button>
            </div>
          </div>
        </div>

        <button
          type="button"
          onclick={() => (showRotateDialog = true)}
          class="density-control mt-4 inline-flex items-center gap-2 rounded-md border border-status-warn/40 bg-status-warn/10 px-3 py-2 text-sm font-medium text-status-warn hover:bg-status-warn/20"
        >
          <ArrowClockwise size={16} aria-hidden="true" /> Rotate API key
        </button>
      </div>

      {#if rotatedKey}
        <div class="rounded-lg border border-status-warn/40 bg-status-warn/10 p-4">
          <h3 class="font-semibold text-status-warn">New API key</h3>
          <p class="mt-1 text-sm text-secondary">Copy this key now. It will be hidden after you continue.</p>
          <p class="mt-3 break-all rounded-md border border-border bg-elevated p-3 font-mono text-sm text-primary">
            {rotatedKey}
          </p>
          <button
            type="button"
            onclick={copyRotatedAndContinue}
            class="density-control mt-3 inline-flex items-center gap-2 rounded-md bg-cyan px-3 py-2 text-sm font-medium text-base hover:bg-cyan-light"
          >
            <Copy size={16} aria-hidden="true" /> Copy and continue
          </button>
        </div>
      {/if}
    </div>
  {:else if activeTab === "appearance"}
    <div
      id={panelId("appearance")}
      role="tabpanel"
      aria-labelledby={tabId("appearance")}
      class="grid grid-cols-1 gap-4 lg:grid-cols-2"
    >
      <div class="density-section rounded-lg border border-border bg-surface p-5">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Theme</h2>
        <div class="mt-4 grid grid-cols-3 gap-2" role="group" aria-label="Theme">
          {#each ["system", "dark", "light"] as theme}
            <button
              type="button"
              onclick={() => selectTheme(theme as ThemeChoice)}
              class={themeChoice === theme
                ? "density-control rounded-md border border-cyan bg-cyan/15 px-3 py-2 text-sm text-cyan"
                : "density-control rounded-md border border-border bg-elevated px-3 py-2 text-sm text-secondary hover:bg-muted"}
            >
              {theme}
            </button>
          {/each}
        </div>
      </div>
      <div class="density-section rounded-lg border border-border bg-surface p-5">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Density</h2>
        <div class="mt-4 grid grid-cols-2 gap-2" role="group" aria-label="Density">
          {#each ["comfortable", "compact"] as density}
            <button
              type="button"
              onclick={() => selectDensity(density as DensityChoice)}
              class={densityChoice === density
                ? "density-control rounded-md border border-cyan bg-cyan/15 px-3 py-2 text-sm text-cyan"
                : "density-control rounded-md border border-border bg-elevated px-3 py-2 text-sm text-secondary hover:bg-muted"}
            >
              {density}
            </button>
          {/each}
        </div>
      </div>
    </div>
  {:else}
    <div id={panelId("about")} role="tabpanel" aria-labelledby={tabId("about")} class="space-y-4">
      <div class="density-section rounded-lg border border-border bg-surface p-5">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">About glean</h2>
        <dl class="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <dt class="text-xs text-tertiary">Version</dt>
            <dd class="mt-1 font-mono text-sm text-primary">{systemInfo?.version ?? initialize?.version}</dd>
          </div>
          <div>
            <dt class="text-xs text-tertiary">Hostname</dt>
            <dd class="mt-1 font-mono text-sm text-primary">{systemInfo?.hostname}</dd>
          </div>
          <div>
            <dt class="text-xs text-tertiary">Python</dt>
            <dd class="mt-1 font-mono text-sm text-primary">{systemInfo?.python}</dd>
          </div>
          <div>
            <dt class="text-xs text-tertiary">Platform</dt>
            <dd class="mt-1 font-mono text-sm text-primary">{systemInfo?.platform}</dd>
          </div>
          <div>
            <dt class="text-xs text-tertiary">Database path</dt>
            <dd class="mt-1 break-all font-mono text-sm text-primary">{systemInfo?.database_path}</dd>
          </div>
          <div>
            <dt class="text-xs text-tertiary">Config path</dt>
            <dd class="mt-1 break-all font-mono text-sm text-primary">{systemInfo?.config_path}</dd>
          </div>
          <div>
            <dt class="text-xs text-tertiary">Feeds</dt>
            <dd class="mt-1 font-mono text-sm text-primary">{systemInfo?.feeds_count ?? 0}</dd>
          </div>
          <div>
            <dt class="text-xs text-tertiary">Default LLM</dt>
            <dd class="mt-1 font-mono text-sm text-primary">
              {systemInfo?.llm_provider && systemInfo?.llm_model
                ? `${systemInfo.llm_provider} / ${systemInfo.llm_model}`
                : "Unavailable"}
            </dd>
          </div>
          <div>
            <dt class="text-xs text-tertiary">Started at</dt>
            <dd class="mt-1 font-mono text-sm text-primary">{formatDateTime(systemInfo?.started_at)}</dd>
          </div>
          <div>
            <dt class="text-xs text-tertiary">Uptime</dt>
            <dd class="mt-1 font-mono text-sm text-primary">{formatUptime(systemInfo?.uptime_seconds)}</dd>
          </div>
        </dl>
        <div class="mt-5 flex flex-wrap gap-3 text-sm">
          <a class="text-cyan hover:underline" href="https://github.com/jaypetez/glean">GitHub repo</a>
          <a class="text-cyan hover:underline" href="https://github.com/jaypetez/glean/issues/64">
            Web UI issue #64
          </a>
        </div>
      </div>
    </div>
  {/if}
</div>

<Dialog
  open={showRotateDialog}
  title="Rotate API key?"
  description="All clients, including CLI scripts, this web UI, and other browser tabs, will need the new key immediately. The new key is shown only once."
  confirmLabel={rotating ? "Rotating" : "Rotate key"}
  cancelLabel="Cancel"
  danger
  disabled={rotating}
  onconfirm={confirmRotate}
  oncancel={() => (showRotateDialog = false)}
/>
