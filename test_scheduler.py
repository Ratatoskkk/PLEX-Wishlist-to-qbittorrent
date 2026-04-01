import sys
from unittest.mock import MagicMock
sys.modules['plexapi'] = MagicMock()
sys.modules['plexapi.myplex'] = MagicMock()
sys.modules['plexapi.server'] = MagicMock()
sys.modules['qbittorrentapi'] = MagicMock()

import downloader
from scheduler import is_already_downloaded

def mock_normalize_title(title: str):
    return title.lower().split()
downloader.normalize_title = mock_normalize_title

def test_is_already_downloaded():
    existing_qbt_names = [
        "The Best Show S01E01 1080p",
        "The Best Show S01E02 1080p",
        "Another Show S02E05 720p",
        "The Best Show S02 1080p"
    ]

    assert is_already_downloaded(existing_qbt_names, 1, 1) == True
    assert is_already_downloaded(existing_qbt_names, 1, 3) == False
    assert is_already_downloaded(existing_qbt_names, 2, 5) == True
    assert is_already_downloaded(existing_qbt_names, 2, 6) == False

    assert is_already_downloaded(existing_qbt_names, 2) == True
    assert is_already_downloaded(existing_qbt_names, 3) == False

test_is_already_downloaded()
print("Tests pass!")
