# Plex Watchlist to qBittorrent Automation 🎬

Automatically monitor your Plex Watchlist and send 4K HDR Remux releases to qBittorrent via the Aither private tracker API. Runs completely headless as a Windows background daemon with a modern, reactive web dashboard.

✨ ***Proudly developed and optimized by Google Gemini*** ✨

## Architecture

This project uses a **decoupled hybrid architecture**:

- **Backend**: Python (Flask + Waitress) — handles scheduling, Plex API polling, Aither torrent search, qBittorrent management, and serves the REST API at `/api/state`.
- **Frontend**: SvelteKit 5 (Runes mode) + TypeScript + SCSS — a glassmorphism SPA served statically by Flask, polling the API every 5 seconds for live updates.

## Features

- **Plex Watchlist Sync** — Automatically checks your Plex Watchlist on a schedule.
- **Smart Quality Filtering** — Prioritizes 4K HDR Remux. Skips Full Disc releases. Falls back to 1080p.
- **Queue Manager** — Keeps exactly 2 active downloads simultaneously to prevent bandwidth saturation.
- **Dynamic Drive Allocation** — Checks free space across configured drives and picks the best one per download.
- **Real-time Progress & ETA** — The dashboard shows live download percentage and estimated time remaining, updated every scheduler cycle.
- **Large File Gatekeeper** — Files >100GB require manual approval from the dashboard before downloading.
- **Approval/Deny UI** — Approve or deny individual torrents or entire season packs from the web dashboard.
- **Single-Instance Lock** — Prevents duplicate background daemons from spawning when `run.bat` is clicked multiple times.
- **Headless System Tray** — Runs entirely in the background via a Windows System Tray icon.
- **Basic Authentication** — The web dashboard and API are protected by credentials configured in your `.env` file.

## Setup

### 1. Python Backend

```bash
pip install -r requirements.txt
```

### 2. Frontend (first-time only)

> Requires [Node.js](https://nodejs.org/) v18+.

```bash
cd frontend
npm install
npm run build
cd ..
```

> **Note:** The compiled output goes to `frontend/dist/` and is served automatically by Flask. You only need to rebuild when you change frontend source files.

### 3. Configuration

1. Rename `.env.example` to `.env`.
2. Fill in your credentials:

```env
PLEX_URL=http://your-plex-server:32400
PLEX_TOKEN=your_plex_token
AITHER_API_KEY=your_aither_api_key
QBITTORRENT_URL=http://localhost:8080
QBITTORRENT_USERNAME=admin
QBITTORRENT_PASSWORD=password
DOWNLOAD_DIR_1=E:\Torrent
DOWNLOAD_DIR_2=D:\Torrent
WEB_USERNAME=admin
WEB_PASSWORD=choose_a_strong_password
```

> Find your Plex token via [this guide](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).

### 4. Run

Double-click `run.bat` (or `start_hidden.vbs` to launch fully silently).

A system tray icon will appear in the bottom-right of your taskbar. Right-click it to:
- **Open Dashboard** → `http://localhost:5000`
- **Quit**

## Dashboard

The web UI at `http://localhost:5000` shows:

| Section | Description |
|---|---|
| **Status Bar** | Last scheduler check time and any errors |
| **Requires Approval** | Pending large files or season packs needing manual action |
| **Active & History** | All downloads with status, progress %, ETA, and date added |

## Rebuilding the Frontend

If you modify any files inside `frontend/src/`, you need to rebuild before the changes are served:

```bash
# Stop the server first (right-click tray icon → Quit), then:
cd frontend
npm run build
cd ..
# Restart the server
run.bat
```

## Project Structure

```
plex_aither_automation/
├── app.py              # Flask REST API + SPA host (with Basic Auth)
├── scheduler.py        # APScheduler jobs (watchlist + download monitor)
├── downloader.py       # Aither API search + qBittorrent integration
├── database.py         # SQLite history with progress/ETA tracking
├── tray.py             # Windows system tray daemon
├── run.bat             # Launch script
├── .env                # Your credentials (not committed)
├── .env.example        # Template for your credentials
├── frontend/
│   ├── src/
│   │   ├── routes/     # SvelteKit pages (+layout.svelte, +page.svelte)
│   │   ├── components/ # HistoryList, PendingCard
│   │   └── types.ts    # Shared TypeScript interfaces
│   ├── dist/           # Built SPA output (served by Flask, not committed)
│   └── svelte.config.js
└── requirements.txt
```
