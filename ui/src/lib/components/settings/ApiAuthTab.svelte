<script lang="ts">
  import { ArrowClockwise, Copy, Eye, EyeSlash } from "@phosphor-icons/svelte";
  import { onMount } from "svelte";
  import {
    getInitialize,
    getStoredApiKey,
    rotateApiKey,
    validateAndStoreApiKey,
    type InitializeResponse,
  } from "../../api";
  import Dialog from "../Dialog.svelte";

  let loading = $state(true);
  let saving = $state(false);
  let rotating = $state(false);
  let error = $state<string | null>(null);
  let notice = $state<string | null>(null);
  let info = $state<InitializeResponse | null>(null);
  let currentApiKey = $state<string | null>(null);
  let replacementKey = $state("");
  let rotatedKey = $state<string | null>(null);
  let showCurrentApiKey = $state(false);
  let showReplacementKey = $state(false);
  let showRotateDialog = $state(false);

  function showNotice(message: string): void {
    notice = message;
    window.setTimeout(() => {
      if (notice === message) notice = null;
    }, 2500);
  }

  function displayCurrentKey(): string {
    if (!currentApiKey) return "No API key stored in this browser.";
    if (showCurrentApiKey) return currentApiKey;
    if (currentApiKey.length <= 8) return "•".repeat(currentApiKey.length);
    return `${currentApiKey.slice(0, 4)}${"•".repeat(Math.max(8, currentApiKey.length - 8))}${currentApiKey.slice(-4)}`;
  }

  async function loadState(): Promise<void> {
    loading = true;
    error = null;
    currentApiKey = getStoredApiKey();
    try {
      info = await getInitialize();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  async function copyCurrentKey(): Promise<void> {
    if (!currentApiKey) return;
    try {
      await navigator.clipboard.writeText(currentApiKey);
      showNotice("API key copied.");
    } catch {
      error = "Clipboard copy failed. Copy the API key manually.";
    }
  }

  async function replaceApiKey(): Promise<void> {
    if (saving) return;
    error = null;
    saving = true;
    try {
      await validateAndStoreApiKey(replacementKey);
      currentApiKey = getStoredApiKey();
      replacementKey = "";
      showReplacementKey = false;
      showNotice("API key updated.");
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }

  async function confirmRotate(): Promise<void> {
    if (rotating) return;
    error = null;
    rotating = true;
    try {
      const response = await rotateApiKey();
      currentApiKey = response.api_key;
      rotatedKey = response.api_key;
      showRotateDialog = false;
      showCurrentApiKey = true;
      showNotice("API key rotated.");
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      rotating = false;
    }
  }

  async function copyRotatedKey(): Promise<void> {
    if (!rotatedKey) return;
    try {
      await navigator.clipboard.writeText(rotatedKey);
      rotatedKey = null;
      showNotice("New API key copied.");
    } catch {
      error = "Clipboard copy failed. Select and copy the new API key manually.";
    }
  }

  onMount(() => {
    void loadState();
  });
</script>

<div class="space-y-4">
  {#if loading}
    <p class="text-tertiary">Loading API &amp; auth settings…</p>
  {:else}
    {#if notice}
      <div class="rounded-lg border border-status-ok/40 bg-status-ok/10 p-4 text-sm text-status-ok">
        {notice}
      </div>
    {/if}

    {#if info?.auth_disabled}
      <div class="rounded-lg border border-status-warn/40 bg-status-warn/10 p-4 text-sm text-status-warn">
        Auth is DISABLED (GLEAN_DISABLE_AUTH=1 is set). Anyone on this network can hit the API.
      </div>
    {/if}

    {#if error}
      <div class="rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error">
        {error}
      </div>
    {/if}

    <section class="density-section rounded-lg border border-border bg-surface p-5">
      <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Current API key</h2>
      <div class="mt-4 rounded-md border border-border bg-elevated p-4">
        <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p class="text-xs text-tertiary">Stored in this browser</p>
            <p class="mt-1 break-all font-mono text-sm text-primary">{displayCurrentKey()}</p>
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
              onclick={() => void copyCurrentKey()}
              disabled={!currentApiKey}
              class="density-control inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-secondary hover:bg-surface disabled:opacity-50"
            >
              <Copy size={16} aria-hidden="true" /> Copy
            </button>
          </div>
        </div>
      </div>
    </section>

    <section class="density-section rounded-lg border border-border bg-surface p-5">
      <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Replace API key</h2>
      <p class="mt-2 text-sm text-tertiary">
        Paste a new key and the UI will validate it against the daemon before storing it here.
      </p>

      <form
        class="mt-4 space-y-4"
        onsubmit={(event) => {
          event.preventDefault();
          void replaceApiKey();
        }}
      >
        <label class="block">
          <span class="mb-1 block text-xs text-tertiary">API key</span>
          <span class="flex rounded-md border border-border bg-elevated focus-within:ring-2 focus-within:ring-cyan">
            <input
              type={showReplacementKey ? "text" : "password"}
              bind:value={replacementKey}
              autocomplete="off"
              class="density-control min-w-0 flex-1 bg-transparent px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none"
            />
            <button
              type="button"
              class="px-3 text-tertiary hover:text-primary"
              aria-label={showReplacementKey ? "Hide replacement API key" : "Show replacement API key"}
              onclick={() => (showReplacementKey = !showReplacementKey)}
            >
              {#if showReplacementKey}<EyeSlash size={16} aria-hidden="true" />{:else}<Eye size={16} aria-hidden="true" />{/if}
            </button>
          </span>
        </label>

        <div class="flex justify-end">
          <button
            type="submit"
            disabled={saving || !replacementKey.trim()}
            class="density-control rounded-md bg-cyan px-4 py-2 text-sm font-medium text-base hover:bg-cyan-light disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Validating" : "Validate and store"}
          </button>
        </div>
      </form>
    </section>

    <section class="density-section rounded-lg border border-border bg-surface p-5">
      <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Rotate daemon API key</h2>
      <p class="mt-2 text-sm text-tertiary">
        Generate a brand-new daemon key. Existing CLI scripts, browser tabs, and other clients will
        need the new key immediately.
      </p>
      <button
        type="button"
        onclick={() => (showRotateDialog = true)}
        class="density-control mt-4 inline-flex items-center gap-2 rounded-md border border-status-warn/40 bg-status-warn/10 px-3 py-2 text-sm font-medium text-status-warn hover:bg-status-warn/20"
      >
        <ArrowClockwise size={16} aria-hidden="true" /> Rotate API key
      </button>
    </section>

    {#if rotatedKey}
      <div class="rounded-lg border border-status-warn/40 bg-status-warn/10 p-4">
        <h3 class="font-semibold text-status-warn">New API key</h3>
        <p class="mt-1 text-sm text-secondary">Copy this key now. It is only shown once.</p>
        <p class="mt-3 break-all rounded-md border border-border bg-elevated p-3 font-mono text-sm text-primary">
          {rotatedKey}
        </p>
        <button
          type="button"
          onclick={() => void copyRotatedKey()}
          class="density-control mt-3 inline-flex items-center gap-2 rounded-md bg-cyan px-3 py-2 text-sm font-medium text-base hover:bg-cyan-light"
        >
          <Copy size={16} aria-hidden="true" /> Copy and continue
        </button>
      </div>
    {/if}
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
