<script lang="ts">
  import { onMount } from "svelte";
  import { Route, Router } from "svelte-routing";
  import { getInitialize, type InitializeResponse } from "./lib/api";
  import AppShell from "./lib/components/AppShell.svelte";
  import SkillEditor from "./lib/routes/SkillEditor.svelte";
  import SkillsList from "./lib/routes/SkillsList.svelte";

  let info: InitializeResponse | null = $state(null);
  let error: string | null = $state(null);

  // Keep this prop for merge compatibility with the parallel FeedEditor routes.
  let url = "";

  onMount(async () => {
    try {
      info = await getInitialize();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });
</script>

<Router {url}>
  <AppShell>
    <!-- Skill routes (THIS PR) -->
    <Route path="/skills"><SkillsList /></Route>
    <Route path="/skills/new"><SkillEditor mode="create" /></Route>
    <Route path="/skills/:name" let:params><SkillEditor mode="edit" name={params.name} /></Route>

    <Route path="/">
      {#if error}
        <div class="p-8 text-status-error">
          <h1 class="text-xl font-semibold">Failed to connect to glean</h1>
          <pre class="mt-4 font-mono text-sm">{error}</pre>
        </div>
      {:else if !info}
        <div class="p-8 text-tertiary">Loading…</div>
      {:else}
        <div class="p-8">
          <h1 class="text-2xl font-semibold text-primary">Welcome to glean</h1>
          <p class="mt-2 text-tertiary">
            Connected to glean v{info.version}. The full UI is being built incrementally — see
            <a class="text-cyan hover:underline" href="https://github.com/jaypetez/glean/issues/64"
              >issue #64</a
            >.
          </p>
          <div class="mt-8 flex gap-2 text-sm">
            <span
              class="rounded-md bg-status-ok/15 border border-status-ok/30 px-2 py-1 text-status-ok"
            >
              API connected
            </span>
            {#if info.auth_disabled}
              <span
                class="rounded-md bg-status-warn/15 border border-status-warn/30 px-2 py-1 text-status-warn"
              >
                Auth disabled
              </span>
            {:else}
              <span class="rounded-md bg-cyan/15 border border-cyan/30 px-2 py-1 text-cyan">
                API key authentication
              </span>
            {/if}
          </div>
        </div>
      {/if}
    </Route>
  </AppShell>
</Router>
