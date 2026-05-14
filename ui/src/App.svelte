<script lang="ts">
  import { onMount } from "svelte";
  import { navigate, Route, Router } from "svelte-routing";
  import { getInitialize, listFeedConfigs, type InitializeResponse } from "./lib/api";
  import AppShell from "./lib/components/AppShell.svelte";
  import Dashboard from "./lib/routes/Dashboard.svelte";
  import FeedEditor from "./lib/routes/FeedEditor.svelte";
  import Setup from "./lib/routes/Setup.svelte";
  import SkillEditor from "./lib/routes/SkillEditor.svelte";
  import SkillsList from "./lib/routes/SkillsList.svelte";

  let info: InitializeResponse | null = $state(null);
  let error: string | null = $state(null);

  let url = typeof window === "undefined" ? "/" : window.location.pathname;

  onMount(async () => {
    try {
      info = await getInitialize();
      if (
        window.location.pathname === "/" &&
        localStorage.getItem("glean.skipped_setup") !== "1" &&
        (await listFeedConfigs()).length === 0
      ) {
        navigate("/setup");
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });
</script>

<Router {url}>
  <AppShell>
    <Route path="/setup"><Setup /></Route>
    <Route path="/feeds/new"><FeedEditor mode="create" /></Route>
    <Route path="/feeds/:name" let:params><FeedEditor mode="edit" name={params.name} /></Route>
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
        <div class="p-8 text-tertiary">Loading</div>
      {:else}
        <Dashboard />
      {/if}
    </Route>
  </AppShell>
</Router>
