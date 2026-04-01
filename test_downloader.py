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

    def test_is_full_disc(self):
        self.assertTrue(downloader.is_full_disc("Full Disc", "Some Movie"))
        self.assertTrue(downloader.is_full_disc("Movie", "Some Movie Full Disc"))
        self.assertTrue(downloader.is_full_disc("BD50", "Some Movie"))
        self.assertTrue(downloader.is_full_disc("BD25", "Some Movie"))
        self.assertFalse(downloader.is_full_disc("Remux", "Some Movie Remux"))

    def test_filter_best_torrent(self):
        torrents = [
            {'id': 1, 'attributes': {'name': 'Movie 1080p', 'resolution': '1080p', 'size': 1000}},
            {'id': 2, 'attributes': {'name': 'Movie 1080p Remux', 'resolution': '1080p', 'type': 'Remux', 'size': 2000}},
            {'id': 3, 'attributes': {'name': 'Movie 4K', 'resolution': '2160p', 'size': 3000}},
            {'id': 4, 'attributes': {'name': 'Movie 4K HDR', 'resolution': '2160p', 'media_info': 'HDR10', 'size': 4000}},
            {'id': 5, 'attributes': {'name': 'Movie 4K HDR Remux', 'resolution': '2160p', 'type': 'Remux', 'hdr': True, 'size': 5000}},
            {'id': 6, 'attributes': {'name': 'Movie 4K HDR Remux 2', 'resolution': '4K', 'type': 'Remux', 'hdr': True, 'size': 6000}},
            {'id': 7, 'attributes': {'name': 'Movie Full Disc', 'type': 'Full Disc', 'resolution': '2160p', 'size': 9000}},
        ]

        # Test finding the best one (score 100, highest size)
        best = downloader.filter_best_torrent(torrents)
        self.assertIsNotNone(best)
        self.assertEqual(best['id'], 6)

        # Test filtering out full disc
        self.assertNotEqual(best['id'], 7)

        # Test empty list
        self.assertIsNone(downloader.filter_best_torrent([]))

        # Test no valid torrents
        self.assertIsNone(downloader.filter_best_torrent([{'id': 8, 'attributes': {'name': 'Movie 720p', 'resolution': '720p', 'size': 500}}]))

    def test_score_torrents(self):
        torrents = [
            {'id': 1, 'attributes': {'name': 'Show S01E01 1080p', 'resolution': '1080p', 'size': 1000, 'download_link': 'link1'}},
            {'id': 2, 'attributes': {'name': 'Show S01E01 4K', 'resolution': '2160p', 'size': 2000, 'download_link': 'link2'}},
            {'id': 3, 'attributes': {'name': 'Show S01E01 4K HDR Remux', 'resolution': '2160p', 'size': 3000, 'download_link': 'link3'}},
        ]

        best = downloader.score_torrents(torrents)
        self.assertIsNotNone(best)
        self.assertEqual(best['id'], 3)
        self.assertEqual(best['name'], 'Show S01E01 4K HDR Remux')

        self.assertIsNone(downloader.score_torrents([]))

    def test_parse_tv_torrents(self):
        torrents = [
            {'id': 1, 'attributes': {'name': 'Show S01'}},
            {'id': 2, 'attributes': {'name': 'Show S01E01'}},
            {'id': 3, 'attributes': {'name': 'Show S01 E02'}},
            {'id': 4, 'attributes': {'name': 'Show Season 2'}}, # Doesn't match RE_S_NUM (\bS(\d{1,2})\b)
            {'id': 5, 'attributes': {'name': 'Show S02'}},
            {'id': 6, 'attributes': {'name': 'Show Full Disc S01', 'type': 'Full Disc'}}, # Should be ignored
        ]

        seasons, episodes = downloader.parse_tv_torrents(torrents)

        # Seasons
        self.assertIn(1, seasons)
        self.assertEqual(len(seasons[1]), 1)
        self.assertEqual(seasons[1][0]['id'], 1)
        self.assertIn(2, seasons)
        self.assertEqual(len(seasons[2]), 1)

        # Episodes
        self.assertIn((1, 1), episodes)
        self.assertEqual(len(episodes[(1, 1)]), 1)
        self.assertEqual(episodes[(1, 1)][0]['id'], 2)

        self.assertIn((1, 2), episodes)
        self.assertEqual(len(episodes[(1, 2)]), 1)
        self.assertEqual(episodes[(1, 2)][0]['id'], 3)

        # Full disc ignored
        self.assertNotIn(6, [t['id'] for sublist in seasons.values() for t in sublist])
        self.assertNotIn(6, [t['id'] for sublist in episodes.values() for t in sublist])

    def test_normalize_title(self):
        self.assertEqual(downloader.normalize_title("Show Name Season 1"), ["show", "name", "s01"])
        self.assertEqual(downloader.normalize_title("Show Name S01"), ["show", "name", "s01"])
        self.assertEqual(downloader.normalize_title("Show.Name.S01E01.1080p"), ["show", "name", "s01e01", "1080p"])

if __name__ == '__main__':
    unittest.main()
