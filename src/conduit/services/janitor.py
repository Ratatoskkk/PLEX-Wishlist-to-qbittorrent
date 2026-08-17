"""Housekeeping: watched detection, reclaiming space, keeping the DB tidy."""

from __future__ import annotations

import contextlib
from typing import Any

from ..domain.models import DownloadState, EventLevel
from ..logs import get_logger
from ..util.text import human_duration, human_size
from .context import Conduit

log = get_logger("janitor")


async def sync_watched_flags(ctx: Conduit) -> dict[str, int]:
    """Mark completed downloads whose content the user has now watched.

    Derived entirely from the library index, so it costs one SQL pass instead
    of the reference project's per-title Plex search.
    """
    completed = await ctx.repos.downloads.completed()
    if not completed:
        return {"checked": 0, "watched": 0}

    movie_watched = await ctx.repos.library.movie_watched_map()
    # Both caches are per-show, not per-row: a ten-episode series otherwise
    # asked the same two questions ten times.
    show_cache: dict[str, set[tuple[int, int]]] = {}
    have_cache: dict[str, set[tuple[int, int]]] = {}
    updates: list[tuple[int, int]] = []

    for row in completed:
        tmdb_id = str(row.get("tmdb_id") or "")
        media_type = row.get("media_type") or "movie"
        watched = False

        if media_type == "movie":
            watched = movie_watched.get(tmdb_id, False)
        elif tmdb_id:
            if tmdb_id not in show_cache:
                show_cache[tmdb_id] = await ctx.repos.library.watched_episodes(tmdb_id)
            seen = show_cache[tmdb_id]
            season = row.get("season")
            if season is not None:
                if row.get("is_season_pack"):
                    if tmdb_id not in have_cache:
                        have_cache[tmdb_id] = await ctx.repos.library.have_episodes(tmdb_id)
                    season_keys = {k for k in have_cache[tmdb_id] if k[0] == int(season)}
                    watched = bool(season_keys) and season_keys <= seen
                else:
                    start = row.get("episode_from")
                    end = row.get("episode_to") or start
                    if start is not None:
                        span = {(int(season), e) for e in range(int(start), int(end) + 1)}
                        watched = bool(span) and span <= seen

        if bool(row.get("watched")) != watched:
            updates.append((int(watched), int(row["id"])))

    if updates:
        await ctx.repos.downloads.set_watched_bulk(updates)
        ctx.bus.publish("cleanup.updated", changed=len(updates))

    total_watched = sum(1 for u in updates if u[0] == 1)
    log.debug(
        "watched flags synced",
        extra={"checked": len(completed), "changed": len(updates)},
    )
    return {"checked": len(completed), "changed": len(updates), "watched": total_watched}


async def cleanup_candidates(ctx: Conduit) -> list[dict[str, Any]]:
    """Watched downloads, annotated with how far through seeding they are.

    Deleting a torrent before the tracker's seed requirement is met earns a
    hit-and-run, so every candidate carries its live seeding time and whether
    the goal has been reached. Nothing is hidden -- items still seeding are
    listed with a countdown so you can see what is coming.
    """
    policy = ctx.config.policy
    rows = await ctx.repos.downloads.completed(watched_only=True)
    if not rows:
        return []

    live: dict[str, Any] = {}
    if ctx.qbt is not None:
        try:
            live = {t.info_hash: t for t in await ctx.qbt.torrents() if t.info_hash}
        except Exception as exc:
            log.warning("could not read seeding state", extra={"err": str(exc)})

    required = policy.min_seed_days * 86400
    out: list[dict[str, Any]] = []

    for row in rows:
        torrent = live.get((row.get("info_hash") or "").lower())
        seeded = float(torrent.seeding_time) if torrent else 0.0
        ratio = float(torrent.ratio) if torrent else 0.0

        # Gone from the client entirely: nothing left to seed, so nothing to wait for.
        orphaned = torrent is None
        by_time = seeded >= required
        by_ratio = policy.min_seed_ratio > 0 and ratio >= policy.min_seed_ratio
        satisfied = orphaned or by_time or by_ratio

        out.append(
            {
                **row,
                "drive_label": _drive_label(ctx, row.get("save_path") or ""),
                "human_size": human_size(float(row.get("size_bytes") or 0)),
                "seeding_seconds": int(seeded),
                "seeding_human": human_duration(seeded) if torrent else "not in client",
                "seed_ratio": round(ratio, 2),
                "seed_required_seconds": int(required),
                "seed_remaining_seconds": max(0, int(required - seeded)) if torrent else 0,
                "seed_progress": min(1.0, seeded / required) if required > 0 else 1.0,
                "seed_satisfied": satisfied,
                "seed_reason": (
                    "no longer in qBittorrent" if orphaned
                    else "seed time met" if by_time
                    else f"ratio {ratio:.2f} met" if by_ratio
                    else f"{human_duration(required - seeded)} of seeding left"
                ),
                "in_client": torrent is not None,
            }
        )

    # Ready to reclaim first, then whatever frees the most space soonest.
    out.sort(key=lambda r: (not r["seed_satisfied"], -float(r.get("size_bytes") or 0)))
    return out


async def remove_download(
    ctx: Conduit, download_id: int, *, delete_files: bool = True,
    respect_seed_goal: bool = False,
) -> dict[str, Any]:
    """Remove a download from the client (optionally with its files) and archive it.

    ``respect_seed_goal`` refuses the delete while the tracker's seeding
    requirement is unmet. The reclaim UI sets it; an explicit removal from the
    queue does not, because that is a deliberate act on something you chose.
    """
    row = await ctx.repos.downloads.get(download_id)
    if not row:
        return {"ok": False, "error": "not found"}

    removed = False
    info_hash = (row.get("info_hash") or "").lower()

    if respect_seed_goal and not ctx.config.policy.allow_delete_before_seed_goal:
        blocker = await _seed_blocker(ctx, info_hash)
        if blocker:
            return {"ok": False, "error": blocker, "seed_blocked": True}

    if ctx.qbt is not None:
        hashes = [info_hash] if info_hash else []
        if not hashes:
            prefix = f"{ctx.config.policy.torrent_tag_prefix}_{download_id}"
            hashes = [
                t.info_hash
                for t in await ctx.qbt.torrents()
                if prefix in t.tags
            ]
        if hashes:
            await ctx.qbt.delete(hashes, delete_files=delete_files)
            removed = True

    await ctx.repos.downloads.archive(download_id)
    await ctx.record(
        "cleanup",
        f"Removed {row['display_title']}"
        + (" and its files" if delete_files and removed else ""),
        level=EventLevel.INFO,
        media_id=row.get("media_id"),
        download_id=download_id,
        data={"freed_bytes": float(row.get("size_bytes") or 0) if delete_files else 0},
    )
    ctx.bus.publish("cleanup.removed", download_id=download_id)
    return {"ok": True, "client_removed": removed}


async def _seed_blocker(ctx: Conduit, info_hash: str) -> str | None:
    """Reason this torrent must not be deleted yet, or None if it is free to go."""
    if not info_hash or ctx.qbt is None:
        return None
    policy = ctx.config.policy
    try:
        torrents = await ctx.qbt.torrents_by_hash([info_hash])
    except Exception as exc:
        # If the client genuinely cannot be reached, do not stand in the
        # user's way -- but say so loudly, because a swallowed error here
        # silently disables the hit-and-run guard.
        log.warning(
            "could not verify seeding state; allowing the delete",
            extra={"info_hash": info_hash, "err": f"{type(exc).__name__}: {exc}"},
        )
        return None
    torrent = torrents.get(info_hash)
    if torrent is None:
        return None  # already gone from the client

    required = policy.min_seed_days * 86400
    if torrent.seeding_time >= required:
        return None
    if policy.min_seed_ratio > 0 and torrent.ratio >= policy.min_seed_ratio:
        return None
    remaining = human_duration(required - torrent.seeding_time)
    return (
        f"Still seeding: {remaining} short of the {policy.min_seed_days:g}-day "
        f"requirement. Deleting now risks a hit-and-run."
    )


async def retire_superseded_episodes(
    ctx: Conduit, media_id: int, season: int, keep_download_id: int
) -> int:
    """A season pack landed -- drop the individual episodes it replaces.

    Only Conduit's own grabs for that season are touched, identified by
    database rows rather than by regex-matching names in the download client.
    """
    rows = await ctx.repos.downloads.list_by_state(
        DownloadState.DOWNLOADING, DownloadState.QUEUED,
        DownloadState.PENDING_APPROVAL, DownloadState.NO_SPACE,
        DownloadState.COMPLETED,
    )
    victims = [
        row
        for row in rows
        if int(row["id"]) != keep_download_id
        and row.get("media_id") == media_id
        and row.get("season") == season
        and not row.get("is_season_pack")
    ]
    if not victims:
        return 0

    for row in victims:
        await remove_download(ctx, int(row["id"]), delete_files=True)

    await ctx.record(
        "cleanup",
        f"Season {season} pack replaced {len(victims)} individual episode download(s)",
        media_id=media_id,
        download_id=keep_download_id,
    )
    log.info("superseded episodes retired", extra={"count": len(victims), "season": season})
    return len(victims)


async def housekeeping(ctx: Conduit) -> dict[str, int]:
    """Periodic tidy-up of caches, events and the database file."""
    purged = await ctx.repos.cache.purge_expired()
    pruned = await ctx.repos.events.prune(keep=5000)
    if pruned:
        with contextlib.suppress(Exception):
            await ctx.db.vacuum()
    log.debug("housekeeping done", extra={"cache_purged": purged, "events_pruned": pruned})
    return {"cache_purged": purged, "events_pruned": pruned}


def _drive_label(ctx: Conduit, save_path: str) -> str:
    if not save_path:
        return "Unknown"
    normalised = save_path.rstrip("/\\").lower()
    for index, path in enumerate(ctx.settings.download_dirs):
        if normalised.startswith(str(path).rstrip("/\\").lower()):
            return f"Drive {index + 1}"
    return "Unknown"
