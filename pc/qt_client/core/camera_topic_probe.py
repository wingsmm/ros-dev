"""Probe ROS2 camera topics off the Qt UI thread (subprocess, no rclpy in main thread)."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field

from core.camera_topics import CAMERA_PROBE_TOPICS
from core.ros2_runtime import ros2_shell_prefix

_HZ_RE = re.compile(r"average rate:\s*([\d.]+)")


@dataclass
class CameraTopicProbeEntry:
    topic: str
    online: bool = False
    hz: float = 0.0
    detail: str = ""


@dataclass
class CameraTopicProbeResult:
    entries: dict[str, CameraTopicProbeEntry] = field(default_factory=dict)
    probe_error: str = ""
    probed_ms: int = 0


def _run_shell(inner_cmd: str, timeout: float = 6.0) -> tuple[int, str, str]:
    cmd = ["bash", "-lc", ros2_shell_prefix() + inner_cmd]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()


def _list_topics() -> tuple[set[str], str]:
    code, stdout, stderr = _run_shell("ros2 topic list 2>/dev/null", timeout=5.0)
    if code != 0 and not stdout:
        return set(), stderr or "ros2 topic list 失败"
    topics = {line.strip() for line in stdout.splitlines() if line.strip().startswith("/")}
    return topics, ""


def _probe_hz(topic: str) -> tuple[float, str]:
    code, stdout, stderr = _run_shell(
        f"timeout 3 ros2 topic hz {topic} 2>/dev/null | head -n 5",
        timeout=5.0,
    )
    text = stdout or stderr
    if code != 0 and not text:
        return 0.0, ""
    match = _HZ_RE.search(text)
    if match:
        try:
            return float(match.group(1)), ""
        except ValueError:
            pass
    if "no new messages" in text.lower():
        return 0.0, "无新消息"
    return 0.0, ""


def probe_camera_topics(
    topics: tuple[str, ...] = CAMERA_PROBE_TOPICS,
) -> CameraTopicProbeResult:
    """Sync probe — call from QThread worker only."""
    now_ms = int(time.time() * 1000)
    available, list_err = _list_topics()
    if list_err and not available:
        return CameraTopicProbeResult(
            probe_error=list_err,
            probed_ms=now_ms,
        )

    entries: dict[str, CameraTopicProbeEntry] = {}
    for topic in topics:
        online = topic in available
        hz = 0.0
        detail = "离线" if not online else "在线"
        if online:
            hz, hz_note = _probe_hz(topic)
            if hz > 0.01:
                detail = f"{hz:.1f} Hz"
            elif hz_note:
                detail = f"在线 ({hz_note})"
            else:
                detail = "在线 (0 Hz)"
        entries[topic] = CameraTopicProbeEntry(
            topic=topic,
            online=online,
            hz=hz,
            detail=detail,
        )

    return CameraTopicProbeResult(entries=entries, probed_ms=now_ms)


def format_probe_summary(
    result: CameraTopicProbeResult,
    topics: tuple[str, ...] = CAMERA_PROBE_TOPICS,
) -> str:
    if result.probe_error:
        return result.probe_error
    parts = []
    for topic in topics:
        entry = result.entries.get(topic)
        if entry is None:
            parts.append(f"{topic}: ?")
        elif entry.online:
            parts.append(f"{topic}: {entry.detail}")
        else:
            parts.append(f"{topic}: 离线")
    return " | ".join(parts)
