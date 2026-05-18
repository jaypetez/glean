<script lang="ts">
  import { onMount } from "svelte";
  import { navigate, Route, Router } from "svelte-routing";
  import {
    getInitialize,
    getStoredApiKey,
    listFeedConfigs,
    validateAndStoreApiKey,
    type InitializeResponse,
  } from "./lib/api";
  import AppShell from "./lib/components/AppShell.svelte";
  import Logo from "./lib/components/Logo.svelte";
  import Digests from "./lib/routes/Digests.svelte";
  import FeedDetail from "./lib/routes/FeedDetail.svelte";
  import FeedEditor from "./lib/routes/FeedEditor.svelte";
  import FeedsList from "./lib/routes/FeedsList.svelte";
  import Home from "./lib/routes/Home.svelte";
  import Settings from "./lib/routes/Settings.svelte";
  import Setup from "./lib/routes/Setup.svelte";
  import SkillEditor from "./lib/routes/SkillEditor.svelte";
  import SkillsList from "./lib/routes/SkillsList.svelte";
  import { loadAppearance } from "./lib/theme";

  let info: InitializeResponse | null = $state(null);
  let error: string | null = $state(null);
  let authReady = $state(false);
  let showApiKeyModal = $state(false);
  let apiKeyInput = $state("");
  let apiKeyError: string | null = $state(null);
  let validatingApiKey = $state(false);
  let setupChecked = $state(false);

  let url = typeof window === "undefined" ? "/" : window.location.pathname;

  async function maybeRedirectToSetup(): Promise<void> {
    if (setupChecked) return;
    setupChecked = true;
    if (
      window.location.pathname === "/" &&
      localStorage.getItem("glean.skipped_setup") !== "1" &&
      (await listFeedConfigs()).length === 0
    ) {
      navigate("/setup");
    }
  }

  async function finishAuthenticatedStartup(): Promise<void> {
    authReady = true;
    await maybeRedirectToSetup();
  }

  async function submitApiKey(): Promise<void> {
    if (validatingApiKey) return;
    validatingApiKey = true;
    apiKeyError = null;
    try {
      await validateAndStoreApiKey(apiKeyInput);
      apiKeyInput = "";
      showApiKeyModal = false;
      await finishAuthenticatedStartup();
    } catch (e) {
      apiKeyError = e instanceof Error ? e.message : String(e);
    } finally {
      validatingApiKey = false;
    }
  }

  onMount(async () => {
    loadAppearance();
    try {
      info = await getInitialize();
      if (info.auth_disabled || getStoredApiKey()) {
        await finishAuthenticatedStartup();
      } else {
        showApiKeyModal = true;
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });
</script>

{#if !info && !error}
  <div class="flex min-h-screen items-center justify-center bg-base">
    <div class="flex flex-col items-center gap-4 text-cyan motion-safe:animate-pulse">
      <Logo variant="mark" class="h-16 w-16" />
      <span class="text-sm text-tertiary">Loading…</span>
    </div>
  </div>
{:else if error}
  <div class="flex min-h-screen items-center justify-center bg-base p-6">
    <div class="flex max-w-md flex-col items-center gap-4 text-center">
      <Logo variant="mark" class="h-16 w-16 text-status-error" />
      <h1 class="text-xl font-semibold text-primary">Can't reach glean</h1>
      <p class="text-sm text-secondary">{error}</p>
      <p class="text-xs text-tertiary">
        Verify the daemon is running and your API key is valid. To recover the initial key, run
        <code class="rounded bg-elevated px-2 py-0.5 font-mono text-xs">
          docker logs glean | grep GLEAN_INITIAL_API_KEY
        </code>
      </p>
    </div>
  </div>
{:else}
  <Router {url}>
    <AppShell>
      {#if !authReady}
        <div class="mx-auto max-w-2xl px-6 py-12 text-tertiary">
          <h1 class="text-xl font-semibold text-primary">Authentication required</h1>
          <p class="mt-2 text-sm">Paste your glean API key to continue.</p>
        </div>
      {:else}
        <Route path="/setup"><Setup /></Route>
        <Route path="/feeds/new"><FeedEditor mode="create" /></Route>
        <Route path="/feeds/:name/edit" let:params>
          <FeedDetail name={params.name} defaultTab="edit" />
        </Route>
        <Route path="/feeds/:name" let:params><FeedDetail name={params.name} /></Route>
        <Route path="/feeds"><FeedsList /></Route>
        <Route path="/skills"><SkillsList /></Route>
        <Route path="/skills/new"><SkillEditor mode="create" /></Route>
        <Route path="/skills/:name" let:params><SkillEditor mode="edit" name={params.name} /></Route
        >
        <Route path="/digests"><Digests /></Route>
        <Route path="/settings"><Settings /></Route>
        <Route path="/"><Home /></Route>
      {/if}
    </AppShell>
  </Router>
{/if}

{#if showApiKeyModal}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-base/80 p-4">
    <form
      class="w-full max-w-md rounded-xl border border-border bg-surface p-6 text-primary shadow-2xl"
      onsubmit={(event) => {
        event.preventDefault();
        void submitApiKey();
      }}
    >
      <h2 class="text-lg font-semibold">Paste your glean API key</h2>
      <p class="mt-2 text-sm leading-6 text-tertiary">
        Get the initial key from
        <code class="rounded bg-elevated px-1 py-0.5 font-mono text-xs text-secondary">
          docker logs glean | grep GLEAN_INITIAL_API_KEY
        </code>
        or set
        <code class="rounded bg-elevated px-1 py-0.5 font-mono text-xs text-secondary"
          >GLEAN_API_KEY</code
        >. See the
        <a
          class="text-cyan hover:underline"
          href="https://github.com/jaypetez/glean#web-ui"
          target="_blank"
          rel="noreferrer">docs</a
        >.
      </p>
      <label class="mt-5 block">
        <span class="mb-1 block text-xs text-tertiary">API key</span>
        <input
          type="password"
          bind:value={apiKeyInput}
          autocomplete="off"
          aria-invalid={apiKeyError ? "true" : "false"}
          class="density-control w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan"
        />
      </label>
      {#if apiKeyError}
        <p class="mt-2 text-sm text-status-error">{apiKeyError}</p>
      {/if}
      <div class="mt-5 flex justify-end">
        <button
          type="submit"
          disabled={validatingApiKey || !apiKeyInput.trim()}
          class="density-control rounded-md bg-cyan px-4 py-2 text-sm font-medium text-base hover:bg-cyan-light disabled:cursor-not-allowed disabled:opacity-50"
        >
          {validatingApiKey ? "Validating" : "Continue"}
        </button>
      </div>
    </form>
  </div>
{/if}
