import pytest
from scheduler import is_already_downloaded

def test_exact_episode_match():
    # Test 1: Exact episode match
    assert is_already_downloaded(["Show A S01E05", "Other Show S01E05"], 1, 5) == True

def test_different_episode_same_show():
    # Test 2: Different episode of the same show
    assert is_already_downloaded(["Show A S01E04"], 1, 5) == False

def test_same_episode_different_show():
    # Test 3: Same episode of a different show
    # Assuming relevant_qbt_names already pre-filtered for "Show A" matching
    # In this new logic, the function only checks episode/season match.
    # It assumes the strings passed in ARE already relevant.
    # So if "Show B S01E05" is passed in relevant_qbt_names, it will match!
    # That is the new semantics of the refactored function.
    assert is_already_downloaded(["Show B S01E05"], 1, 5) == True

def test_season_pack_match():
    # Test 4: Season pack match (no e_num, existing torrent has "S01" but no "Exx")
    assert is_already_downloaded(["Show A S01 1080p"], 1) == True

def test_season_pack_requested_but_single_episode_exists():
    # Test 5: Season pack requested but only single episode exists
    assert is_already_downloaded(["Show A S01E05 1080p"], 1) == False

def test_episode_match_with_dots_spaces():
    # Test 9: Episode match with dots/spaces (S01.E05 or S01 E05)
    assert is_already_downloaded(["Show A S01.E05", "Show A S01 E05"], 1, 5) == True

def test_season_pack_with_multiple_existing():
    # Test 12: Season pack match with multiple torrents
    assert is_already_downloaded(["Other Show S01", "Show A S01"], 1) == True

def test_season_pack_wrong_season():
    # Test 13: Season pack match but wrong season
    assert is_already_downloaded(["Show A S02"], 1) == False

def test_empty_existing_torrents():
    # Test 14: Empty existing torrents list
    assert is_already_downloaded([], 1, 1) == False
    assert is_already_downloaded([], 1) == False

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
