import sys
import unittest
from unittest.mock import MagicMock

# Stub external dependencies
sys.modules['requests'] = MagicMock()
sys.modules['qbittorrentapi'] = MagicMock()
sys.modules['dotenv'] = MagicMock()

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

class TestIsFullDisc(unittest.TestCase):
    def test_is_full_disc_true_positives_type(self):
        # Test exact match in type
        self.assertTrue(downloader.is_full_disc('full disc', 'movie'))
        self.assertTrue(downloader.is_full_disc('bd50', 'movie'))
        self.assertTrue(downloader.is_full_disc('bd25', 'movie'))

        # Test substring match in type
        self.assertTrue(downloader.is_full_disc('1080p full disc', 'movie'))
        self.assertTrue(downloader.is_full_disc('remux bd50', 'movie'))

        # Test mixed case
        self.assertTrue(downloader.is_full_disc('Full Disc', 'movie'))
        self.assertTrue(downloader.is_full_disc('BD50', 'movie'))

    def test_is_full_disc_true_positives_name(self):
        # Test exact match in name
        self.assertTrue(downloader.is_full_disc('movie', 'Movie Name Full Disc'))
        self.assertTrue(downloader.is_full_disc('movie', 'Movie BD50'))
        self.assertTrue(downloader.is_full_disc('movie', 'Movie BD25'))

        # Test mixed case
        self.assertTrue(downloader.is_full_disc('movie', 'Movie Name FULL DISC'))
        self.assertTrue(downloader.is_full_disc('movie', 'Movie bd50'))

    def test_is_full_disc_false_positives(self):
        # Should not match partial words
        self.assertFalse(downloader.is_full_disc('full', 'movie'))
        self.assertFalse(downloader.is_full_disc('disc', 'movie'))
        self.assertFalse(downloader.is_full_disc('bd', 'movie'))
        self.assertFalse(downloader.is_full_disc('movie', 'A full movie'))
        self.assertFalse(downloader.is_full_disc('movie', 'A movie disc'))
        self.assertFalse(downloader.is_full_disc('movie', 'Movie bd'))

    def test_is_full_disc_legitimate_releases(self):
        # Typical releases that are not full discs
        self.assertFalse(downloader.is_full_disc('remux', 'Movie 1080p Remux'))
        self.assertFalse(downloader.is_full_disc('movie', 'Movie 4K HDR'))
        self.assertFalse(downloader.is_full_disc('web-dl', 'Movie 1080p WEB-DL'))
        self.assertFalse(downloader.is_full_disc('bluray', 'Movie 1080p BluRay'))

    def test_is_full_disc_edge_cases(self):
        # Empty strings
        self.assertFalse(downloader.is_full_disc('', ''))

        # Numbers only
        self.assertFalse(downloader.is_full_disc('1080', '2160'))

if __name__ == '__main__':
    unittest.main()
