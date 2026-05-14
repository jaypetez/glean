<script lang="ts">
  import { navigate } from "svelte-routing";
  import { createFeedConfig, getDefaults, updateDefaults, validateFeedConfig } from "../api";
  import DoneStep from "../components/wizard/DoneStep.svelte";
  import LlmStep from "../components/wizard/LlmStep.svelte";
  import TelegramStep from "../components/wizard/TelegramStep.svelte";
  import TemplateGalleryStep from "../components/wizard/TemplateGalleryStep.svelte";
  import WelcomeStep from "../components/wizard/WelcomeStep.svelte";
  import WizardStepper from "../components/wizard/WizardStepper.svelte";
  import { feedConfigFromTemplate, feedTemplates } from "../templates";
  import type { DefaultsConfig, LLMConfig } from "../types";

  const steps = ["Welcome", "Telegram", "LLM", "Templates", "Done"];

  let step = $state(0);
  let busy = $state(false);
  let error: string | null = $state(null);

  let welcomeReady = $state(false);
  let botToken = $state("");
  let chatId = $state("");
  let telegramSkipped = $state(false);
  let telegramValid = $state(false);
  let llmConfig: LLMConfig = $state({ provider: "ollama", model: "qwen2.5:7b" });
  let llmValid = $state(false);
  let selectedTemplateIds: string[] = $state([]);
  let installedTemplateIds: string[] = $state([]);
  let installProgress = $state("");

  function canContinue(): boolean {
    if (busy) return false;
    if (step === 0) return welcomeReady;
    if (step === 1) return telegramValid;
    if (step === 2) return llmValid;
    if (step === 3) return selectedTemplateIds.length > 0;
    return true;
  }

  function skipSetup() {
    localStorage.setItem("glean.skipped_setup", "1");
    navigate("/");
  }

  function goDashboard() {
    localStorage.removeItem("glean.skipped_setup");
    navigate("/");
  }

  async function saveTelegramDefaults() {
    if (telegramSkipped) return;
    const defaults = await getDefaults();
    const trimmedToken = botToken.trim();
    const trimmedChatId = chatId.trim();
    const telegramSink: Record<string, unknown> = {
      type: "telegram",
      chat_id: trimmedChatId,
      token: trimmedToken,
    };
    const nextDefaults: DefaultsConfig = {
      ...defaults,
      telegram: {
        ...(defaults.telegram ?? {}),
        bot_token: trimmedToken,
        chat_id: trimmedChatId,
      },
      sinks: [telegramSink],
    };
    await updateDefaults(nextDefaults);
  }

  async function saveLlmDefaults() {
    const defaults = await getDefaults();
    await updateDefaults({ ...defaults, llm: llmConfig });
  }

  async function installTemplates() {
    const defaults = await getDefaults();
    const selected = feedTemplates.filter(
      (template) => selectedTemplateIds.includes(template.id) && template.id !== "custom-blank"
    );
    if (selected.length === 0) {
      throw new Error("Select at least one installable template.");
    }

    const remaining = selected.filter((template) => !installedTemplateIds.includes(template.id));
    for (const [index, template] of remaining.entries()) {
      installProgress = `Installing ${index + 1} of ${remaining.length}: ${template.title}`;
      const feed = feedConfigFromTemplate(template);
      const validation = await validateFeedConfig(feed, defaults);
      if (!validation.valid) {
        throw new Error(`${template.title}: ${validation.errors.join("; ")}`);
      }
      await createFeedConfig(feed);
      installedTemplateIds = [...installedTemplateIds, template.id];
    }
  }

  async function next() {
    if (!canContinue()) return;
    error = null;
    busy = true;
    try {
      if (step === 1) await saveTelegramDefaults();
      if (step === 2) await saveLlmDefaults();
      if (step === 3) await installTemplates();
      step = Math.min(step + 1, steps.length - 1);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      installProgress = "";
      busy = false;
    }
  }

  function back() {
    if (step > 0 && !busy) step -= 1;
  }
</script>

<div class="mx-auto max-w-6xl px-6 py-8">
  <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
    <div>
      <p class="text-sm font-medium uppercase tracking-wide text-cyan">First-run setup</p>
      <h1 class="mt-1 text-3xl font-semibold text-primary">Create your first glean feed</h1>
    </div>
    {#if step < steps.length - 1}
      <button
        type="button"
        onclick={skipSetup}
        class="rounded-md border border-border px-3 py-2 text-sm text-secondary hover:bg-elevated"
      >
        Skip setup
      </button>
    {/if}
  </div>

  <WizardStepper {steps} current={step} />

  {#if error}
    <div class="mb-4 rounded-lg border border-status-error/50 bg-status-error/10 p-4 text-sm text-status-error">
      {error}
    </div>
  {/if}

  {#if step === 0}
    <WelcomeStep bind:ready={welcomeReady} />
  {:else if step === 1}
    <TelegramStep
      bind:botToken
      bind:chatId
      bind:skipped={telegramSkipped}
      bind:valid={telegramValid}
    />
  {:else if step === 2}
    <LlmStep bind:config={llmConfig} bind:valid={llmValid} />
  {:else if step === 3}
    <TemplateGalleryStep bind:selectedIds={selectedTemplateIds} />
  {:else}
    <DoneStep />
  {/if}

  <div class="mt-6 flex items-center justify-between gap-3">
    <button
      type="button"
      onclick={back}
      disabled={step === 0 || busy || step === steps.length - 1}
      class="rounded-md border border-border px-3 py-2 text-sm text-secondary hover:bg-elevated disabled:opacity-50"
    >
      Back
    </button>

    {#if step === steps.length - 1}
      <button
        type="button"
        onclick={goDashboard}
        class="rounded-md bg-cyan px-4 py-2 text-sm font-medium text-base hover:bg-cyan-light"
      >
        Go to dashboard
      </button>
    {:else}
      <button
        type="button"
        onclick={next}
        disabled={!canContinue()}
        class="rounded-md bg-cyan px-4 py-2 text-sm font-medium text-base hover:bg-cyan-light disabled:opacity-50"
      >
        {busy ? installProgress || "Saving…" : step === 3 ? "Install templates" : "Next"}
      </button>
    {/if}
  </div>
</div>
