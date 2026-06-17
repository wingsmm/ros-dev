from __future__ import annotations

from typing import Tuple, TYPE_CHECKING
from urllib.parse import urlparse

from backends.base import RobotBackend
from gateway.json_client import JsonClientBridge, JsonTcpClient

if TYPE_CHECKING:
    from ui.models.robot_info import RobotInfo


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
    """Reuse legacy xtark JSON TCP bridge for velocity commands."""

    def __init__(self) -> None:
        self._bridge = JsonClientBridge()
        self._client = JsonTcpClient(self._bridge)
        self._host = ""
        self._port = 8765
        self._bridge.log_line.connect(lambda text: print(f"JSON gateway: {text}"))
        self._bridge.connection_changed.connect(
            lambda ok, detail: print(f"JSON gateway connection: ok={ok} {detail}")
        )

    def connect(self, profile: RobotInfo) -> None:
        host, port = _parse_json_gateway(profile)
        print(f"JSON gateway connect: {host}:{port}")
        self._client.connect(host, port)
        self._host = host
        self._port = port

    def disconnect(self) -> None:
        print(f"JSON gateway disconnect: {self._host}:{self._port}")
        self._client.disconnect(send_stop=True)

    def is_connected(self) -> bool:
        return self._client.connected

    def send_velocity(
        self, linear_x: float, linear_y: float, angular_z: float
    ) -> None:
        if not self.is_connected():
            raise RuntimeError("JSON gateway not connected")
        ok = self._client.send_cmd_vel(linear_x, linear_y, angular_z)
        print(
            "JSON velocity:",
            f"lx={linear_x:.3f} ly={linear_y:.3f} az={angular_z:.3f}",
            f"sent={ok}",
        )
        if not ok:
            raise RuntimeError("JSON gateway send_cmd_vel failed")

    def stop_motion(self) -> None:
        if self.is_connected():
            ok = self._client.send_cmd_vel(0.0, 0.0, 0.0)
            print("JSON stop_motion:", f"sent={ok}")
            if not ok:
                raise RuntimeError("JSON gateway stop_motion failed")

    def emergency_stop(self) -> None:
        print("JSON emergency_stop")
        self.stop_motion()
