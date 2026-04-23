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
    max-width: 1200px;
    margin: 0 auto;
    padding: 3rem 2rem;
    display: flex;
    flex-direction: column;
    gap: 3rem;
  }
  
</style>
