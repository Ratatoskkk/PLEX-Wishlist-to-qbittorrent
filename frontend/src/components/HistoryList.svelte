<script lang="ts">
  import type { Download, ProgressUpdate } from '../types';

  interface Props {
    downloads: Download[];
    liveProgress: Record<string, ProgressUpdate>;
  }
  let { downloads, liveProgress } = $props<Props>();

  function formatTime(secs: number) {
    if (secs < 0 || secs >= 8640000) return '∞';
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  function getLive(id: number): ProgressUpdate | null {
    return liveProgress[String(id)] ?? null;
  }

  function getProgress(dl: Download): number {
    return getLive(dl.id)?.progress ?? dl.progress ?? 0;
  }

  function getEta(dl: Download): number {
    return getLive(dl.id)?.eta_seconds ?? dl.eta_seconds ?? -1;
  }

  function getSpeed(dl: Download): number | null {
    return getLive(dl.id)?.speed_mbps ?? null;
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
          <th class="progress-th">Progress</th>
          <th>Added</th>
        </tr>
      </thead>
      <tbody>
        {#each downloads as dl (dl.id)}
          {@const live = getLive(dl.id)}
          {@const progress = getProgress(dl)}
          {@const eta = getEta(dl)}
          {@const speed = getSpeed(dl)}
          {@const isLive = live !== null && dl.status === 'downloading'}
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
                    <div
                      class="progress-fill"
                      class:live={isLive}
                      style="width: {(progress * 100).toFixed(2)}%"
                    ></div>
                  </div>
                  <div class="progress-stats">
                    <span class="pct">{(progress * 100).toFixed(1)}%</span>
                    <span class="meta-row">
                      {#if speed !== null}
                        <span class="speed">{speed} MB/s</span>
                      {/if}
                      <span class="eta">ETA: {formatTime(eta)}</span>
                    </span>
                  </div>
                </div>
              {:else if dl.status === 'completed'}
                <div class="progress-container">
                  <div class="progress-bar-bg">
                    <div class="progress-fill completed" style="width: 100%"></div>
                  </div>
                  <div class="progress-stats">
                    <span class="pct success-text">100%</span>
                  </div>
                </div>
              {:else}
                <span class="muted-text">—</span>
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
      background: rgba(99, 102, 241, 0.04);
    }
  }

  .progress-th { min-width: 200px; }

  .title-cell {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;

    .title-text { font-weight: 500; }
    .res-badge {
      font-size: 0.65rem;
      padding: 2px 6px;
      border-radius: 4px;
      font-weight: 600;
      background: rgba(255,255,255,0.1);
      color: var(--text-muted);
      white-space: nowrap;
    }
  }

  .status-badge {
    font-size: 0.75rem;
    padding: 4px 8px;
    border-radius: 6px;
    font-weight: 600;
    white-space: nowrap;

    &.pending_approval { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
    &.downloading { background: rgba(99, 102, 241, 0.2); color: var(--accent); }
    &.completed { background: rgba(16, 185, 129, 0.2); color: var(--success); }
    &.queued { background: rgba(255, 255, 255, 0.1); color: var(--text-main); }
    &.error, &.denied { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
  }

  .progress-container {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    min-width: 160px;
  }

  .progress-bar-bg {
    height: 6px;
    background: rgba(255,255,255,0.08);
    border-radius: 3px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    border-radius: 3px;
    background: var(--accent);
    transition: width 1.2s cubic-bezier(0.4, 0, 0.2, 1);

    &.live {
      background: linear-gradient(90deg, var(--accent), #a78bfa);
      box-shadow: 0 0 8px rgba(99, 102, 241, 0.6);
    }

    &.completed {
      background: var(--success);
      transition: none;
    }
  }

  .progress-stats {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.75rem;
  }

  .pct { font-weight: 700; color: var(--accent); }

  .meta-row {
    display: flex;
    gap: 0.75rem;
    align-items: center;

    .speed {
      color: var(--success);
      font-weight: 600;
      font-size: 0.7rem;
    }

    .eta { color: var(--text-muted); }
  }

  .success-text { color: var(--success); font-weight: 600; }
  .muted-text { color: var(--text-muted); }
  .date-col { color: var(--text-muted); font-size: 0.85rem; white-space: nowrap; }
</style>
