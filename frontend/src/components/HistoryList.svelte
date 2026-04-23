<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import type { Download, ProgressUpdate } from '../types';
  import { formatTime } from '../lib/utils';

  interface Props {
    downloads: Download[];
    liveProgress: Record<string, ProgressUpdate>;
  }
  let { downloads, liveProgress } = $props<Props>();

  // Smoothed values driven by rAF — plain object, not reactive (avoids batching lag)
  const targets: Record<string, number> = {};
  const displayed: Record<string, number> = {};

  // Reactive display state written to from rAF
  let smoothProgress = $state<Record<string, number>>({});

  let rafId: number;

  function animate() {
    let dirty = false;

    for (const id of Object.keys(targets)) {
      const target = targets[id];
      const current = displayed[id] ?? target;
      const delta = target - current;

      // Lerp fast enough to reach target before next SSE tick (~1.5s @ 60fps = 90 frames)
      // Factor 0.07 → reaches 99% of target in ~63 frames (~1.05s) — always ahead of SSE
      const next = Math.abs(delta) < 0.0001 ? target : current + delta * 0.07;
      displayed[id] = next;
      dirty = true;
    }

    if (dirty) {
      smoothProgress = { ...displayed };
    }

    rafId = requestAnimationFrame(animate);
  }

  // Keep targets in sync with incoming SSE data
  $effect(() => {
    for (const [id, update] of Object.entries(liveProgress)) {
      targets[id] = update.progress;
      // Seed display on first tick so bar doesn't jump from 0
      if (displayed[id] === undefined) {
        displayed[id] = update.progress;
      }
    }
  });

  onMount(() => {
    rafId = requestAnimationFrame(animate);
  });

  onDestroy(() => {
    cancelAnimationFrame(rafId);
  });

  function getLive(id: number): ProgressUpdate | null {
    return liveProgress[String(id)] ?? null;
  }

  function getProgress(dl: Download): number {
    return smoothProgress[String(dl.id)] ?? dl.progress ?? 0;
  }

  function getEta(dl: Download): number {
    return getLive(dl.id)?.eta_seconds ?? dl.eta_seconds ?? -1;
  }

  function getSpeed(dl: Download): number | null {
    const s = getLive(dl.id)?.speed_mbps;
    return s !== undefined ? s : null;
  }

  // No decimals — rounded values only
  const fmtPct = (p: number) => `${Math.round(p * 100)}%`;
  const fmtSpeed = (mb: number) => `${Math.round(mb)} MB/s`;
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
                      style="width: {(progress * 100).toFixed(3)}%"
                    ></div>
                  </div>
                  <div class="progress-stats">
                    <span class="pct">{fmtPct(progress)}</span>
                    <span class="meta-row">
                      {#if speed !== null}
                        <span class="speed">{fmtSpeed(speed)}</span>
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
    padding: 48px;
    text-align: center;
    color: var(--border-strong);
    font-family: var(--font-body);
    font-style: italic;
    font-size: 19.2px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    text-align: left;

    th {
      padding: 16px 24px;
      color: var(--border-strong);
      font-weight: 500;
      font-size: 13px;
      font-family: var(--font-system);
      text-transform: uppercase;
      letter-spacing: 0.048px;
      border-bottom: 2px solid var(--border-primary);
    }

    td {
      padding: 20px 24px;
      border-bottom: 1px solid var(--border-primary);
      vertical-align: middle;
    }

    tr:last-child td { border-bottom: none; }

    tr.downloading {
      background: var(--surface-300);
    }
  }

  .progress-th { min-width: 210px; }

  .title-cell {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;

    .title-text { 
      font-family: var(--font-display);
      font-weight: 400; 
      font-size: 16px;
    }
    .res-badge {
      font-family: var(--font-code);
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 9999px;
      font-weight: 400;
      letter-spacing: -0.275px;
      background: var(--surface-500);
      color: var(--cursor-dark);
      white-space: nowrap;
    }
  }

  .status-badge {
    font-family: var(--font-system);
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 4px;
    font-weight: 600;
    white-space: nowrap;
    letter-spacing: 0.053px;

    &.pending_approval { background: rgba(192, 133, 50, 0.15); color: #c08532; }
    &.downloading      { background: var(--surface-200); color: var(--color-accent); border: 1px solid var(--border-primary); }
    &.completed        { background: rgba(31, 138, 101, 0.1); color: var(--color-success); }
    &.queued           { background: var(--surface-300); color: var(--border-strong); }
    &.error, &.denied  { background: rgba(207, 45, 86, 0.1);  color: var(--color-error); }
  }

  .progress-container {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 160px;
  }

  .progress-bar-bg {
    height: 4px;
    background: var(--border-primary);
    border-radius: 2px;
    overflow: hidden;
    will-change: contents;
  }

  .progress-fill {
    height: 100%;
    border-radius: 2px;
    background: var(--color-accent);
    will-change: width;

    &.completed {
      background: var(--color-success);
    }

    position: relative;
    overflow: hidden;
  }

  .progress-stats {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    font-family: var(--font-code);
    font-variant-numeric: tabular-nums;
  }

  .pct {
    font-weight: 400;
    color: var(--color-accent);
    min-width: 4ch;
  }

  .meta-row {
    display: flex;
    gap: 12px;
    align-items: center;

    .speed {
      color: var(--border-strong);
      min-width: 6ch;
      text-align: right;
    }

    .eta {
      color: var(--border-strong);
      min-width: 6ch;
      text-align: right;
    }
  }

  .success-text { color: var(--color-success); font-weight: 400; }
  .muted-text   { color: var(--border-strong); }
  .date-col     { color: var(--border-strong); font-size: 14px; white-space: nowrap; }
</style>
