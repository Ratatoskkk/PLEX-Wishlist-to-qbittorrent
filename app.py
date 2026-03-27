import os
import sys
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

import secrets
from flask import Flask, render_template, request, redirect, url_for, flash
from apscheduler.schedulers.background import BackgroundScheduler
import database
import scheduler
import downloader
import datetime

# Validation check
required_vars = ['PLEX_URL', 'PLEX_TOKEN', 'AITHER_API_KEY', 'QBITTORRENT_URL', 'QBITTORRENT_USERNAME', 'QBITTORRENT_PASSWORD']
missing = [v for v in required_vars if not os.getenv(v)]

if missing:
    print("\n[!] ERROR: Missing configuration variables:", ", ".join(missing))
    print("[!] Please make sure you have renamed '.env.example' to EXACTLY '.env'")
    print("[!] and filled it out completely before running run.bat.\n")
    sys.exit(1)

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Initialize database
database.init_db()

# Setup APScheduler
bg_scheduler = BackgroundScheduler()
bg_scheduler.add_job(func=scheduler.check_watchlist, trigger="interval", seconds=15, max_instances=1)
bg_scheduler.add_job(func=scheduler.process_queue, trigger="interval", seconds=15, max_instances=1)
bg_scheduler.add_job(func=scheduler.monitor_downloads, trigger="interval", seconds=60, max_instances=1)
bg_scheduler.start()

@app.route('/')
def index():
    downloads = database.get_all_downloads()
    system_status = database.get_system_status()
    pending = [d for d in downloads if d['status'] == 'pending_approval']
    
    last_check_str = "Never"
    if system_status and system_status['last_checked']:
        # Format the datetime object correctly string from DB
        try:
             # Depending on sqlite formatting, it might be string
             dt = datetime.datetime.fromisoformat(system_status['last_checked'])
             last_check_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
             last_check_str = str(system_status['last_checked'])
             
    return render_template('index.html', 
                         downloads=downloads, 
                         pending_count=len(pending),
                         last_check=last_check_str,
                         last_error=system_status['last_error'] if system_status else None)

@app.route('/approve/<int:download_id>', methods=['POST'])
def approve(download_id):
    dl = database.get_download(download_id)
    if dl and dl['status'] == 'pending_approval':
        database.update_download_status(download_id, 'queued')
        flash(f"Approved! '{dl['title']}' has been added to the download queue.", "success")
    return redirect(url_for('index'))

@app.route('/deny/<int:download_id>', methods=['POST'])
def deny(download_id):
    dl = database.get_download(download_id)
    if dl and dl['status'] == 'pending_approval':
        database.update_download_status(download_id, 'denied')
        flash(f"Denied download for '{dl['title']}'.", "info")
    return redirect(url_for('index'))

@app.route('/clear', methods=['POST'])
def clear_history():
    with database.get_db() as db:
        db.execute("DELETE FROM downloads WHERE status NOT IN ('pending_approval', 'downloading', 'queued')")
        db.commit()
    flash("Cleared completed/denied/error history.", "success")
    return redirect(url_for('index'))

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
    
    # Memory Optimization: Drop heavy multithreading (4 to 2) since this is a localized CLI tool
    server_thread = threading.Thread(target=serve, args=(app,), kwargs={'host': '0.0.0.0', 'port': 5000, 'threads': 2}, daemon=True)
    server_thread.start()
    
    icon = setup_tray()
    icon.run()
