"""Remote L1 LIO stack control via SSH (cockpit self-contained, no jetson.sh)."""

from __future__ import annotations

import shlex

from core.config import CockpitConfig, load_config
from core.l1_tf_control import remote_ros2_ws, remote_shell_path, run_ssh

_VALID_ACTIONS = frozenset({"start", "stop", "restart", "status", "logs"})


def _remote_lio_script(cfg: CockpitConfig) -> str:
    return "%s/scripts/l1_lio.sh" % remote_ros2_ws(cfg)


def run_l1_lio(
    action: str,
    cfg: CockpitConfig | None = None,
    timeout: int | None = None,
) -> tuple[bool, str]:
    """Run l1_lio.sh on Jetson. action: start|stop|restart|status|logs."""
    cfg = cfg or load_config()
    action = action.strip().lower()
    if action not in _VALID_ACTIONS:
        return False, "未知 LIO 命令: %s" % action

    if timeout is None:
        timeout = 55 if action in {"start", "restart"} else 25

    script = _remote_lio_script(cfg)
    remote = "bash %s %s" % (remote_shell_path(script), shlex.quote(action))
    return run_ssh(cfg, remote, timeout=timeout)


def start_l1_lio(cfg: CockpitConfig | None = None) -> tuple[bool, str]:
    return run_l1_lio("start", cfg=cfg)


def stop_l1_lio(cfg: CockpitConfig | None = None) -> tuple[bool, str]:
    return run_l1_lio("stop", cfg=cfg)


def status_l1_lio(cfg: CockpitConfig | None = None) -> tuple[bool, str]:
    return run_l1_lio("status", cfg=cfg)
