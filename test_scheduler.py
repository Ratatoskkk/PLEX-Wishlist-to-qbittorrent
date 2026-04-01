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
from scheduler import is_already_downloaded, extract_tmdb_id

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

    def test_extract_tmdb_id_success(self):
        mock_item = MagicMock()
        mock_guid = MagicMock()
        mock_guid.id = "tmdb://12345"
        mock_item.guids = [mock_guid]

        result = extract_tmdb_id(mock_item)
        self.assertEqual(result, "12345")

    def test_extract_tmdb_id_no_guids(self):
        mock_item = object()  # Object without guids attribute

        result = extract_tmdb_id(mock_item)
        self.assertIsNone(result)

    def test_extract_tmdb_id_empty_guids(self):
        mock_item = MagicMock()
        mock_item.guids = []

        result = extract_tmdb_id(mock_item)
        self.assertIsNone(result)

    def test_extract_tmdb_id_no_tmdb(self):
        mock_item = MagicMock()
        mock_guid1 = MagicMock()
        mock_guid1.id = "imdb://tt1234567"
        mock_guid2 = MagicMock()
        mock_guid2.id = "tvdb://76543"
        mock_item.guids = [mock_guid1, mock_guid2]

        result = extract_tmdb_id(mock_item)
        self.assertIsNone(result)

    def test_extract_tmdb_id_multiple_guids(self):
        mock_item = MagicMock()
        mock_guid1 = MagicMock()
        mock_guid1.id = "imdb://tt1234567"
        mock_guid2 = MagicMock()
        mock_guid2.id = "tmdb://98765"
        mock_guid3 = MagicMock()
        mock_guid3.id = "tvdb://76543"
        mock_item.guids = [mock_guid1, mock_guid2, mock_guid3]

        result = extract_tmdb_id(mock_item)
        self.assertEqual(result, "98765")

if __name__ == '__main__':
    unittest.main()
