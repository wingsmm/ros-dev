"""Remote L1 cloud-align YAML read/apply + node restart via SSH.

The cloud-align YAML on Jetson is the source of truth for the
/unilidar/cloud_aligned rotation applied to the raw L1 point cloud.
This module keeps the same SSH conventions as :mod:`core.l1_tf_control`.
"""

from __future__ import annotations

import base64
import math
import re
import shlex
from dataclasses import dataclass

from core.config import CockpitConfig, load_config
from core.l1_tf_control import remote_ros2_ws, remote_shell_path, run_ssh

JETSON_CLOUD_ALIGN_YAML = "~/qt/ros2_ws/src/l1_cloud_align/config/l1_cloud_align.yaml"

_VALID_ALIGN_ACTIONS = frozenset({"start", "stop", "restart", "status"})


@dataclass(frozen=True)
class CloudAlignExtrinsics:
    xyz: tuple[float, float, float]
    base_rpy_rad: tuple[float, float, float]
    trim_rpy_rad: tuple[float, float, float]
    input_topic: str = "/unilidar/cloud"
    output_topic: str = "/unilidar/cloud_aligned"
    target_frame: str = "base_link"


@dataclass(frozen=True)
class CloudAlignApplyResult:
    write_ok: bool
    restart_ok: bool
    write_detail: str
    restart_detail: str

    @property
    def ok(self) -> bool:
        return self.write_ok and self.restart_ok


def remote_align_yaml(cfg: CockpitConfig) -> str:
    return "%s/src/l1_cloud_align/config/l1_cloud_align.yaml" % remote_ros2_ws(cfg)


def _remote_align_script(cfg: CockpitConfig) -> str:
    return "%s/scripts/l1_cloud_align.sh" % remote_ros2_ws(cfg)


def _parse_bracket_floats(line: str) -> list[float]:
    m = re.search(r"\[([^\]]+)\]", line)
    if not m:
        return []
    return [float(x.strip()) for x in m.group(1).split(",") if x.strip()]


def _parse_scalar(line: str, key: str) -> str | None:
    prefix = key + ":"
    if not line.startswith(prefix):
        return None
    return line[len(prefix):].strip() or None


def parse_align_yaml(text: str) -> CloudAlignExtrinsics:
    """Strict cloud_align YAML parse.

    Requires both ``base_rpy_rad`` and ``trim_rpy_rad`` to be present as
    3-element float lists. Raises ``ValueError`` on any structural issue.
    Never silently defaults to zeros — cockpit uses this to preserve the
    fixed base rotation across writes.
    """
    xyz: list[float] | None = None
    base_rpy: list[float] | None = None
    trim_rpy: list[float] | None = None
    input_topic = "/unilidar/cloud"
    output_topic = "/unilidar/cloud_aligned"
    target_frame = "base_link"
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("xyz:"):
            vals = _parse_bracket_floats(line)
            if len(vals) == 3:
                xyz = vals
        elif line.startswith("base_rpy_rad:"):
            vals = _parse_bracket_floats(line)
            if len(vals) == 3:
                base_rpy = vals
        elif line.startswith("trim_rpy_rad:"):
            vals = _parse_bracket_floats(line)
            if len(vals) == 3:
                trim_rpy = vals
        else:
            for key in ("input_topic", "output_topic", "target_frame"):
                v = _parse_scalar(line, key)
                if v is not None:
                    if key == "input_topic":
                        input_topic = v
                    elif key == "output_topic":
                        output_topic = v
                    elif key == "target_frame":
                        target_frame = v
                    break
    if xyz is None:
        raise ValueError("缺少 xyz 或格式不是 3 元素浮点数组")
    if base_rpy is None:
        raise ValueError("缺少 base_rpy_rad 或格式不是 3 元素浮点数组")
    if trim_rpy is None:
        raise ValueError("缺少 trim_rpy_rad 或格式不是 3 元素浮点数组")
    return CloudAlignExtrinsics(
        xyz=(xyz[0], xyz[1], xyz[2]),
        base_rpy_rad=(base_rpy[0], base_rpy[1], base_rpy[2]),
        trim_rpy_rad=(trim_rpy[0], trim_rpy[1], trim_rpy[2]),
        input_topic=input_topic,
        output_topic=output_topic,
        target_frame=target_frame,
    )


def format_align_yaml(ext: CloudAlignExtrinsics) -> str:
    return (
        "# L1 point-cloud alignment (rigid-body transform)\n"
        "# Written by cockpit apply. Rotates /unilidar/cloud into target_frame\n"
        "# and republishes as output_topic. Not for base_link static TF.\n"
        "#\n"
        "# Mounting baseline for this robot:\n"
        "#   lidar +Z -> base_link +X  (front)\n"
        "#   lidar +X -> base_link +Z  (up)\n"
        "#   lidar +Y -> base_link -Y  (right)\n"
        "#\n"
        "# base_rpy_rad = fixed L1 -> base_link mounting baseline (never changed via UI)\n"
        "# trim_rpy_rad = live trim in base_link frame (UI edits this)\n"
        "#   roll  = side tilt / left-right lean, around base_link +X\n"
        "#   pitch = front-back tilt, around base_link +Y\n"
        "#   yaw   = heading direction trim, around base_link +Z\n"
        "\n"
        "input_topic: %s\n"
        "output_topic: %s\n"
        "target_frame: %s\n"
        "\n"
        "xyz: [%s, %s, %s]\n"
        "\n"
        "base_rpy_rad: [%s, %s, %s]\n"
        "trim_rpy_rad: [%s, %s, %s]\n"
    ) % (
        ext.input_topic,
        ext.output_topic,
        ext.target_frame,
        ext.xyz[0], ext.xyz[1], ext.xyz[2],
        ext.base_rpy_rad[0], ext.base_rpy_rad[1], ext.base_rpy_rad[2],
        ext.trim_rpy_rad[0], ext.trim_rpy_rad[1], ext.trim_rpy_rad[2],
    )


def rad_to_deg(rad: float) -> float:
    return rad * 180.0 / math.pi


def deg_to_rad(deg: float) -> float:
    return deg * math.pi / 180.0


def rpy_deg_from_ext(ext: CloudAlignExtrinsics) -> tuple[float, float, float]:
    """UI edits ``trim_rpy_rad`` only, so convert that side to degrees."""
    return (
        rad_to_deg(ext.trim_rpy_rad[0]),
        rad_to_deg(ext.trim_rpy_rad[1]),
        rad_to_deg(ext.trim_rpy_rad[2]),
    )


def fetch_align_yaml(cfg: CockpitConfig | None = None, timeout: int = 20) -> tuple[bool, str]:
    cfg = cfg or load_config()
    path = remote_align_yaml(cfg)
    return run_ssh(cfg, "cat %s" % remote_shell_path(path), timeout=timeout)


def read_cloud_align(
    cfg: CockpitConfig | None = None,
    timeout: int = 20,
) -> tuple[bool, CloudAlignExtrinsics | str]:
    ok, text = fetch_align_yaml(cfg=cfg, timeout=timeout)
    if not ok:
        return False, text
    try:
        return True, parse_align_yaml(text)
    except ValueError as exc:
        return False, "YAML 解析失败: %s" % exc


def write_align_yaml(
    ext: CloudAlignExtrinsics,
    cfg: CockpitConfig | None = None,
    timeout: int = 25,
) -> tuple[bool, str]:
    cfg = cfg or load_config()
    path = remote_align_yaml(cfg)
    body = format_align_yaml(ext)
    b64 = base64.b64encode(body.encode("utf-8")).decode("ascii")
    remote = "echo %s | base64 -d > %s" % (shlex.quote(b64), remote_shell_path(path))
    return run_ssh(cfg, remote, timeout=timeout)


def run_cloud_align_script(
    action: str,
    cfg: CockpitConfig | None = None,
    timeout: int = 25,
) -> tuple[bool, str]:
    cfg = cfg or load_config()
    action = action.strip().lower()
    if action not in _VALID_ALIGN_ACTIONS:
        return False, "未知 cloud_align 命令: %s" % action
    return run_ssh(
        cfg,
        "bash %s %s" % (remote_shell_path(_remote_align_script(cfg)), shlex.quote(action)),
        timeout=timeout,
    )


def apply_cloud_align(
    xyz: tuple[float, float, float],
    trim_rpy_deg: tuple[float, float, float],
    template: CloudAlignExtrinsics,
    cfg: CockpitConfig | None = None,
    timeout: int = 30,
) -> CloudAlignApplyResult:
    """Write YAML then restart l1_cloud_align node.

    ``template`` MUST be a CloudAlignExtrinsics previously read from
    Jetson. This keeps ``base_rpy_rad`` and topics intact — no zero
    fallback, no default base. Restarts only cloud_align; L1 driver and
    static TF are untouched.
    """
    if not isinstance(template, CloudAlignExtrinsics):
        return CloudAlignApplyResult(
            False, False,
            "缺少已读取的对齐参数模板（base_rpy_rad 未知，拒绝写入）",
            "未执行",
        )
    cfg = cfg or load_config()

    ext = CloudAlignExtrinsics(
        xyz=xyz,
        base_rpy_rad=template.base_rpy_rad,
        trim_rpy_rad=(
            deg_to_rad(trim_rpy_deg[0]),
            deg_to_rad(trim_rpy_deg[1]),
            deg_to_rad(trim_rpy_deg[2]),
        ),
        input_topic=template.input_topic,
        output_topic=template.output_topic,
        target_frame=template.target_frame,
    )
    write_ok, write_detail = write_align_yaml(ext, cfg=cfg, timeout=timeout)
    if not write_ok:
        return CloudAlignApplyResult(False, False, write_detail, "未执行")

    restart_ok, restart_detail = run_cloud_align_script("restart", cfg=cfg, timeout=timeout)
    return CloudAlignApplyResult(write_ok, restart_ok, write_detail, restart_detail)
