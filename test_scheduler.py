import unittest
from unittest.mock import MagicMock
import sys

# Stub external dependencies
sys.modules['requests'] = MagicMock()
sys.modules['qbittorrentapi'] = MagicMock()
sys.modules['dotenv'] = MagicMock()
sys.modules['plexapi'] = MagicMock()
sys.modules['plexapi.myplex'] = MagicMock()
sys.modules['plexapi.server'] = MagicMock()

import downloader
from scheduler import is_already_downloaded

class TestScheduler(unittest.TestCase):
    def test_is_already_downloaded(self):
        # Temporarily mock normalize_title to match test logic without affecting other tests globally
        original_normalize_title = downloader.normalize_title
        def mock_normalize_title(title: str):
            return title.lower().split()
        downloader.normalize_title = mock_normalize_title

        # In reality, scheduler.py filters these names first before calling is_already_downloaded.
        best_show_names = [
            "The Best Show S01E01 1080p",
            "The Best Show S01E02 1080p",
            "The Best Show S02 1080p"
        ]

        another_show_names = [
            "Another Show S02E05 720p"
        ]

        try:
            self.assertTrue(is_already_downloaded(best_show_names, 1, 1))
            self.assertFalse(is_already_downloaded(best_show_names, 1, 3))
            self.assertTrue(is_already_downloaded(another_show_names, 2, 5))
            self.assertFalse(is_already_downloaded(another_show_names, 2, 6))

            self.assertTrue(is_already_downloaded(best_show_names, 2))
            self.assertFalse(is_already_downloaded(best_show_names, 3))
        finally:
            downloader.normalize_title = original_normalize_title

if __name__ == '__main__':
    unittest.main()
