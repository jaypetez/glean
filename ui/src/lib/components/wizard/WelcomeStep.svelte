<script lang="ts">
  import { Sparkle } from "@phosphor-icons/svelte";
  import WizardStep from "./WizardStep.svelte";

  interface Props {
    ready: boolean;
  }

  let { ready = $bindable(false) }: Props = $props();
</script>

<WizardStep title="Welcome to glean" description="Set up your first automated digest in a few guided steps.">
  <div class="flex gap-4 rounded-lg border border-border bg-elevated p-4">
    <Sparkle class="mt-1 h-6 w-6 shrink-0 text-cyan" weight="duotone" aria-hidden="true" />
    <p class="text-sm leading-6 text-secondary">
      glean watches the sources you care about, removes duplicates, ranks and summarizes the
      important items with your chosen LLM, then sends concise digests on a schedule to Telegram or
      another sink you configure.
    </p>
  </div>

  <label class="mt-6 flex items-start gap-3 rounded-lg border border-border bg-base/40 p-4">
    <input
      type="checkbox"
      bind:checked={ready}
      class="mt-1 h-4 w-4 rounded border-border bg-elevated text-cyan focus:ring-cyan"
    />
    <span>
      <span class="block text-sm font-medium text-primary">I’m ready to start</span>
      <span class="mt-1 block text-xs text-tertiary">
        You can skip setup at any time and configure feeds manually later.
      </span>
    </span>
  </label>
</WizardStep>
