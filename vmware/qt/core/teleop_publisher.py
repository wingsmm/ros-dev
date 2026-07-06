"""ROS1 /cmd_vel publisher via python2 bridge (Melodic: rospy is py2)."""

import logging
import os
import shlex
import shutil
import subprocess

from core.env import bash_ros_prefix

logger = logging.getLogger(__name__)


class TeleopPublisher(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self._proc = None
        self._init_error = ""

    @property
    def is_available(self):
        return bool(shutil.which("python2"))

    @property
    def init_error(self):
        return self._init_error

    def _bridge_command(self):
        script = shlex.quote(
            str(self.cfg.app_dir / "scripts" / "teleop_ros1_bridge.py")
        )
        return (
            "%sexport CMD_VEL_TOPIC=%s; python2 %s"
            % (
                bash_ros_prefix(self.cfg),
                shlex.quote(self.cfg.cmd_vel_topic),
                script,
            )
        )

    def ensure_ready(self):
        if self._proc is not None and self._proc.poll() is None:
            return True, ""
        if self._init_error:
            return False, self._init_error
        if not self.is_available:
            self._init_error = "python2 不可用，无法发布 /cmd_vel"
            return False, self._init_error
        if not self.cfg.ros_ip:
            self._init_error = "ROS_IP 未设置，无法发布 /cmd_vel"
            return False, self._init_error

        try:
            self._proc = subprocess.Popen(
                ["bash", "-lc", self._bridge_command()],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
            )
            logger.info("teleop bridge started pid=%s", self._proc.pid)
            return True, ""
        except OSError as exc:
            self._init_error = str(exc)
            logger.exception("teleop bridge start failed")
            return False, self._init_error

    def _write_line(self, line):
        ok, err = self.ensure_ready()
        if not ok:
            return False, err
        if self._proc.poll() is not None:
            self._init_error = "teleop bridge 已退出"
            self._proc = None
            ok, err = self.ensure_ready()
            if not ok:
                return False, err
        try:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
            return True, ""
        except (IOError, OSError) as exc:
            self._init_error = str(exc)
            self._proc = None
            return False, self._init_error

    def publish_velocity(self, linear_x, linear_y, angular_z):
        return self._write_line(
            "%s %s %s"
            % (float(linear_x), float(linear_y), float(angular_z))
        )

    def stop(self, repeat=3):
        del repeat  # bridge publishes stop repeat internally
        self._write_line("stop")

    def shutdown(self):
        self.stop(repeat=3)
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self._proc.kill()
                except OSError:
                    pass
        self._proc = None
