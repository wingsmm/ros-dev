"""Remote L1 extrinsics read/apply and l1_static_tf restart via SSH (cockpit self-contained)."""

from __future__ import annotations

import base64
import math
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.config import CockpitConfig, load_config

# Extrinsics YAML on Jetson TF package — not in cockpit .env.
JETSON_EXTRINSICS_YAML = "~/qt/ros2_ws/src/l1_tf_bringup/config/l1_extrinsics.yaml"

_VALID_TF_ACTIONS = frozenset({"restart", "status"})


@dataclass(frozen=True)
class L1Extrinsics:
    xyz: tuple[float, float, float]
    base_rpy_rad: tuple[float, float, float]
    trim_rpy_rad: tuple[float, float, float]
    imu_xyz_in_lidar: tuple[float, float, float] = (-0.007698, -0.014655, 0.00667)
    imu_rpy_in_lidar: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class ExtrinsicsApplyResult:
    write_ok: bool
    tf_restart_ok: bool
    write_detail: str
    tf_detail: str

    @property
    def ok(self) -> bool:
        return self.write_ok and self.tf_restart_ok


@dataclass(frozen=True)
class TfProcessStatus:
    """Jetson-side l1_static_tf.sh process state (internal, not shown as TF buttons)."""

    label: str
    ok: bool
    raw: str


def remote_ros2_ws(cfg: CockpitConfig) -> str:
    """Workspace path on Jetson — do not expand ~ locally (cockpit may run on VM)."""
    return cfg.jetson_remote_ros2_ws.strip().rstrip("/")


def remote_shell_path(path: str) -> str:
    """Quote a Jetson path for remote shell use while allowing leading ~/."""
    path = path.strip()
    if path == "~":
        return "$HOME"
    if path.startswith("~/"):
        return "$HOME/" + shlex.quote(path[2:])
    return shlex.quote(path)


def _remote_ros2_ws(cfg: CockpitConfig) -> str:
    return remote_ros2_ws(cfg)


def remote_extrinsics_yaml(cfg: CockpitConfig) -> str:
    return "%s/src/l1_tf_bringup/config/l1_extrinsics.yaml" % remote_ros2_ws(cfg)


def _remote_tf_script(cfg: CockpitConfig) -> str:
    return "%s/scripts/l1_static_tf.sh" % remote_ros2_ws(cfg)


def _ssh_base_argv(cfg: CockpitConfig) -> list[str]:
    return [
        "ssh",
        "-p",
        str(cfg.jetson_ssh_port),
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=8",
    ]


def _ssh_argv(cfg: CockpitConfig, remote_cmd: str) -> list[str]:
    target = "%s@%s" % (cfg.jetson_ssh_user.strip(), cfg.jetson_ssh_host.strip())
    ssh = _ssh_base_argv(cfg)
    password = cfg.jetson_ssh_password.strip()
    key = cfg.jetson_ssh_key.strip()
    if password:
        ssh = ["sshpass", "-p", password] + ssh
    elif key:
        key = os.path.expanduser(key)
        ssh.extend(["-o", "BatchMode=yes", "-i", key])
    else:
        ssh.extend(["-o", "BatchMode=yes"])

    ssh.extend([target, remote_cmd])
    return ssh


def _ssh_config_error(cfg: CockpitConfig) -> str | None:
    if not cfg.jetson_ssh_host.strip():
        return (
            "未配置 JETSON_SSH_HOST（cockpit/.env）；"
            "VM 仅部署 cockpit 时需填写 Jetson SSH 参数"
        )
    if not cfg.jetson_ssh_user.strip():
        return "未配置 JETSON_SSH_USER（cockpit/.env）"

    password = cfg.jetson_ssh_password.strip()
    key = cfg.jetson_ssh_key.strip()
    if password and not shutil.which("sshpass"):
        return "需要 sshpass：sudo apt install -y sshpass"
    if key:
        key = os.path.expanduser(key)
        if not password and not Path(key).is_file():
            return "JETSON_SSH_KEY 不存在: %s" % key
    return None


def run_ssh(cfg: CockpitConfig, remote_cmd: str, timeout: int = 25) -> tuple[bool, str]:
    err = _ssh_config_error(cfg)
    if err:
        return False, err
    try:
        proc = subprocess.run(
            _ssh_argv(cfg, remote_cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, "ssh 失败: %s" % exc

    text = (proc.stdout or "").strip()
    ok = proc.returncode == 0
    if not text:
        text = "exit=%s" % proc.returncode
    return ok, text


def _run_ssh(cfg: CockpitConfig, remote_cmd: str, timeout: int = 25) -> tuple[bool, str]:
    return run_ssh(cfg, remote_cmd, timeout=timeout)

def _parse_bracket_floats(line: str) -> list[float]:
    m = re.search(r"\[([^\]]+)\]", line)
    if not m:
        return []
    return [float(x.strip()) for x in m.group(1).split(",") if x.strip()]


def parse_extrinsics_yaml(text: str) -> L1Extrinsics:
    """Parse Jetson extrinsics YAML. base_rpy_rad is required (exactly 3 floats)."""
    xyz = [0.0, 0.0, 0.0]
    base_rpy: list[float] | None = None
    trim_rpy = [0.0, 0.0, 0.0]
    imu_xyz = [-0.007698, -0.014655, 0.00667]
    imu_rpy = [0.0, 0.0, 0.0]
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
            if len(vals) != 3:
                raise ValueError(
                    "base_rpy_rad 必须是恰好 3 个 float，当前: %s" % (vals or "缺失/无法解析")
                )
            base_rpy = vals
        elif line.startswith("trim_rpy_rad:"):
            vals = _parse_bracket_floats(line)
            if len(vals) == 3:
                trim_rpy = vals
        elif line.startswith("imu_xyz_in_lidar:"):
            vals = _parse_bracket_floats(line)
            if len(vals) == 3:
                imu_xyz = vals
        elif line.startswith("imu_rpy_in_lidar:"):
            vals = _parse_bracket_floats(line)
            if len(vals) == 3:
                imu_rpy = vals
    if base_rpy is None:
        raise ValueError("YAML 缺少 base_rpy_rad，无法保留远端安装基准")
    return L1Extrinsics(
        xyz=(xyz[0], xyz[1], xyz[2]),
        base_rpy_rad=(base_rpy[0], base_rpy[1], base_rpy[2]),
        trim_rpy_rad=(trim_rpy[0], trim_rpy[1], trim_rpy[2]),
        imu_xyz_in_lidar=(imu_xyz[0], imu_xyz[1], imu_xyz[2]),
        imu_rpy_in_lidar=(imu_rpy[0], imu_rpy[1], imu_rpy[2]),
    )


def format_extrinsics_yaml(ext: L1Extrinsics) -> str:
    """Fixed-format YAML; base_rpy_rad and imu_* preserved from read."""
    return (
        "# L1 static TF extrinsics (radians)\n"
        "# Written by cockpit apply; base_rpy_rad is mount baseline.\n"
        "# imu_* fields required by l1_static_tf.launch.py (fail-closed).\n"
        "\n"
        "parent: base_link\n"
        "child: unilidar_lidar\n"
        "\n"
        "xyz: [%s, %s, %s]\n"
        "\n"
        "base_rpy_rad: [%s, %s, %s]\n"
        "\n"
        "trim_rpy_rad: [%s, %s, %s]\n"
        "\n"
        "imu_xyz_in_lidar: [%s, %s, %s]\n"
        "imu_rpy_in_lidar: [%s, %s, %s]\n"
    ) % (
        ext.xyz[0],
        ext.xyz[1],
        ext.xyz[2],
        ext.base_rpy_rad[0],
        ext.base_rpy_rad[1],
        ext.base_rpy_rad[2],
        ext.trim_rpy_rad[0],
        ext.trim_rpy_rad[1],
        ext.trim_rpy_rad[2],
        ext.imu_xyz_in_lidar[0],
        ext.imu_xyz_in_lidar[1],
        ext.imu_xyz_in_lidar[2],
        ext.imu_rpy_in_lidar[0],
        ext.imu_rpy_in_lidar[1],
        ext.imu_rpy_in_lidar[2],
    )


def rad_to_deg(rad: float) -> float:
    return rad * 180.0 / math.pi


def deg_to_rad(deg: float) -> float:
    return deg * math.pi / 180.0


def trim_rpy_deg_from_ext(ext: L1Extrinsics) -> tuple[float, float, float]:
    return (
        rad_to_deg(ext.trim_rpy_rad[0]),
        rad_to_deg(ext.trim_rpy_rad[1]),
        rad_to_deg(ext.trim_rpy_rad[2]),
    )


def fetch_extrinsics_yaml(cfg: CockpitConfig | None = None, timeout: int = 20) -> tuple[bool, str]:
    cfg = cfg or load_config()
    path = remote_extrinsics_yaml(cfg)
    return run_ssh(cfg, "cat %s" % remote_shell_path(path), timeout=timeout)


def read_extrinsics(cfg: CockpitConfig | None = None, timeout: int = 20) -> tuple[bool, L1Extrinsics | str]:
    ok, text = fetch_extrinsics_yaml(cfg=cfg, timeout=timeout)
    if not ok:
        return False, text
    try:
        return True, parse_extrinsics_yaml(text)
    except ValueError as exc:
        return False, "YAML 解析失败: %s" % exc


def write_extrinsics_yaml(
    ext: L1Extrinsics,
    cfg: CockpitConfig | None = None,
    timeout: int = 25,
) -> tuple[bool, str]:
    cfg = cfg or load_config()
    path = remote_extrinsics_yaml(cfg)
    body = format_extrinsics_yaml(ext)
    b64 = base64.b64encode(body.encode("utf-8")).decode("ascii")
    remote = "echo %s | base64 -d > %s" % (shlex.quote(b64), remote_shell_path(path))
    return _run_ssh(cfg, remote, timeout=timeout)


def run_tf_command(
    action: str,
    cfg: CockpitConfig | None = None,
    timeout: int = 25,
) -> tuple[bool, str]:
    """Internal: restart|status l1_static_tf.sh on Jetson."""
    cfg = cfg or load_config()
    action = action.strip().lower()
    if action not in _VALID_TF_ACTIONS:
        return False, "未知 TF 命令: %s" % action
    return run_ssh(
        cfg,
        "bash %s %s" % (remote_shell_path(_remote_tf_script(cfg)), shlex.quote(action)),
        timeout=timeout,
    )


def parse_tf_process_status(text: str, ssh_ok: bool) -> TfProcessStatus:
    lowered = (text or "").strip().lower()
    if not ssh_ok:
        if "sshpass" in lowered or "need sshpass" in lowered:
            return TfProcessStatus("ssh failed", False, text)
        if "ssh:" in lowered or "connect to host" in lowered or "permission denied" in lowered:
            return TfProcessStatus("ssh failed", False, text)
        if "未配置" in text or "不存在" in text:
            return TfProcessStatus("ssh failed", False, text)
        return TfProcessStatus("restart failed", False, text)
    if "running" in lowered or "already running" in lowered or "started" in lowered:
        return TfProcessStatus("running", True, text)
    if "stopped" in lowered:
        return TfProcessStatus("stopped", False, text)
    return TfProcessStatus("unknown", False, text)


def fetch_tf_process_status(
    cfg: CockpitConfig | None = None,
    timeout: int = 20,
) -> TfProcessStatus:
    ok, text = run_tf_command("status", cfg=cfg, timeout=timeout)
    return parse_tf_process_status(text, ok)


def apply_extrinsics(
    xyz: tuple[float, float, float],
    trim_rpy_deg: tuple[float, float, float],
    base_rpy_rad: tuple[float, float, float] | None = None,
    cfg: CockpitConfig | None = None,
    timeout: int = 30,
) -> ExtrinsicsApplyResult:
    """Write Jetson YAML then restart l1_static_tf (user-facing「应用外参」)."""
    cfg = cfg or load_config()
    imu_xyz = (-0.007698, -0.014655, 0.00667)
    imu_rpy = (0.0, 0.0, 0.0)

    ok_read, current = read_extrinsics(cfg=cfg, timeout=timeout)
    if ok_read and isinstance(current, L1Extrinsics):
        imu_xyz = current.imu_xyz_in_lidar
        imu_rpy = current.imu_rpy_in_lidar
        if base_rpy_rad is None:
            base_rpy_rad = current.base_rpy_rad
    elif base_rpy_rad is None:
        detail = current if isinstance(current, str) else "读取失败"
        return ExtrinsicsApplyResult(
            False,
            False,
            "请先点「读取外参」以保留 Jetson base_rpy_rad：%s" % detail,
            "未执行",
        )

    ext = L1Extrinsics(
        xyz=xyz,
        base_rpy_rad=base_rpy_rad,
        trim_rpy_rad=(
            deg_to_rad(trim_rpy_deg[0]),
            deg_to_rad(trim_rpy_deg[1]),
            deg_to_rad(trim_rpy_deg[2]),
        ),
        imu_xyz_in_lidar=imu_xyz,
        imu_rpy_in_lidar=imu_rpy,
    )
    write_ok, write_detail = write_extrinsics_yaml(ext, cfg=cfg, timeout=timeout)
    if not write_ok:
        return ExtrinsicsApplyResult(False, False, write_detail, "未执行")

    tf_ok, tf_detail = run_tf_command("restart", cfg=cfg, timeout=timeout)
    return ExtrinsicsApplyResult(write_ok, tf_ok, write_detail, tf_detail)
