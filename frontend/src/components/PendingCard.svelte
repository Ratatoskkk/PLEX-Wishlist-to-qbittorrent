<script lang="ts">
  import type { Download } from '../types';

  interface Props {
    title: string;
    items: Download[];
    onAction: () => void;
  }
  let { title, items, onAction } = $props<Props>();

  function formatSize(bytes: number) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  async function groupAction(path: string) {
    await fetch(path + '/' + encodeURIComponent(title), { method: 'POST' });
    onAction();
  }

  async function singleAction(path: string, id: number) {
    await fetch(path + '/' + id, { method: 'POST' });
    onAction();
  }
</script>

<div class="pending-card glass-panel">
  <div class="card-header">
    <h3>{title}</h3>
    {#if items.length > 1}
      <div class="group-actions">
        <button class="success" onclick={() => groupAction('/api/approve_group')}>Approve All</button>
        <button class="danger" onclick={() => groupAction('/api/deny_group')}>Deny All</button>
      </div>
    {/if}
  </div>

  <div class="items-list">
    {#each items as item}
      <div class="item-row">
        <div class="item-info">
          <span class="item-title">{item.title}</span>
          <div class="item-meta">
            <span class="badge size">{formatSize(item.file_size_bytes)}</span>
            <span class="badge res">{item.resolution}</span>
          </div>
        </div>
        <div class="item-actions">
          <button class="success" onclick={() => singleAction('/api/approve', item.id)} title="Approve">✓</button>
          <button class="danger" onclick={() => singleAction('/api/deny', item.id)} title="Deny">✕</button>
        </div>
      </div>
    {/each}
  </div>
</div>

<style lang="scss">
  .pending-card {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  
  .card-header {
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--border-glass);
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: rgba(0,0,0,0.2);
    
    h3 { margin: 0; font-size: 1.1rem; font-weight: 600; }
    
    .group-actions {
      display: flex;
      gap: 0.5rem;
      button { padding: 4px 8px; font-size: 0.75rem; border-radius: 4px; }
    }
  }
  
  .items-list {
    display: flex;
    flex-direction: column;
  }
  
  .item-row {
    padding: 1rem 1.25rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(255,255,255,0.03);
    
    &:last-child { border-bottom: none; }
  }
  
  .item-info {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    
    .item-title { font-weight: 500; font-size: 0.95rem; }
    
    .item-meta {
      display: flex;
      gap: 0.5rem;
      
      .badge {
        font-size: 0.7rem;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 600;
        background: rgba(255,255,255,0.1);
        
        &.size { color: var(--warning); background: rgba(245, 158, 11, 0.15); }
        &.res { color: var(--accent); background: rgba(99, 102, 241, 0.15); }
      }
    }
  }
  
  .item-actions {
    display: flex;
    gap: 0.5rem;
    
    button {
      padding: 6px 10px;
      font-size: 1rem;
    }
  }
</style>
