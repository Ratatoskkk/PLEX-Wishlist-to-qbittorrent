<script lang="ts">
  import type { Download } from '../types';

  interface Props {
    downloads: Download[];
  }
  let { downloads } = $props<Props>();

  function formatTime(secs: number) {
    if (secs < 0 || secs >= 8640000) return '∞';
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  }
</script>

<div class="history-list">
  {#if downloads.length === 0}
    <div class="empty-state">No active or historical downloads found.</div>
  {:else}
    <table>
      <thead>
        <tr>
          <th>Title</th>
          <th>Status</th>
          <th>Progress</th>
          <th>Added</th>
        </tr>
      </thead>
      <tbody>
        {#each downloads as dl}
          <tr class:downloading={dl.status === 'downloading'}>
            <td>
              <div class="title-cell">
                <span class="title-text">{dl.title}</span>
                {#if dl.resolution && dl.resolution !== 'Unknown'}
                  <span class="res-badge">{dl.resolution}</span>
                {/if}
              </div>
            </td>
            <td>
              <span class="status-badge {dl.status}">
                {dl.status.replace('_', ' ').toUpperCase()}
              </span>
            </td>
            <td class="progress-col">
              {#if dl.status === 'downloading'}
                <div class="progress-container">
                  <div class="progress-bar-bg">
                    <div class="progress-fill" style="width: {dl.progress * 100}%"></div>
                  </div>
                  <div class="progress-stats">
                    <span class="pct">{(dl.progress * 100).toFixed(1)}%</span>
                    <span class="eta">ETA: {formatTime(dl.eta_seconds)}</span>
                  </div>
                </div>
              {:else if dl.status === 'completed'}
                <span class="success-text">100%</span>
              {:else}
                <span class="muted-text">-</span>
              {/if}
            </td>
            <td class="date-col">
              {new Date(dl.added_date).toLocaleDateString()}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style lang="scss">
  .history-list {
    width: 100%;
    overflow-x: auto;
  }
  
  .empty-state {
    padding: 3rem;
    text-align: center;
    color: var(--text-muted);
    font-style: italic;
  }
  
  table {
    width: 100%;
    border-collapse: collapse;
    text-align: left;
    
    th {
      padding: 1rem 1.5rem;
      background: rgba(0,0,0,0.2);
      color: var(--text-muted);
      font-weight: 500;
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    
    td {
      padding: 1.25rem 1.5rem;
      border-bottom: 1px solid var(--border-glass);
      vertical-align: middle;
    }
    
    tr:last-child td { border-bottom: none; }
    
    tr.downloading {
      background: rgba(99, 102, 241, 0.05);
    }
  }
  
  .title-cell {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    
    .title-text { font-weight: 500; }
    .res-badge {
      font-size: 0.65rem;
      padding: 2px 6px;
      border-radius: 4px;
      font-weight: 600;
      background: rgba(255,255,255,0.1);
      color: var(--text-muted);
    }
  }
  
  .status-badge {
    font-size: 0.75rem;
    padding: 4px 8px;
    border-radius: 6px;
    font-weight: 600;
    
    &.pending_approval { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
    &.downloading { background: rgba(99, 102, 241, 0.2); color: var(--accent); }
    &.completed { background: rgba(16, 185, 129, 0.2); color: var(--success); }
    &.queued { background: rgba(255, 255, 255, 0.1); color: var(--text-main); }
    &.error, &.denied { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
  }
  
  .progress-container {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    min-width: 150px;
    
    .progress-bar-bg {
      height: 6px;
      background: rgba(255,255,255,0.1);
      border-radius: 3px;
      overflow: hidden;
      
      .progress-fill {
        height: 100%;
        background: var(--success);
        transition: width 0.3s ease;
      }
    }
    
    .progress-stats {
      display: flex;
      justify-content: space-between;
      font-size: 0.75rem;
      
      .pct { font-weight: 600; color: var(--success); }
      .eta { color: var(--text-muted); }
    }
  }
  
  .success-text { color: var(--success); font-weight: 600; font-size: 0.85rem;}
  .muted-text { color: var(--text-muted); }
  .date-col { color: var(--text-muted); font-size: 0.85rem; }
</style>
