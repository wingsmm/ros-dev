"""Central shutdown registry: one graceful teardown path for X / Ctrl+C / SIGTERM."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, List

logger = logging.getLogger(__name__)

ShutdownFn = Callable[[], None]


@dataclass
class _Hook:
    name: str
    priority: int
    callback: ShutdownFn


_hooks: List[_Hook] = []
_ran = False


def register_shutdown(
    callback: ShutdownFn,
    *,
    name: str = "",
    priority: int = 100,
) -> str:
    """Register a shutdown hook; lower priority runs earlier."""
    token = name or f"hook@{len(_hooks)}"
    _hooks.append(_Hook(name=token, priority=priority, callback=callback))
    return token


def unregister_shutdown(name: str) -> None:
    global _hooks
    _hooks = [hook for hook in _hooks if hook.name != name]


def run_shutdown() -> None:
    global _ran
    if _ran:
        return
    _ran = True
    if not _hooks:
        return
    logger.info("app shutdown: running %d hook(s)", len(_hooks))
    for hook in sorted(_hooks, key=lambda item: item.priority):
        try:
            logger.debug("app shutdown: %s", hook.name)
            hook.callback()
        except Exception:
            logger.exception("app shutdown hook failed: %s", hook.name)


def reset_shutdown_state_for_tests() -> None:
    """Test helper only."""
    global _ran, _hooks
    _ran = False
    _hooks = []
