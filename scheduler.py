import os
import shutil
import re
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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

_100_GB = 100 * 1024 * 1024 * 1024

# (threading imported at top)


def _extract_best_release_date(tmdb_id: Optional[str]) -> Optional[str]:
    """Return the earliest physical/digital release date for a movie from TMDB.

    Priority: Digital (4) or Physical (5) > Theatrical (3), Limited (2), Premiere (1).
    """
    if not tmdb_id:
        return None
    data = downloader.fetch_tmdb_movie_release_dates(tmdb_id)
    if not data or 'release_dates' not in data:
        return None
    results = data['release_dates'].get('results', [])
    best: Optional[str] = None
    for priority_types in ([4, 5], [1, 2, 3]):
        for country in results:
            for release in country.get('release_dates', []):
                if release.get('type') in priority_types:
                    date_str = release.get('release_date', '').split('T')[0]
                    if date_str and (not best or date_str < best):
                        best = date_str
        if best:
            break
    return best

@dataclass
class WatchlistRunContext:
    """Holds per-run caches to avoid redundant DB queries and API calls.

    - recorded_ids: Set of Aither torrent IDs already in a live DB state.
      Loaded once at the start of check_watchlist; mutated when new items are
      queued so subsequent loop iterations see the updated state without a
      second DB round-trip.
    - tv_show_cache: Maps tmdb_id -> poster_path returned by track_tv_show.
      Prevents duplicate TMDB calls when the same show appears multiple times.
    - watched_status_cache: Maps show title -> (watched_seasons, watched_episodes).
      Prevents duplicate Plex server round-trips for the same show.
    """
    recorded_ids: Set[str] = field(default_factory=set)
    tv_show_cache: Dict[str, Optional[str]] = field(default_factory=dict)
    watched_status_cache: Dict[str, Tuple[List[int], Set[Tuple[int, int]]]] = field(default_factory=dict)

    def is_recorded(self, aither_id: str) -> bool:
        return str(aither_id) in self.recorded_ids

    def mark_recorded(self, aither_id: str) -> None:
        self.recorded_ids.add(str(aither_id))

def _do_delayed_remove(account: MyPlexAccount, item) -> None:
    time.sleep(10)
    try:
        account.removeFromWatchlist(item)
    except Exception:
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

def process_movie(item, account: MyPlexAccount, title: str, tmdb_id: Optional[str]) -> None:
    best_torrent = downloader.search_aither(title, tmdb_id)
    if not best_torrent:
        print(f"No suitable torrent found for {title}.")
        best_date = _extract_best_release_date(tmdb_id)
        poster_path = downloader.fetch_movie_poster(tmdb_id) if tmdb_id else None
        database.add_tracked_episode(
            tmdb_id=tmdb_id,
            show_title=title,
            season_num=0,
            episode_num=0,
            air_date_str=best_date,
            poster_path=poster_path,
            media_type='movie',
        )
        print(f"Added unreleased movie {title} to upcoming list (Date: {best_date}).")
        delayed_remove_from_watchlist(account, item)
        return

    size_bytes = best_torrent.get('size', 0)
    aither_id = str(best_torrent.get('id', ''))

    if database.is_already_recorded(aither_id):
        print(f"Skipping {title} — torrent {aither_id} already recorded. Removing from watchlist.")
        delayed_remove_from_watchlist(account, item)
        return

    is_large = float(size_bytes) > _100_GB
    status = 'pending_approval' if is_large else 'queued'
    poster_path = downloader.fetch_movie_poster(tmdb_id) if tmdb_id else None
    params = database.DownloadParams(
        title=title,
        tmdb_id=tmdb_id,
        file_size_bytes=float(size_bytes),
        status=status,
        aither_torrent_id=aither_id,
        download_link=best_torrent.get('download_link'),
        resolution=best_torrent.get('resolution', 'Unknown'),
        poster_path=poster_path,
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

def track_tv_show(show_title: str, tmdb_id: Optional[str]) -> Optional[str]:
    if not tmdb_id:
        return None
    details = downloader.fetch_tmdb_tv_details(tmdb_id)
    if not details:
        return None
    tmdb_status = details.get('status', '')
    poster_path = details.get('poster_path')
    if tmdb_status in {'Ended', 'Canceled'}:
        return poster_path

    next_ep = details.get('next_episode_to_air')
    last_ep = details.get('last_episode_to_air')

    track_status = 'waiting'
    try:
        with database.get_db() as db:
            row = db.execute(
                'SELECT status FROM tracked_episodes WHERE tmdb_id = ? ORDER BY id DESC LIMIT 1',
                (tmdb_id,)
            ).fetchone()
            if row and row['status'] == 'ignored':
                track_status = 'ignored'
    except Exception:
        pass

    if next_ep:
        database.add_tracked_episode(
            tmdb_id=tmdb_id,
            show_title=show_title,
            season_num=next_ep.get('season_number', 1),
            episode_num=next_ep.get('episode_number', 1),
            air_date_str=next_ep.get('air_date'),
            poster_path=poster_path,
            status=track_status,
        )
    if last_ep:
        air_date = last_ep.get('air_date')
        if air_date:
            try:
                dt = datetime.strptime(air_date, '%Y-%m-%d')
                if datetime.now() - dt < timedelta(days=7):
                    database.add_tracked_episode(
                        tmdb_id=tmdb_id,
                        show_title=show_title,
                        season_num=last_ep.get('season_number', 1),
                        episode_num=last_ep.get('episode_number', 1),
                        air_date_str=air_date,
                        poster_path=poster_path,
                        status=track_status,
                    )
            except Exception:
                pass
    return poster_path

def _fetch_show_data(
    title: str,
    tmdb_id: Optional[str],
    plex: Optional[PlexServer],
    ctx: WatchlistRunContext,
) -> Tuple[Optional[str], List[int], Set[Tuple[int, int]], Dict[str, Any]]:
    """Fetch all data needed to process a TV show, using per-run caches."""
    if tmdb_id in ctx.tv_show_cache:
        poster_path = ctx.tv_show_cache[tmdb_id]
    else:
        poster_path = track_tv_show(title, tmdb_id)
        ctx.tv_show_cache[tmdb_id] = poster_path

    if title in ctx.watched_status_cache:
        watched_seasons, watched_episodes = ctx.watched_status_cache[title]
    else:
        watched_seasons, watched_episodes = get_watched_status(plex, title)
        ctx.watched_status_cache[title] = (watched_seasons, watched_episodes)

    available_data = downloader.search_aither_tv(title, tmdb_id)
    return poster_path, watched_seasons, watched_episodes, available_data


def _collect_season_pack_items(
    season_packs: Dict[int, Any],
    watched_seasons: List[int],
    relevant_qbt_names: List[str],
    ctx: WatchlistRunContext,
    title: str,
) -> Tuple[List[Tuple[Any, str]], Set[int]]:
    """Return (items_to_queue, distinct_seasons) for unwatched, unrecorded season packs."""
    items_to_queue = []
    distinct_seasons: Set[int] = set()
    for s_num, best_t in season_packs.items():
        if s_num == 0 or s_num in watched_seasons:
            continue
        if is_already_downloaded(relevant_qbt_names, s_num):
            continue
        if ctx.is_recorded(best_t.get('id', '')):
            continue
        items_to_queue.append((best_t, f"{title} (Season {s_num})"))
        distinct_seasons.add(s_num)
    return items_to_queue, distinct_seasons


def _collect_episode_items(
    single_eps: Dict[Tuple[int, int], Any],
    watched_episodes: Set[Tuple[int, int]],
    watched_seasons: List[int],
    season_packs: Dict[int, Any],
    relevant_qbt_names: List[str],
    ctx: WatchlistRunContext,
    title: str,
) -> Tuple[List[Tuple[Any, str]], Set[int]]:
    """Return (items_to_queue, distinct_seasons) for unwatched, unrecorded single episodes."""
    items_to_queue = []
    distinct_seasons: Set[int] = set()
    for (s_num, e_num), best_t in single_eps.items():
        already_covered = (
            s_num == 0
            or (s_num, e_num) in watched_episodes
            or s_num in watched_seasons
            or s_num in season_packs
        )
        if already_covered:
            continue
        if is_already_downloaded(relevant_qbt_names, s_num, e_num):
            continue
        if ctx.is_recorded(best_t.get('id', '')):
            continue
        items_to_queue.append((best_t, f"{title} (S{s_num:02d}E{e_num:02d})"))
        distinct_seasons.add(s_num)
    return items_to_queue, distinct_seasons


def process_show(
    item,
    account: MyPlexAccount,
    plex: Optional[PlexServer],
    title: str,
    tmdb_id: Optional[str],
    relevant_qbt_names: List[str],
    ctx: WatchlistRunContext,
):
    poster_path, watched_seasons, watched_episodes, available_data = _fetch_show_data(
        title, tmdb_id, plex, ctx
    )
    season_packs = available_data.get('seasons', {})
    single_eps = available_data.get('episodes', {})

    pack_items, pack_seasons = _collect_season_pack_items(
        season_packs, watched_seasons, relevant_qbt_names, ctx, title
    )
    ep_items, ep_seasons = _collect_episode_items(
        single_eps, watched_episodes, watched_seasons, season_packs, relevant_qbt_names, ctx, title
    )

    items_to_queue = pack_items + ep_items
    distinct_seasons_queued = pack_seasons | ep_seasons
    force_pending = len(distinct_seasons_queued) > 1

    for t_dict, name in items_to_queue:
        queue_tv_item(t_dict, name, tmdb_id, force_pending=force_pending, poster_path=poster_path)
        ctx.mark_recorded(t_dict.get('id', ''))

    delayed_remove_from_watchlist(account, item)
    if items_to_queue:
        print(f"Processed TV Show {title}. {len(items_to_queue)} items queued.")
    else:
        print(f"No suitable or un-watched seasons/episodes found on Aither for {title}.")


def queue_tv_item(t_dict: Dict[str, Any], save_name: str, tmdb_id: Optional[str], force_pending: bool = False, poster_path: Optional[str] = None) -> None:
    """Record a TV season/episode torrent in the DB queue."""
    is_large = float(t_dict.get('size', 0)) > _100_GB
    status = 'pending_approval' if (is_large or force_pending) else 'queued'
    params = database.DownloadParams(
        title=save_name,
        tmdb_id=tmdb_id,
        file_size_bytes=float(t_dict.get('size', 0)),
        status=status,
        aither_torrent_id=str(t_dict.get('id', '')),
        download_link=t_dict.get('download_link'),
        resolution=t_dict.get('resolution', 'Unknown'),
        poster_path=poster_path,
    )
    database.record_download(params)
    print(f"Successfully queued {save_name}.")

def process_season(item, account: MyPlexAccount, title: str, tmdb_id: Optional[str], ctx: WatchlistRunContext):
    show_title = getattr(item, 'parentTitle', title)
    if tmdb_id in ctx.tv_show_cache:
        poster_path = ctx.tv_show_cache[tmdb_id]
    else:
        poster_path = track_tv_show(show_title, tmdb_id)
        ctx.tv_show_cache[tmdb_id] = poster_path

    season_num = getattr(item, 'index', 1)
    print(f"Processing explicit Season Watchlist: {show_title} Season {season_num}")

    available_data = downloader.search_aither_tv(show_title, tmdb_id)
    best_t = available_data.get('seasons', {}).get(season_num)

    if not best_t:
        print(f"No suitable pack found on Aither for {show_title} Season {season_num}.")
        delayed_remove_from_watchlist(account, item)
        return

    queue_tv_item(best_t, f"{show_title} (Season {season_num})", tmdb_id, poster_path=poster_path)
    ctx.mark_recorded(best_t.get('id', ''))
    delayed_remove_from_watchlist(account, item)


def process_episode(item, account: MyPlexAccount, title: str, tmdb_id: Optional[str], ctx: WatchlistRunContext):
    show_title = getattr(item, 'grandparentTitle', title)
    if tmdb_id in ctx.tv_show_cache:
        poster_path = ctx.tv_show_cache[tmdb_id]
    else:
        poster_path = track_tv_show(show_title, tmdb_id)
        ctx.tv_show_cache[tmdb_id] = poster_path

    season_num = getattr(item, 'parentIndex', 1)
    episode_num = getattr(item, 'index', 1)
    print(f"Processing explicit Episode Watchlist: {show_title} S{season_num:02d}E{episode_num:02d}")

    available_data = downloader.search_aither_tv(show_title, tmdb_id)
    best_t = available_data.get('episodes', {}).get((season_num, episode_num))

    if not best_t:
        print(f"No suitable file found on Aither for {show_title} S{season_num:02d}E{episode_num:02d}.")
        delayed_remove_from_watchlist(account, item)
        return

    queue_tv_item(best_t, f"{show_title} (S{season_num:02d}E{episode_num:02d})", tmdb_id, poster_path=poster_path)
    ctx.mark_recorded(best_t.get('id', ''))
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

        # Batch-load all recorded Aither IDs once to avoid O(N) DB queries inside loops
        ctx = WatchlistRunContext(recorded_ids=database.get_all_recorded_aither_ids())

        existing_qbt_names = downloader.get_all_torrent_names(qbt_client)
        precomputed_qbt_names = [
            (t_name, set(downloader.normalize_title(t_name)), t_name.lower())
            for t_name in existing_qbt_names
        ]

        for item in watchlist:
            title = item.title
            item_type = getattr(item, 'type', 'movie')
            tmdb_id = extract_tmdb_id(item)

            if item_type == 'movie':
                process_movie(item, account, title, tmdb_id)
            elif item_type == 'show':
                title_lower = title.lower()
                normalized_title_words = set(downloader.normalize_title(title))
                relevant_qbt_names = [
                    t_name
                    for t_name, t_words, t_lower in precomputed_qbt_names
                    if normalized_title_words.issubset(t_words) or (title_lower in t_lower)
                ]
                process_show(item, account, plex, title, tmdb_id, relevant_qbt_names, ctx)
            elif item_type == 'season':
                process_season(item, account, title, tmdb_id, ctx)
            elif item_type == 'episode':
                process_episode(item, account, title, tmdb_id, ctx)

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
                    database.update_download_save_path(item['id'], selected_dir)
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
                database.complete_download(db_id)
                completed_item = next((i for i in active_items if i['id'] == db_id), None)
                completed_title = completed_item['title'] if completed_item else str(db_id)
                print(f"Marked download {db_id} ('{completed_title}') as completed!")
                trigger_plex_refresh(completed_title)
                
                # Cleanup single episodes if a Season Pack just completed
                match = re.search(r'^(.*?)\s+\(Season (\d+)\)$', completed_title)
                if match:
                    show_title = match.group(1).strip()
                    season_num = int(match.group(2))
                    try:
                        torrents = qbt_client.torrents_info()
                        hashes_to_delete = []
                        re_episode = re.compile(rf'\bS{season_num:02d}[ .]?E\d{{1,2}}\b', re.IGNORECASE)
                        show_words = set(downloader.normalize_title(show_title))
                        target_tag = f"plexaither_{db_id}"
                        
                        for t in torrents:
                            tags = [tag.strip() for tag in getattr(t, 'tags', '').split(',')] if getattr(t, 'tags', '') else []
                            if target_tag in tags:
                                continue # Skip the season pack itself
                                
                            t_words = set(downloader.normalize_title(t.name))
                            if show_words.issubset(t_words) and re_episode.search(t.name):
                                hashes_to_delete.append(t.hash)
                                
                        if hashes_to_delete:
                            print(f"Cleanup: Deleting {len(hashes_to_delete)} obsolete single episodes for {show_title} Season {season_num}...")
                            qbt_client.torrents_delete(delete_files=True, torrent_hashes=hashes_to_delete)
                    except Exception as e:
                        print(f"Error during episode cleanup: {e}")
            else:
                database.update_download_progress(db_id, data['progress'], data['eta_seconds'])
            
    except Exception as e:
        print(f"Error monitoring downloads: {e}")

def poll_tracked_episodes() -> None:
    try:
        downloader.clear_caches()

        waiting = database.get_episodes_by_status('waiting')
        now = datetime.now()

        for ep in waiting:
            if not ep['air_date']:
                if ep['media_type'] == 'movie':
                    best_date = _extract_best_release_date(ep['tmdb_id'])
                    if best_date:
                        with database.get_db() as db:
                            db.execute("UPDATE tracked_episodes SET air_date = ? WHERE id = ?", (best_date, ep['id']))
                            db.commit()
                        print(f"Updated missing release date for {ep['show_title']} to {best_date}.")
                continue
            try:
                air_dt = datetime.strptime(ep['air_date'], '%Y-%m-%d')
                if now >= air_dt:
                    database.update_tracked_episode_status(ep['id'], 'polling')
                    label = f"{ep['show_title']} S{ep['season_num']:02d}E{ep['episode_num']:02d}"
                    print(f"{label} air date reached — now polling Aither.")
            except Exception as e:
                print(f"Error parsing air date: {e}")

        polling = database.get_episodes_by_status('polling')
        if not polling:
            return

        print(f"Querying Aither for {len(polling)} due episodes...")
        for ep in polling:
            _poll_single_episode(ep, now)
    except Exception as e:
        print(f"Error polling tracked episodes: {e}")


def _poll_single_episode(ep, now: datetime) -> None:
    """Search Aither for a single tracked episode/movie and queue if found."""
    tmdb_id = ep['tmdb_id']
    show_title = ep['show_title']
    s_num = ep['season_num']
    e_num = ep['episode_num']
    is_movie = ep['media_type'] == 'movie'

    # Give-up check
    if ep['air_date']:
        try:
            air_dt = datetime.strptime(ep['air_date'], '%Y-%m-%d')
            give_up_hours = 24 * 90 if is_movie else 48
            if now >= air_dt + timedelta(hours=give_up_hours):
                database.update_tracked_episode_status(ep['id'], 'give_up')
                label = f"movie {show_title}" if is_movie else f"episode {show_title} S{s_num:02d}E{e_num:02d}"
                print(f"Giving up on polling {label} ({give_up_hours}h passed).")
                if not is_movie:
                    track_tv_show(show_title, tmdb_id)
                return
        except Exception:
            pass

    if is_movie:
        best_t = downloader.search_aither(show_title, tmdb_id)
        if best_t:
            if not database.is_already_recorded(best_t.get('id', '')):
                is_large = float(best_t.get('size', 0)) > _100_GB
                status = 'pending_approval' if is_large else 'queued'
                params = database.DownloadParams(
                    title=show_title,
                    tmdb_id=tmdb_id,
                    file_size_bytes=float(best_t.get('size', 0)),
                    status=status,
                    aither_torrent_id=str(best_t.get('id', '')),
                    download_link=best_t.get('download_link'),
                    resolution=best_t.get('resolution', 'Unknown'),
                    poster_path=ep['poster_path'],
                )
                database.record_download(params)
            database.update_tracked_episode_status(ep['id'], 'downloaded')
            print(f"Successfully found and queued polled movie {show_title}.")
        return

    data = downloader.search_aither_tv(show_title, tmdb_id)
    best_t = data.get('episodes', {}).get((s_num, e_num))
    is_season_pack = False
    if not best_t:
        best_t = data.get('seasons', {}).get(s_num)
        is_season_pack = True

    if best_t:
        if not database.is_already_recorded(best_t.get('id', '')):
            save_name = f"{show_title} (Season {s_num})" if is_season_pack else f"{show_title} (S{s_num:02d}E{e_num:02d})"
            poster_path = track_tv_show(show_title, tmdb_id)
            queue_tv_item(best_t, save_name, tmdb_id, poster_path=poster_path)
        database.update_tracked_episode_status(ep['id'], 'downloaded')
        print(f"Successfully found and queued polled episode {show_title} S{s_num:02d}E{e_num:02d}.")


def poll_fresh_releases() -> None:
    """Aggressive hourly poll for items aired within the last 7 days."""
    try:
        downloader.clear_caches()
        fresh = database.get_fresh_polling_episodes(days=7)
        if not fresh:
            return

        now = datetime.now()
        print(f"[Fresh Poll] Checking Aither for {len(fresh)} recently aired items...")
        for ep in fresh:
            _poll_single_episode(ep, now)
    except Exception as e:
        print(f"Error in fresh releases poll: {e}")
