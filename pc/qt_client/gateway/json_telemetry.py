from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

# Shared display rules for HUD + detail panel (odom_base / base_status).
POS_DECIMALS = 3
SPEED_DECIMALS = 3
YAW_DEG_DECIMALS = 1
BATTERY_DECIMALS = 2


@dataclass(frozen=True)
class OdomDisplay:
    """Unified odom_base presentation for Qt UI."""

    x_m: str
    y_m: str
    yaw_deg: str
    vx_mps: str
    vy_mps: str
    wz_deg_s: str
    pose_summary: str
    linear_hud: str
    angular_hud: str


@dataclass(frozen=True)
class BaseStatusDisplay:
    """Unified base_status presentation for Qt UI."""

    online: str
    estop: str
    battery_v: str
    mode: str
    error_code: str
    connection_summary: str


def _fmt_num(value: Optional[float], decimals: int, *, unit: str = "") -> str:
    if value is None:
        return "-"
    text = "{:.{d}f}".format(float(value), d=decimals)
    return text + unit if unit else text


def format_odom_display(msg: Dict[str, Any]) -> OdomDisplay:
    """Single formatter: HUD and detail panel must both use this."""
    x = msg.get("x")
    y = msg.get("y")
    yaw = msg.get("yaw")
    if x is None or y is None or yaw is None:
        empty = "-"
        return OdomDisplay(
            x_m=empty,
            y_m=empty,
            yaw_deg=empty,
            vx_mps=empty,
            vy_mps=empty,
            wz_deg_s=empty,
            pose_summary=empty,
            linear_hud=empty,
            angular_hud=empty,
        )

    x_f, y_f = float(x), float(y)
    yaw_rad = float(yaw)
    yaw_deg_f = math.degrees(yaw_rad)
    vx = float(msg.get("linear_x", 0.0) or 0.0)
    vy = float(msg.get("linear_y", 0.0) or 0.0)
    wz_rad = float(msg.get("angular_z", 0.0) or 0.0)
    wz_deg = math.degrees(wz_rad)

    x_m = _fmt_num(x_f, POS_DECIMALS)
    y_m = _fmt_num(y_f, POS_DECIMALS)
    yaw_deg = _fmt_num(yaw_deg_f, YAW_DEG_DECIMALS, unit="°")
    vx_mps = _fmt_num(vx, SPEED_DECIMALS)
    vy_mps = _fmt_num(vy, SPEED_DECIMALS)
    wz_deg_s = _fmt_num(wz_deg, SPEED_DECIMALS)

    pose_summary = "{x}, {y}, {yaw}".format(x=x_m, y=y_m, yaw=yaw_deg)
    linear_hud = _fmt_num(vx, SPEED_DECIMALS)
    angular_hud = wz_deg_s

    return OdomDisplay(
        x_m=x_m,
        y_m=y_m,
        yaw_deg=yaw_deg,
        vx_mps=vx_mps,
        vy_mps=vy_mps,
        wz_deg_s=wz_deg_s,
        pose_summary=pose_summary,
        linear_hud=linear_hud,
        angular_hud=angular_hud,
    )


def format_base_status_display(
    msg: Dict[str, Any], robot_name: str = ""
) -> BaseStatusDisplay:
    online = msg.get("online")
    estop = msg.get("estop")
    battery = msg.get("battery_v")
    mode = msg.get("mode")
    error_code = msg.get("error_code")

    battery_text = (
        "-"
        if battery is None
        else "{:.{d}f} V".format(float(battery), d=BATTERY_DECIMALS)
    )

    parts = [robot_name] if robot_name else []
    if battery is not None:
        parts.append("{:.{d}f}V".format(float(battery), d=BATTERY_DECIMALS))
    if estop:
        parts.append("急停")
    connection_summary = " · ".join(p for p in parts if p)

    return BaseStatusDisplay(
        online="-" if online is None else str(online),
        estop="-" if estop is None else str(estop),
        battery_v=battery_text,
        mode="-" if mode is None else str(mode),
        error_code="-" if error_code is None else str(error_code),
        connection_summary=connection_summary or robot_name or "-",
    )


def format_pose_text(msg: Dict[str, Any]) -> str:
    return format_odom_display(msg).pose_summary


def format_motion_text(msg: Dict[str, Any]) -> Tuple[str, str]:
    view = format_odom_display(msg)
    return view.linear_hud, view.angular_hud


def format_connection_detail(robot_name: str, msg: Dict[str, Any]) -> str:
    return format_base_status_display(msg, robot_name).connection_summary
