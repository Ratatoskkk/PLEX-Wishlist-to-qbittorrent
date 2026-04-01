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

    def test_parse_tv_torrents(self):
        # Arrange
        mock_torrents = [
            {'id': 1, 'attributes': {'name': 'Show S01E02 1080p'}},
            {'id': 2, 'attributes': {'name': 'Show S01 1080p'}},
            {'id': 3, 'attributes': {'name': 'Show S01.E03 1080p'}},
            {'id': 4, 'attributes': {'name': 'Show S01 E04 1080p'}},
            {'id': 5, 'attributes': {'name': 'Show S1E2 1080p'}},
            {'id': 6, 'attributes': {'name': 'Show S01E01 Full Disc', 'type': 'full disc'}},
            {'id': 7, 'attributes': {'name': 'Show Movie 2024'}},
            {'id': 8, 'attributes': {'name': 'Show S01E02 720p'}},
        ]

        # Act
        seasons, episodes = downloader.parse_tv_torrents(mock_torrents)

        # Assert
        # Season pack checks
        self.assertIn(1, seasons)
        self.assertEqual(len(seasons[1]), 1)
        self.assertEqual(seasons[1][0]['id'], 2)

        # Episode checks
        self.assertIn((1, 2), episodes)
        self.assertEqual(len(episodes[(1, 2)]), 3) # IDs 1, 5, 8
        self.assertEqual(episodes[(1, 2)][0]['id'], 1)
        self.assertEqual(episodes[(1, 2)][1]['id'], 5)
        self.assertEqual(episodes[(1, 2)][2]['id'], 8)

        self.assertIn((1, 3), episodes)
        self.assertEqual(len(episodes[(1, 3)]), 1)
        self.assertEqual(episodes[(1, 3)][0]['id'], 3)

        self.assertIn((1, 4), episodes)
        self.assertEqual(len(episodes[(1, 4)]), 1)
        self.assertEqual(episodes[(1, 4)][0]['id'], 4)

        # Check skipped full disc
        self.assertNotIn((1, 1), episodes)

        # Check skipped non-match
        # Should not throw error, should just ignore id 7


if __name__ == '__main__':
    unittest.main()
