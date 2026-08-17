"""Command line entry point.

``conduit run``    start the server (add ``--tray`` for a Windows tray icon)
``conduit check``  validate configuration and probe every upstream service
``conduit config`` print the effective behaviour configuration
"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
import threading
import webbrowser
from typing import Any

from . import __version__, logs
from .config import CONFIG_FILE, ConfigStore, get_settings, load_config

LOCK_PORT = 50051


def _acquire_single_instance_lock() -> socket.socket | None:
    """One Conduit per machine. Returns None if another is already running."""
    lock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        lock.close()
        return None
    return lock


# ---------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> int:
    import uvicorn

    settings = get_settings()
    logs.configure(args.log_level or settings.conduit_log_level)
    log = logs.get_logger("main")

    missing = settings.missing_required()
    if missing and not args.force:
        print("\n  ras cannot start -- these settings are empty in .env:\n")
        for name in missing:
            print(f"    - {name}")
        print(f"\n  Edit {os.path.abspath('.env')} and try again.")
        print("  (Run with --force to start anyway and fix it from the dashboard.)\n")
        return 1

    lock = None
    if not args.allow_multiple:
        lock = _acquire_single_instance_lock()
        if lock is None:
            print("ras is already running. Check your system tray.")
            return 0

    from .web.app import create_app

    app = create_app(settings=settings, config_store=ConfigStore(), run_tasks=not args.no_tasks)
    host = args.host or settings.conduit_host
    port = args.port or settings.conduit_port
    url = f"http://localhost:{port}"

    log.info("starting ras", extra={"version": __version__, "url": url})

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_config=None,
        access_log=False,
        ws_ping_interval=20,
        ws_ping_timeout=20,
        timeout_graceful_shutdown=10,
    )
    server = uvicorn.Server(config)

    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    if args.tray:
        return _run_with_tray(server, url)

    try:
        server.run()
    finally:
        if lock is not None:
            lock.close()
    return 0


def _run_with_tray(server: Any, url: str) -> int:
    """Run the server on a background thread behind a system-tray icon."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        print("Tray mode needs 'pystray' and 'pillow'. Falling back to console mode.")
        server.run()
        return 0

    thread = threading.Thread(target=server.run, name="conduit-server", daemon=True)
    thread.start()

    def make_icon() -> Any:
        """The rás mark: three streams merging into one channel."""
        cyan, blue = (34, 211, 238), (79, 140, 255)
        image = Image.new("RGB", (64, 64), (14, 16, 20))
        draw = ImageDraw.Draw(image)
        draw.line((12, 18, 34, 32), fill=cyan, width=5)
        draw.line((12, 46, 34, 32), fill=cyan, width=5)
        draw.line((12, 32, 40, 32), fill=blue, width=5)
        draw.ellipse((40, 26, 52, 38), fill=blue)
        return image

    def quit_app(icon: Any, _item: Any) -> None:
        server.should_exit = True
        icon.stop()

    icon = pystray.Icon(
        "ras",
        make_icon(),
        "rás",
        menu=pystray.Menu(
            pystray.MenuItem("Open dashboard", lambda: webbrowser.open(url), default=True),
            pystray.MenuItem("Quit", quit_app),
        ),
    )
    icon.run()
    server.should_exit = True
    thread.join(timeout=10)
    return 0


# ---------------------------------------------------------------------------
def cmd_check(args: argparse.Namespace) -> int:
    logs.configure(args.log_level or "INFO")
    return asyncio.run(_check())


async def _check() -> int:
    from .clients import PlexClient, QBittorrentClient, TmdbClient
    from .clients.indexers import SearchQuery, build_indexer

    settings = get_settings()
    config = load_config()
    problems = 0

    print(f"\nras {__version__} -- configuration check\n")

    missing = settings.missing_required()
    if missing:
        problems += 1
        print(f"  [FAIL] .env is incomplete: {', '.join(missing)}")
    else:
        print("  [ OK ] .env has every required value")

    print(f"  [INFO] config file: {CONFIG_FILE}")
    print(f"  [INFO] profiles: {', '.join(p.name for p in config.profiles)}")
    print(f"  [INFO] download roots: {', '.join(str(p) for p in settings.download_dirs)}")

    for path in settings.download_dirs:
        marker = " OK " if path.exists() else "WARN"
        print(f"  [{marker}] {path} {'exists' if path.exists() else 'is not reachable'}")

    plex = PlexClient(settings.plex_url, settings.plex_token)
    try:
        sections = await plex.sections()
        print(f"  [ OK ] Plex server: {len(sections)} librar{'y' if len(sections) == 1 else 'ies'}")
    except Exception as exc:
        problems += 1
        print(f"  [FAIL] Plex server: {exc}")
    try:
        entries = await plex.watchlist()
        print(f"  [ OK ] Plex watchlist: {len(entries)} item(s)")
    except Exception as exc:
        problems += 1
        print(f"  [FAIL] Plex watchlist: {exc}")
    await _check_matching(plex)
    await plex.aclose()

    tmdb = TmdbClient(settings.tmdb_api_key)
    try:
        show = await tmdb.show(1399)
        print(f"  [ OK ] TMDB: reachable ({(show or {}).get('name')})")
    except Exception as exc:
        problems += 1
        print(f"  [FAIL] TMDB: {exc}")
    await tmdb.aclose()

    qbt = QBittorrentClient(
        settings.qbittorrent_url, settings.qbittorrent_username, settings.qbittorrent_password
    )
    try:
        await qbt.login()
        torrents = await qbt.torrents()
        print(f"  [ OK ] qBittorrent {qbt.health()['version']}: {len(torrents)} torrent(s)")
    except Exception as exc:
        problems += 1
        print(f"  [FAIL] qBittorrent: {exc}")
    await qbt.aclose()

    for spec in config.enabled_indexers():
        key = settings.tracker_api_key(spec.api_key_env)
        if not key:
            problems += 1
            print(f"  [FAIL] {spec.name}: {spec.api_key_env} is not set in .env")
            continue
        indexer = build_indexer(spec, key)
        try:
            results = await indexer.search(SearchQuery(media_type="movie", tmdb_id="27205"))
            print(f"  [ OK ] {spec.name}: {len(results)} result(s) for a test query")
        except Exception as exc:
            problems += 1
            print(f"  [FAIL] {spec.name}: {exc}")
        await indexer.aclose()

    print()
    if problems:
        print(f"  {problems} problem(s) found.\n")
        return 1
    print("  Everything checks out.\n")
    return 0


async def _check_matching(plex: Any) -> None:
    """Report library entries Plex has not matched to a TMDB id.

    Not counted as a failure -- nothing is broken -- but it is the one thing
    de-duplication cannot see, so an unmatched entry means Conduit may pay to
    download something already sitting on the disk.
    """
    from .services.library import count_unmatched

    try:
        items = await plex.index_library()
    except Exception as exc:
        print(f"  [WARN] could not scan the library for unmatched entries: {exc}")
        return

    unmatched = count_unmatched(items)
    if not unmatched:
        print(f"  [ OK ] every one of {len(items)} library items has a TMDB match")
        return

    print(f"  [WARN] {unmatched} librar{'y entry has' if unmatched == 1 else 'y entries have'} "
          f"no TMDB match:")
    for item in items:
        if item.kind in ("movie", "show") and not item.tmdb_id:
            print(f"         - {item.kind}: {item.title}")
    print("         ras cannot tell you already own these, so it may fetch them")
    print("         again. Fix each one in Plex with Match, then re-index.")


def cmd_config(args: argparse.Namespace) -> int:
    import json

    logs.configure("WARNING")
    print(json.dumps(load_config().model_dump(mode="json"), indent=2))
    return 0


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conduit", description="ras media automation")
    parser.add_argument("--version", action="version", version=f"conduit {__version__}")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING, ERROR")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="start the server and background tasks")
    run.add_argument("--host", default=None)
    run.add_argument("--port", type=int, default=None)
    run.add_argument("--tray", action="store_true", help="show a Windows system-tray icon")
    run.add_argument("--open", action="store_true", help="open the dashboard in a browser")
    run.add_argument("--no-tasks", action="store_true", help="serve the UI without background jobs")
    run.add_argument("--allow-multiple", action="store_true", help="skip the single-instance lock")
    run.add_argument("--force", action="store_true", help="start even if .env is incomplete")
    run.set_defaults(func=cmd_run)

    check = sub.add_parser("check", help="validate configuration and connectivity")
    check.set_defaults(func=cmd_check)

    show = sub.add_parser("config", help="print the effective behaviour configuration")
    show.set_defaults(func=cmd_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args([*(argv or []), "run"])
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
