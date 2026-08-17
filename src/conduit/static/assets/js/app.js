// Application shell: routing, navigation, global event delegation.

import { api } from './api.js';
import { closeModal, toast } from './components.js';
import { store } from './store.js';
import { $, html, relativeTime, setHTML } from './util.js';

import activity from './views/activity.js';
import calendarView from './views/calendar.js';
import dashboard from './views/dashboard.js';
import library from './views/library.js';
import queue from './views/queue.js';
import settings from './views/settings.js';

const VIEWS = [dashboard, queue, calendarView, library, activity, settings];
const BY_ID = Object.fromEntries(VIEWS.map((view) => [view.id, view]));
const THEME_KEY = 'conduit.theme';

let current = null;
let frame = null;

// ---------------------------------------------------------------------------
// Routing
// ---------------------------------------------------------------------------
function routeId() {
  const id = (location.hash.replace(/^#\/?/, '') || 'dashboard').split('/')[0];
  return BY_ID[id] ? id : 'dashboard';
}

async function renderRoute() {
  const view = BY_ID[routeId()];
  if (current && current !== view) current.destroy?.();
  current = view;

  $('#page-title').textContent = view.title;
  document.title = view.id === 'dashboard' ? 'rás' : `${view.title} · rás`;
  renderNav();

  const root = $('#view');
  try {
    await view.render(root);
  } catch (error) {
    setHTML(root, html`<div class="card"><div class="empty">
      <span class="empty__icon">⚠</span>${error.message}</div></div>`);
  }
  root.focus({ preventScroll: true });
  closeRailOnMobile();
}

function renderNav() {
  const active = routeId();
  setHTML($('#nav'), html`
    ${VIEWS.map((view) => {
      const badge = view.badge?.();
      return html`
        <a class="navlink" href="#/${view.id}" ${active === view.id ? 'aria-current="page"' : ''}>
          <span class="navlink__icon" aria-hidden="true">${view.icon}</span>
          <span class="grow">${view.title}</span>
          ${badge ? html`<span class="navlink__badge">${badge}</span>` : ''}
        </a>`;
    })}`);
}

// ---------------------------------------------------------------------------
// Status strip
// ---------------------------------------------------------------------------
function renderStatus() {
  const summary = store.summary;
  const connection = store.connection;
  const connectionPill = {
    live: ['pill--ok', 'Live'],
    connecting: ['pill--warn', 'Connecting…'],
    offline: ['pill--err', 'Offline'],
  }[connection] || ['pill--warn', connection];

  const problems = (summary.failed || 0) + (summary.no_space || 0);

  setHTML($('#status-strip'), html`
    ${summary.dry_run ? html`<span class="pill pill--warn">Dry run</span>` : ''}
    ${problems ? html`<a class="pill pill--err" href="#/queue">${problems} problem${problems === 1 ? '' : 's'}</a>` : ''}
    ${summary.downloading
      ? html`<span class="pill pill--info">
               <span class="pill__dot pill__dot--live"></span>${summary.downloading} downloading
             </span>`
      : ''}
    <span class="pill" title="Watchlist last checked">
      ⟳ ${relativeTime(store.timestamps.watchlist_checked_at)}
    </span>
    <span class="pill ${connectionPill[0]}">
      <span class="pill__dot ${connection === 'live' ? 'pill__dot--live' : ''}"></span>${connectionPill[1]}
    </span>`);

  $('#version').textContent = store.state?.version ? `v${store.state.version}` : '';
}

// ---------------------------------------------------------------------------
// Global actions
// ---------------------------------------------------------------------------
const GLOBAL_ACTIONS = {
  async approve(target) {
    await api.approve([Number(target.dataset.id)]);
    toast('Approved — it will start on the next queue pass', 'ok');
    store.refresh();
  },
  async deny(target) {
    await api.deny([Number(target.dataset.id)]);
    toast('Denied and blocklisted');
    store.refresh();
  },
  async retry(target) {
    await api.retry(Number(target.dataset.id));
    toast('Requeued');
    store.refresh();
  },
  async remove(target) {
    if (!confirm('Remove this download from qBittorrent and delete its files?')) return;
    await api.removeDownload(Number(target.dataset.id), true);
    toast('Removed');
    store.refresh();
  },
};

document.addEventListener('click', async (event) => {
  const target = event.target.closest('[data-action], [data-close]');
  if (!target) return;

  if (target.hasAttribute('data-close')) {
    closeModal();
    return;
  }

  const action = target.dataset.action;
  if (!action || target.tagName === 'INPUT' || target.tagName === 'SELECT') return;
  event.preventDefault();

  try {
    if (await current?.onAction?.(action, target, $('#view'))) return;
    if (GLOBAL_ACTIONS[action]) await GLOBAL_ACTIONS[action](target);
  } catch (error) {
    toast(error.message || 'Something went wrong', 'err');
    if (target.disabled) target.disabled = false;
  }
});

const onFieldEvent = (event) => {
  const target = event.target.closest('[data-action]');
  if (!target) return;
  current?.onInput?.(target.dataset.action, target, $('#view'));
};
document.addEventListener('input', onFieldEvent);
document.addEventListener('change', onFieldEvent);

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeModal();
});

// ---------------------------------------------------------------------------
// Theme + chrome
// ---------------------------------------------------------------------------
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
}

$('#theme-toggle').addEventListener('click', () => {
  const order = ['auto', 'dark', 'light'];
  const next = order[(order.indexOf(document.documentElement.dataset.theme) + 1) % order.length];
  applyTheme(next);
  toast(`Theme: ${next}`);
});

$('#menu-toggle').addEventListener('click', () => {
  const rail = $('#rail');
  rail.dataset.open = rail.dataset.open === 'true' ? 'false' : 'true';
});

function closeRailOnMobile() {
  const rail = $('#rail');
  if (window.matchMedia('(max-width: 820px)').matches) rail.dataset.open = 'false';
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------
function scheduleProgressPaint() {
  if (frame) return;
  const paint = () => {
    frame = null;
    if (current?.onProgress) current.onProgress($('#view'));
    if (store.summary.downloading) scheduleProgressPaint();
  };
  frame = requestAnimationFrame(() => setTimeout(paint, 200));
}

store.on('state', () => {
  renderNav();
  renderStatus();
  // Views that cache their own data reload it on the next visit.
  if (current && ['dashboard', 'queue', 'calendar'].includes(current.id)) {
    current.render($('#view'));
  }
  scheduleProgressPaint();
});
store.on('connection', renderStatus);
store.on('progress', scheduleProgressPaint);
store.on('tick', () => {
  if (store.summary.downloading) scheduleProgressPaint();
});
store.on('error', (event) => toast(event.detail.message, 'err'));
store.on('notice', (event) => {
  const { topic } = event.detail;
  if (topic === 'download.created') toast(`Found: ${event.detail.title}`, 'ok');
  if (topic === 'download.completed') toast(`Finished: ${event.detail.title}`, 'ok');
  if (topic === 'config.reloaded') settings.invalidate?.();
  if (topic === 'library.indexed') library.invalidate?.();
});

window.addEventListener('hashchange', renderRoute);

applyTheme(localStorage.getItem(THEME_KEY) || 'auto');
renderNav();
renderStatus();
renderRoute();
store.start();
