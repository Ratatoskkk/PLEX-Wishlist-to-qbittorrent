# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Existing guidance files
- No existing `AGENTS.md` or `WARP.md` was found.
- No Claude/Cursor/Copilot rule files were found (`CLAUDE.md`, `.cursorrules`, `.cursor/rules/*`, `.github/copilot-instructions.md`).
- Project-specific rules do exist in `.agent/workflows/project_rules.md`; key rules are summarized below.

## Core development commands
### Backend setup and run
```powershell
pip install -r requirements.txt
python app.py
```

### Windows launcher scripts
```powershell
.\run.bat
```
Runs the app in a console window.

```powershell
cscript .\start_hidden.vbs
```
Runs the app hidden/headless via VBScript.

### Frontend setup and build
```powershell
cd frontend
npm install
npm run build
```
Build artifacts are emitted to `frontend/dist` and served by Flask.

### Frontend dev/type checks
```powershell
cd frontend
npm run dev
```

```powershell
cd frontend
npm run check
```
There is no dedicated ESLint/Prettier script in `frontend/package.json`; `npm run check` (Svelte/TypeScript) is the main static validation command.

### Tests
No formal automated test suite is configured (no repo-level pytest/unittest/vitest scripts).

Available test/debug script:
```powershell
python .\test_watch_state.py
```
This is a Plex watchlist inspection script, not an assertion-based test suite.

Single-test command is therefore currently this script itself (there are no granular test cases to select).

## Architecture overview
### Runtime shape
- `app.py` is the process entrypoint and orchestration hub:
  - Loads `.env` and hard-fails if required credentials are missing.
  - Enforces a single-instance lock via UDP bind on `127.0.0.1:50050`.
  - Initializes SQLite (`database.init_db()`).
  - Starts APScheduler background jobs:
    - `scheduler.check_watchlist` every 15s
    - `scheduler.process_queue` every 15s
    - `scheduler.monitor_downloads` every 60s
  - Serves the built Svelte SPA from `frontend/dist` and exposes API endpoints under `/api/*`.
  - Runs Flask via Waitress in a background thread, with a system tray UI (pystray) controlling open/quit behavior.

### Backend module responsibilities
- `scheduler.py` handles domain workflow:
  - Reads Plex watchlist items (movie/show/season/episode flows).
  - Uses `downloader.py` to query Aither and qBittorrent.
  - Creates queue entries in `database.py`, including `pending_approval` gating for large files and multi-season TV sets.
  - Enforces queue concurrency (max 2 active downloads) and dynamic drive selection (`DOWNLOAD_DIR_1` / `DOWNLOAD_DIR_2`) by free space.
  - Monitors active torrent state and triggers Plex library refresh on completion.

- `downloader.py` encapsulates external integrations and scoring:
  - Authenticated Aither API querying (`search_aither`, `search_aither_tv`).
  - Quality selection logic (4K remux/HDR preference, full-disc filtering).
  - qBittorrent client auth and torrent submission/status reads.
  - Canonical title normalization used for matching DB records to live torrent names.

- `database.py` is the persistence layer:
  - SQLite file `history.db` with `downloads` and singleton `system_status` table.
  - State-machine-like status transitions (`pending_approval`, `queued`, `downloading`, `completed`, `denied`, `error`, `insufficient_space`).
  - Progress/ETA updates for UI and stream consumers.
  - De-duplication by `aither_torrent_id` for non-terminal/relevant states.

### Frontend shape and data flow
- SvelteKit static SPA (`frontend/src`) with `ssr = false` and prerender enabled (`+layout.ts`).
- Main page (`+page.svelte`) combines:
  - polling `/api/state` every 5s for canonical list/state refresh, and
  - SSE stream `/api/stream` for high-frequency live progress updates.
- `HistoryList.svelte` smooths incoming progress with a `requestAnimationFrame` interpolation loop.
- `PendingCard.svelte` drives approve/deny actions (`/api/approve*`, `/api/deny*`).

The UI is read/write against Flask API only; Flask does not server-render Svelte pages.

## Critical implementation rules (from project rules)
### Flask/Waitress + static assets on Windows
- Keep MIME enforcement in `@app.after_request`; relying on per-route MIME settings can break on `304 Not Modified`.
- Preserve SPA catch-all behavior ordering:
  1) API-prefix guard (`api/*` -> 404 from SPA route),
  2) serve physical file when present,
  3) fallback to `index.html`.

### Process model and startup behavior
- Preserve single-instance daemon lock (UDP bind) to prevent duplicate tray/server processes.
- Preserve stdout/stderr null-guard for hidden/headless runs (`pythonw` behavior).

### Torrent matching and queue correctness
- Keep using normalized-title matching when correlating DB items with qBittorrent names; avoid raw string equality checks.
- Keep large-file and multi-season approval gating behavior intact unless explicitly changing product behavior.

### Frontend/Svelte specifics
- In `+layout.svelte`, keep explicit `children` prop declaration when using `{@render children()}`.
- For progress bars driven by live data, prefer rAF-based smoothing over CSS width transitions.

## Rebuild workflow caveat
If frontend sources change, stop the running server before rebuilding to avoid Windows file-lock issues on build output:
1. Quit running app (tray icon -> Quit, or stop process).
2. Rebuild frontend (`cd frontend && npm run build`).
3. Restart backend (`python app.py` or `.\run.bat`).
