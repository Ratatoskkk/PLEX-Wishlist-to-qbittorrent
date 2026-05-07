import sys
import os

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')

from scheduler import get_plex_server, track_tv_show, extract_tmdb_id
import database

def sync_library():
    print("Syncing existing Plex library shows to the tracker...")
    plex = get_plex_server()
    if not plex:
        print("Plex server not available.")
        return
        
    count = 0
    for section in plex.library.sections():
        if section.type == 'show':
            shows = section.all()
            for show in shows:
                tmdb_id = extract_tmdb_id(show)
                if tmdb_id:
                    print(f"Tracking {show.title.encode('ascii', 'ignore').decode('ascii')}...")
                    track_tv_show(show.title, tmdb_id)
                    count += 1
                    
    print(f"Finished checking {count} shows in library.")

if __name__ == "__main__":
    database.init_db()
    sync_library()
