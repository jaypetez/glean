<script lang="ts">
  import type { DensityChoice } from "../../types";
  import { loadAppearance, saveDensity } from "../../theme";

  const densities: DensityChoice[] = ["comfortable", "compact"];

  let densityChoice: DensityChoice = $state("comfortable");

  function selectDensity(density: DensityChoice): void {
    densityChoice = density;
    saveDensity(density);
  }

  $effect(() => {
    const appearance = loadAppearance();
    densityChoice = appearance.density;
  });
</script>

<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
  <div class="density-section rounded-lg border border-border bg-surface p-5">
    <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Density</h2>
    <p class="mt-1 text-sm text-tertiary">Pick the spacing that feels best for your screen.</p>
    <div class="mt-4 grid grid-cols-2 gap-2" role="group" aria-label="Density">
      {#each densities as density}
        <button
          type="button"
          onclick={() => selectDensity(density)}
          class={densityChoice === density
            ? "density-control rounded-md border border-cyan bg-cyan/15 px-3 py-2 text-sm text-cyan"
            : "density-control rounded-md border border-border bg-elevated px-3 py-2 text-sm text-secondary hover:bg-muted"}
        >
          {density}
        </button>
      {/each}
    </div>
  </div>

  <div class="density-section rounded-lg border border-border bg-surface p-5">
    <h2 class="text-sm font-semibold uppercase tracking-wide text-tertiary">Theme</h2>
    <p class="mt-1 text-sm text-tertiary">Glean is always rendered in light mode.</p>
  </div>
</div>
