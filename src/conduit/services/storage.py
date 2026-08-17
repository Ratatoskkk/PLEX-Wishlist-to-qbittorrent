"""Disk-space awareness for download placement."""

from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from ..logs import get_logger

log = get_logger("storage")

GIB = 1024**3


@dataclass(slots=True)
class DriveInfo:
    path: str
    label: str
    exists: bool
    total_bytes: int = 0
    free_bytes: int = 0
    used_bytes: int = 0

    @property
    def percent_used(self) -> float:
        return (self.used_bytes / self.total_bytes * 100) if self.total_bytes else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "label": self.label,
            "exists": self.exists,
            "total_bytes": self.total_bytes,
            "free_bytes": self.free_bytes,
            "used_bytes": self.used_bytes,
            "percent_used": round(self.percent_used, 1),
        }


def _inspect(path: Path, index: int) -> DriveInfo:
    label = f"Drive {index + 1}"
    if not path.exists():
        return DriveInfo(path=str(path), label=label, exists=False)
    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        log.warning("could not stat drive", extra={"path": str(path), "err": str(exc)})
        return DriveInfo(path=str(path), label=label, exists=False)
    return DriveInfo(
        path=str(path),
        label=label,
        exists=True,
        total_bytes=usage.total,
        free_bytes=usage.free,
        used_bytes=usage.used,
    )


_cache: tuple[float, tuple[str, ...], list[DriveInfo]] | None = None
_CACHE_SECONDS = 20.0


async def survey(paths: list[Path], *, force: bool = False) -> list[DriveInfo]:
    """Stat every configured download root, off the event loop.

    Briefly cached: this sits on the dashboard's hot path, and ``disk_usage``
    on a nearly-full spinning disk can stall for a noticeable moment. Twenty
    seconds is far shorter than anything that meaningfully changes free space.
    """
    global _cache
    key = tuple(str(p) for p in paths)
    now = time.monotonic()
    if not force and _cache is not None:
        stamped, cached_key, drives = _cache
        if cached_key == key and now - stamped < _CACHE_SECONDS:
            return drives

    drives = await asyncio.to_thread(
        lambda: [_inspect(p, i) for i, p in enumerate(paths)]
    )
    _cache = (now, key, drives)
    return drives


def choose(
    drives: list[DriveInfo], needed_bytes: float, *, reserve_gb: float = 0.0,
    headroom_percent: float = 5.0,
) -> DriveInfo | None:
    """Pick the drive with the most room that can still take this download.

    ``reserve_gb`` is space we refuse to touch, so a drive never fills to the
    point where Plex cannot write its own metadata.
    """
    required = needed_bytes * (1 + headroom_percent / 100) + reserve_gb * GIB
    viable = [d for d in drives if d.exists and d.free_bytes >= required]
    if not viable:
        return None
    return max(viable, key=lambda d: d.free_bytes)


def format_shortfall(drives: list[DriveInfo], needed_bytes: float) -> str:
    best = max((d.free_bytes for d in drives if d.exists), default=0)
    return (
        f"needs {needed_bytes / GIB:.1f} GB, "
        f"most free on any drive is {best / GIB:.1f} GB"
    )
