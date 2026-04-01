    # Convert 'Season X' to 'S0X' for scene torrent matching
    title = RE_SEASON.sub(lambda m: f"S{int(m.group(1)):02d}", title)
    return [w.lower() for w in RE_WORDS.findall(title)]

def get_active_downloads_status(qbt_client: qbittorrentapi.Client, active_db_items: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Check active DB items against qBittorrent and return their progress, ETA, and completed status."""
    status_updates = {}
    try:
        torrents = qbt_client.torrents_info()
        # Precompute torrent words to avoid redundant string parsing (O(N*M) -> O(N+M))
        precomputed_torrents = [(t, set(normalize_title(t.name))) for t in torrents]
        
        for item in active_db_items:
            db_id = item['id']
            plex_words = set(normalize_title(item['title']))
            
            for t, t_words in precomputed_torrents:
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
