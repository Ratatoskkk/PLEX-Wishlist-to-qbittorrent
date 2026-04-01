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

    def test_filter_best_torrent_empty(self):
        # Act
        result = downloader.filter_best_torrent([])

        # Assert
        self.assertIsNone(result)

    def test_filter_best_torrent_no_valid(self):
        # Arrange
        torrents = [
            {'id': 1, 'attributes': {'resolution': '720p', 'name': 'movie 720p'}},
            {'id': 2, 'attributes': {'type': 'full disc', 'name': 'movie bd50'}}
        ]

        # Act
        result = downloader.filter_best_torrent(torrents)

        # Assert
        self.assertIsNone(result)

    def test_filter_best_torrent_priorities(self):
        # Arrange
        torrents = [
            {'id': 1, 'attributes': {'resolution': '1080p', 'name': 'movie 1080p'}},
            {'id': 2, 'attributes': {'resolution': '1080p', 'name': 'movie 1080p remux'}},
            {'id': 3, 'attributes': {'resolution': '2160p', 'name': 'movie 4k'}},
            {'id': 4, 'attributes': {'resolution': '2160p', 'name': 'movie 4k hdr'}},
            {'id': 5, 'attributes': {'resolution': '2160p', 'name': 'movie 4k remux'}},
            {'id': 6, 'attributes': {'resolution': '2160p', 'name': 'movie 4k hdr remux'}},
        ]

        # Act
        result = downloader.filter_best_torrent(torrents)

        # Assert
        self.assertEqual(result.get('id'), 6)

        # Test finding second best when first best is not there
        result2 = downloader.filter_best_torrent(torrents[:5])
        self.assertEqual(result2.get('id'), 5)

        # Test finding third best
        result3 = downloader.filter_best_torrent(torrents[:4])
        self.assertEqual(result3.get('id'), 4)

        # Test finding fourth best
        result4 = downloader.filter_best_torrent(torrents[:3])
        self.assertEqual(result4.get('id'), 3)

        # Test finding fifth best
        result5 = downloader.filter_best_torrent(torrents[:2])
        self.assertEqual(result5.get('id'), 2)

        # Test finding sixth best
        result6 = downloader.filter_best_torrent(torrents[:1])
        self.assertEqual(result6.get('id'), 1)

    def test_filter_best_torrent_size_tiebreaker(self):
        # Arrange
        torrents = [
            {'id': 1, 'attributes': {'resolution': '2160p', 'name': 'movie 4k hdr remux', 'size': 1000}},
            {'id': 2, 'attributes': {'resolution': '2160p', 'name': 'movie 4k hdr remux', 'size': 2000}},
            {'id': 3, 'attributes': {'resolution': '2160p', 'name': 'movie 4k hdr remux', 'size': 1500}},
        ]

        # Act
        result = downloader.filter_best_torrent(torrents)

        # Assert
        self.assertEqual(result.get('id'), 2)

    def test_filter_best_torrent_hdr_detection(self):
        # Arrange
        torrents_hdr_in_name = [
            {'id': 1, 'attributes': {'resolution': '2160p', 'name': 'movie 4k hdr remux'}}
        ]
        torrents_hdr_in_media_info = [
            {'id': 2, 'attributes': {'resolution': '2160p', 'name': 'movie 4k remux', 'media_info': 'hdr10'}}
        ]
        torrents_hdr_as_bool = [
            {'id': 3, 'attributes': {'resolution': '2160p', 'name': 'movie 4k remux', 'hdr': True}}
        ]
        torrents_no_hdr = [
            {'id': 4, 'attributes': {'resolution': '2160p', 'name': 'movie 4k remux'}}
        ]

        # Act & Assert
        self.assertEqual(downloader.filter_best_torrent(torrents_hdr_in_name + torrents_no_hdr).get('id'), 1)
        self.assertEqual(downloader.filter_best_torrent(torrents_hdr_in_media_info + torrents_no_hdr).get('id'), 2)
        self.assertEqual(downloader.filter_best_torrent(torrents_hdr_as_bool + torrents_no_hdr).get('id'), 3)

    def test_filter_best_torrent_remux_detection(self):
        # Arrange
        torrents_remux_in_name = [
            {'id': 1, 'attributes': {'resolution': '2160p', 'name': 'movie 4k remux hdr'}}
        ]
        torrents_remux_in_type = [
            {'id': 2, 'attributes': {'resolution': '2160p', 'name': 'movie 4k hdr', 'type': 'remux'}}
        ]
        torrents_no_remux = [
            {'id': 3, 'attributes': {'resolution': '2160p', 'name': 'movie 4k hdr'}}
        ]

        # Act & Assert
        self.assertEqual(downloader.filter_best_torrent(torrents_remux_in_name + torrents_no_remux).get('id'), 1)
        self.assertEqual(downloader.filter_best_torrent(torrents_remux_in_type + torrents_no_remux).get('id'), 2)

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

    def test_score_torrents_empty_list(self):
        # Act
        result = downloader.score_torrents([])

        # Assert
        self.assertIsNone(result)

    def test_score_torrents_poorly_formatted(self):
        # Act
        result_empty_dict = downloader.score_torrents([{}])
        result_empty_attrs = downloader.score_torrents([{'attributes': {}}])

        # Assert
        expected_fallback = {
            'id': None,
            'name': '',
            'size': 0,
            'download_link': None,
            'resolution': 'Unknown'
        }
        self.assertEqual(result_empty_dict, expected_fallback)
        self.assertEqual(result_empty_attrs, expected_fallback)

    def test_normalize_title(self):
        self.assertEqual(downloader.normalize_title("Show Name Season 1"), ["show", "name", "s01"])
        self.assertEqual(downloader.normalize_title("Show Name S01"), ["show", "name", "s01"])
        self.assertEqual(downloader.normalize_title("Show.Name.S01E01.1080p"), ["show", "name", "s01e01", "1080p"])


if __name__ == '__main__':
    unittest.main()
