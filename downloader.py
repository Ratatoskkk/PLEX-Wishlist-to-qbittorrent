import os
import requests
import qbittorrentapi
import re
from typing import Dict, Any, List, Optional, Tuple
import functools
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

AITHER_API_KEY = os.getenv('AITHER_API_KEY')
QBITTORRENT_URL = os.getenv('QBITTORRENT_URL')
QBITTORRENT_USERNAME = os.getenv('QBITTORRENT_USERNAME')
QBITTORRENT_PASSWORD = os.getenv('QBITTORRENT_PASSWORD')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')

AITHER_URL = "https://aither.cc/api/torrents/filter"
TMDB_URL = "https://api.themoviedb.org/3"

# Pre-compiled regex patterns for performance
RE_S_NUM = re.compile(r'\bS(\d{1,2})\b', re.IGNORECASE)
RE_E_NUM = re.compile(r'\bE(\d{1,2})\b', re.IGNORECASE)
RE_SE_NUM = re.compile(r'\bS(\d{1,2})[ .]?E(\d{1,2})\b', re.IGNORECASE)
RE_SEASON = re.compile(r'\(?Season\s+(\d+)\)?', re.IGNORECASE)
RE_WORDS = re.compile(r'\w+')
RE_SE_IDENTIFIER = re.compile(r'^s\d+(e\d+)?$')

# Shared API headers for Aither requests
_AITHER_HEADERS = {
    'Authorization': f'Bearer {AITHER_API_KEY}',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}


def _cache_unless_empty(fn):
    """Cache results only when non-empty. Prevents caching failed lookups permanently."""
    cache: Dict[Tuple, Any] = {}
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        key = args + tuple(sorted(kwargs.items()))
        if key in cache:
            return cache[key]
        result = fn(*args, **kwargs)
        is_empty = (
            result is None
            or result == {"seasons": {}, "episodes": {}}
            or (isinstance(result, dict) and not result)
        )
        if not is_empty:
            cache[key] = result
        return result
    wrapper.cache = cache
    wrapper.cache_clear = lambda: cache.clear()
    return wrapper


def get_qbt_client() -> qbittorrentapi.Client:
    """Dependency injection for qBittorrent client."""
    qbt_client = qbittorrentapi.Client(
        host=QBITTORRENT_URL,
        username=QBITTORRENT_USERNAME,
        password=QBITTORRENT_PASSWORD,
    )
    qbt_client.auth_log_in()
    return qbt_client


@_cache_unless_empty
def search_aither(title: str, tmdb_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Search Aither API for the optimal movie torrent."""
    params: Dict[str, str] = {'perPage': '100', 'sortField': 'size', 'sortDirection': 'desc'}
    if tmdb_id:
        params['tmdbId'] = str(tmdb_id)
    else:
        params['name'] = title

    try:
        response = requests.get(AITHER_URL, headers=_AITHER_HEADERS, params=params, timeout=15)
        response.raise_for_status()
        data = response.json().get('data', [])
        if isinstance(data, dict) and 'data' in data:
            data = data['data']
        return filter_best_torrent(data)
    except Exception as e:
        print(f"Error querying Aither for {title}: {e}")
        return None


def is_full_disc(type_str: str, name_str: str) -> bool:
    """Return True if the release appears to be a full Blu-ray disc (already lowercased inputs)."""
    full_disc_keywords = ('full disc', 'bd50', 'bd25')
    return any(kw in type_str or kw in name_str for kw in full_disc_keywords)


def score_movie_torrent(res: str, name_str: str, media_info: str, type_str: str, hdr: bool) -> int:
    """Score a single movie torrent by quality tier. Returns 0 if below minimum threshold."""
    is_4k = '2160p' in res or '4k' in res
    is_remux = 'remux' in name_str or 'remux' in type_str
    is_hdr = 'hdr' in name_str or 'hdr' in media_info or hdr
    is_1080p = '1080p' in res

    if is_4k and is_remux and is_hdr:
        return 100
    if is_4k and is_remux:
        return 90
    if is_4k and is_hdr:
        return 80
    if is_4k:
        return 70
    if is_1080p and is_remux:
        return 60
    if is_1080p:
        return 50
    return 0


def filter_best_torrent(torrents: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Filter and rank torrents; prefer 4K HDR Remux > 4K HDR > 1080p Remux."""
    valid_torrents = []

    for t in torrents:
        attrs = t.get('attributes', {})
        type_str = str(attrs.get('type', '')).lower()
        name_str = str(attrs.get('name', '')).lower()

        if is_full_disc(type_str, name_str):
            continue

        res = str(attrs.get('resolution', '')).lower()
        media_info = str(attrs.get('media_info', '')).lower()
        hdr = bool(attrs.get('hdr', False))

        score = score_movie_torrent(res, name_str, media_info, type_str, hdr)
        if score > 0:
            valid_torrents.append((score, attrs, t.get('id')))

    if not valid_torrents:
        return None

    valid_torrents.sort(key=lambda x: (x[0], x[1].get('size', 0)), reverse=True)
    best_attrs = valid_torrents[0][1]
    best_attrs['id'] = valid_torrents[0][2]
    return best_attrs


def score_torrents(torrent_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Select the highest-quality torrent from a list of TV season/episode candidates."""
    best_t = None
    best_sc = -1
    for t in torrent_list:
        attrs = t.get('attributes', {})
        t_name = attrs.get('name', '')
        t_name_lower = t_name.lower()
        res = str(attrs.get('resolution', '')).lower()

        score = 0
        if '2160p' in res or '4k' in res:
            score += 50
            if 'remux' in t_name_lower:
                score += 50
            if 'hdr' in t_name_lower or 'dv' in t_name_lower:
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
                'resolution': res or 'Unknown',
            }
    return best_t


def parse_tv_torrents(
    torrents: List[Dict[str, Any]],
) -> Tuple[Dict[int, List[Dict[str, Any]]], Dict[Tuple[int, int], List[Dict[str, Any]]]]:
    """Separate Aither TV torrents into season packs and single episodes."""
    seasons: Dict[int, List[Dict[str, Any]]] = {}
    episodes: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}

    for t in torrents:
        attrs = t.get('attributes', {})
        t_name = attrs.get('name', '')
        t_type = str(attrs.get('type', '')).lower()

        if is_full_disc(t_type, t_name.lower()):
            continue

        match_se = RE_SE_NUM.search(t_name)
        if match_se:
            key = (int(match_se.group(1)), int(match_se.group(2)))
            episodes.setdefault(key, []).append(t)
            continue

        match_s = RE_S_NUM.search(t_name)
        match_e = RE_E_NUM.search(t_name)
        if match_s and not match_e:
            seasons.setdefault(int(match_s.group(1)), []).append(t)

    return seasons, episodes


@_cache_unless_empty
def search_aither_tv(title: str, tmdb_id: Optional[str] = None) -> Dict[str, Any]:
    """Find and rank the best season packs and episodes for a TV show on Aither."""

    try:
        params: Dict[str, str] = {'perPage': '100'}
        if tmdb_id:
            params['tmdbId'] = str(tmdb_id)
        else:
            params['name'] = title

        response = requests.get(AITHER_URL, headers=_AITHER_HEADERS, params=params, timeout=15)
        response.raise_for_status()
        data = response.json().get('data', [])
        if isinstance(data, dict) and 'data' in data:
            data = data['data']

        print(f"[Aither] Found {len(data)} results for '{title}' (tmdbId={tmdb_id})")

        seasons, episodes = parse_tv_torrents(data)
        best_seasons = {s: best for s, ts in seasons.items() if (best := score_torrents(ts))}
        best_episodes = {key: best for key, es in episodes.items() if (best := score_torrents(es))}
        return {"seasons": best_seasons, "episodes": best_episodes}
    except Exception as e:
        print(f"Error searching Aither TV (TMDB {tmdb_id} / Title {title}): {e}")
        return {"seasons": {}, "episodes": {}}


def get_active_downloads_count(qbt_client: qbittorrentapi.Client) -> int:
    """Return the number of actively downloading torrents, or -1 on error."""
    try:
        return len(qbt_client.torrents_info(status_filter='downloading'))
    except Exception as e:
        print(f"Error getting active downloads count: {e}")
        return -1


def send_to_qbittorrent(
    qbt_client: qbittorrentapi.Client,
    download_link: str,
    save_path: str,
    db_id: Optional[int] = None,
) -> bool:
    """Add a torrent URL to qBittorrent and tag it for later identification."""
    try:
        tags = f"plexaither_{db_id}" if db_id else ""
        qbt_client.torrents_add(urls=download_link, save_path=save_path, is_paused=False, tags=tags)
        return True
    except Exception as e:
        print(f"Error sending to qBittorrent: {e}")
        return False


@functools.lru_cache(maxsize=64)
def fetch_tmdb_tv_details(tmdb_id: str) -> Optional[Dict[str, Any]]:
    """Fetch show metadata from TMDB (cached per run)."""
    if not TMDB_API_KEY:
        print("TMDB_API_KEY missing, cannot fetch TV details.")
        return None
    try:
        resp = requests.get(f"{TMDB_URL}/tv/{tmdb_id}?api_key={TMDB_API_KEY}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching TMDB TV details for {tmdb_id}: {e}")
        return None


@functools.lru_cache(maxsize=64)
def fetch_tmdb_movie_release_dates(tmdb_id: str) -> Optional[Dict[str, Any]]:
    """Fetch movie metadata + release dates from TMDB (cached per run)."""
    if not TMDB_API_KEY:
        return None
    try:
        resp = requests.get(
            f"{TMDB_URL}/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=release_dates",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching TMDB movie dates for {tmdb_id}: {e}")
        return None


def fetch_movie_poster(tmdb_id: str) -> Optional[str]:
    """Return the poster_path string for a movie from TMDB, or None."""
    if not TMDB_API_KEY or not tmdb_id:
        return None
    try:
        resp = requests.get(f"{TMDB_URL}/movie/{tmdb_id}?api_key={TMDB_API_KEY}", timeout=5)
        if resp.status_code == 200:
            return resp.json().get('poster_path')
    except Exception:
        pass
    return None


def normalize_title(title: str) -> List[str]:
    """Convert a title to a canonical word list for fuzzy matching against torrent names."""
    # Convert 'Season X' / '(Season X)' to scene-standard 'S0X'
    title = RE_SEASON.sub(lambda m: f"S{int(m.group(1)):02d}", title)
    return [w.lower() for w in RE_WORDS.findall(title)]


def _parse_torrent_tags(tags_str: str) -> List[str]:
    """Parse a qBittorrent comma-separated tag string into a clean list."""
    return [tag.strip() for tag in tags_str.split(',')] if tags_str else []


def get_active_downloads_status(
    qbt_client: qbittorrentapi.Client,
    active_db_items: List[Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """Match active DB items to live qBittorrent torrents and return progress/ETA/status."""
    status_updates: Dict[int, Dict[str, Any]] = {}
    try:
        torrents = qbt_client.torrents_info()
        # Precompute normalised word sets once — O(N) instead of O(N*M)
        precomputed = [(t, set(normalize_title(t.name))) for t in torrents]

        for item in active_db_items:
            db_id = item['id']
            plex_words = set(normalize_title(item['title']))
            matched = None

            # 1. Tag-based match is the most reliable
            target_tag = f"plexaither_{db_id}"
            for t, _ in precomputed:
                if target_tag in _parse_torrent_tags(getattr(t, 'tags', '')):
                    matched = t
                    break

            # 2. Word-subset heuristic fallback
            if not matched:
                identifiers = {w for w in plex_words if RE_SE_IDENTIFIER.match(w)}
                for t, t_words in precomputed:
                    if plex_words.issubset(t_words):
                        matched = t
                        break
                    # Edge-case: show names that differ in common words (e.g. "Electric Dreams")
                    if identifiers and identifiers.issubset(t_words):
                        non_id = plex_words - identifiers
                        overlap = non_id.intersection(t_words)
                        if any(len(w) > 3 for w in overlap) or len(overlap) >= 2:
                            matched = t
                            break

            if matched:
                # qBittorrent uses 8640000 (100 days) to represent "infinite" ETA
                eta = int(matched.eta) if matched.eta < 8640000 else -1
                status_updates[db_id] = {
                    'status': 'completed' if (matched.progress >= 1.0 or matched.completion_on != -1) else 'downloading',
                    'progress': float(matched.progress),
                    'eta_seconds': eta,
                }

        return status_updates
    except Exception as e:
        print(f"Error checking download status: {e}")
        return status_updates


def get_all_torrent_names(qbt_client: qbittorrentapi.Client) -> List[str]:
    """Return the names of all torrents currently in qBittorrent."""
    try:
        return [t.name for t in qbt_client.torrents_info()]
    except Exception as e:
        print(f"Error getting torrent names: {e}")
        return []


def clear_caches() -> None:
    """Clear all LRU caches to prevent stale data between scheduled job runs."""
    search_aither.cache_clear()
    search_aither_tv.cache_clear()
    fetch_tmdb_tv_details.cache_clear()
    fetch_tmdb_movie_release_dates.cache_clear()
