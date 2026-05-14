<script lang="ts">
  import { Brain } from "@phosphor-icons/svelte";
  import { validateConfig } from "../../api";
  import type { LLMConfig } from "../../types";
  import WizardStep from "./WizardStep.svelte";

  type ProviderChoice = "ollama" | "openai" | "anthropic" | "openrouter";

  interface Props {
    config: LLMConfig;
    valid: boolean;
  }

  let { config = $bindable({ provider: "ollama", model: "qwen2.5:7b" }), valid = $bindable(false) }: Props =
    $props();

  const modelOptions: Record<ProviderChoice, string[]> = {
    ollama: ["qwen2.5:7b", "llama3.1:8b", "mistral:7b"],
    openai: ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"],
    anthropic: ["claude-haiku-4-5", "claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"],
    openrouter: ["openai/gpt-4o-mini", "anthropic/claude-3.5-haiku", "meta-llama/llama-3.1-8b-instruct"],
  };

  const providerLabels: Record<ProviderChoice, string> = {
    ollama: "Ollama (local)",
    openai: "OpenAI",
    anthropic: "Anthropic",
    openrouter: "OpenRouter",
  };

  let provider: ProviderChoice = $state("ollama");
  let model = $state(modelOptions.ollama[0]);
  let apiKey = $state("");
  let baseUrl = $state("http://ollama:11434");
  let testing = $state(false);
  let error: string | null = $state(null);
  let success: string | null = $state(null);

  function chooseProvider(nextProvider: ProviderChoice) {
    provider = nextProvider;
    model = modelOptions[nextProvider][0];
    apiKey = "";
    baseUrl = nextProvider === "ollama" ? "http://ollama:11434" : nextProvider === "openrouter" ? "https://openrouter.ai/api/v1" : "";
    valid = false;
    success = null;
    error = null;
  }

  function needsApiKey(): boolean {
    return provider !== "ollama";
  }

  function formValid(): boolean {
    return model.trim().length > 0 && (!needsApiKey() || apiKey.trim().length > 0);
  }

  function buildConfig(): LLMConfig {
    const mappedProvider = provider === "openrouter" ? "openai" : provider;
    const out: LLMConfig = {
      provider: mappedProvider,
      model: model.trim(),
    };
    if (baseUrl.trim()) out.base_url = baseUrl.trim();
    if (apiKey.trim()) out.api_key = apiKey.trim();
    return out;
  }

  async function testSettings() {
    valid = false;
    success = null;
    error = null;
    if (!formValid()) {
      error = needsApiKey() ? "Model and API key are required." : "Model is required.";
      return;
    }

    testing = true;
    try {
      const candidate = buildConfig();
      const result = await validateConfig({ defaults: { llm: candidate }, feeds: [] });
      if (!result.valid) {
        throw new Error(result.errors.join("; ") || "Config validation failed.");
      }
      config = candidate;
      valid = true;
      success = "LLM settings validated.";
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      testing = false;
    }
  }
</script>

<WizardStep
  title="Choose an LLM"
  description="Pick the provider that should rank, summarize, and write digest intros for starter feeds."
>
  <div class="mb-5 flex gap-4 rounded-lg border border-border bg-elevated p-4">
    <Brain class="mt-1 h-6 w-6 shrink-0 text-cyan" weight="duotone" aria-hidden="true" />
    <p class="text-sm leading-6 text-secondary">
      Ollama is the default because it runs locally and needs no API key. Hosted providers require
      an API key and can optionally use a custom base URL for compatible gateways.
    </p>
  </div>

  <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
    <label class="block">
      <span class="mb-1 block text-xs font-medium text-tertiary">Provider</span>
      <select
        value={provider}
        onchange={(e) => chooseProvider((e.currentTarget as HTMLSelectElement).value as ProviderChoice)}
        class="w-full rounded-md border border-border bg-elevated px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
      >
        {#each Object.entries(providerLabels) as [value, label]}
          <option value={value}>{label}</option>
        {/each}
      </select>
    </label>

    <label class="block">
      <span class="mb-1 block text-xs font-medium text-tertiary">Model</span>
      <select
        bind:value={model}
        onchange={() => {
          valid = false;
          success = null;
        }}
        class="w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
      >
        {#each modelOptions[provider] as option}
          <option value={option}>{option}</option>
        {/each}
      </select>
      {#if model.trim().length === 0}
        <p class="mt-1 text-xs text-status-warn">Model is required.</p>
      {/if}
    </label>

    {#if needsApiKey()}
      <label class="block">
        <span class="mb-1 block text-xs font-medium text-tertiary">API key</span>
        <input
          type="password"
          bind:value={apiKey}
          oninput={() => {
            valid = false;
            success = null;
          }}
          autocomplete="off"
          class="w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary focus:outline-none focus:ring-2 focus:ring-cyan"
        />
        {#if apiKey.trim().length === 0}
          <p class="mt-1 text-xs text-status-warn">API key is required for {providerLabels[provider]}.</p>
        {/if}
      </label>
    {/if}

    <label class="block">
      <span class="mb-1 block text-xs font-medium text-tertiary">
        Base URL {provider === "ollama" || provider === "openrouter" ? "" : "(optional)"}
      </span>
      <input
        type="url"
        bind:value={baseUrl}
        readonly={provider === "openrouter"}
        oninput={() => {
          valid = false;
          success = null;
        }}
        placeholder={provider === "ollama" ? "http://ollama:11434" : "https://api.example.com/v1"}
        class="w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan read-only:opacity-70"
      />
    </label>
  </div>

  <div class="mt-5 flex flex-wrap items-center gap-3">
    <button
      type="button"
      onclick={testSettings}
      disabled={testing || !formValid()}
      class="rounded-md bg-cyan px-3 py-2 text-sm font-medium text-base hover:bg-cyan-light disabled:opacity-50"
    >
      {testing ? "Validating…" : "Test settings"}
    </button>
    {#if success}
      <span class="text-sm text-status-ok">{success}</span>
    {/if}
    {#if error}
      <span class="text-sm text-status-error">{error}</span>
    {/if}
  </div>
</WizardStep>
