"""Lidar topic / Hz / Jetson port probes for cockpit."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.ros2_probe import _run, topic_status


@dataclass(frozen=True)
class LioStatus:
    odom_topic: str
    path_topic: str
    cloud_registered_topic: str
    odom_hz: float | None
    cloud_reg_hz: float | None
    path_has_pub: bool
    odom_ok: bool
    cloud_reg_ok: bool
    jetson_lio: str
    detail: str


@dataclass(frozen=True)
class LidarStatus:
    cloud_topic: str
    imu_topic: str
    cloud_hz: float | None
    imu_hz: float | None
    cloud_publisher: str
    imu_publisher: str
    cloud_ok: bool
    imu_ok: bool
    jetson_port: str
    tf_parent: str
    tf_child: str
    tf_ok: bool
    tf_detail: str
    detail: str


def _parse_hz(text: str) -> float | None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("average rate:"):
            continue
        try:
            return float(stripped.split(":", 1)[1].strip())
        except ValueError:
            return None
    return None


def _topic_hz(topic: str, seconds: int = 4) -> float | None:
    try:
        proc = _run(
            "timeout %d ros2 topic hz %s 2>&1" % (seconds, topic),
            timeout=seconds + 3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return _parse_hz((proc.stdout or "") + "\n" + (proc.stderr or ""))


def _publisher_node(topic: str) -> str:
    try:
        proc = _run("ros2 topic info %s -v 2>&1" % topic, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    text = proc.stdout or ""
    for line in text.splitlines():
        if line.strip().startswith("Node name:"):
            return line.split(":", 1)[1].strip()
    return ""


def probe_static_tf(
    parent: str = "base_link",
    child: str = "unilidar_lidar",
) -> tuple[bool, str]:
    """Return whether base_link -> unilidar_lidar is visible on /tf_static or tf2."""
    label = "%s -> %s" % (parent, child)
    try:
        proc = _run("timeout 4 ros2 topic echo /tf_static --once 2>&1", timeout=6)
    except (OSError, subprocess.TimeoutExpired):
        proc = None
    if proc is not None:
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if ("frame_id: %s" % parent) in text and ("child_frame_id: %s" % child) in text:
            return True, "%s OK" % label

    try:
        proc = _run(
            "timeout 4 ros2 run tf2_ros tf2_echo %s %s 2>&1" % (parent, child),
            timeout=7,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "%s missing" % label

    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    lowered = text.lower()
    if "frame does not exist" in lowered or "invalid frame" in lowered:
        return False, "%s missing" % label
    if "translation:" in lowered or "at time" in lowered:
        return True, "%s OK" % label
    return False, "%s no data" % label


def fetch_jetson_lidar_port(cockpit_root: Path | None = None) -> str:
    root = cockpit_root or Path(__file__).resolve().parent.parent
    jetson_sh = root.parent / "scripts" / "jetson.sh"
    if not jetson_sh.is_file():
        return "(jetson.sh 不可用)"
    try:
        proc = subprocess.run(
            ["bash", str(jetson_sh), "ros2", "status"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "(查询失败: %s)" % exc
    match = re.search(r"port=(\S+)", proc.stdout or "")
    if match:
        return match.group(1)
    return "(82 未运行或无法解析 port)"


def fetch_jetson_lio_state(cockpit_root: Path | None = None) -> str:
    root = cockpit_root or Path(__file__).resolve().parent.parent
    jetson_sh = root.parent / "scripts" / "jetson.sh"
    if not jetson_sh.is_file():
        return "(jetson.sh 不可用)"
    try:
        proc = subprocess.run(
            ["bash", str(jetson_sh), "ros2", "lio-status"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "(查询失败: %s)" % exc
    text = (proc.stdout or "").strip().splitlines()
    return text[0] if text else "(无状态)"


def probe_lio_status(
    odom_topic: str = "/odom",
    path_topic: str = "/path",
    cloud_registered_topic: str = "/cloud_registered",
    cockpit_root: Path | None = None,
) -> LioStatus:
    odom_row = topic_status(odom_topic)
    path_row = topic_status(path_topic)
    cloud_row = topic_status(cloud_registered_topic)
    odom_hz = _topic_hz(odom_topic, seconds=3) if odom_row.has_publisher else None
    cloud_hz = _topic_hz(cloud_registered_topic, seconds=3) if cloud_row.has_publisher else None
    jetson_lio = fetch_jetson_lio_state(cockpit_root)

    parts = []
    if "stopped" in jetson_lio:
        parts.append("Jetson LIO 未启动 (jetson.sh ros2 lio-start)")
    if not odom_row.has_publisher:
        parts.append("%s 无 publisher" % odom_topic)
    if not path_row.has_publisher:
        parts.append("%s 无 publisher" % path_topic)
    if not cloud_row.has_publisher:
        parts.append("%s 无 publisher" % cloud_registered_topic)

    return LioStatus(
        odom_topic=odom_topic,
        path_topic=path_topic,
        cloud_registered_topic=cloud_registered_topic,
        odom_hz=odom_hz,
        cloud_reg_hz=cloud_hz,
        path_has_pub=path_row.has_publisher,
        odom_ok=odom_row.has_publisher,
        cloud_reg_ok=cloud_row.has_publisher and cloud_hz is not None and cloud_hz > 0.1,
        jetson_lio=jetson_lio,
        detail="；".join(parts) if parts else "OK",
    )


def probe_lidar_status(
    cloud_topic: str = "/unilidar/cloud",
    imu_topic: str = "/unilidar/imu",
    cockpit_root: Path | None = None,
    tf_parent: str = "base_link",
    tf_child: str = "unilidar_lidar",
) -> LidarStatus:
    cloud_row = topic_status(cloud_topic)
    imu_row = topic_status(imu_topic)
    cloud_hz = _topic_hz(cloud_topic) if cloud_row.has_publisher else None
    imu_hz = _topic_hz(imu_topic) if imu_row.has_publisher else None
    cloud_pub = _publisher_node(cloud_topic) if cloud_row.has_publisher else ""
    imu_pub = _publisher_node(imu_topic) if imu_row.has_publisher else ""
    port = fetch_jetson_lidar_port(cockpit_root)
    tf_ok, tf_detail = probe_static_tf(tf_parent, tf_child)

    parts = []
    if not cloud_row.has_publisher:
        parts.append("%s 无 publisher" % cloud_topic)
    if not imu_row.has_publisher:
        parts.append("%s 无 publisher" % imu_topic)
    if cloud_hz is None and cloud_row.has_publisher:
        parts.append("%s 无频率数据" % cloud_topic)
    if imu_hz is None and imu_row.has_publisher:
        parts.append("%s 无频率数据" % imu_topic)
    if cloud_pub and cloud_pub != "unitree_lidar_ros2_node":
        parts.append("cloud publisher 异常: %s" % cloud_pub)
    if not tf_ok:
        parts.append("TF %s" % tf_detail)

    return LidarStatus(
        cloud_topic=cloud_topic,
        imu_topic=imu_topic,
        cloud_hz=cloud_hz,
        imu_hz=imu_hz,
        cloud_publisher=cloud_pub or "-",
        imu_publisher=imu_pub or "-",
        cloud_ok=cloud_row.has_publisher and cloud_hz is not None and cloud_hz > 0.5,
        imu_ok=imu_row.has_publisher and imu_hz is not None and imu_hz > 1.0,
        jetson_port=port,
        tf_parent=tf_parent,
        tf_child=tf_child,
        tf_ok=tf_ok,
        tf_detail=tf_detail,
        detail="；".join(parts) if parts else "OK",
    )


def format_lidar_summary(status: LidarStatus) -> str:
    cloud_hz = "-" if status.cloud_hz is None else "%.1f Hz" % status.cloud_hz
    imu_hz = "-" if status.imu_hz is None else "%.0f Hz" % status.imu_hz
    tf_state = status.tf_detail if status.tf_ok else status.tf_detail
    return (
        "port=%s；%s %s；%s %s；TF %s；publisher=%s"
        % (
            status.jetson_port,
            status.cloud_topic,
            cloud_hz,
            status.imu_topic,
            imu_hz,
            tf_state,
            status.cloud_publisher,
        )
    )


def format_lio_summary(status: LioStatus) -> str:
    odom_hz = "-" if status.odom_hz is None else "%.1f Hz" % status.odom_hz
    cloud_hz = "-" if status.cloud_reg_hz is None else "%.1f Hz" % status.cloud_reg_hz
    return (
        "%s；%s %s；%s %s；%s %s"
        % (
            status.jetson_lio,
            status.odom_topic,
            odom_hz,
            status.cloud_registered_topic,
            cloud_hz,
            status.path_topic,
            "OK" if status.path_has_pub else "missing",
        )
    )
