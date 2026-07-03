"""ROS1 topic / master probes via shell (runs on VM)."""

import subprocess

from core.env import (
    CMD_VEL_TOPIC_DEFAULT,
    DEPTH_PREVIEW_TOPIC,
    VMWARE_DEPTH_POINTS_TOPIC,
    bash_ros_prefix,
)

KEY_TOPICS = [
    "/scan",
    "/odom",
    "/camera/image_raw",
    "/camera/depth/image_raw",
    "/camera/depth/camera_info",
    DEPTH_PREVIEW_TOPIC,
]

# VM-local topics; only published after Qt starts 深度增强 point cloud.
ENHANCED_LOCAL_TOPICS = [VMWARE_DEPTH_POINTS_TOPIC]


class TopicStatus(object):
    def __init__(self, topic, has_publisher, detail):
        self.topic = topic
        self.has_publisher = has_publisher
        self.detail = detail


class DepthDiagResult(object):
    def __init__(self, lines, depth_has_pub, depth_frame_ok, depth_hz):
        self.lines = lines
        self.depth_has_pub = depth_has_pub
        self.depth_frame_ok = depth_frame_ok
        self.depth_hz = depth_hz


def _run(cfg, cmd, timeout=30):
    full = "%s %s" % (bash_ros_prefix(cfg), cmd)
    return subprocess.run(
        ["bash", "-lc", full],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=timeout,
    )


def master_reachable(cfg, timeout=8):
    try:
        proc = _run(cfg, "rostopic list >/dev/null 2>&1; echo $?", timeout=timeout)
        return proc.stdout.strip().endswith("0")
    except (subprocess.TimeoutExpired, OSError):
        return False


def package_available(cfg, package, timeout=8):
    try:
        proc = _run(cfg, "rospack find %s 2>/dev/null" % package, timeout=timeout)
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def tf_transform_exists(cfg, parent, child, timeout=4):
    try:
        proc = _run(
            cfg,
            "timeout %d rosrun tf tf_echo %s %s 2>&1"
            % (timeout, parent, child),
            timeout=timeout + 8,
        )
        text = (proc.stdout or "") + (proc.stderr or "")
        if "Failure" in text or "Exception" in text or "not part of the same tree" in text:
            return False
        return "Translation:" in text or "At time" in text
    except (subprocess.TimeoutExpired, OSError):
        return False


def topic_has_subscriber(cfg, topic):
    try:
        proc = _run(
            cfg,
            "rostopic info %s 2>/dev/null | awk '/^Subscribers:/{f=1;next} /^Publishers:/{f=0} f' | grep -q '[^[:space:]]'"
            % topic,
            timeout=12,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def cmd_vel_subscriber_ok(cfg, topic=None):
    topic = topic or CMD_VEL_TOPIC_DEFAULT
    if not master_reachable(cfg):
        return False, "Master 不可达"
    if topic_has_subscriber(cfg, topic):
        return True, "%s 有 subscriber" % topic
    return False, "%s 无 subscriber（小车需 radar2d-start / full-start）" % topic


def topic_has_publisher(cfg, topic):
    try:
        proc = _run(
            cfg,
            "rostopic info %s 2>/dev/null | awk '/^Publishers:/{f=1;next} /^Subscribers:/{f=0} f' | grep -q '[^[:space:]]'"
            % topic,
            timeout=12,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def probe_topics(cfg):
    results = []
    for topic in KEY_TOPICS:
        has_pub = topic_has_publisher(cfg, topic)
        detail = "publisher OK" if has_pub else "no publisher"
        results.append(TopicStatus(topic, has_pub, detail))
    return results


def probe_enhanced_local_topics(cfg):
    results = []
    for topic in ENHANCED_LOCAL_TOPICS:
        has_pub = topic_has_publisher(cfg, topic)
        detail = "publisher OK" if has_pub else "no publisher (启动深度增强后才有)"
        results.append(TopicStatus(topic, has_pub, detail))
    return results


def _parse_hz(stdout):
    for line in stdout.splitlines():
        if "average rate" in line.lower():
            return line.strip()
    if stdout.strip():
        return stdout.strip().splitlines()[-1]
    return "(无输出)"


def depth_diagnostics(cfg):
    lines = []
    depth_topic = "/camera/depth/image_raw"
    info_topic = "/camera/depth/camera_info"

    if not master_reachable(cfg):
        lines.append("[ERR] ROS Master 不可达")
        return DepthDiagResult(lines, False, False, "")

    has_pub = topic_has_publisher(cfg, depth_topic)
    lines.append(
        "%s: %s" % (depth_topic, "publisher OK" if has_pub else "no publisher")
    )

    try:
        proc = _run(cfg, "rostopic info %s" % depth_topic, timeout=15)
        if proc.stdout.strip():
            lines.append(proc.stdout.strip())
        if proc.stderr.strip():
            lines.append(proc.stderr.strip())
    except (subprocess.TimeoutExpired, OSError) as exc:
        lines.append("[WARN] rostopic info 失败: %s" % exc)

    frame_ok = False
    try:
        proc = _run(cfg, "timeout 12 rostopic echo %s -n 1" % depth_topic, timeout=18)
        if proc.returncode == 0 and proc.stdout.strip():
            frame_ok = True
            lines.append("[OK] 收到 1 帧深度图")
        else:
            lines.append("[WARN] 12s 内未收到深度帧")
            if proc.stderr.strip():
                lines.append(proc.stderr.strip())
    except (subprocess.TimeoutExpired, OSError) as exc:
        lines.append("[WARN] rostopic echo 失败: %s" % exc)

    hz_text = ""
    try:
        proc = _run(cfg, "timeout 6 rostopic hz %s" % depth_topic, timeout=10)
        hz_text = _parse_hz(proc.stdout + "\n" + proc.stderr)
        lines.append("hz: %s" % hz_text)
    except (subprocess.TimeoutExpired, OSError) as exc:
        lines.append("[WARN] rostopic hz 失败: %s" % exc)

    try:
        proc = _run(cfg, "rostopic info %s" % info_topic, timeout=12)
        if proc.stdout.strip():
            lines.append("--- %s ---" % info_topic)
            lines.append(proc.stdout.strip())
    except (subprocess.TimeoutExpired, OSError):
        pass

    return DepthDiagResult(lines, has_pub, frame_ok, hz_text)


def format_topic_table(rows):
    out = []
    for row in rows:
        mark = "OK" if row.has_publisher else "--"
        out.append("[%s] %s: %s" % (mark, row.topic, row.detail))
    return "\n".join(out)


def rviz_running(cfg):
    try:
        proc = _run(cfg, "pgrep -f '[r]viz -d' >/dev/null 2>&1; echo $?", timeout=8)
        return proc.stdout.strip().endswith("0")
    except (subprocess.TimeoutExpired, OSError):
        return False


def which_rviz(cfg):
    try:
        proc = _run(cfg, "which rviz", timeout=8)
        path = proc.stdout.strip()
        if proc.returncode == 0 and path:
            return path
        return ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def env_check_report(cfg):
    """Local VM checks only — no SSH, no pc_stack."""
    lines = ["=== 环境检查 (VM 本地) ==="]

    if not cfg.ros_setup_exists:
        lines.append("[ERR] ROS setup 缺失: %s" % cfg.ros_setup)
    else:
        lines.append("[OK] ROS setup: %s" % cfg.ros_setup)

    if not cfg.ws_setup_exists:
        lines.append("[ERR] workspace setup 缺失: %s" % cfg.ws_setup)
    else:
        lines.append("[OK] WS setup: %s" % cfg.ws_setup)

    rviz_path = which_rviz(cfg)
    if rviz_path:
        lines.append("[OK] rviz: %s" % rviz_path)
    else:
        lines.append("[ERR] rviz 未找到 (which rviz)")

    lines.append("ROS_MASTER_URI=%s" % cfg.ros_master_uri)
    lines.append("ROS_IP=%s" % (cfg.ros_ip or "(未检测)"))

    if master_reachable(cfg):
        lines.append("[OK] ROS Master 可达")
        try:
            proc = _run(cfg, "rostopic list", timeout=15)
            if proc.stdout.strip():
                lines.append("--- rostopic list ---")
                lines.append(proc.stdout.strip())
            else:
                lines.append("[WARN] rostopic list 无输出")
            if proc.stderr.strip():
                lines.append(proc.stderr.strip())
        except (subprocess.TimeoutExpired, OSError) as exc:
            lines.append("[ERR] rostopic list 失败: %s" % exc)
    else:
        lines.append("[ERR] ROS Master 不可达")
        lines.append("      请在小车手动: ~/ros_ws/scripts/pc_stack.sh camera-start 或 full-start")

    if rviz_running(cfg):
        lines.append("[INFO] RViz 进程: 运行中")
    else:
        lines.append("[INFO] RViz 进程: 未启动")

    return "\n".join(lines)
