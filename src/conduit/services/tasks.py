"""The background task roster.

Each entry names one job, points at its coroutine, and reads its interval from
live config -- so retuning cadence is a config edit, never a redeploy.
"""

from __future__ import annotations

from . import calendar, janitor, library, monitor, queue, search, watchlist
from .context import Conduit
from .supervisor import TaskSpec


async def _config_watch(ctx: Conduit) -> None:
    """Cheap tick that picks up edits to conduit.toml."""
    ctx.refresh_config()


def build_tasks() -> list[TaskSpec]:
    return [
        TaskSpec(
            name="config-watch",
            description="Reload conduit.toml when it changes on disk",
            run=_config_watch,
            interval=lambda ctx: 15,
            jitter=0.0,
            start_delay=5.0,
        ),
        TaskSpec(
            name="library-index",
            description="Mirror the Plex library (what you have, what you've watched)",
            run=lambda ctx: library.index_library(ctx),
            interval=lambda ctx: ctx.config.intervals.library_index,
            start_delay=1.0,
        ),
        TaskSpec(
            name="watchlist-sync",
            description="Read the Plex watchlist and turn it into monitored titles",
            run=lambda ctx: watchlist.sync_watchlist(ctx),
            interval=lambda ctx: ctx.config.intervals.watchlist_sync,
            start_delay=6.0,
        ),
        TaskSpec(
            name="follow-watched",
            description="Start following series you are actively watching",
            run=lambda ctx: library.track_watched_shows(ctx),
            interval=lambda ctx: ctx.config.intervals.watched_scan,
            start_delay=20.0,
        ),
        TaskSpec(
            name="calendar",
            description="Refresh air dates and work out what is still missing",
            run=lambda ctx: calendar.refresh_calendar(ctx),
            interval=lambda ctx: ctx.config.intervals.calendar_refresh,
            start_delay=25.0,
        ),
        TaskSpec(
            name="search-fresh",
            description="Aggressively chase recently aired episodes",
            run=lambda ctx: search.run_search(ctx, fresh_only=True, limit=40),
            interval=lambda ctx: ctx.config.intervals.fresh_release_poll,
            start_delay=40.0,
        ),
        TaskSpec(
            name="search-full",
            description="Search trackers for everything else that is due",
            run=lambda ctx: search.run_search(ctx, fresh_only=False),
            interval=lambda ctx: ctx.config.intervals.release_poll,
            start_delay=60.0,
        ),
        TaskSpec(
            name="queue-dispatch",
            description="Send approved grabs to qBittorrent on the roomiest drive",
            run=lambda ctx: queue.dispatch_queue(ctx),
            interval=lambda ctx: ctx.config.intervals.queue_dispatch,
            start_delay=15.0,
        ),
        TaskSpec(
            name="download-monitor",
            description="Track progress, completion and failures in the client",
            run=lambda ctx: monitor.monitor_downloads(ctx),
            interval=lambda ctx: ctx.config.intervals.download_monitor,
            jitter=0.05,
            start_delay=10.0,
        ),
        TaskSpec(
            name="watched-sync",
            description="Flag finished downloads you have already watched",
            run=lambda ctx: janitor.sync_watched_flags(ctx),
            interval=lambda ctx: ctx.config.intervals.watched_scan,
            start_delay=45.0,
        ),
        TaskSpec(
            name="housekeeping",
            description="Prune old events and expired caches",
            run=lambda ctx: janitor.housekeeping(ctx),
            interval=lambda ctx: ctx.config.intervals.housekeeping,
            run_at_start=False,
        ),
    ]
