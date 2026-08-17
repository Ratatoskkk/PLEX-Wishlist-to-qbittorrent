import { api } from '../api.js';
import {
  card, downloadRow, emptyState, paintProgress, poster, progressBar, toast,
} from '../components.js';
import { store } from '../store.js';
import { bytes, dayLabel, episodeCode, html, relativeTime, setHTML } from '../util.js';

export default {
  id: 'dashboard',
  title: 'Dashboard',
  icon: '◈',
  badge: () => store.summary.pending_approval || 0,

  render(root) {
    const s = store.summary;
    const active = store.byState('downloading');
    const groups = store.pendingGroups;
    // Two different questions. "Am I ready to start season 4?" is not the same
    // decision as "do I want this title at all?", so they do not share a list.
    const continuations = groups.filter((g) => g.kind === 'continuation');
    const fresh = groups.filter((g) => g.kind !== 'continuation');
    const soon = store.upcoming.slice(0, 8);

    setHTML(root, html`
      <div class="stats">
        ${statTile('Downloading', s.downloading ?? 0, active.length ? 'in flight now' : 'idle', 'stat--accent')}
        ${statTile('Awaiting you', s.pending_approval ?? 0, 'approvals', (s.pending_approval ? 'stat--warn' : ''))}
        ${statTile('Queued', s.queued ?? 0, 'ready to start')}
        ${statTile('Completed', s.completed ?? 0, s.library_size || '0 B')}
        ${statTile('Upcoming', s.upcoming ?? 0, 'tracked releases')}
        ${statTile('Problems', (s.failed ?? 0) + (s.no_space ?? 0), 'failed or out of space',
                   ((s.failed ?? 0) + (s.no_space ?? 0)) ? 'stat--err' : '')}
      </div>

      ${unmatchedCard()}

      ${continuations.length ? html`
        <div class="stack">
          <div class="sectionhead">
            <h2>Ready when you are</h2>
            <span class="sectionhead__note">
              the next season of something you already watch — it waits here until you start it
            </span>
          </div>
          ${continuations.map(continuationCard)}
        </div>` : ''}

      ${fresh.length ? html`
        <div class="stack">
          <div class="sectionhead">
            <h2>Needs your approval</h2>
            <span class="sectionhead__note">new titles, and anything over the size gate</span>
          </div>
          ${fresh.map(approvalCard)}
        </div>` : ''}

      <div class="split">
        <div class="stack">
          ${card('Active downloads',
            active.length
              ? html`<div class="list">${active.map((d) => downloadRow(d, store.progressOf(d)))}</div>`
              : emptyState('◌', 'Nothing downloading',
                           'Approved grabs start automatically when a slot frees up.'),
            html`<button class="btn btn--sm btn--ghost" data-action="sync-watchlist">Check watchlist</button>
                 <button class="btn btn--sm" data-action="dispatch">Run queue now</button>`)}

          ${card('Recent activity',
            html`<div class="list" id="dash-activity">${emptyState('…', 'Loading…')}</div>`,
            html`<a class="btn btn--sm btn--ghost" href="#/activity">View all</a>`)}
        </div>

        <div class="stack">
          ${card('Tracker account',
            html`<div class="card__body stack" style="gap:8px" id="dash-accounts">
              <span class="muted">Loading…</span>
            </div>`)}
          ${card('Storage', html`<div class="card__body">${store.drives.map(driveRow)}</div>`)}
          ${card('Coming up',
            soon.length
              ? html`<div class="list">${soon.map(upcomingRow)}</div>`
              : emptyState('◷', 'Nothing scheduled'),
            html`<a class="btn btn--sm btn--ghost" href="#/calendar">Calendar</a>`)}
          ${card('System', html`<div class="card__body stack" style="gap:8px">${systemRows()}</div>`)}
        </div>
      </div>
    `);

    loadActivity(root);
    loadAccounts(root);
  },

  onProgress(root) {
    for (const item of store.byState('downloading')) {
      paintProgress(root, item, store.progressOf(item));
    }
  },

  async onAction(action, target, root) {
    if (action === 'dispatch') {
      await api.action('dispatch-queue');
      toast('Queue dispatch triggered');
      store.refresh();
      return true;
    }
    if (action === 'sync-watchlist') {
      target.disabled = true;
      const result = await api.action('sync-watchlist');
      toast(
        result.seen
          ? `Watchlist: ${result.seen} item(s), ${result.added} taken on`
          : 'Watchlist is empty',
        result.added ? 'ok' : '',
      );
      store.refresh();
      return true;
    }
    if (action === 'approve-group' || action === 'deny-group') {
      const ids = JSON.parse(target.dataset.ids);
      if (action === 'approve-group') await api.approve(ids);
      else await api.deny(ids);
      toast(`${action === 'approve-group' ? 'Approved' : 'Denied'} ${ids.length} item(s)`,
            action === 'approve-group' ? 'ok' : '');
      store.refresh();
      return true;
    }
    return false;
  },
};

/**
 * The one blind spot in de-duplication, made visible.
 *
 * Everything Conduit knows about what you already own is keyed on the TMDB id
 * Plex assigns. An entry Plex has not matched carries no id, so it looks like
 * missing media and gets bought again -- which costs real credit on a private
 * tracker. Rare, but silent, so it is worth a card rather than a log line.
 */
function unmatchedCard() {
  const rows = store.unmatched;
  if (!rows.length) return '';
  return html`
    <section class="card card--warn">
      <header class="card__head">
        <h2>⚠ ${rows.length} librar${rows.length === 1 ? 'y entry Plex has' : 'y entries Plex has'} not matched</h2>
      </header>
      <div class="card__body stack" style="gap:10px">
        <p class="muted" style="margin:0">
          rás decides what you already own by TMDB id, and these entries have none —
          so it cannot see these files and may pay to download them again.
          Fix each one in Plex (⋯ → <strong>Match</strong>, then <strong>Merge</strong> into
          the right title), then use <a href="#/library">Rescan watched state</a>.
        </p>
        <div class="list">
          ${rows.map((row) => html`
            <div class="row">
              <span class="tag">${row.kind === 'movie' ? 'film' : 'series'}</span>
              <span class="grow trunc">${row.title}</span>
              ${row.episodes
                ? html`<span class="faint mono">${row.episodes} episode${row.episodes === 1 ? '' : 's'} hidden</span>`
                : html`<span class="faint mono">not de-duplicated</span>`}
            </div>`)}
        </div>
      </div>
    </section>`;
}

function statTile(label, value, hint, cls = '') {
  return html`
    <div class="stat ${cls}">
      <div class="stat__label">${label}</div>
      <div class="stat__value">${value}</div>
      <div class="stat__hint">${hint}</div>
    </div>`;
}

function pendingRow(item) {
  return html`
    <div class="approval__row">
      <div class="grow">
        <div class="trunc">${item.title}</div>
        <div class="item__release trunc">${item.release_name}</div>
      </div>
      <span class="faint mono">${bytes(item.size_bytes)}</span>
      <div class="item__actions">
        <button class="btn btn--sm" data-action="approve" data-id="${item.id}">Approve</button>
        <button class="btn btn--sm btn--ghost" data-action="deny" data-id="${item.id}">Deny</button>
      </div>
    </div>`;
}

/**
 * The next season of a show already on the shelf.
 *
 * Deliberately not styled as a warning: nothing is wrong, and the card is
 * *meant* to sit here. It is a shelf, not an inbox — the question is "am I
 * ready to start this?", and leaving it untouched is a valid answer.
 */
function continuationCard(group) {
  const ids = JSON.stringify(group.ids);
  const prev = group.previous_season;
  const season = group.target_season;
  return html`
    <section class="approval approval--next">
      <header class="approval__head">
        ${poster(group.poster_path, group.title)}
        <div class="grow">
          <div class="item__title">${group.title}</div>
          <div class="item__meta">
            ${season !== undefined && season !== null
              ? html`<span class="pill pill--accent">Season ${season} ready</span>` : ''}
            <span class="faint">${group.total_size}</span>
          </div>
          ${prev ? html`
            <div class="approval__progress">
              ${progressBar(prev.progress)}
              <span class="faint mono">
                ${prev.watched}/${prev.episodes} through season ${prev.season}
              </span>
            </div>` : ''}
        </div>
        <div class="item__actions">
          <button class="btn btn--sm btn--primary" data-action="approve-group" data-ids='${ids}'>
            ${season !== undefined && season !== null ? html`Start season ${season}` : 'Start'}
          </button>
          <button class="btn btn--sm btn--ghost" data-action="deny-group" data-ids='${ids}'
                  title="Blocklists this release so it is never offered again. If you are simply not ready yet, leave the card where it is.">
            Not this one
          </button>
        </div>
      </header>
      <div class="approval__body">${group.items.map(pendingRow)}</div>
    </section>`;
}

function approvalCard(group) {
  const ids = JSON.stringify(group.ids);
  return html`
    <section class="approval">
      <header class="approval__head">
        ${poster(group.poster_path, group.title)}
        <div class="grow">
          <div class="item__title">${group.title}</div>
          <div class="item__meta">
            <span class="pill pill--warn">${group.count} item${group.count === 1 ? '' : 's'}</span>
            <span class="faint">${group.total_size} total</span>
          </div>
        </div>
        <div class="item__actions">
          <button class="btn btn--sm btn--primary" data-action="approve-group" data-ids='${ids}'>
            Approve all
          </button>
          <button class="btn btn--sm btn--danger" data-action="deny-group" data-ids='${ids}'>
            Deny all
          </button>
        </div>
      </header>
      <div class="approval__body">${group.items.map(pendingRow)}</div>
    </section>`;
}

function driveRow(drive) {
  const used = drive.percent_used || 0;
  const variant = used > 92 ? 'drive__fill--full' : used > 80 ? 'drive__fill--warn' : '';
  return html`
    <div class="drive">
      <div class="row">
        <strong>${drive.label}</strong>
        <span class="faint mono trunc grow">${drive.path}</span>
        ${drive.exists
          ? html`<span class="mono">${bytes(drive.free_bytes)} free</span>`
          : html`<span class="pill pill--err">offline</span>`}
      </div>
      <div class="drive__bar"><div class="drive__fill ${variant}" style="width:${used}%"></div></div>
      <div class="faint">
        ${bytes(drive.used_bytes)} of ${bytes(drive.total_bytes)} used · ${used}%
      </div>
    </div>`;
}

function upcomingRow(item) {
  const code = episodeCode(item.season, item.episode);
  return html`
    <div class="item" style="grid-template-columns:36px 1fr auto">
      ${poster(item.poster_path, item.title)}
      <div class="grow">
        <div class="trunc">${item.title}</div>
        <div class="faint">
          ${code ? `${code} · ` : ''}${item.episode_title || ''}
        </div>
      </div>
      <span class="faint mono">${dayLabel(item.air_date)}</span>
    </div>`;
}

function systemRows() {
  const t = store.timestamps;
  const rows = [
    ['Watchlist checked', relativeTime(t.watchlist_checked_at)],
    ['Library indexed', relativeTime(t.library_indexed_at)],
    ['Calendar refreshed', relativeTime(t.calendar_refreshed_at)],
    ['Running since', relativeTime(t.started_at)],
    ['Trackers', `${store.summary.indexers ?? 0} enabled`],
  ];
  if (store.summary.dry_run) rows.push(['Mode', 'DRY RUN — nothing will be sent']);
  return rows.map(([label, value]) => html`
    <div class="row"><span class="muted grow">${label}</span><span class="mono">${value}</span></div>`);
}

async function loadAccounts(root) {
  const host = root.querySelector('#dash-accounts');
  if (!host) return;
  try {
    const accounts = await api.accounts();
    if (!accounts.length) {
      setHTML(host, html`<span class="faint">No tracker reachable.</span>`);
      return;
    }
    setHTML(host, html`${accounts.map((a) => html`
      <div class="stack" style="gap:6px">
        <div class="row">
          <strong>${a.indexer}</strong>
          ${a.group ? html`<span class="pill">${a.group}</span>` : ''}
          <span class="grow"></span>
          <span class="faint">${a.username || ''}</span>
        </div>
        <div class="row"><span class="muted grow">Ratio</span>
          <span class="mono" style="color:var(--ok)">${a.ratio ?? '—'}</span></div>
        <div class="row"><span class="muted grow">Buffer</span>
          <span class="mono">${a.buffer ?? '—'}</span></div>
        <div class="row"><span class="muted grow">Up / down</span>
          <span class="mono">${a.uploaded ?? '—'} / ${a.downloaded ?? '—'}</span></div>
        <div class="row"><span class="muted grow">Seeding</span>
          <span class="mono">${a.seeding ?? 0} · ${a.leeching ?? 0} leeching</span></div>
        ${Number(a.hit_and_runs) > 0
          ? html`<div class="row"><span class="muted grow">Hit and runs</span>
                   <span class="mono" style="color:var(--warn)">${a.hit_and_runs}</span></div>`
          : ''}
      </div>`)}`);
  } catch {
    setHTML(host, html`<span class="faint">Tracker unreachable.</span>`);
  }
}

async function loadActivity(root) {
  try {
    const events = await api.events({ limit: 12 });
    const host = root.querySelector('#dash-activity');
    if (!host) return;
    setHTML(host, events.length
      ? html`${events.map((e) => html`
          <div class="event event--${e.level}">
            <span class="event__time">${relativeTime(e.ts)}</span>
            <span class="event__msg">
              <span class="event__cat">${e.category}</span>${e.message}
            </span>
          </div>`)}`
      : emptyState('·', 'No activity yet'));
  } catch { /* the card just stays on its loading state */ }
}
