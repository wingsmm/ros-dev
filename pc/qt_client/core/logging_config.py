"""Unified logging for xtark Qt client (WSL/Ubuntu)."""

from __future__ import annotations

import logging
import os
import queue
import re
import sys
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path
from typing import Optional, Tuple

_LOG_FILENAME_RE = re.compile(r"^xtark-console-\d{4}-\d{2}-\d{2}\.log$")
_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_DEFAULT_LEVEL = "INFO"
_DEFAULT_RETENTION_DAYS = 30
_DEFAULT_LOG_DIR = "logs"
_DEFAULT_ODOM_LOG_INTERVAL_SEC = 1.0
_MIN_ODOM_LOG_INTERVAL_SEC = 0.1
_MAX_ODOM_LOG_INTERVAL_SEC = 60.0

_JSON_LINE_PREFIXES = (
    "CONNECT ",
    "DISCONNECT",
    "TX ",
    "RX ",
    "RX INVALID",
    "SEND ERR",
    "RECV ERR",
    "CONNECTION LOST",
)

_file_handler: Optional["DailyFileHandler"] = None
_queue_listener: Optional[QueueListener] = None
_setup_done = False


def qt_client_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def _env_value(key: str, env_file: dict[str, str]) -> str:
    if key in os.environ:
        return os.environ[key].strip()
    return env_file.get(key, "").strip()


def _parse_level(raw: str) -> str:
    level = (raw or _DEFAULT_LEVEL).upper()
    if level not in _VALID_LEVELS:
        return _DEFAULT_LEVEL
    return level


def _parse_retention_days(raw: str) -> int:
    if not raw:
        return _DEFAULT_RETENTION_DAYS
    try:
        days = int(raw)
    except ValueError:
        return _DEFAULT_RETENTION_DAYS
    if days < 1:
        return _DEFAULT_RETENTION_DAYS
    return days


def _parse_bool(raw: str, *, default: bool = False) -> bool:
    text = (raw or "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_odom_interval_sec(raw: str) -> float:
    if not raw:
        return _DEFAULT_ODOM_LOG_INTERVAL_SEC
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_ODOM_LOG_INTERVAL_SEC
    if value < _MIN_ODOM_LOG_INTERVAL_SEC:
        return _MIN_ODOM_LOG_INTERVAL_SEC
    if value > _MAX_ODOM_LOG_INTERVAL_SEC:
        return _MAX_ODOM_LOG_INTERVAL_SEC
    return value


def resolve_log_dir(raw_dir: str) -> Path:
    text = (raw_dir or _DEFAULT_LOG_DIR).strip() or _DEFAULT_LOG_DIR
    path = Path(text)
    if path.is_absolute():
        return path
    return qt_client_root() / path


@dataclass(frozen=True)
class LoggingSettings:
    log_dir: Path
    level: str
    retention_days: int
    odom_log_enabled: bool = False
    odom_log_interval_sec: float = _DEFAULT_ODOM_LOG_INTERVAL_SEC
    file_logging_enabled: bool = True


def load_logging_settings(
    *,
    env_path: Optional[Path] = None,
    env_overrides: Optional[dict[str, str]] = None,
) -> LoggingSettings:
    if env_path is None:
        env_path = qt_client_root() / ".env"
    env_file = _parse_env_file(env_path)
    if env_overrides:
        env_file = {**env_file, **env_overrides}

    log_dir = resolve_log_dir(_env_value("XTARK_LOG_DIR", env_file))
    level = _parse_level(_env_value("XTARK_LOG_LEVEL", env_file))
    retention_days = _parse_retention_days(
        _env_value("XTARK_LOG_RETENTION_DAYS", env_file)
    )
    odom_log_enabled = _parse_bool(
        _env_value("XTARK_LOG_ODOM", env_file),
        default=False,
    )
    odom_log_interval_sec = _parse_odom_interval_sec(
        _env_value("XTARK_LOG_ODOM_INTERVAL", env_file)
    )
    return LoggingSettings(
        log_dir=log_dir,
        level=level,
        retention_days=retention_days,
        odom_log_enabled=odom_log_enabled,
        odom_log_interval_sec=odom_log_interval_sec,
    )


class XtarkFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        ct = datetime.fromtimestamp(record.created)
        return ct.strftime("%Y-%m-%d %H:%M:%S") + f".{int(record.msecs):03d}"

    def format(self, record: logging.LogRecord) -> str:
        record.asctime = self.formatTime(record)
        level = record.levelname
        if len(level) < 8:
            level = level + " " * (8 - len(level))
        message = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            message = f"{message}\n{record.exc_text}"
        return (
            f"{record.asctime} {level} pid={record.process} "
            f"thread={record.threadName} {record.name}: {message}"
        )


class DailyFileHandler(logging.Handler):
    """Append to xtark-console-YYYY-MM-DD.log; rotate at local midnight."""

    def __init__(
        self,
        log_dir: Path,
        retention_days: int = _DEFAULT_RETENTION_DAYS,
        *,
        today: Optional[date] = None,
    ) -> None:
        super().__init__()
        self._log_dir = log_dir
        self._retention_days = retention_days
        self._lock = threading.RLock()
        self._today_override = today
        self._current_date: Optional[date] = None
        self._stream = None

    def _today(self) -> date:
        return self._today_override or date.today()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with self._lock:
                self._ensure_stream()
                if self._stream is not None:
                    self._stream.write(msg + "\n")
                    self._stream.flush()
        except Exception:
            self.handleError(record)

    def _ensure_stream(self) -> None:
        today = self._today()
        if self._current_date == today and self._stream is not None:
            return
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self._current_date = today
        path = self._log_dir / f"xtark-console-{today.isoformat()}.log"
        self._stream = open(path, "a", encoding="utf-8")

    def cleanup_old_logs(self) -> None:
        if self._retention_days < 1:
            return
        cutoff = self._today() - timedelta(days=self._retention_days - 1)
        try:
            entries = list(self._log_dir.iterdir())
        except OSError:
            return
        for entry in entries:
            if not entry.is_file():
                continue
            if not _LOG_FILENAME_RE.match(entry.name):
                continue
            try:
                file_date = date.fromisoformat(entry.stem.removeprefix("xtark-console-"))
            except ValueError:
                continue
            if file_date < cutoff:
                try:
                    entry.unlink()
                except OSError:
                    pass

    def close(self) -> None:
        with self._lock:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
                self._current_date = None
        super().close()


def is_json_gateway_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.startswith(_JSON_LINE_PREFIXES):
        return True
    if stripped == "DISCONNECT":
        return True
    return False


def json_gateway_log_level(text: str) -> int:
    stripped = text.strip()
    if stripped.startswith("TX "):
        return logging.DEBUG
    if (
        stripped.startswith("SEND ERR")
        or stripped.startswith("RECV ERR")
        or stripped.startswith("RX INVALID")
        or stripped == "CONNECTION LOST"
        or " ERR " in stripped
    ):
        return logging.WARNING
    if stripped.startswith("RX "):
        return logging.DEBUG
    return logging.INFO


def log_json_gateway_line(text: str) -> None:
    logger = logging.getLogger("gateway.json_client")
    level = json_gateway_log_level(text)
    logger.log(level, text)


def log_ui_line(text: str) -> None:
    logging.getLogger("ui").info(text)


def setup_logging(
    settings: Optional[LoggingSettings] = None,
) -> LoggingSettings:
    global _file_handler, _queue_listener, _setup_done
    if settings is None:
        settings = load_logging_settings()

    shutdown_logging_handlers()

    from core.odom_telemetry_logger import configure_odom_telemetry

    configure_odom_telemetry(
        enabled=settings.odom_log_enabled,
        interval_sec=settings.odom_log_interval_sec,
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, settings.level))

    formatter = XtarkFormatter()
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_logging_enabled = True
    _file_handler = None
    _queue_listener = None
    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        handler = DailyFileHandler(settings.log_dir, settings.retention_days)
        handler.setFormatter(formatter)
        handler.cleanup_old_logs()
        _file_handler = handler
        log_queue: queue.Queue[logging.LogRecord] = queue.Queue(-1)
        queue_handler = QueueHandler(log_queue)
        root.addHandler(queue_handler)
        _queue_listener = QueueListener(
            log_queue,
            handler,
            respect_handler_level=True,
        )
        _queue_listener.start()
    except OSError as exc:
        file_logging_enabled = False
        logging.getLogger("logging_config").warning(
            "file logging disabled; using console only: %s", exc
        )

    settings = LoggingSettings(
        log_dir=settings.log_dir,
        level=settings.level,
        retention_days=settings.retention_days,
        odom_log_enabled=settings.odom_log_enabled,
        odom_log_interval_sec=settings.odom_log_interval_sec,
        file_logging_enabled=file_logging_enabled,
    )
    _setup_done = True
    return settings


def shutdown_logging_handlers() -> None:
    """Stop queue listener and close handlers without tearing down the logging module."""
    global _queue_listener, _file_handler
    if _queue_listener is not None:
        _queue_listener.stop()
        _queue_listener = None
    if _file_handler is not None:
        _file_handler.close()
        _file_handler = None


def shutdown_logging() -> None:
    shutdown_logging_handlers()
    logging.shutdown()


def install_excepthook() -> None:
    def _report(exc_type, exc_value, exc_tb) -> None:
        try:
            import traceback

            text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            logging.getLogger("app").critical("uncaught exception\n%s", text)
        except Exception:
            try:
                logging.getLogger("app").critical(
                    "uncaught exception: %s: %s",
                    getattr(exc_type, "__name__", exc_type),
                    exc_value,
                )
            except Exception:
                pass

    def _hook(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        _report(exc_type, exc_value, exc_tb)
        try:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    sys.excepthook = _hook

    if hasattr(threading, "excepthook"):

        def _thread_hook(args) -> None:  # type: ignore[no-untyped-def]
            _hook(args.exc_type, args.exc_value, args.exc_traceback)

        threading.excepthook = _thread_hook


def daily_log_path(for_date: Optional[date] = None) -> Path:
    settings = load_logging_settings()
    day = for_date or date.today()
    return settings.log_dir / f"xtark-console-{day.isoformat()}.log"
