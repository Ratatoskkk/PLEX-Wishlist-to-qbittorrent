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

    # Filter list for "The Best Show"
    the_best_show_names = [name for name in existing_qbt_names if "The Best Show" in name]
    # Filter list for "Another Show"
    another_show_names = [name for name in existing_qbt_names if "Another Show" in name]

    assert is_already_downloaded(the_best_show_names, 1, 1) == True
    assert is_already_downloaded(the_best_show_names, 1, 3) == False
    assert is_already_downloaded(another_show_names, 2, 5) == True
    assert is_already_downloaded(another_show_names, 2, 6) == False

    assert is_already_downloaded(the_best_show_names, 2) == True
    assert is_already_downloaded(the_best_show_names, 3) == False

test_is_already_downloaded()
print("Tests pass!")
