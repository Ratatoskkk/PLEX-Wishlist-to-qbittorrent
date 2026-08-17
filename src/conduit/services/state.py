"""Builds the snapshot the dashboard renders.

One query pass produces everything the UI needs, so the front end never has to
stitch together four endpoints (and never has to poll -- the same shape is
pushed over the WebSocket when something changes).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..domain.models import DownloadState
from ..util.text import human_size
from . import storage
from .context import Conduit


async def build_state(ctx: Conduit) -> dict[str, Any]:
    repos = ctx.repos
    downloads = await repos.downloads.dashboard()
    pending = [d for d in downloads if d["state"] == DownloadState.PENDING_APPROVAL]
    upcoming = await repos.wanted.upcoming(limit=400)
    totals = await repos.downloads.totals()
    want_counts = await repos.wanted.counts_by_state()
    drives = await storage.survey(ctx.settings.download_dirs)
    unmatched = await repos.library.unmatched()
    season_progress = await repos.library.season_progress(
        {str(d["tmdb_id"]) for d in pending if d.get("tmdb_id")}
    )

    return {
        "summary": {
            "downloading": int(totals.get("downloading") or 0),
            "pending_approval": int(totals.get("pending") or 0),
            "queued": int(totals.get("queued") or 0),
            "completed": int(totals.get("completed") or 0),
            "failed": int(totals.get("failed") or 0),
            "no_space": int(totals.get("no_space") or 0),
            "library_bytes": float(totals.get("completed_bytes") or 0),
            "library_size": human_size(float(totals.get("completed_bytes") or 0)),
            "wanted": want_counts,
            "upcoming": len(upcoming),
            "indexers": len(ctx.indexers),
            "dry_run": ctx.config.policy.dry_run,
            "unmatched": len(unmatched),
        },
        "downloads": [_download(row) for row in downloads],
        "pending_groups": _group_pending(pending, season_progress),
        "upcoming": [_upcoming(row) for row in upcoming],
        "drives": [d.as_dict() for d in drives],
        # Plex entries with no TMDB id. De-duplication is keyed on that id, so
        # these are the titles Conduit cannot tell you already own.
        "unmatched": unmatched,
        "timestamps": {
            "watchlist_checked_at": await ctx.db.get_meta("watchlist_checked_at"),
            "library_indexed_at": await ctx.db.get_meta("library_indexed_at"),
            "calendar_refreshed_at": await ctx.db.get_meta("calendar_refreshed_at"),
            "started_at": ctx.started_at.isoformat(),
        },
        "profiles": [
            {"name": p.name, "description": p.description} for p in ctx.config.profiles
        ],
    }


def _download(row: dict[str, Any]) -> dict[str, Any]:
    size = float(row.get("size_bytes") or 0)
    return {
        "id": row["id"],
        "media_id": row.get("media_id"),
        "tmdb_id": row.get("tmdb_id"),
        "media_type": row.get("media_type"),
        "title": row["display_title"],
        "release_name": row.get("release_name"),
        "indexer": row.get("indexer"),
        "state": row["state"],
        "progress": float(row.get("progress") or 0),
        "eta_seconds": int(row.get("eta_seconds") or -1),
        "speed_bps": float(row.get("speed_bps") or 0),
        "size_bytes": size,
        "size": human_size(size),
        "resolution": row.get("resolution"),
        "source": row.get("source"),
        "dynamic_range": row.get("dynamic_range"),
        "audio": row.get("audio"),
        "video_codec": row.get("video_codec"),
        "release_group": row.get("release_group"),
        "score": row.get("score"),
        "seeders": row.get("seeders"),
        "season": row.get("season"),
        "episode_from": row.get("episode_from"),
        "episode_to": row.get("episode_to"),
        "is_season_pack": bool(row.get("is_season_pack")),
        "poster_path": row.get("poster_path"),
        "save_path": row.get("save_path"),
        "error": row.get("error"),
        "watched": bool(row.get("watched")),
        "created_at": row.get("created_at"),
        "completed_at": row.get("completed_at"),
    }


def _group_pending(
    rows: list[dict[str, Any]],
    season_progress: dict[str, dict[int, dict[str, int]]] | None = None,
) -> list[dict[str, Any]]:
    """Group approvals by title so a 5-season show is one card, not five."""
    groups: dict[Any, dict[str, Any]] = defaultdict(
        lambda: {"items": [], "total_bytes": 0.0}
    )
    for row in rows:
        # A download whose media row was deleted still has to group somewhere.
        key = row.get("media_id") or row["display_title"]
        group = groups[key]
        group["media_id"] = row.get("media_id")
        group["title"] = row.get("media_title") or row["display_title"]
        group["poster_path"] = row.get("poster_path")
        group["tmdb_id"] = row.get("tmdb_id")
        group["media_type"] = row.get("media_type")
        group["items"].append(_download(row))
        group["total_bytes"] += float(row.get("size_bytes") or 0)

    result = []
    for group in groups.values():
        group["total_size"] = human_size(group["total_bytes"])
        group["count"] = len(group["items"])
        group["ids"] = [item["id"] for item in group["items"]]
        _classify_pending(group, season_progress or {})
        result.append(group)
    # Continuations first: they are a "am I ready?" decision, which is quicker
    # to answer than "do I want this at all?".
    return sorted(
        result, key=lambda g: (g["kind"] != "continuation", -g["count"], g["title"])
    )


def _classify_pending(
    group: dict[str, Any], season_progress: dict[str, dict[int, dict[str, int]]]
) -> None:
    """Is this the next season of something already being watched, or new?

    Derived, not stored: if the library already holds an *earlier* season of
    the same show, this is a continuation -- a "ready when you are" gate rather
    than a "do I want this?" question. The two read very differently to whoever
    is looking at the card, so they are not shown in the same list.
    """
    group["kind"] = "new"
    seasons = season_progress.get(str(group.get("tmdb_id") or ""))
    if not seasons:
        return
    wanted = [i["season"] for i in group["items"] if i.get("season") is not None]
    if not wanted:
        return

    target = min(wanted)
    earlier = [s for s in seasons if s < target]
    if not earlier:
        return

    previous = max(earlier)
    stats = seasons[previous]
    episodes = stats["episodes"]
    group["kind"] = "continuation"
    group["target_season"] = target
    group["previous_season"] = {
        "season": previous,
        "episodes": episodes,
        "watched": stats["watched"],
        "progress": round(stats["watched"] / episodes, 4) if episodes else 0.0,
    }


def _upcoming(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "media_id": row["media_id"],
        "tmdb_id": row.get("tmdb_id"),
        "media_type": row.get("media_type"),
        "title": row.get("media_title") or "",
        "episode_title": row.get("title") or "",
        "season": row.get("season"),
        "episode": row.get("episode"),
        "air_date": row.get("air_date"),
        "state": row["state"],
        "reason": row.get("reason"),
        "search_attempts": row.get("search_attempts") or 0,
        "last_search_at": row.get("last_search_at"),
        "poster_path": row.get("poster_path"),
        "tmdb_status": row.get("tmdb_status"),
    }
