"""Capacity-1 latest-frame mailbox for bridge ingress (no unbounded queues)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class DepthBridgeFrame:
    """Raw depth HTTP payload for ROS2 bridge (no preview conversion)."""

    header: dict
    data: bytes
    camera_info: Optional[dict] = None


class LatestFrameMailbox(Generic[T]):
    """Stores at most one pending item; coalesces bridge delivery notifications."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._item: Optional[T] = None
        self._notify_armed = False

    def put(self, item: T) -> bool:
        """Overwrite latest item. True => schedule one bridge delivery."""
        with self._lock:
            self._item = item
            if self._notify_armed:
                return False
            self._notify_armed = True
            return True

    def take(self) -> Optional[T]:
        with self._lock:
            item = self._item
            self._item = None
            return item

    def has_pending(self) -> bool:
        with self._lock:
            return self._item is not None

    def finish_delivery_cycle(self) -> None:
        with self._lock:
            if self._item is None:
                self._notify_armed = False

    def clear(self) -> None:
        with self._lock:
            self._item = None
            self._notify_armed = False
