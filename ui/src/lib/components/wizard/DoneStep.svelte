<script lang="ts">
  import { CheckCircle } from "@phosphor-icons/svelte";
  import WizardStep from "./WizardStep.svelte";
</script>

<WizardStep title="You’re all set" description="Your defaults and starter feeds are saved.">
  <div class="flex gap-4 rounded-lg border border-status-ok/40 bg-status-ok/10 p-5">
    <CheckCircle class="mt-1 h-7 w-7 shrink-0 text-status-ok" weight="duotone" aria-hidden="true" />
    <div>
      <h2 class="font-medium text-primary">Setup complete</h2>
      <p class="mt-1 text-sm leading-6 text-secondary">
        glean is ready to run your configured feeds. You can edit schedules, sources, and pipeline
        stages from the dashboard later.
      </p>
    </div>
  </div>
</WizardStep>
