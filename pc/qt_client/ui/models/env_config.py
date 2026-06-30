from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

from ui.models.robot_info import RobotInfo


def _parse_env_file(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: Dict[str, str] = {}
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


def apply_env_overrides(robot: RobotInfo, env_path: Optional[Path] = None) -> RobotInfo:
    """
    Apply repo-local .env overrides to a robot profile.

    This is intentionally minimal: it affects only runtime defaults and should not
    be used as a persistent config store (robots.json remains the source of truth).
    """
    if env_path is None:
        # pc/qt_client/.env
        env_path = Path(__file__).resolve().parents[2] / ".env"
    env = _parse_env_file(env_path)
    if not env:
        return robot

    host = env.get("XTARK_HOST", "").strip()
    json_port = env.get("XTARK_JSON_PORT", "").strip()
    mjpeg_url = env.get("XTARK_MJPEG_URL", "").strip()
    backend = env.get("XTARK_BACKEND", "").strip()
    gateway_uri = env.get("XTARK_GATEWAY_URI", "").strip()
    linear_speed = env.get("XTARK_LINEAR_SPEED", "").strip()
    angular_speed = env.get("XTARK_ANGULAR_SPEED", "").strip()

    updates: Dict[str, str | int | float] = {}
    if backend:
        updates["backend_type"] = backend

    # If gateway_uri is explicit, it wins.
    if gateway_uri:
        updates["gateway_uri"] = gateway_uri
    elif host and json_port:
        updates["gateway_uri"] = f"{host}:{json_port}"
    elif host and backend == "json_gateway":
        updates["gateway_uri"] = f"{host}:8765"

    if mjpeg_url:
        updates["camera_url"] = mjpeg_url

    if host:
        # If master_uri already parses, keep scheme; otherwise use http.
        parsed = urlparse(robot.master_uri)
        scheme = parsed.scheme or "http"
        updates["master_uri"] = f"{scheme}://{host}:11311"

    # Manual control defaults: apply only when robot has no persisted value.
    if linear_speed and robot.manual_linear_speed is None:
        try:
            updates["manual_linear_speed"] = float(linear_speed)
        except ValueError:
            pass
    if angular_speed and robot.manual_angular_speed is None:
        try:
            updates["manual_angular_speed"] = float(angular_speed)
        except ValueError:
            pass

    def _env_bool(key: str) -> Optional[bool]:
        raw = env.get(key, "").strip().lower()
        if raw in ("1", "true", "yes", "on"):
            return True
        if raw in ("0", "false", "no", "off"):
            return False
        return None

    warning_enable = _env_bool("QT_WARNING_ENABLE")
    if warning_enable is not None:
        updates["warning_enabled"] = warning_enable
    warning_safemode = _env_bool("QT_WARNING_SAFEMODE")
    if warning_safemode is not None:
        updates["warning_safemode"] = warning_safemode
    warning_min = env.get("QT_WARNING_MIN_DISTANCE_M", "").strip()
    if warning_min:
        try:
            updates["warning_min_distance"] = float(warning_min)
        except ValueError:
            pass
    warning_half = env.get("QT_WARNING_FRONT_HALF_ANGLE_DEG", "").strip()
    if warning_half:
        try:
            updates["warning_front_half_angle"] = float(warning_half)
        except ValueError:
            pass
    warning_valid = env.get("QT_WARNING_MIN_VALID_RANGE_M", "").strip()
    if warning_valid:
        try:
            updates["warning_min_valid_range"] = float(warning_valid)
        except ValueError:
            pass

    if not updates:
        return robot
    return replace(robot, **updates)

