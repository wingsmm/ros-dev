from __future__ import annotations

import logging
from typing import Callable, Optional, Tuple, TYPE_CHECKING
from urllib.parse import urlparse

from backends.base import RobotBackend
from core.logging_config import log_json_gateway_line
from gateway.json_client import JsonClientBridge, JsonTcpClient

if TYPE_CHECKING:
    from ui.models.robot_info import RobotInfo

logger = logging.getLogger(__name__)

MessageHandler = Callable[[object], None]
ConnectionHandler = Callable[[bool, str], None]


def _parse_json_gateway(profile: RobotInfo) -> Tuple[str, int]:
    raw = (profile.gateway_uri or "").strip()
    if raw:
        if "://" in raw:
            parsed = urlparse(raw)
            host = parsed.hostname or ""
            port = parsed.port or 8765
        elif ":" in raw:
            host, _, port_text = raw.partition(":")
            port = int(port_text or 8765)
        else:
            host, port = raw, 8765
        if host:
            return host, port
    parsed = urlparse(profile.master_uri)
    host = parsed.hostname or "192.168.1.169"
    return host, 8765


class JsonGatewayBackend(RobotBackend):
    """xtark JSON TCP bridge: cmd_vel out, odom_base / base_status in."""

    def __init__(self) -> None:
        self._bridge = JsonClientBridge()
        self._client = JsonTcpClient(self._bridge)
        self._host = ""
        self._port = 8765
        self._message_handlers: list[MessageHandler] = []
        self._connection_handlers: list[ConnectionHandler] = []
        self._bridge.log_line.connect(log_json_gateway_line)
        self._bridge.message.connect(self._dispatch_message)
        self._bridge.connection_changed.connect(self._dispatch_connection)

    def bind_feedback(
        self,
        *,
        on_message: MessageHandler,
        on_connection: ConnectionHandler,
    ) -> None:
        if on_message not in self._message_handlers:
            self._message_handlers.append(on_message)
        if on_connection not in self._connection_handlers:
            self._connection_handlers.append(on_connection)

    def unbind_feedback(
        self,
        *,
        on_message: MessageHandler,
        on_connection: ConnectionHandler,
    ) -> None:
        if on_message in self._message_handlers:
            self._message_handlers.remove(on_message)
        if on_connection in self._connection_handlers:
            self._connection_handlers.remove(on_connection)

    def _dispatch_message(self, msg: object) -> None:
        for handler in list(self._message_handlers):
            handler(msg)

    def _dispatch_connection(self, ok: bool, detail: str) -> None:
        for handler in list(self._connection_handlers):
            handler(ok, detail)

    def connect(self, profile: RobotInfo) -> None:
        host, port = _parse_json_gateway(profile)
        logger.info("JSON gateway connect: %s:%s", host, port)
        self._client.connect(host, port)
        self._host = host
        self._port = port

    def disconnect(self) -> None:
        logger.info("JSON gateway disconnect: %s:%s", self._host, self._port)
        self._client.disconnect(send_stop=True)

    def is_connected(self) -> bool:
        return self._client.connected

    def send_velocity(
        self, linear_x: float, linear_y: float, angular_z: float
    ) -> None:
        if not self.is_connected():
            raise RuntimeError("JSON gateway not connected")
        ok = self._client.send_cmd_vel(linear_x, linear_y, angular_z)
        logger.debug(
            "JSON velocity: lx=%.3f ly=%.3f az=%.3f sent=%s",
            linear_x,
            linear_y,
            angular_z,
            ok,
        )
        if not ok:
            raise RuntimeError("JSON gateway send_cmd_vel failed")

    def stop_motion(self) -> None:
        if self.is_connected():
            ok = self._client.send_cmd_vel(0.0, 0.0, 0.0)
            logger.info("JSON stop_motion: sent=%s", ok)
            if not ok:
                raise RuntimeError("JSON gateway stop_motion failed")

    def emergency_stop(self) -> None:
        logger.warning("JSON emergency_stop")
        self.stop_motion()
