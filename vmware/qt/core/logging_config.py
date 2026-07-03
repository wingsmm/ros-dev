"""Unified logging for VMware Qt client (ROS1 / RViz)."""

import logging
import os
import queue
import re
import sys
import threading
from datetime import date, datetime, timedelta
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path

_LOG_FILENAME_RE = re.compile(r"^vmware-console-\d{4}-\d{2}-\d{2}\.log$")
_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_DEFAULT_LEVEL = "INFO"
_DEFAULT_RETENTION_DAYS = 30
_DEFAULT_LOG_DIR = "logs"


def _parse_log_file_date(name):
    stem = name.replace("vmware-console-", "").replace(".log", "")
    parts = stem.split("-")
    if len(parts) != 3:
        raise ValueError(stem)
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


_file_handler = None
_queue_listener = None


def app_root():
    return Path(__file__).resolve().parent.parent


def _parse_env_file(path):
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def _env_value(key, env_file):
    if key in os.environ:
        return os.environ.get(key, "").strip()
    return env_file.get(key, "").strip()


def _parse_level(raw):
    level = (raw or _DEFAULT_LEVEL).upper()
    if level not in _VALID_LEVELS:
        return _DEFAULT_LEVEL
    return level


def _parse_retention_days(raw):
    if not raw:
        return _DEFAULT_RETENTION_DAYS
    try:
        days = int(raw)
    except ValueError:
        return _DEFAULT_RETENTION_DAYS
    if days < 1:
        return _DEFAULT_RETENTION_DAYS
    return days


def resolve_log_dir(raw_dir):
    text = (raw_dir or _DEFAULT_LOG_DIR).strip() or _DEFAULT_LOG_DIR
    path = Path(text)
    if path.is_absolute():
        return path
    return app_root() / path


class LoggingSettings(object):
    def __init__(self, log_dir, level, retention_days, file_logging_enabled=True):
        self.log_dir = log_dir
        self.level = level
        self.retention_days = retention_days
        self.file_logging_enabled = file_logging_enabled


def load_logging_settings(env_path=None):
    if env_path is None:
        env_path = app_root() / ".env"
    env_file = _parse_env_file(env_path)
    return LoggingSettings(
        log_dir=resolve_log_dir(_env_value("XTARK_LOG_DIR", env_file)),
        level=_parse_level(_env_value("XTARK_LOG_LEVEL", env_file)),
        retention_days=_parse_retention_days(
            _env_value("XTARK_LOG_RETENTION_DAYS", env_file)
        ),
    )


class VMwareFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ct = datetime.fromtimestamp(record.created)
        return ct.strftime("%Y-%m-%d %H:%M:%S") + ".%03d" % int(record.msecs)

    def format(self, record):
        record.asctime = self.formatTime(record)
        level = record.levelname
        if len(level) < 8:
            level = level + " " * (8 - len(level))
        message = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            message = "%s\n%s" % (message, record.exc_text)
        return (
            "%s %s pid=%s thread=%s %s: %s"
            % (
                record.asctime,
                level,
                record.process,
                record.threadName,
                record.name,
                message,
            )
        )


class DailyFileHandler(logging.Handler):
    """Append to vmware-console-YYYY-MM-DD.log; rotate at local midnight."""

    def __init__(self, log_dir, retention_days=_DEFAULT_RETENTION_DAYS, today=None):
        super(DailyFileHandler, self).__init__()
        self._log_dir = log_dir
        self._retention_days = retention_days
        self._today_override = today
        self._lock = threading.RLock()
        self._current_date = None
        self._stream = None

    def _today(self):
        return self._today_override or date.today()

    def emit(self, record):
        try:
            msg = self.format(record)
            with self._lock:
                self._ensure_stream()
                if self._stream is not None:
                    self._stream.write(msg + "\n")
                    self._stream.flush()
        except Exception:
            self.handleError(record)

    def _ensure_stream(self):
        today = self._today()
        if self._current_date == today and self._stream is not None:
            return
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self._current_date = today
        path = self._log_dir / ("vmware-console-%s.log" % today.isoformat())
        self._stream = open(str(path), "a", encoding="utf-8")

    def cleanup_old_logs(self):
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
                file_date = _parse_log_file_date(entry.name)
            except ValueError:
                continue
            if file_date < cutoff:
                try:
                    entry.unlink()
                except OSError:
                    pass

    def close(self):
        with self._lock:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
                self._current_date = None
        super(DailyFileHandler, self).close()


def log_ui_line(text):
    logging.getLogger("ui").info(text)


def new_child_log_path(prefix="rviz"):
    settings = load_logging_settings()
    log_dir = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.-]+", "_", prefix)[:48] or "proc"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return log_dir / ("%s_%s.log" % (safe, stamp))


def new_rviz_log_path():
    return new_child_log_path("rviz")


def setup_logging(settings=None):
    global _file_handler, _queue_listener
    if settings is None:
        settings = load_logging_settings()

    shutdown_logging_handlers()

    root = logging.getLogger()
    root.handlers = []
    root.setLevel(getattr(logging, settings.level))

    formatter = VMwareFormatter()
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
        log_queue = queue.Queue(-1)
        queue_handler = QueueHandler(log_queue)
        root.addHandler(queue_handler)
        _queue_listener = QueueListener(log_queue, handler, respect_handler_level=True)
        _queue_listener.start()
    except OSError as exc:
        file_logging_enabled = False
        logging.getLogger("logging_config").warning(
            "file logging disabled; console only: %s", exc
        )

    return LoggingSettings(
        log_dir=settings.log_dir,
        level=settings.level,
        retention_days=settings.retention_days,
        file_logging_enabled=file_logging_enabled,
    )


def shutdown_logging_handlers():
    global _queue_listener, _file_handler
    if _queue_listener is not None:
        _queue_listener.stop()
        _queue_listener = None
    if _file_handler is not None:
        _file_handler.close()
        _file_handler = None


def shutdown_logging():
    shutdown_logging_handlers()
    logging.shutdown()


def install_excepthook():
    def _report(exc_type, exc_value, exc_tb):
        try:
            import traceback

            text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            logging.getLogger("app").critical("uncaught exception\n%s", text)
        except Exception:
            pass

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        _report(exc_type, exc_value, exc_tb)
        try:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    sys.excepthook = _hook
