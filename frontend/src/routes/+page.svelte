<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import type { AppState } from '../types';
  import PendingCard from '../components/PendingCard.svelte';
  import HistoryList from '../components/HistoryList.svelte';

  let state = $state({
    downloads: [],
    pending_groups: {},
    pending_count: 0,
    last_check: 'Loading...',
    last_error: null
  });

  let pollInterval;

  async function fetchState() {
    try {
      const res = await fetch('/api/state');
      if (res.ok) {
        state = await res.json();
      }
    } catch (err) {
      console.error("Failed to fetch state:", err);
    }
  }

  onMount(() => {
    fetchState();
    pollInterval = setInterval(fetchState, 5000);
  });

  onDestroy(() => {
    if (pollInterval) clearInterval(pollInterval);
  });
  
  async function clearHistory() {
    await fetch('/api/clear', { method: 'POST' });
    fetchState();
  }
</script>

<div class="dashboard">
  <section class="status-bar glass-panel">
    <div class="status-item">
      <span class="label">Last Checked:</span>
      <span class="value">{state.last_check}</span>
    </div>
    {#if state.last_error}
      <div class="status-item error">
        <span class="label">Error:</span>
        <span class="value">{state.last_error}</span>
      </div>
    {/if}
  </section>

  {#if state.pending_count > 0}
    <section class="pending-section">
      <div class="section-header">
        <h2>Requires Approval ({state.pending_count})</h2>
        <p class="subtitle">These items exceed the size threshold or are part of a multi-season pack.</p>
      </div>
      
      <div class="pending-grid">
        {#each Object.entries(state.pending_groups) as [rootTitle, items]}
          <PendingCard title={rootTitle} {items} onAction={fetchState} />
        {/each}
      </div>
    </section>
  {/if}

  <section class="history-section glass-panel">
    <div class="section-header flat">
      <h2>Active & History</h2>
      <button class="danger" onclick={clearHistory}>Clear Completed</button>
    </div>
    <HistoryList downloads={state.downloads} />
  </section>
</div>

<style lang="scss">
  .dashboard {
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }
  
  .status-bar {
    display: flex;
    padding: 1rem 1.5rem;
    gap: 2rem;
    
    .status-item {
      display: flex;
      gap: 0.5rem;
      align-items: center;
      
      .label { color: var(--text-muted); font-size: 0.875rem; }
      .value { font-weight: 500; }
      
      &.error .value { color: var(--danger); }
    }
  }
  
  .section-header {
    margin-bottom: 1.5rem;
    
    h2 { margin: 0 0 0.5rem 0; font-size: 1.25rem; font-weight: 600; }
    .subtitle { margin: 0; color: var(--text-muted); font-size: 0.875rem; }
    
    &.flat {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0;
      padding: 1.5rem;
      border-bottom: 1px solid var(--border-glass);
      h2 { margin: 0; }
    }
  }
  
  .pending-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
    gap: 1.5rem;
  }
  
  .history-section {
    padding: 0;
    overflow: hidden;
  }
</style>
