<script lang="ts">
  import { Cards, CheckCircle, FilePlus } from "@phosphor-icons/svelte";
  import { navigate } from "svelte-routing";
  import { stringify as yamlStringify } from "yaml";
  import { feedConfigFromTemplate, feedTemplates, type FeedTemplate } from "../../templates";
  import WizardStep from "./WizardStep.svelte";

  interface Props {
    selectedIds: string[];
  }

  let { selectedIds = $bindable([]) }: Props = $props();
  let previewId = $state(feedTemplates[0]?.id ?? "");

  function isCustom(template: FeedTemplate): boolean {
    return template.id === "custom-blank";
  }

  function toggle(template: FeedTemplate) {
    previewId = template.id;
    if (isCustom(template)) {
      navigate("/feeds/new");
      return;
    }
    selectedIds = selectedIds.includes(template.id)
      ? selectedIds.filter((id) => id !== template.id)
      : [...selectedIds, template.id];
  }

  function previewTemplate(): FeedTemplate {
    return feedTemplates.find((template) => template.id === previewId) ?? feedTemplates[0];
  }

  function previewYaml(): string {
    return yamlStringify(feedConfigFromTemplate(previewTemplate()));
  }
</script>

<WizardStep
  title="Choose starter templates"
  description="Pick one or more ready-made feeds to install now. You can preview the YAML before saving."
>
  <div class="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_24rem]">
    <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
      {#each feedTemplates as template}
        {@const selected = selectedIds.includes(template.id)}
        <article
          class={`rounded-lg border bg-surface p-4 transition hover:border-cyan/50 ${
            selected ? "border-cyan" : "border-border"
          }`}
        >
          <div class="mb-3 flex items-start justify-between gap-3">
            <div class="flex items-center gap-2">
              {#if isCustom(template)}
                <FilePlus class="h-5 w-5 text-cyan" weight="duotone" aria-hidden="true" />
              {:else}
                <Cards class="h-5 w-5 text-cyan" weight="duotone" aria-hidden="true" />
              {/if}
              <h2 class="font-medium text-primary">{template.title}</h2>
            </div>
            {#if selected}
              <CheckCircle class="h-5 w-5 text-status-ok" weight="fill" aria-label="Selected" />
            {/if}
          </div>
          <p class="min-h-10 text-sm leading-5 text-tertiary">{template.description}</p>
          <dl class="mt-4 space-y-2 text-xs">
            <div>
              <dt class="text-faint">Sources</dt>
              <dd class="mt-1 text-secondary">{template.source_labels.join(", ")}</dd>
            </div>
            <div>
              <dt class="text-faint">Suggested schedule</dt>
              <dd class="mt-1 font-mono text-secondary">{template.schedule}</dd>
            </div>
          </dl>
          <div class="mt-4 flex gap-2">
            <button
              type="button"
              onclick={() => {
                previewId = template.id;
              }}
              class="rounded-md border border-border px-3 py-1.5 text-xs text-secondary hover:bg-elevated"
            >
              Preview YAML
            </button>
            <button
              type="button"
              onclick={() => toggle(template)}
              class={`rounded-md px-3 py-1.5 text-xs font-medium ${
                isCustom(template)
                  ? "border border-cyan/30 bg-cyan/10 text-cyan hover:bg-cyan/20"
                  : selected
                    ? "border border-cyan/30 bg-cyan/10 text-cyan hover:bg-cyan/20"
                    : "bg-cyan text-base hover:bg-cyan-light"
              }`}
            >
              {isCustom(template) ? "Open editor" : selected ? "Selected" : "Select"}
            </button>
          </div>
        </article>
      {/each}
    </div>

    <aside class="rounded-lg border border-border bg-elevated p-4">
      <div class="mb-3 flex items-center justify-between gap-3">
        <h2 class="text-sm font-semibold text-primary">YAML preview</h2>
        <span class="rounded-full bg-muted px-2 py-1 text-xs text-tertiary">
          {selectedIds.length} selected
        </span>
      </div>
      <p class="mb-3 text-xs text-tertiary">
        Previewing <span class="font-medium text-secondary">{previewTemplate().title}</span>.
      </p>
      <pre class="max-h-[32rem] overflow-auto rounded-md border border-border bg-base p-3 text-xs leading-5 text-secondary"><code>{previewYaml()}</code></pre>
    </aside>
  </div>

  {#if selectedIds.length === 0}
    <p class="mt-4 text-sm text-status-warn">Select at least one starter template, or open the blank editor.</p>
  {/if}
</WizardStep>
