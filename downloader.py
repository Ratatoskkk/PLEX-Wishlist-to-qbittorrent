import os
import requests
import qbittorrentapi
import re
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

AITHER_API_KEY = os.getenv('AITHER_API_KEY')
QBITTORRENT_URL = os.getenv('QBITTORRENT_URL')
QBITTORRENT_USERNAME = os.getenv('QBITTORRENT_USERNAME')
QBITTORRENT_PASSWORD = os.getenv('QBITTORRENT_PASSWORD')

AITHER_URL = "https://aither.cc/api/torrents/filter"

# Pre-compiled regex patterns for performance
RE_S_NUM = re.compile(r'\bS(\d{1,2})\b', re.IGNORECASE)
RE_E_NUM = re.compile(r'\bE(\d{1,2})\b', re.IGNORECASE)
RE_SE_NUM = re.compile(r'\bS(\d{1,2})[ .]?E(\d{1,2})\b', re.IGNORECASE)
RE_SEASON = re.compile(r'\(?Season\s+(\d+)\)?', re.IGNORECASE)
RE_WORDS = re.compile(r'\w+')

def get_qbt_client() -> qbittorrentapi.Client:
    """Dependency Injection for Qbittorrent client"""
    qbt_client = qbittorrentapi.Client(
        host=QBITTORRENT_URL,
        username=QBITTORRENT_USERNAME,
        password=QBITTORRENT_PASSWORD
    )
    qbt_client.auth_log_in()
    return qbt_client

def search_aither(title: str, tmdb_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Search Aither API for the optimal movie torrent."""
    headers = {
        'Authorization': f'Bearer {AITHER_API_KEY}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    params = {
        'perPage': '100',
        'sortField': 'size',
        'sortDirection': 'desc'
    }
    
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
            
        return filter_best_torrent(data)

    except Exception as e:
        print(f"Error querying Aither for {title}: {e}")
        return None

def is_full_disc(type_str: str, name_str: str) -> bool:
    """Guard clause filter to check if a release is a full disc."""
    t = type_str.lower()
    n = name_str.lower()
    if 'full disc' in t or 'bd50' in t or 'bd25' in t:
        return True
    if 'full disc' in n or 'bd50' in n or 'bd25' in n:
        return True
    return False

def filter_best_torrent(torrents: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Filters torrents based on rule: prefer 4K HDR Remux > 4K HDR > 1080p Remux."""
    valid_torrents = []
    
    for t in torrents:
        attrs = t.get('attributes', {})
        if is_full_disc(str(attrs.get('type', '')), str(attrs.get('name', ''))):
            continue
            
        res = str(attrs.get('resolution', '')).lower()
        name = str(attrs.get('name', '')).lower()
        media_info = str(attrs.get('media_info', '')).lower()
        
        is_4k = '2160p' in res or '4k' in res
        is_remux = 'remux' in name or 'remux' in str(attrs.get('type', '')).lower()
        is_hdr = 'hdr' in name or 'hdr' in media_info or attrs.get('hdr', False)
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
            valid_torrents.append((score, attrs, t.get('id')))

    if not valid_torrents:
        return None
        
    valid_torrents.sort(key=lambda x: (x[0], x[1].get('size', 0)), reverse=True)
    best_attrs = valid_torrents[0][1]
    best_attrs['id'] = valid_torrents[0][2]
    return best_attrs

def score_torrents(torrent_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Rates a list of TV season/episode torrents to find the highest quality."""
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

def parse_tv_torrents(torrents: List[Dict[str, Any]]) -> Tuple[Dict[int, List[Dict[str, Any]]], Dict[Tuple[int, int], List[Dict[str, Any]]]]:
    """Separates a list of Aither TV torrents into Season Packs and single Episodes."""
    seasons = {} 
    episodes = {}
    
    for t in torrents:
        attrs = t.get('attributes', {})
        t_name = attrs.get('name', '')
        if is_full_disc(str(attrs.get('type', '')), t_name):
            continue
        
        match_s = RE_S_NUM.search(t_name)
        match_e = RE_E_NUM.search(t_name)
        match_se = RE_SE_NUM.search(t_name)
        
        if match_se:
            s_num, e_num = int(match_se.group(1)), int(match_se.group(2))
            key = (s_num, e_num)
            if key not in episodes:
                episodes[key] = []
            episodes[key].append(t)
        elif match_s and not match_e:
            season_num = int(match_s.group(1))
            if season_num not in seasons:
                seasons[season_num] = []
            seasons[season_num].append(t)
            
    return seasons, episodes

def search_aither_tv(title: str, tmdb_id: Optional[str] = None) -> Dict[str, Dict[Any, Any]]:
    """Finds best season packs and episodes for a TV show."""
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
            
        seasons, episodes = parse_tv_torrents(data)
        
        best_seasons = {s_num: best for s_num, s_torrents in seasons.items() if (best := score_torrents(s_torrents))}
        best_episodes = {key: best for key, e_torrents in episodes.items() if (best := score_torrents(e_torrents))}
            
        return {"seasons": best_seasons, "episodes": best_episodes}
    except Exception as e:
        print(f"Error searching Aither TV (TMDB {tmdb_id}): {e}")
        return {"seasons": {}, "episodes": {}}

def get_active_downloads_count(qbt_client: qbittorrentapi.Client) -> int:
    """Get the number of active/downloading torrents."""
    try:
        torrents = qbt_client.torrents_info(status_filter='downloading')
        return len(torrents)
    except Exception as e:
        print(f"Error getting active downloads count: {e}")
        return -1

def send_to_qbittorrent(qbt_client: qbittorrentapi.Client, download_link: str, save_path: str) -> bool:
    """Send a download URL to qBittorrent."""
    try:
        qbt_client.torrents_add(urls=download_link, save_path=save_path, is_paused=False)
        return True
    except Exception as e:
        print(f"Error sending to qbittorrent: {e}")
        return False

def normalize_title(title: str) -> List[str]:
    # Convert 'Season X' to 'S0X' for scene torrent matching
    title = RE_SEASON.sub(lambda m: f"S{int(m.group(1)):02d}", title)
    return [w.lower() for w in RE_WORDS.findall(title)]

def get_active_downloads_status(qbt_client: qbittorrentapi.Client, active_db_items: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Check active DB items against qBittorrent and return their progress, ETA, and completed status."""
    status_updates = {}
    try:
        torrents = qbt_client.torrents_info()
        torrent_words = [(t, set(normalize_title(t.name))) for t in torrents]
        
        for item in active_db_items:
            db_id = item['id']
            plex_words = set(normalize_title(item['title']))
            
            for t, t_words in torrent_words:
                if plex_words.issubset(t_words):
                    is_completed = (t.progress >= 1.0 or t.completion_on != -1)
                    progress = float(t.progress)
                    eta = int(t.eta) if t.eta < 8640000 else -1 # qBittorrent uses 8640000 (100 days) for infinity
                    
                    status_updates[db_id] = {
                        'status': 'completed' if is_completed else 'downloading',
                        'progress': progress,
                        'eta_seconds': eta
                    }
                    break
                        
        return status_updates
    except Exception as e:
        print(f"Error checking downloads status: {e}")
        return status_updates

def get_all_torrent_names(qbt_client: qbittorrentapi.Client) -> List[str]:
    """Retrieve all torrent names currently mapped to qBittorrent history."""
    try:
        torrents = qbt_client.torrents_info()
        return [t.name for t in torrents]
    except Exception as e:
        print(f"Error getting torrent names: {e}")
        return []
