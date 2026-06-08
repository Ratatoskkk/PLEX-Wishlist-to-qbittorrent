<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import type { TrackedEpisode } from '../types';

  interface Props {
    upcoming: TrackedEpisode[];
    onAction: () => void;
  }
  let { upcoming, onAction }: Props = $props();

  type SortKey = 'date' | 'name';
  let sortKey: SortKey = $state('date');

  const sorted = $derived((() => {
    const copy = [...upcoming];
    
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const todayStr = `${year}-${month}-${day}`;
    
    copy.sort((a, b) => {
      const aIgnored = a.status === 'ignored';
      const bIgnored = b.status === 'ignored';
      if (aIgnored !== bIgnored) {
        return aIgnored ? 1 : -1;
      }
      
      if (sortKey === 'date') {
        const da = a.air_date || '9999-99-99';
        const db = b.air_date || '9999-99-99';
        
        if (da === '9999-99-99' && db !== '9999-99-99') return 1;
        if (db === '9999-99-99' && da !== '9999-99-99') return -1;
        if (da === db) return 0;
        
        const aFuture = da >= todayStr;
        const bFuture = db >= todayStr;
        
        if (aFuture && !bFuture) return -1;
        if (!aFuture && bFuture) return 1;
        
        if (aFuture && bFuture) {
          return da.localeCompare(db);
        } else {
          return db.localeCompare(da);
        }
      } else {
        return a.show_title.localeCompare(b.show_title);
      }
    });
    return copy;
  })());

  let now = $state(Date.now());
  let tickInterval: ReturnType<typeof setInterval>;

  onMount(() => {
    tickInterval = setInterval(() => { now = Date.now(); }, 1000);
  });

  onDestroy(() => {
    clearInterval(tickInterval);
  });

  async function toggleStatus(id: number) {
    await fetch('/api/tracked_episode/' + id + '/toggle', { method: 'POST' });
    onAction();
  }

  function getFormattedDate(airDateStr: string) {
    const target = new Date(airDateStr);
    const today = new Date();
    
    const day = target.getDate();
    const monthName = target.toLocaleString('default', { month: 'short' });
    
    // Add year only if it's next year (or later)
    if (target.getFullYear() > today.getFullYear()) {
      return `${day} ${monthName} ${target.getFullYear()}`;
    }
    return `${day} ${monthName}`;
  }

  function getCountdown(airDateStr: string) {
    const target = new Date(airDateStr).getTime();
    const diff = target - now;
    if (diff <= 0) return "Aired";
    
    const d = Math.floor(diff / (1000 * 60 * 60 * 24));
    const h = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const m = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    
    return `${d.toString().padStart(2, '0')}d ${h.toString().padStart(2, '0')}h ${m.toString().padStart(2, '0')}m`;
  }
</script>

<div class="sidebar cursor-card">
  <div class="header">
    <h2>Upcoming Episodes</h2>
    <div class="sort-pills">
      <button
        class="sort-pill"
        class:active={sortKey === 'date'}
        onclick={() => { sortKey = 'date'; }}
        id="upcoming-sort-date"
      >Date</button>
      <button
        class="sort-pill"
        class:active={sortKey === 'name'}
        onclick={() => { sortKey = 'name'; }}
        id="upcoming-sort-name"
      >Name</button>
    </div>
  </div>
  <div class="episode-list">
    {#each sorted as ep (ep.id)}
      <div class="episode-card" class:ignored={ep.status === 'ignored'}>
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div class="poster-container" onclick={() => toggleStatus(ep.id)} title="Click to toggle download status">
          {#if ep.poster_path}
            <img src="https://image.tmdb.org/t/p/w200{ep.poster_path}" alt="{ep.show_title} poster" loading="lazy" />
          {:else}
            <div class="placeholder">No Poster</div>
          {/if}
          <div class="toggle-overlay">
            {#if ep.status === 'ignored'}
              <span class="icon">✕ Ignored</span>
            {:else}
              <span class="icon">✓ Download</span>
            {/if}
          </div>
        </div>
        <div class="info">
          <div class="title">{ep.show_title}</div>
          {#if ep.media_type === 'movie'}
            <div class="season-ep">Movie</div>
          {:else}
            <div class="season-ep">S{ep.season_num.toString().padStart(2, '0')}E{ep.episode_num.toString().padStart(2, '0')}</div>
          {/if}
          <div class="release-date">{getFormattedDate(ep.air_date)}</div>
          <div class="countdown live-number">{getCountdown(ep.air_date)}</div>
        </div>
      </div>
    {/each}
    {#if upcoming.length === 0}
      <div class="empty">No upcoming episodes.</div>
    {/if}
  </div>
</div>

<style lang="scss">
  .sidebar {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  
  .header {
    padding: 20px 24px;
    border-bottom: 1px solid var(--border-primary);
    background: var(--surface-300);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    h2 { 
      margin: 0; 
      font-size: 18px; 
      font-weight: 400; 
      letter-spacing: -0.11px;
      white-space: nowrap;
    }
  }

  .sort-pills {
    display: flex;
    gap: 4px;
    flex-shrink: 0;
  }

  .sort-pill {
    background: var(--surface-500);
    color: var(--border-strong);
    border: 1px solid var(--border-primary);
    padding: 3px 10px;
    border-radius: 9999px;
    font-size: 12px;
    font-family: var(--font-system);
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease;

    &.active {
      background: var(--color-accent);
      color: white;
      border-color: transparent;
    }

    &:hover:not(.active) {
      color: var(--cursor-dark);
    }
  }

  .episode-list {
    display: flex;
    flex-direction: column;
    overflow-y: auto;
  }

  .empty {
    padding: 24px;
    color: var(--border-strong);
    text-align: center;
    font-size: 14px;
  }

  .episode-card {
    display: flex;
    padding: 20px 24px;
    gap: 16px;
    border-bottom: 1px solid var(--border-primary);
    transition: opacity 0.2s ease, filter 0.2s ease;

    &.ignored {
      opacity: 0.4;
      filter: grayscale(100%);
    }

    &:last-child {
      border-bottom: none;
    }
  }

  .poster-container {
    width: 80px;
    height: 120px;
    border-radius: 6px;
    overflow: hidden;
    position: relative;
    cursor: pointer;
    background: var(--surface-500);
    flex-shrink: 0;
    
    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      transition: transform 0.2s ease;
    }

    .placeholder {
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      color: var(--border-strong);
      text-align: center;
    }

    .toggle-overlay {
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      background: rgba(0, 0, 0, 0.7);
      padding: 6px;
      transform: translateY(100%);
      transition: transform 0.2s ease;
      display: flex;
      justify-content: center;
    }

    &:hover .toggle-overlay {
      transform: translateY(0);
    }
    
    &:hover img {
      transform: scale(1.05);
    }

    .icon {
      font-size: 10px;
      font-weight: 600;
      color: white;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
  }

  .info {
    display: flex;
    flex-direction: column;
    gap: 6px;
    justify-content: center;

    .title {
      font-size: 16px;
      font-weight: 500;
      line-height: 1.3;
    }

    .season-ep {
      font-size: 13px;
      color: var(--border-strong);
      font-family: var(--font-code);
      letter-spacing: -0.275px;
    }
    
    .release-date {
      font-size: 13px;
      font-weight: 500;
      color: var(--color-accent);
    }

    .countdown {
      margin-top: 4px;
      font-size: 16px;
      color: var(--color-success);
      font-weight: 600;
    }

    .live-number {
      font-variant-numeric: tabular-nums;
      min-width: 8ch;
    }
  }
</style>
