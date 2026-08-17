// Thin fetch wrapper. Every call funnels through here so auth headers and
// error handling live in exactly one place.

const TOKEN_KEY = 'conduit.token';

export function getToken() {
  const fromUrl = new URLSearchParams(location.search).get('token');
  if (fromUrl) {
    localStorage.setItem(TOKEN_KEY, fromUrl);
    return fromUrl;
  }
  return localStorage.getItem(TOKEN_KEY) || '';
}

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function request(method, path, body) {
  const headers = { Accept: 'application/json' };
  const token = getToken();
  if (token) headers['X-Conduit-Token'] = token;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (cause) {
    throw new ApiError('rás is not reachable', 0);
  }

  if (response.status === 204) return null;
  const text = await response.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { payload = text; }

  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : `HTTP ${response.status}`;
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), response.status);
  }
  return payload;
}

const query = (params = {}) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : '';
};

export const api = {
  state:      () => request('GET', '/state'),
  health:     () => request('GET', '/health'),
  drives:     () => request('GET', '/drives'),
  accounts:   (refresh = false) => request('GET', `/accounts${query({ refresh })}`),
  tasks:      () => request('GET', '/tasks'),
  runTask:    (name) => request('POST', `/tasks/${encodeURIComponent(name)}/run`),
  setTask:    (name, enabled) => request('POST', `/tasks/${encodeURIComponent(name)}/enabled`, { enabled }),

  events:     (params) => request('GET', `/events${query(params)}`),
  logs:       (params) => request('GET', `/logs${query(params)}`),

  approve:    (ids) => request('POST', '/downloads/approve', { ids }),
  deny:       (ids) => request('POST', '/downloads/deny', { ids }),
  retry:      (id) => request('POST', `/downloads/${id}/retry`),
  download:   (id) => request('GET', `/downloads/${id}`),
  removeDownload: (id, deleteFiles = true, respectSeedGoal = false) =>
    request('DELETE', `/downloads/${id}${query({
      delete_files: deleteFiles, respect_seed_goal: respectSeedGoal,
    })}`),
  history:    (params) => request('GET', `/history${query(params)}`),

  cleanup:     () => request('GET', '/cleanup'),
  cleanupScan: () => request('POST', '/cleanup/scan'),

  media:        (params) => request('GET', `/media${query(params)}`),
  mediaDetail:  (id) => request('GET', `/media/${id}`),
  patchMedia:   (id, patch) => request('PATCH', `/media/${id}`, patch),
  deleteMedia:  (id) => request('DELETE', `/media/${id}`),
  searchMedia:  (id) => request('POST', `/media/${id}/search`),
  previewMedia: (id, season) => request('GET', `/media/${id}/preview${query({ season })}`),
  refreshMedia: (id) => request('POST', `/media/${id}/refresh`),

  upcoming:  () => request('GET', '/upcoming'),
  markWatched:      (ids, watched = true) => request('POST', '/wanted/watched', { ids, watched }),
  markMediaWatched: (id, body = {}) => request('POST', `/media/${id}/watched`, body),
  blocklist: () => request('GET', '/blocklist'),
  unblock:   (id) => request('DELETE', `/blocklist/${id}`),

  config:    () => request('GET', '/config'),
  saveConfig: (config) => request('PUT', '/config', config),

  action: (name, params) => request('POST', `/actions/${name}${query(params)}`),
};
