import sqlite3
import downloader

def backfill():
    db = sqlite3.connect('history.db')
    cursor = db.cursor()
    rows = cursor.execute("SELECT id, tmdb_id FROM tracked_episodes WHERE poster_path IS NULL").fetchall()
    
    for r in rows:
        ep_id, tmdb_id = r
        try:
            details = downloader.fetch_tmdb_tv_details(tmdb_id)
            if details and 'poster_path' in details:
                cursor.execute("UPDATE tracked_episodes SET poster_path = ? WHERE id = ?", (details['poster_path'], ep_id))
                print(f"Updated {ep_id} with poster {details['poster_path']}")
        except Exception as e:
            print(f"Failed for {ep_id}: {e}")
            
    db.commit()
    db.close()

if __name__ == '__main__':
    backfill()
