<script lang="ts">
  import { PaperPlaneTilt } from "@phosphor-icons/svelte";
  import WizardStep from "./WizardStep.svelte";

  interface Props {
    botToken: string;
    chatId: string;
    skipped: boolean;
    valid: boolean;
  }

  let {
    botToken = $bindable(""),
    chatId = $bindable(""),
    skipped = $bindable(false),
    valid = $bindable(false),
  }: Props = $props();

  $effect(() => {
    valid = skipped || (botToken.trim().length > 0 && chatId.trim().length > 0);
  });
</script>

<WizardStep
  title="Telegram delivery"
  description="Add your Telegram bot token and chat ID so starter templates can share one default Telegram sink."
>
  <div class="mb-5 flex gap-4 rounded-lg border border-border bg-elevated p-4">
    <PaperPlaneTilt class="mt-1 h-6 w-6 shrink-0 text-cyan" weight="duotone" aria-hidden="true" />
    <p class="text-sm leading-6 text-secondary">
      Need a bot? Follow Telegram’s
      <a
        class="text-cyan hover:underline"
        href="https://core.telegram.org/bots#how-do-i-create-a-bot"
        target="_blank"
        rel="noreferrer"
      >bot setup guide</a>
      , then paste the token from BotFather and the destination chat ID here.
    </p>
  </div>

  <label class="mb-5 flex items-start gap-3 rounded-lg border border-border bg-base/40 p-4">
    <input
      type="checkbox"
      bind:checked={skipped}
      class="mt-1 h-4 w-4 rounded border-border bg-elevated text-cyan focus:ring-cyan"
    />
    <span>
      <span class="block text-sm font-medium text-primary">Use a non-Telegram sink instead</span>
      <span class="mt-1 block text-xs text-tertiary">
        Skip this step if you plan to configure Slack, Discord, ntfy, webhook, or file delivery.
      </span>
    </span>
  </label>

  <div class="grid grid-cols-1 gap-4 md:grid-cols-2" aria-disabled={skipped}>
    <label class="block">
      <span class="mb-1 block text-xs font-medium text-tertiary">Bot token</span>
      <input
        type="password"
        bind:value={botToken}
        disabled={skipped}
        autocomplete="off"
        placeholder="123456:ABC-DEF..."
        class="w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan disabled:opacity-50"
      />
      {#if !skipped && botToken.trim().length === 0}
        <p class="mt-1 text-xs text-status-warn">Bot token is required for Telegram setup.</p>
      {/if}
    </label>

    <label class="block">
      <span class="mb-1 block text-xs font-medium text-tertiary">Chat ID</span>
      <input
        type="text"
        bind:value={chatId}
        disabled={skipped}
        placeholder="-1001234567890"
        class="w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-sm text-primary placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-cyan disabled:opacity-50"
      />
      {#if !skipped && chatId.trim().length === 0}
        <p class="mt-1 text-xs text-status-warn">Chat ID is required for Telegram setup.</p>
      {/if}
    </label>
  </div>
</WizardStep>
