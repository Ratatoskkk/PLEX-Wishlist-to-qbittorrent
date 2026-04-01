import time
import sys

# mock missing libraries to test logic directly without network dependencies
from unittest.mock import MagicMock
sys.modules['requests'] = MagicMock()
sys.modules['qbittorrentapi'] = MagicMock()
sys.modules['dotenv'] = MagicMock()

from downloader import get_active_downloads_status

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

    print(f"Optimized Time taken: {end_time - start_time:.4f} seconds")

if __name__ == "__main__":
    run_benchmark()
