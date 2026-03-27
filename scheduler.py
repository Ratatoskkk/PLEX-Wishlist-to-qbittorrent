import os
import time
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer
import database
import downloader
import shutil
import shutil
import re
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
        
        # Connect to local server to check watch history
        try:
            plex = PlexServer(PLEX_URL, PLEX_TOKEN)
        except Exception as e:
            print(f"Warning: Could not connect to local Plex Server at {PLEX_URL} to verify watch history. TV Shows will assume 0 watch history.")
            plex = None
            
        watchlist = account.watchlist()
        
        for item in watchlist:
            title = item.title
            item_type = getattr(item, 'type', 'movie')
            
            # Find TMDB ID if available from GUIDs
            tmdb_id = None
            for guid in getattr(item, 'guids', []):
                if guid.id.startswith('tmdb://'):
                    tmdb_id = guid.id.replace('tmdb://', '')
                    break

            print(f"Checking watchlist item: {title} (TMDB: {tmdb_id}) Type: {item_type}")
            
            if item_type == 'movie':
                # Existing Movie Logic
                best_torrent = downloader.search_aither(title, tmdb_id)
                
                if best_torrent:
                    size_bytes = best_torrent.get('size', 0)
                    download_link = best_torrent.get('download_link')
                    aither_id = str(best_torrent.get('id', ''))
                    resolution = best_torrent.get('resolution', 'Unknown')
                    
                    is_large = float(size_bytes) > (100 * 1024 * 1024 * 1024)
                    status = 'pending_approval' if is_large else 'queued'
                    
                    database.record_download(
                        title=title, 
                        tmdb_id=tmdb_id, 
                        file_size_bytes=float(size_bytes), 
                        status=status,
                        aither_torrent_id=aither_id,
                        download_link=download_link,
                        resolution=resolution
                    )
                    
                    account.removeFromWatchlist(item)
                    print(f"Processed and queued {title} from watchlist.")
                else:
                    print(f"No suitable torrent found for {title}.")

            elif item_type == 'show':
                # Advanced TV Show Logic with Dashboard Override
                watched_seasons = []
                watched_episodes = set()
                
                if plex:
                    try:
                        local_results = plex.library.search(title, libtype='show')
                        if local_results:
                            local_show = local_results[0]
                            if local_show.title.lower() == title.lower():
                                max_local_season = 0
                                existing_seasons = []
                                
                                for season in local_show.seasons():
                                    s_num = season.seasonNumber
                                    if s_num == 0: continue
                                    
                                    existing_seasons.append(s_num)
                                    if s_num > max_local_season:
                                        max_local_season = s_num
                                        
                                    eps = season.episodes()
                                    if not eps:
                                        watched_seasons.append(s_num)
                                    else:
                                        all_watched = True
                                        for ep in eps:
                                            if ep.isWatched:
                                                watched_episodes.add((s_num, ep.episodeNumber))
                                            else:
                                                all_watched = False
                                        
                                        if all_watched:
                                            watched_seasons.append(s_num)
                                            
                                # Shield: Assume deleted past seasons are fully watched
                                for s in range(1, max_local_season):
                                    if s not in existing_seasons:
                                        watched_seasons.append(s)
                    except Exception as e:
                        print(f"Error checking local Plex explicitly for {title}: {e}")
                
                available_data = downloader.search_aither_tv(title, tmdb_id)
                season_packs = available_data.get('seasons', {})
                single_eps = available_data.get('episodes', {})
                
                existing_qbt_names = downloader.get_all_torrent_names()
                
                def is_already_downloaded(s_num, e_num=None):
                    normalized_title_words = set(downloader.normalize_title(title))
                    for t_name in existing_qbt_names:
                        t_words = set(downloader.normalize_title(t_name))
                        if normalized_title_words.issubset(t_words) or (title.lower() in t_name.lower()):
                            if e_num:
                                if re.search(rf'\bS{s_num:02d}[ .]?E{e_num:02d}\b', t_name, re.IGNORECASE):
                                    return True
                            else:
                                match_s = re.search(r'\bS(\d{1,2})\b', t_name, re.IGNORECASE)
                                has_episode = re.search(r'\bE(\d{1,2})\b', t_name, re.IGNORECASE)
                                if match_s and not has_episode and int(match_s.group(1)) == s_num:
                                    return True
                    return False
                
                items_to_queue = []
                distinct_seasons_queued = set()
                
                # 1. Gather Unwatched Season Packs
                for s_num, best_t in season_packs.items():
                    if s_num == 0 or s_num in watched_seasons: continue
                    if is_already_downloaded(s_num):
                        print(f"Skipping {title} Season {s_num} (Already in qBittorrent history).")
                        continue
                        
                    name = f"{title} (Season {s_num})"
                    items_to_queue.append((best_t, name))
                    distinct_seasons_queued.add(s_num)
                
                # 2. Gather Unwatched Individual Episodes
                for (s_num, e_num), best_t in single_eps.items():
                    if s_num == 0: continue
                    if (s_num, e_num) in watched_episodes: continue
                    if s_num in watched_seasons: continue
                    if s_num in season_packs: continue
                    if is_already_downloaded(s_num, e_num):
                        print(f"Skipping {title} S{s_num:02d}E{e_num:02d} (Already in qBittorrent history).")
                        continue
                    
                    name = f"{title} (S{s_num:02d}E{e_num:02d})"
                    items_to_queue.append((best_t, name))
                    distinct_seasons_queued.add(s_num)
                
                force_pending = len(distinct_seasons_queued) > 1
                
                for t_dict, name in items_to_queue:
                    size_bytes = float(t_dict.get('size', 0))
                    is_large = size_bytes > (100 * 1024 * 1024 * 1024)
                    
                    status = 'pending_approval' if (is_large or force_pending) else 'queued'
                    
                    database.record_download(
                        title=name, 
                        tmdb_id=tmdb_id, 
                        file_size_bytes=size_bytes, 
                        status=status,
                        aither_torrent_id=str(t_dict.get('id', '')),
                        download_link=t_dict.get('download_link'),
                        resolution=t_dict.get('resolution', 'Unknown')
                    )
                
                if items_to_queue:
                    account.removeFromWatchlist(item)
                    msg = "forced pending approval (multi-season)" if force_pending else "queued"
                    print(f"Processed TV Show {title}. 1:{len(items_to_queue)} items {msg}.")
                else:
                    print(f"No suitable or un-watched seasons/episodes found on Aither for {title}.")
                
            elif item_type == 'season':
                # Explicit Season Handling
                show_title = getattr(item, 'parentTitle', title)
                season_num = getattr(item, 'index', 1) 
                
                print(f"Processing explicit Season Watchlist: {show_title} Season {season_num}")
                available_data = downloader.search_aither_tv(show_title, tmdb_id)
                season_packs = available_data.get('seasons', {})
                
                best_t = season_packs.get(season_num)
                if best_t:
                    is_large = float(best_t.get('size', 0)) > (100 * 1024 * 1024 * 1024)
                    database.record_download(
                        title=f"{show_title} (Season {season_num})", 
                        tmdb_id=tmdb_id, 
                        file_size_bytes=float(best_t.get('size', 0)), 
                        status='pending_approval' if is_large else 'queued',
                        aither_torrent_id=str(best_t.get('id', '')),
                        download_link=best_t.get('download_link'),
                        resolution=best_t.get('resolution', 'Unknown')
                    )
                    account.removeFromWatchlist(item)
                    print(f"Successfully queued {show_title} Season {season_num}.")
                else:
                    print(f"No suitable pack found on Aither for {show_title} Season {season_num}.")
                    
            elif item_type == 'episode':
                # Explicit Episode Handling for Ongoing Shows
                show_title = getattr(item, 'grandparentTitle', title)
                season_num = getattr(item, 'parentIndex', 1)
                episode_num = getattr(item, 'index', 1)
                
                print(f"Processing explicit Episode Watchlist: {show_title} S{season_num:02d}E{episode_num:02d}")
                available_data = downloader.search_aither_tv(show_title, tmdb_id)
                episodes = available_data.get('episodes', {})
                
                best_t = episodes.get((season_num, episode_num))
                if best_t:
                    is_large = float(best_t.get('size', 0)) > (100 * 1024 * 1024 * 1024)
                    database.record_download(
                        title=f"{show_title} (S{season_num:02d}E{episode_num:02d})", 
                        tmdb_id=tmdb_id, 
                        file_size_bytes=float(best_t.get('size', 0)), 
                        status='pending_approval' if is_large else 'queued',
                        aither_torrent_id=str(best_t.get('id', '')),
                        download_link=best_t.get('download_link'),
                        resolution=best_t.get('resolution', 'Unknown')
                    )
                    account.removeFromWatchlist(item)
                    print(f"Successfully queued {show_title} S{season_num:02d}E{episode_num:02d}.")
                else:
                    print(f"No suitable file found on Aither for {show_title} S{season_num:02d}E{episode_num:02d}.")
        
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
