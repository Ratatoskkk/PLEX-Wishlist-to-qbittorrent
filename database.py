import sqlite3
from datetime import datetime
import os
from typing import TypedDict, Optional

class DownloadParams(TypedDict):
    title: str
    tmdb_id: Optional[str]
    file_size_bytes: float
    status: str
    aither_torrent_id: str
    download_link: Optional[str]
    resolution: Optional[str]
    poster_path: Optional[str]

DB_PATH = os.path.join(os.path.dirname(__file__), 'history.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                tmdb_id TEXT,
                file_size_bytes REAL,
                status TEXT NOT NULL, -- pending_approval, downloading, completed, error
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                aither_torrent_id TEXT,
                download_link TEXT,
                resolution TEXT,
                progress REAL DEFAULT 0.0,
                eta_seconds INTEGER DEFAULT -1
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS system_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_checked TIMESTAMP,
                last_error TEXT
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS tracked_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id TEXT NOT NULL,
                show_title TEXT NOT NULL,
                season_num INTEGER NOT NULL,
                episode_num INTEGER NOT NULL,
                air_date TIMESTAMP,
                status TEXT NOT NULL -- 'waiting', 'polling', 'downloaded', 'give_up'
            )
        ''')
        # Initialize status row
        db.execute('INSERT OR IGNORE INTO system_status (id, last_checked) VALUES (1, NULL)')

        # Migrations
        cursor = db.execute("PRAGMA table_info(downloads)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'poster_path' not in columns:
            db.execute("ALTER TABLE downloads ADD COLUMN poster_path TEXT")

        cursor = db.execute("PRAGMA table_info(tracked_episodes)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'poster_path' not in columns:
            db.execute("ALTER TABLE tracked_episodes ADD COLUMN poster_path TEXT")
        if 'media_type' not in columns:
            db.execute("ALTER TABLE tracked_episodes ADD COLUMN media_type TEXT DEFAULT 'episode'")

        db.commit()

def record_download(params: DownloadParams):
    with get_db() as db:
        cursor = db.execute('''
            INSERT INTO downloads (title, tmdb_id, file_size_bytes, status, aither_torrent_id, download_link, resolution, poster_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (params['title'], params.get('tmdb_id'), params['file_size_bytes'], params['status'], params['aither_torrent_id'], params.get('download_link'), params.get('resolution', 'Unknown'), params.get('poster_path')))
        db.commit()
        return cursor.lastrowid

def update_download_status(download_id, new_status):
    with get_db() as db:
        db.execute('UPDATE downloads SET status = ? WHERE id = ?', (new_status, download_id))
        db.commit()

def update_download_progress(download_id: int, progress: float, eta_seconds: int):
    with get_db() as db:
        db.execute('UPDATE downloads SET progress = ?, eta_seconds = ? WHERE id = ?', (progress, eta_seconds, download_id))
        db.commit()

def get_all_downloads():
    with get_db() as db:
        return db.execute("SELECT * FROM downloads WHERE status != 'denied' ORDER BY added_date DESC").fetchall()

def get_pending_approvals():
    with get_db() as db:
        return db.execute('SELECT * FROM downloads WHERE status = ? ORDER BY added_date DESC', ('pending_approval',)).fetchall()

def get_next_queued_item():
    with get_db() as db:
        return db.execute('SELECT * FROM downloads WHERE status = ? ORDER BY added_date ASC LIMIT 1', ('queued',)).fetchone()

def get_active_downloads():
    with get_db() as db:
        return db.execute('SELECT * FROM downloads WHERE status = ?', ('downloading',)).fetchall()

def get_download(download_id):
    with get_db() as db:
        return db.execute('SELECT * FROM downloads WHERE id = ?', (download_id,)).fetchone()

def update_last_checked(error=None):
    with get_db() as db:
        db.execute('UPDATE system_status SET last_checked = ?, last_error = ? WHERE id = 1', (datetime.now(), error))
        db.commit()

def get_system_status():
    with get_db() as db:
        return db.execute('SELECT * FROM system_status WHERE id = 1').fetchone()

def is_already_recorded(aither_torrent_id):
    """Return True if this Aither torrent ID is already tracked in a live state.
    
    'Live' means anything that isn't denied or error — i.e. we shouldn't
    re-queue something that is pending_approval, queued, downloading, or completed.
    """
    with get_db() as db:
        row = db.execute(
            "SELECT id FROM downloads WHERE aither_torrent_id = ? AND status NOT IN ('denied', 'error')",
            (str(aither_torrent_id),)
        ).fetchone()
        return row is not None

def add_tracked_episode(tmdb_id: str, show_title: str, season_num: int, episode_num: int, air_date_str: str, poster_path: Optional[str] = None, media_type: str = 'episode', status: str = 'waiting'):
    with get_db() as db:
        # For movies, there's only 1 item per tmdb_id usually, but let's check exact match
        existing = db.execute('SELECT id FROM tracked_episodes WHERE tmdb_id = ? AND season_num = ? AND episode_num = ?', 
                              (tmdb_id, season_num, episode_num)).fetchone()
        if existing:
            return
        db.execute('''
            INSERT INTO tracked_episodes (tmdb_id, show_title, season_num, episode_num, air_date, status, poster_path, media_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (tmdb_id, show_title, season_num, episode_num, air_date_str, status, poster_path, media_type))
        db.commit()

def get_episodes_by_status(status: str):
    with get_db() as db:
        return db.execute('SELECT * FROM tracked_episodes WHERE status = ?', (status,)).fetchall()

def get_upcoming_episodes():
    with get_db() as db:
        return db.execute("SELECT * FROM tracked_episodes WHERE status IN ('waiting', 'polling', 'ignored')").fetchall()

def update_tracked_episode_status(ep_id: int, status: str):
    with get_db() as db:
        db.execute('UPDATE tracked_episodes SET status = ? WHERE id = ?', (status, ep_id))
        db.commit()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
