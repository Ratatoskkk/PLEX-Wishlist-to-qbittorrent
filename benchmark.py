import time
import re
from typing import Dict, Any, List

RE_SEASON = re.compile(r'\(?Season\s+(\d+)\)?', re.IGNORECASE)
RE_WORDS = re.compile(r'\w+')

def normalize_title(title: str) -> List[str]:
    title = RE_SEASON.sub(lambda m: f"S{int(m.group(1)):02d}", title)
    return [w.lower() for w in RE_WORDS.findall(title)]

def get_active_downloads_status(qbt_client, active_db_items: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    status_updates = {}
    try:
        torrents = qbt_client.torrents_info()

        for item in active_db_items:
            db_id = item['id']
            plex_words = set(normalize_title(item['title']))

            for t in torrents:
                t_words = set(normalize_title(t.name))
                if plex_words.issubset(t_words):
                    is_completed = (t.progress >= 1.0 or t.completion_on != -1)
                    progress = float(t.progress)
                    eta = int(t.eta) if t.eta < 8640000 else -1

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

class MockTorrent:
    def __init__(self, name, progress=0.5, completion_on=-1, eta=1000):
        self.name = name
        self.progress = progress
        self.completion_on = completion_on
        self.eta = eta

class MockClient:
    def __init__(self, torrents):
        self._torrents = torrents
    def torrents_info(self):
        return self._torrents

def generate_mock_data(num_db_items, num_torrents):
    active_db_items = [
        {"id": i, "title": f"Movie Title {i}"} for i in range(num_db_items)
    ]

    torrents = []
    # All torrents don't match, causing worst-case performance (O(N*M))
    for i in range(num_torrents):
        torrents.append(MockTorrent(f"Some Random Torrent Release {i} 1080p"))

    return active_db_items, torrents

def run_benchmark():
    active_db_items, torrents = generate_mock_data(500, 2000)
    client = MockClient(torrents)

    start_time = time.time()
    get_active_downloads_status(client, active_db_items)
    end_time = time.time()

    print(f"Baseline Time taken: {end_time - start_time:.4f} seconds")

if __name__ == "__main__":
    run_benchmark()
