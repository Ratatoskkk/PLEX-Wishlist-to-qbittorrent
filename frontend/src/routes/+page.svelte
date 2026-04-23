<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import type { AppState, ProgressUpdate } from '../types';
  import PendingCard from '../components/PendingCard.svelte';
  import HistoryList from '../components/HistoryList.svelte';

  let state = $state({
    downloads: [],
    pending_groups: {},
    pending_count: 0,
    last_check: 'Loading...',
    last_error: null
  } as AppState);

  // SSE live progress: keyed by download id (as string)
  let liveProgress = $state<Record<string, ProgressUpdate>>({});

  let pollInterval: ReturnType<typeof setInterval>;
  let eventSource: EventSource | null = null;

  async function fetchState() {
    try {
      const res = await fetch('/api/state');
      if (res.ok) {
        state = await res.json();
      }
    } catch (err) {
      console.error('Failed to fetch state:', err);
    }
  }

  function connectStream() {
    eventSource = new EventSource('/api/stream');
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        liveProgress = data;
      } catch {
        // ignore parse errors
      }
    };
    eventSource.onerror = () => {
      // Reconnect after 3s on error
      eventSource?.close();
      setTimeout(connectStream, 3000);
    };
  }

  onMount(() => {
    fetchState();
    pollInterval = setInterval(fetchState, 5000);
    connectStream();
  });

  onDestroy(() => {
    clearInterval(pollInterval);
    eventSource?.close();
  });

  async function clearHistory() {
    await fetch('/api/clear', { method: 'POST' });
    fetchState();
  }
</script>

<div class="dashboard">
  <section class="status-bar cursor-card">
    <div class="logo-container">
      <img src="/logo.png" alt="PlexAither Tracker Logo" class="logo" />
    </div>
    <div class="right-section">
      <div class="status-item">
        <span class="label">Last Checked:</span>
        <span class="value">{state.last_check}</span>
      </div>
      {#if Object.keys(liveProgress).length > 0}
        <div class="status-item live-indicator">
          <span class="pulse-dot"></span>
          <span class="label">Live</span>
        </div>
      {/if}
      {#if state.last_error}
        <div class="status-item error">
          <span class="label">Error:</span>
          <span class="value">{state.last_error}</span>
        </div>
      {/if}
    </div>
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

  <section class="history-section cursor-card">
    <div class="section-header flat">
      <h2>Active &amp; History</h2>
      <button class="danger" onclick={clearHistory}>Clear Completed</button>
    </div>
    <HistoryList downloads={state.downloads} {liveProgress} />
  </section>
</div>

<style lang="scss">
  .dashboard {
    display: flex;
    flex-direction: column;
    gap: 3rem; /* Expanded gap */
  }

  .status-bar {
    display: flex;
    padding: 16px 24px;
    align-items: center;
    justify-content: space-between;

    .logo-container {
      display: flex;
      align-items: center;
    }

    .logo {
      height: 96px; /* Rendered bigger */
      width: auto;
    }

    .right-section {
      display: flex;
      align-items: center;
      gap: 2rem;
    }

    .status-item {
      display: flex;
      gap: 0.5rem;
      align-items: center;
      font-size: 14px;

      .label { color: var(--border-strong); }
      .value { font-weight: 500; font-family: var(--font-code); }

      &.error .value { color: var(--color-error); }

      &.live-indicator {
        margin-left: auto;
        gap: 8px;
        .label { 
          color: var(--color-success); 
          font-family: var(--font-system);
          font-size: 13px; 
          font-weight: 600; 
        }
      }
    }
  }

  .pulse-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--color-success);
    animation: pulse 2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.8); }
  }

  .section-header {
    margin-bottom: 1.5rem;

    h2 { 
      margin: 0 0 8px 0; 
      font-size: 26px; 
      letter-spacing: -0.325px; 
    }
    
    .subtitle { 
      margin: 0; 
      color: var(--border-strong); 
      font-family: var(--font-body);
      font-size: 17.28px; 
    }

    &.flat {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0;
      padding: 24px;
      border-bottom: 1px solid var(--border-primary);
      h2 { margin: 0; }
    }
  }

  .pending-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
    gap: 24px;
  }

  .history-section {
    padding: 0;
    overflow: hidden;
  }
</style>
