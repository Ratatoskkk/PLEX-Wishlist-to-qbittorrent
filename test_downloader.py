import sys
import unittest
from unittest.mock import MagicMock

# We should NOT globally stub modules like this when using full test runners,
# because it poisons the module cache for other test modules like test_scheduler.py
# that actually need the real 'requests' module.

# Use patch from unittest.mock for mocking specific things in the tests if needed.
# Since we actually want to test logic that doesn't strictly need these mocked at the
# module level when running via python -m unittest, we can just let them load.
# In an offline environment, we mock only if it fails to import or we can mock
# the external calls.
# Here, we will try to delete the stubbing so that `test_scheduler` can import real requests.

import qbittorrentapi
import downloader

class TestDownloader(unittest.TestCase):
    def test_get_active_downloads_count_success(self):
        # Arrange
        mock_client = MagicMock()
        # Mocking the return value of torrents_info
        mock_client.torrents_info.return_value = [{'hash': '123'}, {'hash': '456'}]

        # Act
        result = downloader.get_active_downloads_count(mock_client)

        # Assert
        self.assertEqual(result, 2)
        mock_client.torrents_info.assert_called_once_with(status_filter='downloading')

    def test_get_active_downloads_count_error(self):
        # Arrange
        mock_client = MagicMock()
        # Mocking torrents_info to raise an exception
        mock_client.torrents_info.side_effect = Exception("Connection error")

        # Act
        result = downloader.get_active_downloads_count(mock_client)

        # Assert
        self.assertEqual(result, -1)
        mock_client.torrents_info.assert_called_once_with(status_filter='downloading')

    def test_send_to_qbittorrent_success(self):
        # Arrange
        mock_client = MagicMock()
        download_link = "http://example.com/torrent"
        save_path = "/downloads"

        # Act
        result = downloader.send_to_qbittorrent(mock_client, download_link, save_path)

        # Assert
        self.assertTrue(result)
        mock_client.torrents_add.assert_called_once_with(urls=download_link, save_path=save_path, is_paused=False)

    def test_send_to_qbittorrent_error(self):
        # Arrange
        mock_client = MagicMock()
        mock_client.torrents_add.side_effect = Exception("Failed to add torrent")
        download_link = "http://example.com/torrent"
        save_path = "/downloads"

        # Act
        result = downloader.send_to_qbittorrent(mock_client, download_link, save_path)

        # Assert
        self.assertFalse(result)
        mock_client.torrents_add.assert_called_once_with(urls=download_link, save_path=save_path, is_paused=False)

    def test_normalize_title(self):
        # Arrange
        test_cases = [
            # (input_title, expected_output)
            ("The Matrix", ["the", "matrix"]),  # Basic title
            ("The Matrix Reloaded 2003", ["the", "matrix", "reloaded", "2003"]),  # Mixed case and numbers
            ("Game of Thrones Season 1", ["game", "of", "thrones", "s01"]),  # Season X conversion
            ("Game of Thrones Season 12", ["game", "of", "thrones", "s12"]),  # 2-digit season
            ("Game of Thrones (Season 1)", ["game", "of", "thrones", "s01"]),  # (Season X) conversion
            ("The.Last.of.Us.S01E01", ["the", "last", "of", "us", "s01e01"]),  # Dots and S01E01
            ("Breaking Bad: The Movie", ["breaking", "bad", "the", "movie"]),  # Special characters (colon)
            ("Spider-Man: Across the Spider-Verse", ["spider", "man", "across", "the", "spider", "verse"]),  # Hyphens
            ("What If...?", ["what", "if"]),  # Ellipsis and question mark
            ("   Spaces   Everywhere   ", ["spaces", "everywhere"]),  # Extraneous spaces
            ("12 Monkeys", ["12", "monkeys"]),  # Starts with number
            ("", []),  # Empty string
            ("!!!@@@###", []),  # Only special characters
            ("sEaSoN 5", ["s05"]), # Case insensitive Season match
            ("Season 05", ["s05"]) # Zero-padded season
        ]

        for input_title, expected_output in test_cases:
            with self.subTest(input_title=input_title):
                # Act
                result = downloader.normalize_title(input_title)

                # Assert
                self.assertEqual(result, expected_output)

if __name__ == '__main__':
    unittest.main()
