<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import type { AppState, ProgressUpdate, CleanupItem } from '../types';
  import PendingCard from '../components/PendingCard.svelte';
  import HistoryList from '../components/HistoryList.svelte';
  import UpcomingSidebar from '../components/UpcomingSidebar.svelte';
  import CleanupSidebar from '../components/CleanupSidebar.svelte';

  let state: AppState = $state({
    downloads: [],
    pending_groups: {},
    pending_count: 0,
    upcoming: [],
    last_check: 'Loading...',
    last_error: null
  });

  let cleanupItems: CleanupItem[] = $state([]);

  // SSE live progress: keyed by download id (as string)
  let liveProgress: Record<string, ProgressUpdate> = $state({});

  let pollInterval: ReturnType<typeof setInterval>;
  let cleanupInterval: ReturnType<typeof setInterval>;
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

  async function fetchCleanup() {
    try {
      const res = await fetch('/api/cleanup');
      if (res.ok) {
        cleanupItems = await res.json();
      }
    } catch (err) {
      console.error('Failed to fetch cleanup:', err);
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
    fetchCleanup();
    pollInterval = setInterval(fetchState, 5000);
    cleanupInterval = setInterval(fetchCleanup, 30000);
    connectStream();
  });

  onDestroy(() => {
    clearInterval(pollInterval);
    clearInterval(cleanupInterval);
    eventSource?.close();
  });

  let isPolling = $state(false);

  async function clearHistory() {
    await fetch('/api/clear', { method: 'POST' });
    fetchState();
  }

  async function triggerPollNow() {
    isPolling = true;
    try {
      await fetch('/api/poll_now', { method: 'POST' });
      // Give the backend a moment to start, then refresh state
      setTimeout(fetchState, 2000);
    } catch (err) {
      console.error('Poll trigger failed:', err);
    } finally {
      setTimeout(() => { isPolling = false; }, 3000);
    }
  }

  async function handleCleanupDelete() {
    await fetchCleanup();
    await fetchState();
  }
</script>

<div class="app-layout">
  <div class="left-column">
    <UpcomingSidebar upcoming={state.upcoming || []} onAction={fetchState} />
  </div>
  
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
      <button class="check-now" onclick={triggerPollNow} disabled={isPolling}>
        {#if isPolling}
          <span class="spinner"></span> Checking…
        {:else}
          ⟳ Check Now
        {/if}
      </button>
    </div>
  </section>

  <div class="dashboard-split">
    {#if state.pending_count > 0}
      <section class="pending-section">
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
  </div>

  <div class="right-column">
    <CleanupSidebar items={cleanupItems} onAction={handleCleanupDelete} />
  </div>
</div>

<style lang="scss">
  .app-layout {
    display: flex;
    flex-direction: row;
    gap: 2rem;
    align-items: stretch;
    height: 100vh;
    padding: 2rem;
    box-sizing: border-box;
    overflow: hidden;

    @media (max-width: 1200px) {
      flex-direction: column;
      height: auto;
      overflow: visible;
      padding: 1rem;
      gap: 1.5rem;
    }
  }

  .left-column {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    flex: 0 0 340px;
    min-height: 0;
    height: 100%;
    overflow-y: auto;

    @media (max-width: 1200px) {
      flex: none;
      width: 100%;
      height: auto;
      max-height: 60vh;
    }
  }

  .right-column {
    flex: 0 0 340px;
    min-height: 0;
    height: 100%;
    overflow-y: auto;

    @media (max-width: 1200px) {
      flex: none;
      width: 100%;
      height: auto;
      max-height: 60vh;
    }
  }

  .dashboard {
    flex: 1 1 0;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 2rem;
    height: 100%;
  }

  .dashboard-split {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    flex: 1;
    min-height: 0;
  }

  .pending-section {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }

  .status-bar {
    display: flex;
    padding: 16px 24px;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 1rem;

    .logo-container {
      display: flex;
      align-items: center;
    }

    .logo {
      height: 96px; 
      width: auto;
    }

    .right-section {
      display: flex;
      align-items: center;
      gap: 2rem;
      flex-wrap: wrap;
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
    &.flat {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 24px;
      border-bottom: 1px solid var(--border-primary);
      flex-wrap: wrap;
      gap: 1rem;
      h2 { margin: 0; font-size: 26px; letter-spacing: -0.325px; }
    }
  }

  .pending-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 24px;
  }

  .history-section {
    flex: 1;
    min-height: 0;
    padding: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }

  .check-now {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border: 1px solid var(--border-primary);
    border-radius: 8px;
    background: var(--surface-300);
    color: var(--cursor-dark);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease;
    white-space: nowrap;

    &:hover:not(:disabled) {
      background: var(--surface-500);
      border-color: var(--border-strong);
    }

    &:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
  }

  .spinner {
    width: 12px;
    height: 12px;
    border: 2px solid var(--border-primary);
    border-top-color: var(--color-accent);
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
    display: inline-block;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
