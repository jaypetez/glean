<script lang="ts">
  import Digests from "../../routes/Digests.svelte";

  interface Props {
    name: string;
  }

  let { name }: Props = $props();
</script>

<Digests feedFilter={name} />
