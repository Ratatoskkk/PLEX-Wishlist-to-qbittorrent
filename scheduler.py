import os
import time
from plexapi.myplex import MyPlexAccount
import database
import downloader
import shutil
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

PLEX_URL = os.getenv('PLEX_URL')
PLEX_TOKEN = os.getenv('PLEX_TOKEN')
DOWNLOAD_DIR_1 = os.getenv('DOWNLOAD_DIR_1', 'D:\\Torrents')
DOWNLOAD_DIR_2 = os.getenv('DOWNLOAD_DIR_2', 'E:\\Torrent')

def check_watchlist():
    try:
        account = MyPlexAccount(token=PLEX_TOKEN)
        watchlist = account.watchlist()
        
        for item in watchlist:
            title = item.title
            
            # Find TMDB ID if available from GUIDs
            tmdb_id = None
            for guid in getattr(item, 'guids', []):
                if guid.id.startswith('tmdb://'):
                    tmdb_id = guid.id.replace('tmdb://', '')
                    break

            print(f"Checking watchlist item: {title} (TMDB: {tmdb_id})")
            
            # Search Aither
            best_torrent = downloader.search_aither(title, tmdb_id)
            
            if best_torrent:
                size_bytes = best_torrent.get('size', 0)
                download_link = best_torrent.get('download_link')
                aither_id = str(best_torrent.get('id', ''))
                resolution = best_torrent.get('resolution', 'Unknown')
                
                # The size is returned in raw Bytes by the API
                # 100GB limit logic:
                is_large = float(size_bytes) > (100 * 1024 * 1024 * 1024)
                
                status = 'pending_approval' if is_large else 'queued'
                
                db_id = database.record_download(
                    title=title, 
                    tmdb_id=tmdb_id, 
                    file_size_bytes=float(size_bytes), 
                    status=status,
                    aither_torrent_id=aither_id,
                    download_link=download_link,
                    resolution=resolution
                )
                
                # Remove from watchlist
                account.removeFromWatchlist(item)
                print(f"Processed and queued {title} from watchlist.")
            else:
                print(f"No suitable torrent found for {title}.")
        
        database.update_last_checked()
        
    except Exception as e:
        print(f"Error checking watchlist: {e}")
        database.update_last_checked(error=str(e))

def check_drive_space(needed_bytes):
    """Check D: and E: drives, return the one with the most space that fits needed_bytes."""
    dirs = [DOWNLOAD_DIR_1, DOWNLOAD_DIR_2]
    best_dir = None
    max_free = -1
    
    for d in dirs:
        if os.path.exists(d):
            free_space = shutil.disk_usage(d).free
            if free_space > needed_bytes and free_space > max_free:
                max_free = free_space
                best_dir = d
                
    return best_dir

def process_queue():
    try:
        active_count = downloader.get_active_downloads_count()
        if active_count >= 2:
            print(f"Queue full ({active_count} active). Waiting.")
            return

        available_slots = 2 - active_count
        
        for _ in range(available_slots):
            item = database.get_next_queued_item()
            if not item:
                break
                
            # Size is actually stored in bytes
            needed_bytes = item['file_size_bytes']
            
            # Add 5% buffer for safety
            needed_bytes = needed_bytes * 1.05
            
            selected_dir = check_drive_space(needed_bytes)
            
            if selected_dir:
                print(f"Sending {item['title']} to {selected_dir}")
                success = downloader.send_to_qbittorrent(item['download_link'], selected_dir)
                if success:
                    database.update_download_status(item['id'], 'downloading')
                else:
                    database.update_download_status(item['id'], 'error')
            else:
                print(f"Insufficient space for {item['title']}. Needed: {needed_bytes / (1024**3):.2f} GB")
                database.update_download_status(item['id'], 'insufficient_space')
                
    except Exception as e:
        print(f"Error processing queue: {e}")

def monitor_downloads():
    try:
        active_items = database.get_active_downloads()
        if not active_items:
            return
            
        completed_ids = downloader.check_completed_downloads(active_items)
        for db_id in completed_ids:
            database.update_download_status(db_id, 'completed')
            print(f"Marked download {db_id} as completed in dashboard!")
            
    except Exception as e:
        print(f"Error monitoring downloads: {e}")
