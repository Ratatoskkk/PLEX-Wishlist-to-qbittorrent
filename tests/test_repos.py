"""Repository behaviour against a real SQLite database."""

from __future__ import annotations

from conduit.domain.models import DownloadState, LibraryItem, WantedState


async def seed_show(repos, title="Silo", tmdb_id="125988") -> int:
    return await repos.media.upsert(
        media_type="show", tmdb_id=tmdb_id, title=title, year=2023
    )


class TestMedia:
    async def test_upsert_is_idempotent_on_tmdb_id(self, repos) -> None:
        first = await seed_show(repos)
        second = await repos.media.upsert(
            media_type="show", tmdb_id="125988", title="Silo", year=2023
        )
        assert first == second
        assert len(await repos.media.list_all()) == 1

    async def test_movies_and_shows_can_share_a_tmdb_id(self, repos) -> None:
        show = await repos.media.upsert(media_type="show", tmdb_id="42", title="Thing")
        movie = await repos.media.upsert(media_type="movie", tmdb_id="42", title="Thing")
        assert show != movie

    async def test_ignoring_excludes_from_monitored(self, repos) -> None:
        media_id = await seed_show(repos)
        await repos.media.set_flags(media_id, ignored=True)
        assert await repos.media.list_all(monitored_only=True) == []
        assert await repos.media.ignored_tmdb_ids() == {"125988"}


class TestWanted:
    async def test_upsert_preserves_progress_already_made(self, repos) -> None:
        media_id = await seed_show(repos)
        wanted_id = await repos.wanted.upsert(media_id=media_id, season=1, episode=1)
        await repos.wanted.set_state(wanted_id, WantedState.GRABBED)

        again = await repos.wanted.upsert(media_id=media_id, season=1, episode=1)
        assert again == wanted_id
        assert (await repos.wanted.get(wanted_id))["state"] == WantedState.GRABBED

    async def test_upsert_revives_something_we_gave_up_on(self, repos) -> None:
        media_id = await seed_show(repos)
        wanted_id = await repos.wanted.upsert(media_id=media_id, season=1, episode=1)
        await repos.wanted.set_state(wanted_id, WantedState.UNAVAILABLE)
        await repos.wanted.upsert(
            media_id=media_id, season=1, episode=1, state=WantedState.SEARCHING
        )
        assert (await repos.wanted.get(wanted_id))["state"] == WantedState.SEARCHING

    async def test_upsert_revives_a_want_a_policy_stood_down(self, repos) -> None:
        """Widening the backlog policy must not be a one-way door."""
        media_id = await seed_show(repos)
        wanted_id = await repos.wanted.upsert(media_id=media_id, season=1, episode=1)
        await repos.wanted.retire(media_id, {(1, 1)}, reason="out of scope")
        assert (await repos.wanted.get(wanted_id))["state"] == WantedState.IGNORED

        await repos.wanted.upsert(
            media_id=media_id, season=1, episode=1, state=WantedState.SEARCHING
        )
        assert (await repos.wanted.get(wanted_id))["state"] == WantedState.SEARCHING

    async def test_marking_seen_survives_a_calendar_recompute(self, repos) -> None:
        """"I already watched this" must stick where a policy stand-down does not."""
        media_id = await seed_show(repos)
        seen = await repos.wanted.upsert(media_id=media_id, season=1, episode=1)
        stood_down = await repos.wanted.upsert(media_id=media_id, season=1, episode=2)

        await repos.wanted.mark_watched([seen])
        await repos.wanted.retire(media_id, {(1, 2)}, reason="out of scope")

        # A later recompute asks for both again.
        await repos.wanted.upsert(
            media_id=media_id, season=1, episode=1, state=WantedState.SEARCHING
        )
        await repos.wanted.upsert(
            media_id=media_id, season=1, episode=2, state=WantedState.SEARCHING
        )

        assert (await repos.wanted.get(seen))["state"] == WantedState.WATCHED
        assert (await repos.wanted.get(stood_down))["state"] == WantedState.SEARCHING

    async def test_files_appearing_in_plex_stand_the_want_down(self, repos) -> None:
        media_id = await seed_show(repos)
        arrived = await repos.wanted.upsert(media_id=media_id, season=1, episode=1)
        still_missing = await repos.wanted.upsert(media_id=media_id, season=1, episode=2)
        out_of_scope = await repos.wanted.upsert(media_id=media_id, season=1, episode=3)
        await repos.wanted.retire(media_id, {(1, 3)}, reason="out of scope")

        await repos.wanted.mark_present(media_id, {(1, 1), (1, 3)})

        assert (await repos.wanted.get(arrived))["state"] == WantedState.DOWNLOADED
        assert (await repos.wanted.get(still_missing))["state"] == WantedState.WAITING
        # A deliberate policy stand-down is not overwritten.
        assert (await repos.wanted.get(out_of_scope))["state"] == WantedState.IGNORED

    async def test_seen_episodes_are_never_searched_for(self, repos) -> None:
        media_id = await seed_show(repos)
        wanted_id = await repos.wanted.upsert(
            media_id=media_id, season=1, episode=1, state=WantedState.SEARCHING
        )
        assert len(await repos.wanted.due_for_search()) == 1
        await repos.wanted.mark_watched([wanted_id])
        assert await repos.wanted.due_for_search() == []
        assert await repos.wanted.upcoming() == []

    async def test_marking_seen_can_be_undone(self, repos) -> None:
        media_id = await seed_show(repos)
        wanted_id = await repos.wanted.upsert(media_id=media_id, season=1, episode=1)
        await repos.wanted.mark_watched([wanted_id])
        assert await repos.wanted.mark_watched([wanted_id], watched=False) == 1
        assert (await repos.wanted.get(wanted_id))["state"] == WantedState.SEARCHING

    async def test_seen_through_an_episode_covers_everything_before_it(self, repos) -> None:
        media_id = await seed_show(repos)
        ids = {
            episode: await repos.wanted.upsert(media_id=media_id, season=2, episode=episode)
            for episode in (1, 2, 3, 4)
        }
        later = await repos.wanted.upsert(media_id=media_id, season=3, episode=1)

        changed = await repos.wanted.mark_watched_for_media(media_id, season=2, up_to_episode=3)
        assert changed == 3
        for episode in (1, 2, 3):
            assert (await repos.wanted.get(ids[episode]))["state"] == WantedState.WATCHED
        assert (await repos.wanted.get(ids[4]))["state"] == WantedState.WAITING
        assert (await repos.wanted.get(later))["state"] == WantedState.WAITING

    async def test_seen_all_clears_every_outstanding_episode(self, repos) -> None:
        media_id = await seed_show(repos)
        for season in (1, 2):
            for episode in (1, 2):
                await repos.wanted.upsert(media_id=media_id, season=season, episode=episode)
        grabbed = await repos.wanted.upsert(media_id=media_id, season=3, episode=1)
        await repos.wanted.set_state(grabbed, WantedState.GRABBED)

        assert await repos.wanted.mark_watched_for_media(media_id) == 4
        # Something already on its way is left alone.
        assert (await repos.wanted.get(grabbed))["state"] == WantedState.GRABBED

    async def test_promote_due_moves_aired_items_to_searching(self, repos) -> None:
        media_id = await seed_show(repos)
        await repos.wanted.upsert(media_id=media_id, season=1, episode=1, air_date="2020-01-01")
        await repos.wanted.upsert(media_id=media_id, season=9, episode=1, air_date="2999-01-01")
        assert await repos.wanted.promote_due("2024-01-01") == 1
        states = {r["season"]: r["state"] for r in await repos.wanted.for_media(media_id)}
        assert states[1] == WantedState.SEARCHING
        assert states[9] == WantedState.WAITING

    async def test_never_searched_items_are_not_expired(self, repos) -> None:
        """A newly followed series' back catalogue must get a chance first."""
        media_id = await seed_show(repos)
        wanted_id = await repos.wanted.upsert(
            media_id=media_id, season=1, episode=1, air_date="1999-01-10",
            state=WantedState.SEARCHING,
        )
        assert await repos.wanted.expire_stale(tv_days=45, movie_days=180) == 0
        assert (await repos.wanted.get(wanted_id))["state"] == WantedState.SEARCHING

    async def test_expires_after_enough_failed_attempts(self, repos) -> None:
        media_id = await seed_show(repos)
        wanted_id = await repos.wanted.upsert(
            media_id=media_id, season=1, episode=1, air_date="1999-01-10",
            state=WantedState.SEARCHING,
        )
        for _ in range(3):
            await repos.wanted.set_state(
                wanted_id, WantedState.SEARCHING, reason="nothing", bump_attempt=True
            )
        assert await repos.wanted.expire_stale(45, 180, max_attempts=3) == 1
        assert (await repos.wanted.get(wanted_id))["state"] == WantedState.UNAVAILABLE

    async def test_upcoming_puts_future_releases_first(self, repos) -> None:
        media_id = await seed_show(repos)
        await repos.wanted.upsert(media_id=media_id, season=1, episode=1, air_date="1999-01-10")
        await repos.wanted.upsert(media_id=media_id, season=9, episode=1, air_date="2999-01-01")
        rows = await repos.wanted.upcoming()
        assert rows[0]["air_date"] == "2999-01-01"

    async def test_retire_stands_down_wants_that_are_no_longer_wanted(self, repos) -> None:
        media_id = await seed_show(repos)
        keep = await repos.wanted.upsert(media_id=media_id, season=3, episode=1)
        drop = await repos.wanted.upsert(media_id=media_id, season=1, episode=1)
        done = await repos.wanted.upsert(media_id=media_id, season=2, episode=1)
        await repos.wanted.set_state(done, WantedState.DOWNLOADED)

        await repos.wanted.retire(media_id, {(1, 1), (2, 1)}, reason="already watched")

        assert (await repos.wanted.get(drop))["state"] == WantedState.IGNORED
        assert (await repos.wanted.get(keep))["state"] == WantedState.WAITING
        # A terminal state is never walked back.
        assert (await repos.wanted.get(done))["state"] == WantedState.DOWNLOADED

    async def test_clearing_the_ignore_list_restores_titles_and_wants(self, repos) -> None:
        media_id = await seed_show(repos)
        wanted_id = await repos.wanted.upsert(media_id=media_id, season=1, episode=1)
        await repos.media.set_flags(media_id, ignored=True)
        await repos.wanted.retire(media_id, {(1, 1)}, reason="assumed watched")

        assert await repos.media.clear_ignored() == 1
        assert await repos.wanted.clear_ignored() == 1
        assert (await repos.media.get(media_id))["ignored"] == 0
        assert (await repos.wanted.get(wanted_id))["state"] == WantedState.SEARCHING

    async def test_mark_covered_settles_a_whole_season(self, repos) -> None:
        media_id = await seed_show(repos)
        for episode in range(1, 4):
            await repos.wanted.upsert(media_id=media_id, season=2, episode=episode)
        await repos.wanted.mark_covered(media_id, 2, None)
        assert all(
            r["state"] == WantedState.GRABBED
            for r in await repos.wanted.for_media(media_id)
        )


class TestDownloads:
    async def test_release_keys_cover_downloads_and_blocklist(self, repos) -> None:
        media_id = await seed_show(repos)
        await repos.downloads.create(
            media_id=media_id, display_title="Silo (Season 1)", indexer="Aither",
            indexer_id="123", size_bytes=1,
        )
        await repos.blocklist.add("Aither", "999", reason="denied")
        assert await repos.downloads.known_release_keys() == {("Aither", "123"), ("Aither", "999")}

    async def test_approval_only_applies_to_pending_rows(self, repos) -> None:
        media_id = await seed_show(repos)
        pending = await repos.downloads.create(
            media_id=media_id, display_title="A", indexer="T", indexer_id="1", size_bytes=1
        )
        already = await repos.downloads.create(
            media_id=media_id, display_title="B", indexer="T", indexer_id="2", size_bytes=1,
            state=DownloadState.COMPLETED,
        )
        assert await repos.downloads.approve_many([pending, already]) == 1
        assert (await repos.downloads.get(pending))["state"] == DownloadState.QUEUED
        assert (await repos.downloads.get(already))["state"] == DownloadState.COMPLETED

    async def test_completion_stamps_progress_and_time(self, repos) -> None:
        media_id = await seed_show(repos)
        download_id = await repos.downloads.create(
            media_id=media_id, display_title="A", indexer="T", indexer_id="1", size_bytes=1
        )
        await repos.downloads.set_state(download_id, DownloadState.COMPLETED)
        row = await repos.downloads.get(download_id)
        assert row["progress"] == 1.0
        assert row["completed_at"] is not None

    async def test_hash_lookup_is_exact(self, repos) -> None:
        media_id = await seed_show(repos)
        download_id = await repos.downloads.create(
            media_id=media_id, display_title="A", indexer="T", indexer_id="1", size_bytes=1
        )
        await repos.downloads.set_hash(download_id, "ABCDEF0123")
        found = await repos.downloads.by_hash("abcdef0123")
        assert found and found["id"] == download_id

    async def test_duplicate_release_is_rejected_by_the_index(self, repos) -> None:
        import sqlite3

        import pytest

        media_id = await seed_show(repos)
        await repos.downloads.create(
            media_id=media_id, display_title="A", indexer="T", indexer_id="1", size_bytes=1
        )
        with pytest.raises(sqlite3.IntegrityError):
            await repos.downloads.create(
                media_id=media_id, display_title="A again", indexer="T", indexer_id="1",
                size_bytes=1,
            )


class TestLibrary:
    async def test_index_replacement_is_all_or_nothing(self, repos) -> None:
        await repos.library.replace_all([
            LibraryItem(kind="episode", rating_key="1", show_tmdb_id="125988",
                        season=1, episode=1, watched=True),
            LibraryItem(kind="episode", rating_key="2", show_tmdb_id="125988",
                        season=1, episode=2),
            LibraryItem(kind="movie", rating_key="3", tmdb_id="27205", watched=True),
        ])
        assert await repos.library.have_episodes("125988") == {(1, 1), (1, 2)}
        assert await repos.library.watched_episodes("125988") == {(1, 1)}
        assert await repos.library.movie_watched_map() == {"27205": True}

        await repos.library.replace_all([
            LibraryItem(kind="episode", rating_key="9", show_tmdb_id="125988",
                        season=2, episode=1),
        ])
        assert await repos.library.have_episodes("125988") == {(2, 1)}

    async def test_watched_shows_are_discoverable(self, repos) -> None:
        await repos.library.replace_all([
            LibraryItem(kind="episode", rating_key="1", show_tmdb_id="a",
                        season=1, episode=1, watched=True),
            LibraryItem(kind="episode", rating_key="2", show_tmdb_id="b", season=1, episode=1),
        ])
        assert await repos.library.watched_show_tmdb_ids() == {"a"}


class TestCacheAndEvents:
    async def test_cache_survives_within_its_ttl(self, repos) -> None:
        await repos.cache.set("k", {"v": 1}, 60)
        assert await repos.cache.get("k") == {"v": 1}

    async def test_expired_entries_are_invisible_and_purgeable(self, repos) -> None:
        await repos.cache.set("k", {"v": 1}, -10)
        assert await repos.cache.get("k") is None
        assert await repos.cache.purge_expired() == 1

    async def test_events_deserialise_their_payload(self, repos) -> None:
        await repos.events.add("grab", "Found something", data={"score": 1500})
        recent = await repos.events.recent()
        assert recent[0]["data"] == {"score": 1500}

    async def test_task_health_is_recorded(self, repos) -> None:
        await repos.tasks.start("search")
        await repos.tasks.finish("search", 1.5, error="boom")
        row = (await repos.tasks.all())[0]
        assert row["error_count"] == 1
        assert row["last_error"] == "boom"
