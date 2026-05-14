<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    open: boolean;
    title: string;
    description?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    danger?: boolean;
    disabled?: boolean;
    children?: Snippet;
    onconfirm: () => void;
    oncancel: () => void;
  }

  let {
    open,
    title,
    description,
    confirmLabel = "Confirm",
    cancelLabel = "Cancel",
    danger = false,
    disabled = false,
    children,
    onconfirm,
    oncancel,
  }: Props = $props();

  let dialog: HTMLDialogElement;

  $effect(() => {
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  });

  function onCancel(event: Event) {
    event.preventDefault();
    oncancel();
  }
</script>

<dialog
  bind:this={dialog}
  oncancel={onCancel}
  class="w-full max-w-md rounded-xl border border-border bg-surface p-0 text-primary shadow-2xl backdrop:bg-base/80"
>
  <form method="dialog" class="density-section space-y-5 p-5">
    <div>
      <h2 class="text-lg font-semibold text-primary">{title}</h2>
      {#if description}
        <p class="mt-2 text-sm leading-6 text-tertiary">{description}</p>
      {/if}
    </div>

    {#if children}
      <div class="text-sm text-secondary">
        {@render children()}
      </div>
    {/if}

    <div class="flex justify-end gap-2">
      <button
        type="button"
        onclick={oncancel}
        class="density-control rounded-md border border-border px-3 py-2 text-sm text-secondary hover:bg-elevated"
      >
        {cancelLabel}
      </button>
      <button
        type="button"
        onclick={onconfirm}
        disabled={disabled}
        class={danger
          ? "density-control rounded-md border border-status-error/40 bg-status-error/10 px-3 py-2 text-sm font-medium text-status-error hover:bg-status-error/20 disabled:cursor-not-allowed disabled:opacity-50"
          : "density-control rounded-md bg-cyan px-3 py-2 text-sm font-medium text-base hover:bg-cyan-light disabled:cursor-not-allowed disabled:opacity-50"}
      >
        {confirmLabel}
      </button>
    </div>
  </form>
</dialog>
