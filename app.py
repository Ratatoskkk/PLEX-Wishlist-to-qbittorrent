import os
import sys
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

import secrets
from flask import Flask, request, jsonify, Response, stream_with_context
from apscheduler.schedulers.background import BackgroundScheduler
import database
import scheduler
import downloader
import datetime
import urllib.parse
import re

# Validation check
required_vars = ['PLEX_URL', 'PLEX_TOKEN', 'AITHER_API_KEY', 'QBITTORRENT_URL', 'QBITTORRENT_USERNAME', 'QBITTORRENT_PASSWORD', 'WEB_PASSWORD']
missing = [v for v in required_vars if not os.getenv(v)]

if missing:
    print("\n[!] ERROR: Missing configuration variables:", ", ".join(missing))
    print("[!] Please make sure you have renamed '.env.example' to EXACTLY '.env'")
    print("[!] and filled it out completely before running run.bat.\n")
    sys.exit(1)

import socket
import sys

# Prevent multiple background daemon instances from fighting over Port 5000 and spawning infinite system tray icons.
try:
    instance_lock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    instance_lock.bind(('127.0.0.1', 50050))
except OSError:
    print("\n[!] SUCCESS/INFO: PlexAither Automation is ALREADY RUNNING.")
    print("[!] Exiting duplicate instance. Please check your System Tray for the active icon.\n")
    sys.exit(0)

import mimetypes
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'frontend', 'dist'))
app.secret_key = secrets.token_hex(16)

# Initialize database
database.init_db()

# Setup APScheduler
bg_scheduler = BackgroundScheduler()
bg_scheduler.add_job(func=scheduler.check_watchlist, trigger="interval", seconds=15, max_instances=1)
bg_scheduler.add_job(func=scheduler.process_queue, trigger="interval", seconds=15, max_instances=1)
bg_scheduler.add_job(func=scheduler.monitor_downloads, trigger="interval", seconds=60, max_instances=1)
bg_scheduler.start()

from flask import send_from_directory

def check_auth(username, password):
    """This function is called to check if a username / password combination is valid."""
    env_user = os.getenv('WEB_USERNAME', 'admin')
    env_pass = os.getenv('WEB_PASSWORD')
    return secrets.compare_digest(username, env_user) and secrets.compare_digest(password, env_pass)

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

@app.before_request
def require_auth():
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return authenticate()


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_spa(path):
    if path.startswith('api/'):
        return jsonify({"error": "API route not found"}), 404
        
    abs_static = os.path.abspath(app.static_folder)
    full_path = os.path.abspath(os.path.join(abs_static, path))

    # Securely check if the requested path is within the static folder before probing the filesystem
    if path != '' and os.path.commonpath([abs_static, full_path]) == abs_static and os.path.exists(full_path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

@app.after_request
def force_mimetypes(response):
    if request.path.endswith('.js'):
        response.content_type = 'application/javascript'
    elif request.path.endswith('.css'):
        response.content_type = 'text/css'
    elif request.path == '/' or request.path.endswith('.html'):
        response.content_type = 'text/html'
        
    # Bruteforce cache reset to clear corrupted browser MIME types from 304 Not Modified
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/api/state')
def get_state():
    downloads = database.get_all_downloads()
    system_status = database.get_system_status()
    pending = [d for d in downloads if d['status'] == 'pending_approval']
    
    last_check_str = "Never"
    if system_status and system_status['last_checked']:
        try:
             dt = datetime.datetime.fromisoformat(system_status['last_checked'])
             last_check_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
             last_check_str = str(system_status['last_checked'])
             
    pending_groups = {}
    for p in pending:
        match = re.search(r'^(.*?) \((?:Season|S\d+)', p['title'])
        root = match.group(1).strip() if match else p['title']
        if root not in pending_groups:
             pending_groups[root] = []
        pending_groups[root].append(dict(p))
             
    return jsonify({
        'downloads': [dict(d) for d in downloads],
        'pending_groups': pending_groups,
        'pending_count': len(pending),
        'last_check': last_check_str,
        'last_error': system_status['last_error'] if system_status else None
    })

@app.route('/api/stream')
def stream_progress():
    """SSE endpoint — pushes real-time qBittorrent progress every 1.5s for active downloads."""
    import json
    import time

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

                torrents = qbt.torrents_info()
                updates = {}

                torrent_words = [(t, set(downloader.normalize_title(t.name))) for t in torrents]

                for item in active_db:
                    plex_words = set(downloader.normalize_title(item['title']))
                    for t, t_words in torrent_words:
                        if plex_words.issubset(t_words):
                            eta = int(t.eta) if t.eta < 8640000 else -1
                            speed_mbps = round(t.dlspeed / 1_000_000, 2)
                            updates[str(item['id'])] = {
                                'progress': round(float(t.progress), 4),
                                'eta_seconds': eta,
                                'speed_mbps': speed_mbps,
                            }
                            break

                yield f"data: {json.dumps(updates)}\n\n"
            except GeneratorExit:
                break
            except Exception:
                yield "data: {}\n\n"

            time.sleep(1.5)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
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
    decoded_title = urllib.parse.unquote(title)
    with database.get_db() as db:
        db.execute("UPDATE downloads SET status = 'queued' WHERE status = 'pending_approval' AND title LIKE ?", (f"{decoded_title} (%",))
        db.commit()
    return jsonify({"success": True})

@app.route('/api/deny_group/<path:title>', methods=['POST'])
def deny_group(title):
    decoded_title = urllib.parse.unquote(title)
    with database.get_db() as db:
        db.execute("UPDATE downloads SET status = 'denied' WHERE status = 'pending_approval' AND title LIKE ?", (f"{decoded_title} (%",))
        db.commit()
    return jsonify({"success": True})

@app.route('/api/clear', methods=['POST'])
def clear_history():
    with database.get_db() as db:
        db.execute("DELETE FROM downloads WHERE status NOT IN ('pending_approval', 'downloading', 'queued')")
        db.commit()
    return jsonify({"success": True})

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
    
    icon = pystray.Icon("PlexTracker", create_image(), "PlexTracker Web Server", menu=pystray.Menu(
        pystray.MenuItem("Open Dashboard", lambda: os.system("start http://localhost:5000")),
        pystray.MenuItem("Quit", quit_action)
    ))
    return icon

if __name__ == '__main__':
    import threading
    from waitress import serve
    import sys
    
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')

    print("Serving PlexTracker on http://0.0.0.0:5000. Check System Tray.")
    import logging
    logging.getLogger('waitress').setLevel(logging.ERROR) # Mute innocuous queue warnings
    server_thread = threading.Thread(target=serve, args=(app,), kwargs={'host': '0.0.0.0', 'port': 5000, 'threads': 16}, daemon=True)
    server_thread.start()
    
    icon = setup_tray()
    icon.run()
