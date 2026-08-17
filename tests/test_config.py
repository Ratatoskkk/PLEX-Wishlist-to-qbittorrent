"""Configuration loading, validation and persistence."""

from __future__ import annotations

import tomllib

import pytest

from conduit.config import (
    AppConfig,
    ConfigStore,
    QualityProfile,
    ScoredTerm,
    Settings,
    default_config,
    load_config,
    save_config,
)


class TestDefaults:
    def test_ships_with_usable_profiles(self, config: AppConfig) -> None:
        names = {p.name for p in config.profiles}
        assert {"uhd-remux", "uhd-efficient", "hd-balanced"} <= names
        assert config.default_profile in names

    def test_media_type_profiles_resolve(self, config: AppConfig) -> None:
        assert config.profile_for("movie").name == config.movie_profile
        assert config.profile_for("show").name == config.tv_profile

    def test_an_unknown_profile_name_falls_back(self, config: AppConfig) -> None:
        assert config.profile("does-not-exist").name in {p.name for p in config.profiles}

    def test_indexers_are_ordered_by_priority(self) -> None:
        config = AppConfig.model_validate({
            "indexers": [
                {"name": "B", "base_url": "https://b", "api_key_env": "B", "priority": 2},
                {"name": "A", "base_url": "https://a", "api_key_env": "A", "priority": 1},
            ]
        })
        assert [i.name for i in config.enabled_indexers()] == ["A", "B"]

    def test_disabled_indexers_are_left_out(self) -> None:
        config = AppConfig.model_validate({
            "indexers": [
                {"name": "A", "base_url": "https://a", "api_key_env": "A", "enabled": False},
            ]
        })
        assert config.enabled_indexers() == []

    def test_a_config_with_no_profiles_gets_the_builtin_set(self) -> None:
        assert AppConfig().profiles


class TestPersistence:
    def test_writes_and_reads_back_identically(self, tmp_path) -> None:
        path = tmp_path / "conduit.toml"
        original = default_config()
        original.policy.max_active_downloads = 7
        save_config(original, path)
        assert AppConfig.model_validate(
            tomllib.loads(path.read_text(encoding="utf-8"))
        ).policy.max_active_downloads == 7

    def test_first_run_creates_the_file(self, tmp_path) -> None:
        path = tmp_path / "conduit.toml"
        assert not path.exists()
        load_config(path)
        assert path.exists()

    def test_the_store_notices_an_edit_on_disk(self, tmp_path) -> None:
        path = tmp_path / "conduit.toml"
        store = ConfigStore(path)
        assert store.refresh() is False

        updated = store.current.model_copy(deep=True)
        updated.policy.max_active_downloads = 3
        save_config(updated, path)
        # Force a different mtime on filesystems with coarse timestamps.
        import os
        import time

        os.utime(path, (time.time() + 1, time.time() + 1))

        assert store.refresh() is True
        assert store.current.policy.max_active_downloads == 3

    def test_a_broken_file_keeps_the_last_good_config(self, tmp_path) -> None:
        path = tmp_path / "conduit.toml"
        store = ConfigStore(path)
        before = store.current.policy.max_active_downloads
        path.write_text("this is not [ valid toml", encoding="utf-8")
        import os
        import time

        os.utime(path, (time.time() + 1, time.time() + 1))
        assert store.refresh() is False
        assert store.current.policy.max_active_downloads == before


class TestProfileRules:
    def test_lookup_is_case_insensitive(self) -> None:
        profile = QualityProfile(
            name="p", resolutions=[ScoredTerm(value="2160P", score=10)]
        )
        assert profile.lookup("resolutions", "2160p") == 10

    def test_zero_max_size_means_unlimited(self) -> None:
        assert QualityProfile(name="p").max_size_bytes == float("inf")

    def test_a_missing_attribute_returns_none_not_zero(self) -> None:
        """None and 0 mean different things: absent versus scored zero."""
        profile = QualityProfile(name="p", sources=[ScoredTerm(value="remux", score=0)])
        assert profile.lookup("sources", "remux") == 0
        assert profile.lookup("sources", "webdl") is None


class TestSettings:
    def test_download_dirs_split_on_commas(self, tmp_path) -> None:
        settings = Settings(DOWNLOAD_DIRS=f"{tmp_path}\\a, {tmp_path}\\b")
        assert len(settings.download_dirs) == 2

    def test_legacy_numbered_variables_still_work(self, monkeypatch, tmp_path) -> None:
        """An .env carried over from the old project must not break."""
        monkeypatch.setenv("DOWNLOAD_DIR_1", str(tmp_path / "one"))
        monkeypatch.setenv("DOWNLOAD_DIR_2", str(tmp_path / "two"))
        settings = Settings(DOWNLOAD_DIRS="")
        assert [p.name for p in settings.download_dirs] == ["one", "two"]

    def test_missing_required_names_what_is_absent(self, tmp_path) -> None:
        missing = Settings(
            plex_token="", tmdb_api_key="", qbittorrent_password="", DOWNLOAD_DIRS=""
        ).missing_required()
        assert {"PLEX_TOKEN", "TMDB_API_KEY", "QBITTORRENT_PASSWORD", "DOWNLOAD_DIRS"} <= set(missing)

    def test_token_mode_demands_a_token(self, tmp_path) -> None:
        settings = Settings(
            plex_token="t", tmdb_api_key="t", qbittorrent_password="p",
            DOWNLOAD_DIRS=str(tmp_path), conduit_auth_mode="token", conduit_api_token="",
        )
        assert "CONDUIT_API_TOKEN" in settings.missing_required()

    def test_tracker_keys_are_read_from_the_environment(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("SOME_TRACKER_KEY", "abc123")
        settings = Settings(DOWNLOAD_DIRS=str(tmp_path))
        assert settings.tracker_api_key("SOME_TRACKER_KEY") == "abc123"

    def test_an_unknown_tracker_key_is_empty_not_an_error(self, tmp_path) -> None:
        assert Settings(DOWNLOAD_DIRS=str(tmp_path)).tracker_api_key("NOPE_KEY") == ""


def test_indexer_base_url_loses_its_trailing_slash() -> None:
    from conduit.config import IndexerConfig

    indexer = IndexerConfig(name="X", base_url="https://x.test/", api_key_env="X")
    assert indexer.base_url == "https://x.test"


@pytest.mark.parametrize("mode", ["lan", "token", "both", "none"])
def test_all_auth_modes_are_accepted(mode, tmp_path) -> None:
    Settings(DOWNLOAD_DIRS=str(tmp_path), conduit_auth_mode=mode, conduit_api_token="x")
