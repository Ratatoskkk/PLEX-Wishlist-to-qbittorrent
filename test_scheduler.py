import sys
import unittest
from unittest.mock import MagicMock

# Stub external dependencies
sys.modules['requests'] = MagicMock()
sys.modules['qbittorrentapi'] = MagicMock()
sys.modules['dotenv'] = MagicMock()
sys.modules['plexapi'] = MagicMock()
sys.modules['plexapi.myplex'] = MagicMock()
sys.modules['plexapi.server'] = MagicMock()
sys.modules['apscheduler'] = MagicMock()
sys.modules['apscheduler.schedulers'] = MagicMock()
sys.modules['apscheduler.schedulers.background'] = MagicMock()

import downloader
from scheduler import is_already_downloaded

def mock_normalize_title(title: str):
    return title.lower().split()
downloader.normalize_title = mock_normalize_title

class TestScheduler(unittest.TestCase):
    def test_is_already_downloaded(self):
        existing_qbt_names = [
            "The Best Show S01E01 1080p",
            "The Best Show S01E02 1080p",
            "Another Show S02E05 720p",
            "The Best Show S02 1080p"
        ]

        # In scheduler.py: def is_already_downloaded(relevant_qbt_names: List[str], s_num: int, e_num: Optional[int] = None) -> bool:
        # Note: the test previously passed title as well, but the function signature changed.
        # relevant_qbt_names should only contain names for the specific show being checked.

        relevant_best_show = ["The Best Show S01E01 1080p", "The Best Show S01E02 1080p", "The Best Show S02 1080p"]
        relevant_another_show = ["Another Show S02E05 720p"]

        self.assertTrue(is_already_downloaded(relevant_best_show, 1, 1))
        self.assertFalse(is_already_downloaded(relevant_best_show, 1, 3))
        self.assertTrue(is_already_downloaded(relevant_another_show, 2, 5))
        self.assertFalse(is_already_downloaded(relevant_another_show, 2, 6))

        self.assertTrue(is_already_downloaded(relevant_best_show, 2))
        self.assertFalse(is_already_downloaded(relevant_best_show, 3))

if __name__ == '__main__':
    unittest.main()
