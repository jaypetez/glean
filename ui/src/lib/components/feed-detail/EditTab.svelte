<script lang="ts">
  import FeedEditor from "../../routes/FeedEditor.svelte";

  interface Props {
    name: string;
  }

  let { name }: Props = $props();
</script>

<FeedEditor mode="edit" {name} embedded returnTo={`/feeds/${encodeURIComponent(name)}`} />
