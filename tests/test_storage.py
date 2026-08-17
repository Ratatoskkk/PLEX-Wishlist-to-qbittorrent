"""Drive selection: deterministic, with no dependence on the host's real disks."""

from __future__ import annotations

from conduit.services.storage import DriveInfo, choose, format_shortfall

GIB = 1024**3


def drive(label: str, free_gb: float, total_gb: float = 1000, exists: bool = True) -> DriveInfo:
    return DriveInfo(
        path=f"X:\\{label}",
        label=label,
        exists=exists,
        total_bytes=int(total_gb * GIB),
        free_bytes=int(free_gb * GIB),
        used_bytes=int((total_gb - free_gb) * GIB),
    )


def test_picks_the_roomiest_drive_that_fits() -> None:
    drives = [drive("A", free_gb=200), drive("B", free_gb=500), drive("C", free_gb=50)]
    assert choose(drives, 40 * GIB, reserve_gb=0).label == "B"


def test_skips_drives_that_are_offline() -> None:
    drives = [drive("A", free_gb=900, exists=False), drive("B", free_gb=100)]
    assert choose(drives, 40 * GIB, reserve_gb=0).label == "B"


def test_returns_nothing_when_no_drive_can_take_it() -> None:
    assert choose([drive("A", free_gb=10)], 40 * GIB, reserve_gb=0) is None


def test_reserve_is_kept_untouched() -> None:
    """A drive with 30 GB free will not accept a 20 GB file behind a 20 GB reserve."""
    drives = [drive("A", free_gb=30)]
    assert choose(drives, 20 * GIB, reserve_gb=0) is not None
    assert choose(drives, 20 * GIB, reserve_gb=20) is None


def test_headroom_is_added_on_top_of_the_reported_size() -> None:
    drives = [drive("A", free_gb=101)]
    assert choose(drives, 100 * GIB, reserve_gb=0, headroom_percent=0) is not None
    assert choose(drives, 100 * GIB, reserve_gb=0, headroom_percent=5) is None


def test_shortfall_message_names_the_numbers() -> None:
    message = format_shortfall([drive("A", free_gb=12)], 40 * GIB)
    assert "40.0 GB" in message
    assert "12.0 GB" in message


def test_percent_used_is_reported_for_the_dashboard() -> None:
    info = drive("A", free_gb=100, total_gb=1000)
    assert round(info.percent_used) == 90
    assert info.as_dict()["label"] == "A"
