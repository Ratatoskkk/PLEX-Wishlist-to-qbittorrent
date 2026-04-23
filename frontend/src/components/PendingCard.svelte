<script lang="ts">
  import type { Download } from '../types';
  import { formatSize } from '$lib/utils';

  interface Props {
    title: string;
    items: Download[];
    onAction: () => void;
  }
  let { title, items, onAction } = $props<Props>();

  async function groupAction(path: string) {
    await fetch(path + '/' + encodeURIComponent(title), { method: 'POST' });
    onAction();
  }

  async function singleAction(path: string, id: number) {
    await fetch(path + '/' + id, { method: 'POST' });
    onAction();
  }
</script>

<div class="pending-card cursor-card">
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
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-primary);
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--surface-300);
    
    h3 { 
      margin: 0; 
      font-size: 18px; 
      font-weight: 400; 
      letter-spacing: -0.11px;
    }
    
    .group-actions {
      display: flex;
      gap: 8px;
    }
  }
  
  .items-list {
    display: flex;
    flex-direction: column;
  }
  
  .item-row {
    padding: 16px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border-primary);
    
    &:last-child { border-bottom: none; }
  }
  
  .item-info {
    display: flex;
    flex-direction: column;
    gap: 8px;
    
    .item-title { 
      font-weight: 400; 
      font-size: 16px; 
    }
    
    .item-meta {
      display: flex;
      gap: 8px;
      
      .badge {
        font-family: var(--font-code);
        font-size: 11px;
        padding: 3px 8px;
        border-radius: 9999px;
        font-weight: 400;
        letter-spacing: -0.275px;
        
        &.size { color: var(--border-strong); background: var(--surface-500); }
        &.res { color: var(--cursor-dark); background: var(--surface-300); border: 1px solid var(--border-primary); }
      }
    }
  }
  
  .item-actions {
    display: flex;
    gap: 8px;
    
    button {
      padding: 6px 12px;
      font-family: var(--font-display);
      font-size: 14px;
    }
  }
</style>
