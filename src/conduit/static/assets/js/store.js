// Live application state.
//
// One WebSocket carries both full snapshots and high-frequency progress
// deltas. Between progress messages the store extrapolates each download from
// its last known speed, so the bars move smoothly instead of stepping every
// time the server ticks.

import { api, getToken } from './api.js';

const RECONNECT_MIN = 1000;
const RECONNECT_MAX = 20000;

class Store extends EventTarget {
  constructor() {
    super();
    this.state = null;
    this.connection = 'connecting';
    this.live = new Map();          // id -> { progress, eta_seconds, speed_bps, at }
    this._socket = null;
    this._retry = RECONNECT_MIN;
    this._tickTimer = null;
    this._reconnectTimer = null;
  }

  // -- lifecycle ----------------------------------------------------------
  async start() {
    try {
      this.state = await api.state();
      this.emit('state');
    } catch (error) {
      this.emit('error', { message: error.message });
    }
    this.connect();
    this._tickTimer = setInterval(() => this.emit('tick'), 1000);
  }

  connect() {
    const token = getToken();
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${scheme}://${location.host}/api/ws${token ? `?token=${encodeURIComponent(token)}` : ''}`;

    let socket;
    try {
      socket = new WebSocket(url);
    } catch {
      this._scheduleReconnect();
      return;
    }
    this._socket = socket;

    socket.onopen = () => {
      if (this._socket !== socket) return;
      this._retry = RECONNECT_MIN;
      this.setConnection('live');
    };
    socket.onmessage = (event) => {
      if (this._socket !== socket) return;
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      this.handle(message);
    };
    socket.onclose = () => {
      // A superseded socket closing must not schedule a second reconnect:
      // on a flaky link that fans out into several parallel connections,
      // each of which then reconnects again on its own close.
      if (this._socket !== socket) return;
      this.setConnection('offline');
      this._scheduleReconnect();
    };
    socket.onerror = () => socket.close();
  }

  _scheduleReconnect() {
    clearTimeout(this._reconnectTimer);
    this._reconnectTimer = setTimeout(() => this.connect(), this._retry);
    this._retry = Math.min(this._retry * 2, RECONNECT_MAX);
  }

  setConnection(value) {
    if (this.connection === value) return;
    this.connection = value;
    this.emit('connection');
  }

  // -- messages -----------------------------------------------------------
  handle(message) {
    switch (message.topic) {
      case 'ping':
        return;
      case 'state':
        this.state = message.state;
        this.live.clear();
        this.emit('state');
        return;
      case 'download.progress': {
        const now = performance.now();
        for (const [id, data] of Object.entries(message.downloads || {})) {
          this.live.set(String(id), { ...data, at: now });
        }
        this.emit('progress');
        return;
      }
      case 'event':
        this.emit('activity', message);
        return;
      case 'task.start':
      case 'task.finish':
        this.emit('task', message);
        return;
      default:
        if (message.state) {
          this.state = message.state;
          this.emit('state');
        }
        this.emit('notice', message);
    }
  }

  async refresh() {
    try {
      this.state = await api.state();
      this.emit('state');
    } catch (error) {
      this.emit('error', { message: error.message });
    }
  }

  /**
   * Best current view of a download's progress: the last server value, moved
   * forward by however long it has been since, at the last reported speed.
   */
  progressOf(download) {
    const live = this.live.get(String(download.id));
    if (!live) {
      return {
        progress: download.progress || 0,
        eta_seconds: download.eta_seconds ?? -1,
        speed_bps: download.speed_bps || 0,
      };
    }
    const elapsed = (performance.now() - live.at) / 1000;
    const size = Number(download.size_bytes) || 0;
    let progress = live.progress || 0;
    if (size > 0 && live.speed_bps > 0 && progress < 1) {
      progress = Math.min(0.999, progress + (live.speed_bps * elapsed) / size);
    }
    const eta = live.eta_seconds >= 0 ? Math.max(0, live.eta_seconds - elapsed) : -1;
    return { progress, eta_seconds: eta, speed_bps: live.speed_bps };
  }

  emit(name, detail = {}) {
    this.dispatchEvent(new CustomEvent(name, { detail }));
  }

  on(name, handler) {
    this.addEventListener(name, handler);
    return () => this.removeEventListener(name, handler);
  }

  // -- convenience accessors ---------------------------------------------
  get summary() { return this.state?.summary ?? {}; }
  get downloads() { return this.state?.downloads ?? []; }
  get pendingGroups() { return this.state?.pending_groups ?? []; }
  get upcoming() { return this.state?.upcoming ?? []; }
  get drives() { return this.state?.drives ?? []; }
  get unmatched() { return this.state?.unmatched ?? []; }
  get tasks() { return this.state?.tasks ?? []; }
  get timestamps() { return this.state?.timestamps ?? {}; }
  byState(...states) { return this.downloads.filter((d) => states.includes(d.state)); }
}

export const store = new Store();
