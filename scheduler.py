import os
import shutil
import re
import time
from typing import List, Set, Tuple, Dict, Any, Optional
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer
import database
import downloader
from dotenv import load_dotenv
import qbittorrentapi

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

PLEX_URL = os.getenv('PLEX_URL')
PLEX_TOKEN = os.getenv('PLEX_TOKEN')
DOWNLOAD_DIR_1 = os.getenv('DOWNLOAD_DIR_1', 'D:\\Torrents')
DOWNLOAD_DIR_2 = os.getenv('DOWNLOAD_DIR_2', 'E:\\Torrent')

# Pre-compiled regex patterns for performance
RE_TV_TITLE = re.compile(r'\((?:Season \d+|S\d+E\d+)\)', re.IGNORECASE)
RE_S_NUM = re.compile(r'\bS(\d{1,2})\b', re.IGNORECASE)
RE_E_NUM = re.compile(r'\bE(\d{1,2})\b', re.IGNORECASE)

import threading

def _do_delayed_remove(account: MyPlexAccount, item):
    time.sleep(10)
    try:
        account.removeFromWatchlist(item)
    except Exception as e:
        pass

def delayed_remove_from_watchlist(account: MyPlexAccount, item):
    """Wait 10 seconds before removing to give Plex time to settle internal states."""
    title = getattr(item, 'title', 'Unknown Item')
    print(f"Scheduling removal of '{title}' from watchlist in 10s...")
    threading.Thread(target=_do_delayed_remove, args=(account, item), daemon=True).start()

def get_plex_server() -> Optional[PlexServer]:
    """Guard clause pattern for optional Plex Server"""
    try:
        if PLEX_URL and PLEX_TOKEN:
            return PlexServer(PLEX_URL, PLEX_TOKEN)
    except Exception as e:
        print(f"Warning: Could not connect to local Plex Server at {PLEX_URL}. (Error: {e})")
    return None

def trigger_plex_refresh(title: str) -> None:
    """Trigger a Plex library refresh after a download completes.
    
    Determines whether the completed item is a movie or TV show from
    the title format, then refreshes only the relevant library section.
    """
    plex = get_plex_server()
    if not plex:
        print(f"Plex refresh skipped — server unavailable.")
        return

    # TV titles are formatted as 'Title (Season X)' or 'Title (S01E01)'
    is_tv = bool(RE_TV_TITLE.search(title))
    target_types = {'show', 'episode'} if is_tv else {'movie'}

    try:
        refreshed = []
        for section in plex.library.sections():
            if section.type in target_types:
                section.update()  # plexapi: triggers partial scan/refresh
                refreshed.append(section.title)
        print(f"Plex library refresh triggered for sections: {', '.join(refreshed) or 'none'}")
    except Exception as e:
        print(f"Warning: Plex refresh failed for '{title}': {e}")

def extract_tmdb_id(item) -> Optional[str]:
    """Early exit string extraction."""
    for guid in getattr(item, 'guids', []):
        if guid.id.startswith('tmdb://'):
            return guid.id.replace('tmdb://', '')
    return None

def process_movie(item, account: MyPlexAccount, title: str, tmdb_id: Optional[str]):
    best_torrent = downloader.search_aither(title, tmdb_id)
    if not best_torrent:
        print(f"No suitable torrent found for {title}.")
        delayed_remove_from_watchlist(account, item)
        return

    size_bytes = best_torrent.get('size', 0)
    aither_id = str(best_torrent.get('id', ''))
    
    if database.is_already_recorded(aither_id):
        print(f"Skipping {title} — torrent {aither_id} already recorded. Removing from watchlist.")
        delayed_remove_from_watchlist(account, item)
        return

    is_large = float(size_bytes) > (100 * 1024 * 1024 * 1024)
    status = 'pending_approval' if is_large else 'queued'
    
    params = database.DownloadParams(
        title=title,
        tmdb_id=tmdb_id,
        file_size_bytes=float(size_bytes),
        status=status,
        aither_torrent_id=aither_id,
        download_link=best_torrent.get('download_link'),
        resolution=best_torrent.get('resolution', 'Unknown')
    )
    database.record_download(params)
    delayed_remove_from_watchlist(account, item)
    print(f"Processed and queued {title} from watchlist.")

def get_watched_status(plex: Optional[PlexServer], title: str) -> Tuple[List[int], Set[Tuple[int, int]]]:
    watched_seasons = []
    watched_episodes = set()
    if not plex:
        return watched_seasons, watched_episodes
    
    try:
        local_results = plex.library.search(title, libtype='show')
        if not local_results or local_results[0].title.lower() != title.lower():
            return watched_seasons, watched_episodes
            
        local_show = local_results[0]
        
        # Single O(1) network query for all episodes
        episodes = local_show.episodes()
        if not episodes:
            return watched_seasons, watched_episodes
            
        season_counts = {}
        watched_counts = {}
        max_local_season = 0
        
        for ep in episodes:
            s = ep.parentIndex
            e = ep.index
            if s == 0: continue
            
            if s not in season_counts:
                season_counts[s] = 0
                watched_counts[s] = 0
                max_local_season = max(max_local_season, s)
                
            season_counts[s] += 1
            if ep.isWatched:
                watched_counts[s] += 1
                watched_episodes.add((s, e))
                
        existing_seasons = set(season_counts.keys())
        
        for s in range(1, max_local_season):
            if s not in existing_seasons:
                watched_seasons.append(s)
                
        for s, total in season_counts.items():
            if total > 0 and watched_counts[s] == total:
                watched_seasons.append(s)
                
    except Exception as e:
        print(f"Error checking local Plex explicitly for {title}: {e}")
        
    return watched_seasons, watched_episodes

def is_already_downloaded(relevant_qbt_names: List[str], s_num: int, e_num: Optional[int] = None) -> bool:
    re_episode = None
    if e_num:
        re_episode = re.compile(rf'\bS{s_num:02d}[ .]?E{e_num:02d}\b', re.IGNORECASE)

    for t_name in relevant_qbt_names:
        if e_num:
            if re_episode.search(t_name):
                return True
        else:
            match_s = RE_S_NUM.search(t_name)
            has_episode = RE_E_NUM.search(t_name)
            if match_s and not has_episode and int(match_s.group(1)) == s_num:
                return True
    return False

def track_tv_show(show_title: str, tmdb_id: Optional[str]):
    if not tmdb_id:
        return
    details = downloader.fetch_tmdb_tv_details(tmdb_id)
    if not details:
        return
    status = details.get('status', '')
    if status == 'Ended' or status == 'Canceled':
        return
        
    next_ep = details.get('next_episode_to_air')
    last_ep = details.get('last_episode_to_air')
    
    if next_ep:
        database.add_tracked_episode(
            tmdb_id=tmdb_id, 
            show_title=show_title, 
            season_num=next_ep.get('season_number', 1), 
            episode_num=next_ep.get('episode_number', 1), 
            air_date_str=next_ep.get('air_date')
        )
    if last_ep:
        air_date = last_ep.get('air_date')
        if air_date:
            try:
                from datetime import datetime, timedelta
                dt = datetime.strptime(air_date, '%Y-%m-%d')
                if datetime.now() - dt < timedelta(days=7):
                    database.add_tracked_episode(
                        tmdb_id=tmdb_id,
                        show_title=show_title,
                        season_num=last_ep.get('season_number', 1),
                        episode_num=last_ep.get('episode_number', 1),
                        air_date_str=air_date
                    )
            except Exception:
                pass

def process_show(item, account: MyPlexAccount, plex: Optional[PlexServer], title: str, tmdb_id: Optional[str], relevant_qbt_names: List[str]):
    track_tv_show(title, tmdb_id)
    watched_seasons, watched_episodes = get_watched_status(plex, title)
    available_data = downloader.search_aither_tv(title, tmdb_id)
    season_packs = available_data.get('seasons', {})
    single_eps = available_data.get('episodes', {})

    items_to_queue = []
    distinct_seasons_queued = set()
    
    for s_num, best_t in season_packs.items():
        if s_num == 0 or s_num in watched_seasons: continue
        if is_already_downloaded(relevant_qbt_names, s_num): continue
        if database.is_already_recorded(best_t.get('id', '')): continue
            
        items_to_queue.append((best_t, f"{title} (Season {s_num})"))
        distinct_seasons_queued.add(s_num)
    
    for (s_num, e_num), best_t in single_eps.items():
        if s_num == 0 or (s_num, e_num) in watched_episodes or s_num in watched_seasons or s_num in season_packs: 
            continue
        if is_already_downloaded(relevant_qbt_names, s_num, e_num):
            continue
        if database.is_already_recorded(best_t.get('id', '')): 
            continue
        
        items_to_queue.append((best_t, f"{title} (S{s_num:02d}E{e_num:02d})"))
        distinct_seasons_queued.add(s_num)
    
    force_pending = len(distinct_seasons_queued) > 1
    
    for t_dict, name in items_to_queue:
        queue_tv_item(item, account, t_dict, name, tmdb_id, force_pending=force_pending)
        
    if items_to_queue:
        delayed_remove_from_watchlist(account, item)
        print(f"Processed TV Show {title}. 1:{len(items_to_queue)} items queued.")
    else:
        print(f"No suitable or un-watched seasons/episodes found on Aither for {title}.")
        delayed_remove_from_watchlist(account, item)

def queue_tv_item(item, account: MyPlexAccount, t_dict: Dict[str, Any], save_name: str, tmdb_id: Optional[str], force_pending: bool = False):
    is_large = float(t_dict.get('size', 0)) > (100 * 1024 * 1024 * 1024)
    status = 'pending_approval' if (is_large or force_pending) else 'queued'
    
    params = database.DownloadParams(
        title=save_name,
        tmdb_id=tmdb_id,
        file_size_bytes=float(t_dict.get('size', 0)),
        status=status,
        aither_torrent_id=str(t_dict.get('id', '')),
        download_link=t_dict.get('download_link'),
        resolution=t_dict.get('resolution', 'Unknown')
    )
    database.record_download(params)
    print(f"Successfully queued {save_name}.")

def process_season(item, account: MyPlexAccount, title: str, tmdb_id: Optional[str]):
    show_title = getattr(item, 'parentTitle', title)
    track_tv_show(show_title, tmdb_id)
    season_num = getattr(item, 'index', 1) 
    print(f"Processing explicit Season Watchlist: {show_title} Season {season_num}")
    
    available_data = downloader.search_aither_tv(show_title, tmdb_id)
    season_packs = available_data.get('seasons', {})
    best_t = season_packs.get(season_num)
    
    if not best_t:
        print(f"No suitable pack found on Aither for {show_title} Season {season_num}.")
        delayed_remove_from_watchlist(account, item)
        return
        
    queue_tv_item(item, account, best_t, f"{show_title} (Season {season_num})", tmdb_id)
    delayed_remove_from_watchlist(account, item)

def process_episode(item, account: MyPlexAccount, title: str, tmdb_id: Optional[str]):
    show_title = getattr(item, 'grandparentTitle', title)
    track_tv_show(show_title, tmdb_id)
    season_num = getattr(item, 'parentIndex', 1)
    episode_num = getattr(item, 'index', 1)
    print(f"Processing explicit Episode Watchlist: {show_title} S{season_num:02d}E{episode_num:02d}")
    
    available_data = downloader.search_aither_tv(show_title, tmdb_id)
    episodes = available_data.get('episodes', {})
    best_t = episodes.get((season_num, episode_num))
    
    if not best_t:
        print(f"No suitable file found on Aither for {show_title} S{season_num:02d}E{episode_num:02d}.")
        delayed_remove_from_watchlist(account, item)
        return
        
    queue_tv_item(item, account, best_t, f"{show_title} (S{season_num:02d}E{episode_num:02d})", tmdb_id)
    delayed_remove_from_watchlist(account, item)

def check_watchlist():
    try:
        downloader.clear_caches()
        if not PLEX_TOKEN:
            raise ValueError("PLEX_TOKEN is missing")
            
        account = MyPlexAccount(token=PLEX_TOKEN)
        plex = get_plex_server()
        qbt_client = downloader.get_qbt_client()
        watchlist = account.watchlist()
        
        existing_qbt_names = downloader.get_all_torrent_names(qbt_client)
        
        for item in watchlist:
            title = item.title
            item_type = getattr(item, 'type', 'movie')
            tmdb_id = extract_tmdb_id(item)
            
            if item_type == 'movie':
                process_movie(item, account, title, tmdb_id)
            elif item_type == 'show':
                title_lower = title.lower()
                normalized_title_words = set(downloader.normalize_title(title))
                relevant_qbt_names = []
                for t_name in existing_qbt_names:
                    t_words = set(downloader.normalize_title(t_name))
                    if normalized_title_words.issubset(t_words) or (title_lower in t_name.lower()):
                        relevant_qbt_names.append(t_name)
                process_show(item, account, plex, title, tmdb_id, relevant_qbt_names)
            elif item_type == 'season':
                process_season(item, account, title, tmdb_id)
            elif item_type == 'episode':
                process_episode(item, account, title, tmdb_id)
                
        database.update_last_checked()
    except Exception as e:
        print(f"Error checking watchlist: {e}")
        database.update_last_checked(error=str(e))

def check_drive_space(needed_bytes: float) -> Optional[str]:
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
        qbt_client = downloader.get_qbt_client()
        active_count = downloader.get_active_downloads_count(qbt_client)
        if active_count < 0:
            print("Error retrieving active downloads count. Waiting.")
            return

        if active_count >= 5:
            print(f"Queue full ({active_count} active). Waiting.")
            return

        available_slots = 5 - active_count
        for _ in range(available_slots):
            item = database.get_next_queued_item()
            if not item:
                break
                
            needed_bytes = item['file_size_bytes'] * 1.05
            selected_dir = check_drive_space(needed_bytes)
            
            if selected_dir:
                print(f"Sending {item['title']} to {selected_dir}")
                success = downloader.send_to_qbittorrent(qbt_client, item['download_link'], selected_dir, item['id'])
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
            
        qbt_client = downloader.get_qbt_client()
        status_updates = downloader.get_active_downloads_status(qbt_client, active_items)
        for db_id, data in status_updates.items():
            if data['status'] == 'completed':
                database.update_download_status(db_id, 'completed')
                database.update_download_progress(db_id, 1.0, 0)
                completed_item = next((i for i in active_items if i['id'] == db_id), None)
                completed_title = completed_item['title'] if completed_item else str(db_id)
                print(f"Marked download {db_id} ('{completed_title}') as completed!")
                trigger_plex_refresh(completed_title)
            else:
                database.update_download_progress(db_id, data['progress'], data['eta_seconds'])
            
    except Exception as e:
        print(f"Error monitoring downloads: {e}")

def poll_tracked_episodes():
    try:
        downloader.clear_caches()
        from datetime import datetime, timedelta
        
        waiting = database.get_episodes_by_status('waiting')
        now = datetime.now()
        
        for ep in waiting:
            if not ep['air_date']:
                continue
            try:
                air_dt = datetime.strptime(ep['air_date'], '%Y-%m-%d')
                if now >= air_dt + timedelta(hours=24):
                    database.update_tracked_episode_status(ep['id'], 'polling')
                    print(f"Episode {ep['show_title']} S{ep['season_num']:02d}E{ep['episode_num']:02d} is now polling.")
            except Exception as e:
                print(f"Error parsing air date: {e}")
                
        polling = database.get_episodes_by_status('polling')
        if not polling:
            return
            
        print(f"Querying Aither for {len(polling)} due episodes...")
        for ep in polling:
            tmdb_id = ep['tmdb_id']
            show_title = ep['show_title']
            s_num = ep['season_num']
            e_num = ep['episode_num']
            
            if ep['air_date']:
                try:
                    air_dt = datetime.strptime(ep['air_date'], '%Y-%m-%d')
                    if now >= air_dt + timedelta(hours=48):
                        database.update_tracked_episode_status(ep['id'], 'give_up')
                        print(f"Giving up on polling {show_title} S{s_num:02d}E{e_num:02d} (48h passed).")
                        track_tv_show(show_title, tmdb_id)
                        continue
                except Exception:
                    pass
                    
            data = downloader.search_aither_tv(show_title, tmdb_id)
            episodes = data.get('episodes', {})
            best_t = episodes.get((s_num, e_num))
            
            if best_t:
                if not database.is_already_recorded(best_t.get('id', '')):
                    save_name = f"{show_title} (S{s_num:02d}E{e_num:02d})"
                    queue_tv_item(None, None, best_t, save_name, tmdb_id, force_pending=False)
                    
                database.update_tracked_episode_status(ep['id'], 'downloaded')
                print(f"Successfully found and queued polled episode {show_title} S{s_num:02d}E{e_num:02d}.")
                track_tv_show(show_title, tmdb_id)
    except Exception as e:
        print(f"Error polling tracked episodes: {e}")
