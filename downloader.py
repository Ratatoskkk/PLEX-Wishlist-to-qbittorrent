import os
import requests
import qbittorrentapi
import re
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

AITHER_API_KEY = os.getenv('AITHER_API_KEY')
QBITTORRENT_URL = os.getenv('QBITTORRENT_URL')
QBITTORRENT_USERNAME = os.getenv('QBITTORRENT_USERNAME')
QBITTORRENT_PASSWORD = os.getenv('QBITTORRENT_PASSWORD')

AITHER_URL = "https://aither.cc/api/torrents/filter"

def search_aither(title, tmdb_id=None):
    """Search Aither API for the optimal torrent."""
    headers = {
        'Authorization': f'Bearer {AITHER_API_KEY}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    # First attempt: exact match with tmdbId if available
    params = {
        'perPage': '100',
        'sortField': 'size',
        'sortDirection': 'desc' # size descending to find biggest valid file first
    }
    
    if tmdb_id:
        params['tmdbId'] = str(tmdb_id)
    else:
        params['name'] = title

    try:
        response = requests.get(AITHER_URL, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json().get('data', [])
        
        # If pagination is returned differently:
        if isinstance(data, dict) and 'data' in data:
            data = data['data']
            
        return filter_best_torrent(data)

    except Exception as e:
        print(f"Error querying Aither: {e}")
        return None

def filter_best_torrent(torrents):
    """
    User logic:
    - No full disk releases
    - Always choose 4K HDR and remux when available
    - Choose 1080p when not available
    """
    valid_torrents = []
    
    for t in torrents:
        attrs = t.get('attributes', {})
        # Filter full disk
        # Assuming type represents "Full Disc" somewhere, or category_id
        type_str = str(attrs.get('type', '')).lower()
        if 'full disc' in type_str or 'bd50' in type_str or 'bd25' in type_str:
            continue
            
        res = str(attrs.get('resolution', '')).lower()
        
        # Determine "rank"
        is_4k = '2160p' in res or '4k' in res
        is_remux = 'remux' in str(attrs.get('name', '')).lower() or 'remux' in type_str
        is_hdr = 'hdr' in str(attrs.get('name', '')).lower() or 'hdr' in str(attrs.get('media_info', '')).lower() or attrs.get('hdr', False)
        is_1080p = '1080p' in res
        
        score = 0
        if is_4k and is_remux and is_hdr:
            score = 100
        elif is_4k and is_remux:
            score = 90
        elif is_4k and is_hdr:
            score = 80
        elif is_4k:
            score = 70
        elif is_1080p and is_remux:
            score = 60
        elif is_1080p:
            score = 50
            
        if score > 0:
            valid_torrents.append((score, attrs))

    if not valid_torrents:
        return None
        
    # Sort by score descending, then by size descending
    valid_torrents.sort(key=lambda x: (x[0], x[1].get('size', 0)), reverse=True)
    
    return valid_torrents[0][1] # Return the attributes of the best torrent

def search_aither_tv(title, tmdb_id=None):
    """
    Finds season packs for a TV show and groups them by highest quality.
    Returns: { season_number: best_torrent_dict }
    """
    headers = {
        'Authorization': f'Bearer {AITHER_API_KEY}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    params = {'perPage': '100'}
    
    if tmdb_id:
        params['tmdbId'] = str(tmdb_id)
    else:
        params['name'] = title

    try:
        response = requests.get(AITHER_URL, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json().get('data', [])
        if isinstance(data, dict) and 'data' in data:
            data = data['data']
        
        torrents = data
        seasons = {} 
        episodes = {}
        
        for t in torrents:
            attrs = t.get('attributes', {})
            t_name = attrs.get('name', '')
            if "full disc" in t_name.lower():
                continue
            
            # Find Season Packs: Look for S01, S12 etc. but ensure there's no E01 (episode)
            match_s = re.search(r'\bS(\d{1,2})\b', t_name, re.IGNORECASE)
            match_e = re.search(r'\bE(\d{1,2})\b', t_name, re.IGNORECASE)
            match_se = re.search(r'\bS(\d{1,2})[ .]?E(\d{1,2})\b', t_name, re.IGNORECASE)
            
            if match_se:
                s_num = int(match_se.group(1))
                e_num = int(match_se.group(2))
                key = (s_num, e_num)
                if key not in episodes:
                    episodes[key] = []
                episodes[key].append(t)
            elif match_s and not match_e:
                season_num = int(match_s.group(1))
                if season_num not in seasons:
                    seasons[season_num] = []
                seasons[season_num].append(t)
                
        def score_torrents(torrent_list):
            best_t = None
            best_sc = -1
            for t in torrent_list:
                attrs = t.get('attributes', {})
                t_name = attrs.get('name', '')
                res = str(attrs.get('resolution', '')).lower()
                
                score = 0
                if '2160p' in res or '4k' in res:
                    score += 50
                    if 'remux' in t_name.lower():
                        score += 50
                    if 'hdr' in t_name.lower() or 'dv' in t_name.lower():
                        score += 20
                elif '1080p' in res:
                    score += 10
                
                if score > best_sc:
                    best_sc = score
                    best_t = {
                        'id': t.get('id'),
                        'name': t_name,
                        'size': attrs.get('size', 0),
                        'download_link': attrs.get('download_link'),
                        'resolution': res if res else 'Unknown'
                    }
            return best_t

        best_seasons = {}
        for s_num, s_torrents in seasons.items():
            best = score_torrents(s_torrents)
            if best: best_seasons[s_num] = best
            
        best_episodes = {}
        for key, e_torrents in episodes.items():
            best = score_torrents(e_torrents)
            if best: best_episodes[key] = best
                
        return {"seasons": best_seasons, "episodes": best_episodes}
    except Exception as e:
        print(f"Error searching Aither TV (TMDB {tmdb_id}): {e}")
        return {"seasons": {}, "episodes": {}}

def get_active_downloads_count():
    """Get the number of active/downloading torrents in qBittorrent."""
    try:
        qbt_client = qbittorrentapi.Client(
            host=QBITTORRENT_URL,
            username=QBITTORRENT_USERNAME,
            password=QBITTORRENT_PASSWORD
        )
        qbt_client.auth_log_in()
        # Find torrents that are actively downloading or stalled/queued for download
        torrents = qbt_client.torrents_info(status_filter='downloading')
        return len(torrents)
    except Exception as e:
        print(f"Error getting qbittorrent info: {e}")
        return 0

def send_to_qbittorrent(download_link, save_path):
    """Send a download URL to qBittorrent."""
    try:
        qbt_client = qbittorrentapi.Client(
            host=QBITTORRENT_URL,
            username=QBITTORRENT_USERNAME,
            password=QBITTORRENT_PASSWORD
        )
        qbt_client.auth_log_in()
        
        qbt_client.torrents_add(
            urls=download_link,
            save_path=save_path,
            is_paused=False
        )
        return True
    except Exception as e:
        print(f"Error sending to qbittorrent: {e}")
        return False

def normalize_title(title):
    return [w.lower() for w in re.findall(r'\w+', title)]

def check_completed_downloads(active_db_items):
    """
    Check if any active DB items are completed in qBittorrent.
    active_db_items is a list of dictionary sqlite rows.
    Returns a list of db_ids that have completed.
    """
    try:
        qbt_client = qbittorrentapi.Client(
            host=QBITTORRENT_URL,
            username=QBITTORRENT_USERNAME,
            password=QBITTORRENT_PASSWORD
        )
        qbt_client.auth_log_in()
        
        # Memory Optimization: Only request completed torrent JSON from qBittorrent to prevent RAM ballooning on large libraries
        torrents = qbt_client.torrents_info(status_filter='completed')
        completed_ids = []
        
        for item in active_db_items:
            plex_words = set(normalize_title(item['title']))
            
            for t in torrents:
                if t.progress >= 1.0 or t.completion_on != -1:
                    t_words = set(normalize_title(t.name))
                    if plex_words.issubset(t_words):
                        completed_ids.append(item['id'])
                        break
                        
        return completed_ids
    except Exception as e:
        print(f"Error checking completed downloads: {e}")
        return []

def get_all_torrent_names():
    """Retrieve all torrent names currently mapped to qBittorrent history."""
    try:
        qbt_client = qbittorrentapi.Client(
            host=QBITTORRENT_URL,
            username=QBITTORRENT_USERNAME,
            password=QBITTORRENT_PASSWORD
        )
        qbt_client.auth_log_in()
        torrents = qbt_client.torrents_info()
        return [t.name for t in torrents]
    except Exception as e:
        print(f"Error getting qbittorrent info: {e}")
        return []
