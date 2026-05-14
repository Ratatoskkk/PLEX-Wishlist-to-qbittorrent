<script lang="ts">
  import type { CleanupItem } from '../types';
  import { formatSize } from '$lib/utils';

  interface Props {
    items: CleanupItem[];
    onAction: () => void;
  }
  let { items, onAction }: Props = $props();

  type SortKey = 'size' | 'drive';
  let sortKey: SortKey = $state('size');

  // Track which item is in "confirm" state
  let confirmingId: number | null = $state(null);
  let deletingId: number | null = $state(null);

  const sorted = $derived((() => {
    const copy = [...items];
    if (sortKey === 'size') {
      copy.sort((a, b) => b.file_size_bytes - a.file_size_bytes);
    } else {
      copy.sort((a, b) => a.drive_label.localeCompare(b.drive_label) || b.file_size_bytes - a.file_size_bytes);
    }
    return copy;
  })());

  async function requestDelete(id: number) {
    if (confirmingId === id) {
      // Second click — confirmed, do the delete
      deletingId = id;
      confirmingId = null;
      try {
        const res = await fetch(`/api/cleanup/${id}`, { method: 'POST' });
        if (!res.ok) {
          const data = await res.json();
          console.error('Delete failed:', data.error);
        }
        onAction();
      } finally {
        deletingId = null;
      }
    } else {
      // First click — enter confirm state
      confirmingId = id;
    }
  }

  function cancelConfirm() {
    confirmingId = null;
  }
</script>

<div class="sidebar cursor-card">
  <div class="header">
    <h2>Clean Up</h2>
    <div class="sort-pills">
      <button
        class="sort-pill"
        class:active={sortKey === 'size'}
        onclick={() => { sortKey = 'size'; }}
        id="cleanup-sort-size"
      >Size</button>
      <button
        class="sort-pill"
        class:active={sortKey === 'drive'}
        onclick={() => { sortKey = 'drive'; }}
        id="cleanup-sort-drive"
      >Drive</button>
    </div>
  </div>

  <div class="item-list">
    {#each sorted as item (item.id)}
      <div class="item-card" class:confirming={confirmingId === item.id}>
        <!-- Poster with delete overlay -->
        <div class="poster-container">
          {#if item.poster_path}
            <img
              src="https://image.tmdb.org/t/p/w200{item.poster_path}"
              alt="{item.title} poster"
              loading="lazy"
            />
          {:else}
            <div class="placeholder">No Poster</div>
          {/if}
          <!-- Delete overlay — shown on hover or confirm -->
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <div
            class="delete-overlay"
            class:visible={confirmingId === item.id}
            onclick={() => requestDelete(item.id)}
          >
            {#if deletingId === item.id}
              <span class="overlay-text">Deleting…</span>
            {:else if confirmingId === item.id}
              <span class="overlay-text confirm">Sure?</span>
            {:else}
              <span class="overlay-text">🗑 Delete</span>
            {/if}
          </div>
        </div>

        <div class="info">
          <div class="title">{item.title}</div>
          <div class="badges">
            {#if item.resolution && item.resolution !== 'Unknown'}
              <span class="badge res">{item.resolution}</span>
            {/if}
            <span class="badge drive" class:unknown={item.drive_label === 'Unknown'}>
              {item.drive_label}
            </span>
          </div>
          <div class="size">{formatSize(item.file_size_bytes)}</div>
          {#if item.save_path}
            <div class="path" title={item.save_path}>{item.save_path}</div>
          {/if}
          {#if confirmingId === item.id}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div class="confirm-bar">
              <span class="confirm-text">Delete torrent + files?</span>
              <div class="confirm-actions">
                <button class="btn-confirm" onclick={() => requestDelete(item.id)}>Confirm</button>
                <button class="btn-cancel" onclick={cancelConfirm}>Cancel</button>
              </div>
            </div>
          {/if}
        </div>
      </div>
    {/each}

    {#if sorted.length === 0}
      <div class="empty">No watched items to clean up.</div>
    {/if}
  </div>
</div>

<style lang="scss">
  .sidebar {
    width: 340px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    flex-shrink: 0;
  }

  .header {
    padding: 16px 24px;
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
      background: var(--color-error);
      color: white;
      border-color: transparent;
    }

    &:hover:not(.active) {
      color: var(--cursor-dark);
    }
  }

  .item-list {
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

  .item-card {
    display: flex;
    padding: 16px 24px;
    gap: 16px;
    border-bottom: 1px solid var(--border-primary);
    transition: background 0.2s ease;

    &.confirming {
      background: rgba(207, 45, 86, 0.04);
    }

    &:last-child {
      border-bottom: none;
    }
  }

  .poster-container {
    width: 60px;
    height: 90px;
    border-radius: 6px;
    overflow: hidden;
    position: relative;
    background: var(--surface-500);
    flex-shrink: 0;
    cursor: pointer;

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
      font-size: 10px;
      color: var(--border-strong);
      text-align: center;
      padding: 4px;
    }

    .delete-overlay {
      position: absolute;
      inset: 0;
      background: rgba(207, 45, 86, 0.85);
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      transition: opacity 0.2s ease;

      &.visible {
        opacity: 1;
      }

      .overlay-text {
        font-size: 10px;
        font-weight: 700;
        color: white;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        text-align: center;

        &.confirm {
          font-size: 12px;
          letter-spacing: 1px;
        }
      }
    }

    &:hover .delete-overlay {
      opacity: 1;
    }

    &:hover img {
      transform: scale(1.05);
    }
  }

  .info {
    display: flex;
    flex-direction: column;
    gap: 5px;
    justify-content: center;
    min-width: 0;

    .title {
      font-size: 14px;
      font-weight: 500;
      line-height: 1.3;
      // Clamp to 2 lines
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .badges {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }

    .badge {
      font-family: var(--font-code);
      font-size: 10px;
      padding: 2px 7px;
      border-radius: 9999px;
      font-weight: 400;
      letter-spacing: -0.2px;
      white-space: nowrap;

      &.res {
        background: var(--surface-500);
        color: var(--cursor-dark);
        border: 1px solid var(--border-primary);
      }

      &.drive {
        background: rgba(245, 78, 0, 0.12);
        color: var(--color-accent);
        border: 1px solid rgba(245, 78, 0, 0.2);

        &.unknown {
          background: var(--surface-500);
          color: var(--border-strong);
          border-color: var(--border-primary);
        }
      }
    }

    .size {
      font-size: 13px;
      font-weight: 600;
      color: var(--color-error);
      font-variant-numeric: tabular-nums;
    }

    .path {
      font-size: 10px;
      color: var(--border-strong);
      font-family: var(--font-code);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  }

  .confirm-bar {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 4px;
    padding-top: 8px;
    border-top: 1px solid rgba(207, 45, 86, 0.25);

    .confirm-text {
      font-size: 11px;
      color: var(--color-error);
      font-weight: 500;
    }

    .confirm-actions {
      display: flex;
      gap: 6px;
    }
  }

  .btn-confirm {
    background: rgba(207, 45, 86, 0.15);
    color: var(--color-error);
    border: 1px solid rgba(207, 45, 86, 0.3);
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
    font-family: var(--font-system);
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s ease;

    &:hover { background: rgba(207, 45, 86, 0.25); }
  }

  .btn-cancel {
    background: var(--surface-500);
    color: var(--border-strong);
    border: 1px solid var(--border-primary);
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
    font-family: var(--font-system);
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s ease;

    &:hover { color: var(--cursor-dark); }
  }
</style>
