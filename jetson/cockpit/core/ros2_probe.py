"""ROS2 graph and environment probes for Jetson cockpit."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

KEY_TOPICS = [
    "/cmd_vel",
    "/vehicle/control_action",
]


@dataclass(frozen=True)
class TopicStatus:
    topic: str
    has_publisher: bool
    has_subscriber: bool
    detail: str


def _run(cmd: str, timeout: int = 12) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-lc", cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def ros2_available() -> bool:
    try:
        return _run("command -v ros2 >/dev/null", timeout=4).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def rclpy_available() -> bool:
    try:
        return _run("python3 -c 'import rclpy'", timeout=4).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ros2_node_list(timeout: int = 8) -> tuple[bool, str]:
    try:
        proc = _run("ros2 node list", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    text = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return False, err or text or "ros2 node list failed"
    return True, text or "(无节点)"


def ros2_topic_list(timeout: int = 8) -> tuple[bool, str]:
    try:
        proc = _run("ros2 topic list", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    text = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return False, err or text or "ros2 topic list failed"
    return True, text or "(无 topic)"


def _topic_info(topic: str, timeout: int = 10) -> str:
    proc = _run("ros2 topic info %s" % topic, timeout=timeout)
    return ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()


def _parse_count(text: str, label: str) -> int:
    prefix = label.lower() + ":"
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith(prefix):
            continue
        _, _, value = stripped.partition(":")
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def topic_status(topic: str) -> TopicStatus:
    try:
        text = _topic_info(topic)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return TopicStatus(topic, False, False, "查询失败: %s" % exc)

    pubs = _parse_count(text, "Publisher count")
    subs = _parse_count(text, "Subscription count")
    detail = "publishers=%d subscribers=%d" % (pubs, subs)
    if text:
        detail += "\n" + text
    return TopicStatus(topic, pubs > 0, subs > 0, detail)


def probe_key_topics(topics: list[str] | tuple[str, ...] | None = None) -> list[TopicStatus]:
    return [topic_status(topic) for topic in (topics or KEY_TOPICS)]


def format_topic_report(rows: list[TopicStatus]) -> str:
    lines = []
    for row in rows:
        mark = "OK" if row.has_publisher or row.has_subscriber else "--"
        lines.append("[%s] %s" % (mark, row.topic))
        lines.append(row.detail)
    return "\n\n".join(lines)


def format_topic_summary(
    rows: list[TopicStatus],
    cmd_vel_topic: str = "/cmd_vel",
    control_action_topic: str = "/vehicle/control_action",
) -> str:
    cmd_vel = next((row for row in rows if row.topic == cmd_vel_topic), None)
    action = next((row for row in rows if row.topic == control_action_topic), None)
    parts = []
    if cmd_vel is not None:
        parts.append(
            "%s subscriber %s"
            % (cmd_vel_topic, "OK" if cmd_vel.has_subscriber else "missing")
        )
    if action is not None:
        parts.append(
            "%s publisher %s"
            % (
                control_action_topic,
                "OK" if action.has_publisher else "missing",
            )
        )
    return "；".join(parts) if parts else "无关键 topic 结果"


def env_check_report() -> str:
    lines = ["=== ROS2 环境检查 ==="]
    lines.append("ROS_DOMAIN_ID=%s" % os.environ.get("ROS_DOMAIN_ID", "(未设置)"))
    lines.append("[OK] ros2" if ros2_available() else "[ERR] ros2 不可用")
    lines.append("[OK] rclpy" if rclpy_available() else "[ERR] rclpy 不可用")

    ok, nodes = ros2_node_list()
    lines.append("--- ros2 node list ---")
    lines.append(nodes if ok else "[ERR] %s" % nodes)

    ok, topics = ros2_topic_list()
    lines.append("--- ros2 topic list ---")
    lines.append(topics if ok else "[ERR] %s" % topics)
    return "\n".join(lines)
