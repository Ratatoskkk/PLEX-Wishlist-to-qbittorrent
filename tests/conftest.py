"""Shared fixtures.

Everything here builds against real objects with fake *edges* -- a real
database on a temp file, real repositories, real scoring, but stub clients.
That keeps the tests honest about SQL and business rules while staying fast.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from conduit.config import AppConfig, ConfigStore, Settings, default_config  # noqa: E402
from conduit.db.database import Database  # noqa: E402
from conduit.db.repo import Repos  # noqa: E402
from conduit.domain.models import Release  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite hermetic.

    Tracker API keys are looked up by name, falling back to the project's real
    ``.env``. Without this a test run on a configured machine would build live
    indexer clients and genuinely dial the tracker -- slow, flaky, and it would
    spend the developer's API budget.
    """
    from conduit import config as config_module

    monkeypatch.setattr(config_module, "_env_file_values", lambda *a, **k: {})


@pytest.fixture
def config() -> AppConfig:
    return default_config()


@pytest.fixture
def profile(config: AppConfig):
    return config.profile("uhd-remux")


@pytest.fixture
def policy(config: AppConfig):
    return config.policy


@pytest.fixture
async def db(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
async def repos(db: Database) -> Repos:
    return Repos(db)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        plex_url="http://plex.test:32400",
        plex_token="token",
        tmdb_api_key="tmdb",
        qbittorrent_url="http://qbt.test:8080",
        qbittorrent_username="user",
        qbittorrent_password="pass",
        DOWNLOAD_DIRS=str(tmp_path / "downloads"),
        conduit_auth_mode="none",
        database_path=tmp_path / "conduit.db",
    )


@pytest.fixture
def config_store(tmp_path: Path) -> ConfigStore:
    return ConfigStore(tmp_path / "conduit.toml")


def make_release(name: str, **overrides: Any) -> Release:
    """Build a plausible indexer result; override only what a test cares about."""
    defaults: dict[str, Any] = {
        "indexer": "Test",
        "indexer_id": str(abs(hash(name)) % 10**6),
        "name": name,
        "size_bytes": 40 * 1024**3,
        "download_url": f"https://tracker.test/download/{abs(hash(name)) % 10**6}",
        "seeders": 25,
        "leechers": 1,
    }
    defaults.update(overrides)
    return Release(**defaults)
