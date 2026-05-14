import os
import sys
import json
import time
import threading

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')

from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

import secrets
import datetime
import urllib.parse
import re

from flask import Flask, request, jsonify, Response, stream_with_context, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
import database
import scheduler
import downloader

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------
required_vars = [
    'PLEX_URL', 'PLEX_TOKEN', 'AITHER_API_KEY',
    'QBITTORRENT_URL', 'QBITTORRENT_USERNAME', 'QBITTORRENT_PASSWORD', 'TMDB_API_KEY',
]
missing = [v for v in required_vars if not os.getenv(v)]
if missing:
    print("\n[!] ERROR: Missing configuration variables:", ", ".join(missing))
    print("[!] Please make sure you have renamed '.env.example' to EXACTLY '.env'")
    print("[!] and filled it out completely before running run.bat.\n")
    sys.exit(1)

import socket

# Prevent duplicate instances competing over Port 5000 / tray icon
try:
    instance_lock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    instance_lock.bind(('127.0.0.1', 50050))
except OSError:
    print("\n[!] PlexAither Automation is ALREADY RUNNING.")
    print("[!] Exiting duplicate instance. Check your System Tray.\n")
    sys.exit(0)

import mimetypes
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'frontend', 'dist'))
app.secret_key = secrets.token_hex(16)

database.init_db()

bg_scheduler = BackgroundScheduler()
bg_scheduler.add_job(func=scheduler.check_watchlist,       trigger="interval", seconds=15,  max_instances=1)
bg_scheduler.add_job(func=scheduler.process_queue,         trigger="interval", seconds=15,  max_instances=1)
bg_scheduler.add_job(func=scheduler.monitor_downloads,     trigger="interval", seconds=60,  max_instances=1)
bg_scheduler.add_job(func=scheduler.poll_tracked_episodes, trigger="interval", minutes=30,  max_instances=1)
bg_scheduler.add_job(func=scheduler.poll_fresh_releases,   trigger="interval", minutes=60,  max_instances=1)
bg_scheduler.start()

# ---------------------------------------------------------------------------
# Startup: one-time watched-status scan
# ---------------------------------------------------------------------------
def _scan_watched_on_startup() -> None:
    """Run once at startup: check all completed downloads against Plex watched status."""
    import time as _time
    _time.sleep(5)  # give Plex connection a moment to settle
    try:
        plex = scheduler.get_plex_server()
        if not plex:
            print("[Cleanup] Plex unavailable at startup — skipping watched scan.")
            return
        completed = database.get_completed_downloads()
        if not completed:
            return
        print(f"[Cleanup] Scanning {len(completed)} completed downloads for watched status...")
        for dl in completed:
            try:
                results = plex.library.search(dl['title'].split(' (')[0], libtype=None)
                watched = False
                for result in results:
                    r_type = getattr(result, 'type', '')
                    if r_type == 'movie' and result.isWatched:
                        watched = True
                        break
                    if r_type in ('show', 'episode'):
                        # For shows/seasons check all episodes
                        try:
                            eps = result.episodes()
                            if eps and all(e.isWatched for e in eps):
                                watched = True
                                break
                        except Exception:
                            pass
                database.mark_download_watched(dl['id'], watched)
            except Exception as e:
                print(f"[Cleanup] Error checking watched status for '{dl['title']}': {e}")
        print("[Cleanup] Startup watched scan complete.")
    except Exception as e:
        print(f"[Cleanup] Startup scan error: {e}")

threading.Thread(target=_scan_watched_on_startup, daemon=True).start()

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
RE_PENDING_GROUP = re.compile(r'^(.*?) \((?:Season|S\d+)')

@app.before_request
def restrict_to_local():
    ip = request.remote_addr
    if not ip:
        return jsonify({"error": "Forbidden"}), 403
    if ip.startswith(('127.', '192.168.', '10.')):
        return None
    if ip.startswith('172.'):
        parts = ip.split('.')
        if len(parts) > 1 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
            return None
    return jsonify({"error": "Access restricted to local network"}), 403

@app.after_request
def force_mimetypes(response):
    path = request.path
    if path.endswith('.js'):
        response.content_type = 'application/javascript'
    elif path.endswith('.css'):
        response.content_type = 'text/css'
    elif path == '/' or path.endswith('.html'):
        response.content_type = 'text/html'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

# ---------------------------------------------------------------------------
# Static / SPA
# ---------------------------------------------------------------------------
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_spa(path):
    if path.startswith('api/'):
        return jsonify({"error": "API route not found"}), 404
    abs_static = os.path.abspath(app.static_folder)
    full_path = os.path.abspath(os.path.join(abs_static, path))
    if path and os.path.commonpath([abs_static, full_path]) == abs_static and os.path.exists(full_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def _format_last_check(ts: str) -> str:
    try:
        return datetime.datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)

def _group_pending(pending) -> dict:
    groups = {}
    for p in pending:
        match = RE_PENDING_GROUP.search(p['title'])
        root = match.group(1).strip() if match else p['title']
        groups.setdefault(root, []).append(dict(p))
    return groups

def get_torrent_updates(qbt, active_db: list) -> dict:
    """Build a progress-update dict from live qBittorrent data for SSE delivery."""
    updates = {}
    torrents = qbt.torrents_info()
    torrent_words = [(t, set(downloader.normalize_title(t.name))) for t in torrents]
    for item in active_db:
        plex_words = set(downloader.normalize_title(item['title']))
        for t, t_words in torrent_words:
            if plex_words.issubset(t_words):
                updates[str(item['id'])] = {
                    'progress': round(float(t.progress), 4),
                    'eta_seconds': int(t.eta) if t.eta < 8640000 else -1,
                    'speed_mbps': round(t.dlspeed / 1_000_000, 2),
                }
                break
    return updates

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
@app.route('/api/state')
def get_state():
    downloads = database.get_all_downloads()
    system_status = database.get_system_status()
    pending = [d for d in downloads if d['status'] == 'pending_approval']

    last_check_str = "Never"
    if system_status and system_status['last_checked']:
        last_check_str = _format_last_check(system_status['last_checked'])

    upcoming = [dict(ep) for ep in database.get_upcoming_episodes()]
    upcoming.sort(key=lambda x: x['air_date'] or "9999-99-99")

    return jsonify({
        'downloads': [dict(d) for d in downloads],
        'pending_groups': _group_pending(pending),
        'pending_count': len(pending),
        'upcoming': upcoming,
        'last_check': last_check_str,
        'last_error': system_status['last_error'] if system_status else None,
    })


@app.route('/api/stream')
def stream_progress():
    """SSE endpoint — pushes real-time qBittorrent progress every 1.5 s."""
    def generate():
        try:
            qbt = downloader.get_qbt_client()
        except Exception:
            yield "data: {}\n\n"
            return

        while True:
            try:
                active_db = [d for d in database.get_all_downloads() if d['status'] == 'downloading']
                if not active_db:
                    yield "data: {}\n\n"
                    time.sleep(1.5)
                    continue
                updates = get_torrent_updates(qbt, active_db)
                yield f"data: {json.dumps(updates)}\n\n"
            except GeneratorExit:
                break
            except Exception:
                yield "data: {}\n\n"
            time.sleep(1.5)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/api/approve/<int:download_id>', methods=['POST'])
def approve(download_id):
    dl = database.get_download(download_id)
    if dl and dl['status'] == 'pending_approval':
        database.update_download_status(download_id, 'queued')
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Download not found or not pending"}), 400


@app.route('/api/deny/<int:download_id>', methods=['POST'])
def deny(download_id):
    dl = database.get_download(download_id)
    if dl and dl['status'] == 'pending_approval':
        database.update_download_status(download_id, 'denied')
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Download not found or not pending"}), 400


@app.route('/api/approve_group/<path:title>', methods=['POST'])
def approve_group(title):
    decoded = urllib.parse.unquote(title)
    with database.get_db() as db:
        db.execute(
            "UPDATE downloads SET status = 'queued' WHERE status = 'pending_approval' AND title LIKE ?",
            (f"{decoded} (%",),
        )
        db.commit()
    return jsonify({"success": True})


@app.route('/api/deny_group/<path:title>', methods=['POST'])
def deny_group(title):
    decoded = urllib.parse.unquote(title)
    with database.get_db() as db:
        db.execute(
            "UPDATE downloads SET status = 'denied' WHERE status = 'pending_approval' AND title LIKE ?",
            (f"{decoded} (%",),
        )
        db.commit()
    return jsonify({"success": True})


@app.route('/api/tracked_episode/<int:ep_id>/toggle', methods=['POST'])
def toggle_tracked_episode(ep_id):
    with database.get_db() as db:
        ep = db.execute('SELECT * FROM tracked_episodes WHERE id = ?', (ep_id,)).fetchone()
        if not ep:
            return jsonify({"success": False, "error": "Not found"}), 404

        tmdb_id = ep['tmdb_id']
        show_title = ep['show_title']

        if ep['status'] == 'ignored':
            new_status = 'polling'
            db.execute(
                "UPDATE tracked_episodes SET status = 'waiting' WHERE tmdb_id = ? AND status = 'ignored'",
                (tmdb_id,),
            )
            db.execute(
                "UPDATE tracked_episodes SET status = 'polling' WHERE tmdb_id = ? AND status = 'waiting' AND datetime(air_date) <= datetime('now')",
                (tmdb_id,),
            )
            db.commit()
            print(f"[*] All tracked items for '{show_title}' set to Auto Download.")
            threading.Thread(target=scheduler.poll_tracked_episodes, daemon=True).start()
        else:
            new_status = 'ignored'
            db.execute(
                "UPDATE tracked_episodes SET status = 'ignored' WHERE tmdb_id = ? AND status IN ('waiting', 'polling')",
                (tmdb_id,),
            )
            db.commit()
            print(f"[*] All tracked items for '{show_title}' set to DO NOT DOWNLOAD.")

    return jsonify({"success": True, "new_status": new_status})


@app.route('/api/poll_now', methods=['POST'])
def poll_now():
    """Manual trigger: run poll_tracked_episodes + poll_fresh_releases immediately."""
    def _run():
        scheduler.poll_tracked_episodes()
        scheduler.poll_fresh_releases()
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"success": True, "message": "Manual poll triggered."})


@app.route('/api/clear', methods=['POST'])
def clear_history():
    with database.get_db() as db:
        db.execute("DELETE FROM downloads WHERE status NOT IN ('pending_approval', 'downloading', 'queued')")
        db.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Cleanup API
# ---------------------------------------------------------------------------
DOWNLOAD_DIR_1 = os.getenv('DOWNLOAD_DIR_1', 'D:\\Torrents')
DOWNLOAD_DIR_2 = os.getenv('DOWNLOAD_DIR_2', 'E:\\Torrent')

def _drive_label(save_path: str) -> str:
    """Return 'Drive 1', 'Drive 2', or 'Unknown' based on which dir the path starts with."""
    if not save_path:
        return 'Unknown'
    p = save_path.rstrip('/\\')
    if p.startswith(DOWNLOAD_DIR_1.rstrip('/\\')):
        return 'Drive 1'
    if DOWNLOAD_DIR_2 and p.startswith(DOWNLOAD_DIR_2.rstrip('/\\')):
        return 'Drive 2'
    return 'Unknown'


@app.route('/api/cleanup')
def get_cleanup_list():
    """Return completed downloads that are marked watched in Plex."""
    completed = database.get_completed_downloads()
    watched_items = [d for d in completed if d['watched']]
    result = []
    for dl in watched_items:
        save_path = dl['save_path'] or ''
        result.append({
            'id': dl['id'],
            'title': dl['title'],
            'poster_path': dl['poster_path'],
            'file_size_bytes': dl['file_size_bytes'],
            'save_path': save_path,
            'drive_label': _drive_label(save_path),
            'resolution': dl['resolution'] or 'Unknown',
        })
    return jsonify(result)


@app.route('/api/cleanup/<int:download_id>', methods=['POST'])
def delete_cleanup_item(download_id):
    """Delete a completed download: remove from qBittorrent (with files) then from DB."""
    dl = database.get_download(download_id)
    if not dl:
        return jsonify({"success": False, "error": "Not found"}), 404

    # Try to remove from qBittorrent
    qbt_removed = False
    try:
        qbt = downloader.get_qbt_client()
        torrents = qbt.torrents_info()
        plex_words = set(downloader.normalize_title(dl['title']))
        target_tag = f"plexaither_{download_id}"
        hashes_to_delete = []

        for t in torrents:
            tags = [tag.strip() for tag in getattr(t, 'tags', '').split(',') if tag.strip()]
            if target_tag in tags:
                hashes_to_delete.append(t.hash)
                break

        # Fallback: word-subset title match
        if not hashes_to_delete:
            for t in torrents:
                t_words = set(downloader.normalize_title(t.name))
                if plex_words.issubset(t_words):
                    hashes_to_delete.append(t.hash)
                    break

        if hashes_to_delete:
            qbt.torrents_delete(delete_files=True, torrent_hashes=hashes_to_delete)
            qbt_removed = True
            print(f"[Cleanup] Deleted torrent for '{dl['title']}' from qBittorrent (with files).")
        else:
            print(f"[Cleanup] Torrent for '{dl['title']}' not found in qBittorrent — already removed.")
            qbt_removed = True  # treat as success if not present
    except Exception as e:
        print(f"[Cleanup] qBittorrent delete error for id={download_id}: {e}")
        return jsonify({"success": False, "error": f"qBittorrent error: {e}"}), 500

    # Remove DB record
    database.delete_download_record(download_id)
    print(f"[Cleanup] Removed download record id={download_id} from DB.")
    return jsonify({"success": True, "qbt_removed": qbt_removed})


# ---------------------------------------------------------------------------
# System tray
# ---------------------------------------------------------------------------
def create_image():
    from PIL import Image, ImageDraw
    image = Image.new('RGB', (64, 64), (108, 92, 231))
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=(255, 255, 255))
    return image


def setup_tray():
    import pystray

    def quit_action(icon, item):
        icon.stop()
        os._exit(0)

    return pystray.Icon(
        "PlexTracker",
        create_image(),
        "PlexTracker Web Server",
        menu=pystray.Menu(
            pystray.MenuItem("Open Dashboard", lambda: os.system("start http://localhost:5000")),
            pystray.MenuItem("Quit", quit_action),
        ),
    )


if __name__ == '__main__':
    from waitress import serve
    import logging

    logging.getLogger('waitress').setLevel(logging.ERROR)
    print("Serving PlexTracker on http://localhost:5000. Check System Tray.")
    server_thread = threading.Thread(
        target=serve, args=(app,), kwargs={'host': '0.0.0.0', 'port': 5000, 'threads': 16}, daemon=True
    )
    server_thread.start()
    setup_tray().run()
