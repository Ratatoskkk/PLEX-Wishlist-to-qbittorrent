# Plex Watchlist to qBittorrent Auth-Downloader 🎬

Automatically monitor your Plex Watchlist and send 4K HDR Remux releases to qBittorrent via the Aither private tracker API. Completely headless, interactive, and highly optimized for minimal memory footprint.

✨ ***Proudly developed and optimized by Google Gemini*** ✨

## Features
- **Plex Watchlist Sync**: Automatically checks your Plex Watchlist every 15 seconds.
- **Smart Quality Filtering**: Prioritizes 4K HDR Remux. Skips Full Disc releases. Falls back to 1080p.
- **Queue Manager**: Keeps exactly 2 active downloads simultaneously in qBittorrent to prevent bandwidth choking.
- **Dynamic Drive Allocation**: Calculates file bytes and checks your drives for free space before downloading, assigning the most optimal drive dynamically.
- **UI Dashboard**: A stunning, dark-mode Glassmorphism web UI available at `http://localhost:5000`.
- **Large File Gatekeeper**: Any file >100GB triggers a safety lock and requires manual approval from your Web Dashboard.
- **Headless System Tray**: Runs entirely in the background via a Windows System Tray icon. 

## Setup Instructions
1. Clone the repository.
2. Install the necessary dependencies: `pip install -r requirements.txt`
3. Rename `.env.example` to `.env`.
4. Fill out the `.env` file with your credentials:
   - Your Plex Token (Follow [this guide](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/) to find your token).
   - Your Aither API Key.
   - Your qBittorrent Web UI credentials.
   - Update `DOWNLOAD_DIR_1` and `DOWNLOAD_DIR_2` to your preferred storage drives.
5. **Start:** Run `start_hidden.vbs` to launch the server silently. A tiny icon will appear in your system tray (bottom right). Right click it to open the dashboard or quit the server.

Enjoy your automated home theater workflow!
