"""Logging: console, rotating JSON-lines file, and an in-memory ring buffer.

The ring buffer is what makes the dashboard's Activity view possible without
tailing files from the browser -- the last N records stay in RAM and are served
straight out of the API, so diagnosing "why did nothing get grabbed?" never
requires opening a terminal.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import threading
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import LOG_DIR

_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "taskName"}


class RingBufferHandler(logging.Handler):
    """Keeps the most recent records in memory for the dashboard."""

    def __init__(self, capacity: int = 1000) -> None:
        super().__init__()
        self._records: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = _record_to_dict(record)
        except Exception:
            return
        with self._lock:
            self._seq += 1
            entry["seq"] = self._seq
            self._records.append(entry)

    def snapshot(
        self, limit: int = 200, level: str | None = None, since_seq: int = 0
    ) -> list[dict[str, Any]]:
        min_level = logging.getLevelName(level.upper()) if level else 0
        if not isinstance(min_level, int):
            min_level = 0
        with self._lock:
            items = list(self._records)
        out = [
            e
            for e in items
            if e["seq"] > since_seq and e["levelno"] >= min_level
        ]
        return out[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


def _record_to_dict(record: logging.LogRecord) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
        "level": record.levelname,
        "levelno": record.levelno,
        "logger": record.name,
        "message": record.getMessage(),
    }
    extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED}
    if extras:
        entry["context"] = {k: _safe(v) for k, v in extras.items()}
    if record.exc_info:
        entry["error"] = logging.Formatter().formatException(record.exc_info)
    return entry


def _safe(value: Any) -> Any:
    if isinstance(value, str | int | float | bool | type(None)):
        return value
    return str(value)


class JsonLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(_record_to_dict(record), ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Compact, aligned, and readable at a glance."""

    COLOURS = {
        "DEBUG": "\033[38;5;244m",
        "INFO": "\033[38;5;39m",
        "WARNING": "\033[38;5;214m",
        "ERROR": "\033[38;5;203m",
        "CRITICAL": "\033[48;5;203;38;5;231m",
    }
    RESET = "\033[0m"

    def __init__(self, colour: bool = True) -> None:
        super().__init__()
        self.colour = colour

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        name = record.name.removeprefix("conduit.")
        level = record.levelname[:4]
        if self.colour:
            level = f"{self.COLOURS.get(record.levelname, '')}{level}{self.RESET}"
        line = f"{ts} {level} {name:<18} {record.getMessage()}"
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED}
        if extras:
            line += "  " + " ".join(f"{k}={_safe(v)}" for k, v in extras.items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


ring_buffer = RingBufferHandler()


def configure(level: str = "INFO", log_dir: Path = LOG_DIR, colour: bool | None = None) -> None:
    """Install handlers on the root logger. Safe to call more than once."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    numeric = getattr(logging, level.upper(), logging.INFO)

    if colour is None:
        colour = sys.stderr is not None and getattr(sys.stderr, "isatty", lambda: False)()

    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(numeric)
        console.setFormatter(ConsoleFormatter(colour=bool(colour)))
        root.addHandler(console)

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "conduit.jsonl",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JsonLinesFormatter())
        root.addHandler(file_handler)
    except OSError:
        pass  # read-only install; console + ring buffer still work

    ring_buffer.setLevel(logging.DEBUG)
    root.addHandler(ring_buffer)

    for noisy in (
        "httpx", "httpcore", "aiosqlite", "uvicorn.access", "watchfiles",
        "asyncio", "multipart", "python_multipart", "PIL",
        # uvicorn logs every WebSocket connect/disconnect at INFO through its
        # "error" logger. With a dashboard open that is a line every reconnect,
        # and it reads like a fault when it is completely routine.
        "uvicorn.error", "uvicorn",
        "websockets.server", "websockets.protocol",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class SafeExtraLogger(logging.LoggerAdapter):
    """Lets callers pass any key in ``extra`` without exploding.

    ``logging`` raises if an extra shadows a built-in ``LogRecord`` attribute
    (``name``, ``module``, ``args`` ...). Structured context should never be a
    minefield of reserved words, so collisions are renamed instead.
    """

    def process(self, msg: Any, kwargs: Any) -> tuple[Any, Any]:
        extra = kwargs.get("extra")
        if extra:
            kwargs["extra"] = {
                (f"{k}_" if k in _RESERVED else k): v for k, v in extra.items()
            }
        return msg, kwargs


def get_logger(name: str) -> SafeExtraLogger:
    return SafeExtraLogger(logging.getLogger(f"conduit.{name}"), {})
