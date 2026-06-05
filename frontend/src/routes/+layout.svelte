<script lang="ts">
  import '../app.scss';
  import type { Snippet } from 'svelte';

  const { children }: { children: Snippet } = $props();
</script>

<main class="app-container">
  {@render children()}
</main>

<style lang="scss">
  .app-container {
    width: 100%;
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }
</style>
