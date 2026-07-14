"""Lidar topic / Hz / Jetson port probes for cockpit."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.config import CockpitConfig
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
    cloud_aligned_topic: str
    imu_topic: str
    cloud_hz: float | None
    imu_hz: float | None
    cloud_publisher: str
    cloud_aligned_publisher: str
    imu_publisher: str
    cloud_ok: bool
    aligned_ok: bool
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
    """Return whether parent -> child is visible via /tf, /tf_static, or tf2_echo.

    Dynamic links (e.g. odom -> base_link) share /tf with Point-LIO, so a single
    ``echo --once`` often samples the wrong stanza. Stream /tf briefly and match
    the parent/child pair. tf2_echo may print transient \"frame does not exist\"
    while the buffer fills — treat that as failure only when no sample succeeds.
    """
    label = "%s -> %s" % (parent, child)
    pair_re = re.compile(
        r"frame_id:\s*%s\s*\n\s*child_frame_id:\s*%s\b"
        % (re.escape(parent), re.escape(child))
    )

    # Stream a short window of /tf (beats intermittent --once misses).
    try:
        proc = _run("timeout 5 ros2 topic echo /tf 2>&1", timeout=7)
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if pair_re.search(text):
            return True, "%s OK (/tf)" % label
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        proc = _run("timeout 3 ros2 topic echo /tf_static --once 2>&1", timeout=5)
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if pair_re.search(text):
            return True, "%s OK (/tf_static)" % label
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        proc = _run(
            "timeout 10 ros2 run tf2_ros tf2_echo %s %s 2>&1" % (parent, child),
            timeout=14,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "%s missing" % label

    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    lowered = text.lower()
    # Prefer success: startup often logs "frame does not exist" before data.
    if "translation:" in lowered or re.search(r"\bat time\b", lowered):
        return True, "%s OK" % label
    if "frame does not exist" in lowered or "invalid frame" in lowered:
        return False, "%s missing" % label
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


def fetch_jetson_lio_state(
    cfg: CockpitConfig | None = None,
    cockpit_root: Path | None = None,
) -> str:
    """Query Jetson LIO status via SSH (VM does not need jetson.sh)."""
    del cockpit_root  # kept for call-site compatibility
    try:
        from core.config import load_config
        from core.l1_lio_control import status_l1_lio
    except ImportError:
        return "(l1_lio_control 不可用)"

    cfg = cfg or load_config()
    ok, text = status_l1_lio(cfg=cfg)
    text = (text or "").strip()
    if not text:
        return "(无状态)" if ok else "(查询失败)"
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    wanted = ("LIO=", "adapter=", "odom=")
    bits = [ln for ln in lines if any(ln.startswith(p) for p in wanted)]
    if bits:
        return " ".join(bits)
    return lines[0]


def probe_lio_mapping_ready(
    cloud_registered_topic: str = "/cloud_registered",
    odom_topic: str = "/odom",
    path_topic: str = "/odom_path",
    odom_frame: str = "odom",
    base_frame: str = "base_link",
) -> tuple[bool, list[str]]:
    """Pre-open checks for localization RViz. Returns (ok, missing_items)."""
    missing: list[str] = []
    if not topic_status(cloud_registered_topic).has_publisher:
        missing.append("%s publisher" % cloud_registered_topic)
    if not topic_status(odom_topic).has_publisher:
        missing.append("%s publisher" % odom_topic)
    if not topic_status(path_topic).has_publisher:
        missing.append("%s publisher" % path_topic)
    tf_ok, _detail = probe_static_tf(odom_frame, base_frame)
    if not tf_ok:
        missing.append("TF %s -> %s" % (odom_frame, base_frame))
    return (len(missing) == 0), missing


def probe_lio_status(
    odom_topic: str = "/odom",
    path_topic: str = "/odom_path",
    cloud_registered_topic: str = "/cloud_registered",
    cockpit_root: Path | None = None,
    cfg: CockpitConfig | None = None,
) -> LioStatus:
    odom_row = topic_status(odom_topic)
    path_row = topic_status(path_topic)
    cloud_row = topic_status(cloud_registered_topic)
    odom_hz = _topic_hz(odom_topic, seconds=3) if odom_row.has_publisher else None
    cloud_hz = _topic_hz(cloud_registered_topic, seconds=3) if cloud_row.has_publisher else None
    jetson_lio = fetch_jetson_lio_state(cfg=cfg, cockpit_root=cockpit_root)

    parts = []
    if "LIO=stopped" in jetson_lio or "adapter=stopped" in jetson_lio:
        parts.append("Jetson 定位栈未就绪 (启动定位)")
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
    cloud_aligned_topic: str = "/unilidar/cloud_aligned",
) -> LidarStatus:
    cloud_row = topic_status(cloud_topic)
    aligned_row = topic_status(cloud_aligned_topic)
    imu_row = topic_status(imu_topic)
    cloud_hz = _topic_hz(cloud_topic) if cloud_row.has_publisher else None
    imu_hz = _topic_hz(imu_topic) if imu_row.has_publisher else None
    cloud_pub = _publisher_node(cloud_topic) if cloud_row.has_publisher else ""
    aligned_pub = _publisher_node(cloud_aligned_topic) if aligned_row.has_publisher else ""
    imu_pub = _publisher_node(imu_topic) if imu_row.has_publisher else ""
    port = fetch_jetson_lidar_port(cockpit_root)
    tf_ok, tf_detail = probe_static_tf(tf_parent, tf_child)

    parts = []
    if not cloud_row.has_publisher:
        parts.append("%s 无 publisher" % cloud_topic)
    if not aligned_row.has_publisher:
        parts.append("%s 无 publisher" % cloud_aligned_topic)
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
        cloud_aligned_topic=cloud_aligned_topic,
        imu_topic=imu_topic,
        cloud_hz=cloud_hz,
        imu_hz=imu_hz,
        cloud_publisher=cloud_pub or "-",
        cloud_aligned_publisher=aligned_pub or "-",
        imu_publisher=imu_pub or "-",
        cloud_ok=cloud_row.has_publisher,
        aligned_ok=aligned_row.has_publisher,
        imu_ok=imu_row.has_publisher,
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
