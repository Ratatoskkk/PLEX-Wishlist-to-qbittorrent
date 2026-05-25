<script lang="ts">
  import '../app.scss';
  import type { Snippet } from 'svelte';

  const { children }: { children: Snippet } = $props();
</script>

<div class="app-container">
  <main>
    {@render children()}
  </main>
</div>

<style lang="scss">
  .app-container {
    width: 100%;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }
  
</style>
