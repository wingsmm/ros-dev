#!/usr/bin/env bash
set -eo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ROS2_WS="${ROOT_DIR}/jetson/mirror/ros2_ws"
COCKPIT_DIR="${ROOT_DIR}/jetson/cockpit"

if [[ -f "${COCKPIT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${COCKPIT_DIR}/.env"
  set +a
fi

set +u
source /opt/ros/humble/setup.bash
set -u

echo "== ros2 environment =="
command -v ros2
python3 -c 'import rclpy; print("rclpy ok")'

echo "== colcon =="
if ! command -v colcon >/dev/null 2>&1; then
  echo "colcon missing"
  exit 20
fi
command -v colcon

echo "== python syntax =="
cd "${ROOT_DIR}"
python3 -m compileall -q \
  jetson/mirror/ros2_ws/src/cmd_vel_car_web_bridge \
  jetson/cockpit

echo "== build cmd_vel_car_web_bridge =="
cd "${ROS2_WS}"
colcon build --packages-select cmd_vel_car_web_bridge

echo "== import installed package =="
set +u
source "${ROS2_WS}/install/setup.bash"
set -u
python3 -c 'from cmd_vel_car_web_bridge.node import CmdVelCarWebBridge; print(CmdVelCarWebBridge.__name__)'

echo "== cockpit sender help =="
cd "${COCKPIT_DIR}"
python3 scripts/cmd_vel_sender.py --help >/dev/null

echo "== cockpit qt import =="
python3 -c 'import app; from main_window import MainWindow; from core.ros2_control import Ros2ControlWorker; from ui.teleop_panel import TeleopPanel; print("qt import ok")'

echo "== dry-run DDS loop =="
bridge_log="$(mktemp)"
set +u
source "${ROS2_WS}/install/setup.bash"
set -u
ros2 run cmd_vel_car_web_bridge bridge >"${bridge_log}" 2>&1 &
bridge_pid=$!
bridge_exec="${ROS2_WS}/install/cmd_vel_car_web_bridge/lib/cmd_vel_car_web_bridge/bridge"
cleanup() {
  # ros2 run 会 fork/exec 出真正的 node 进程，$! 只是 launcher。
  # 先 kill launcher，再按 install 里的可执行路径清扫孤儿 node，
  # 精确匹配路径避免误伤其它 ROS2 节点。
  kill "${bridge_pid}" >/dev/null 2>&1 || true
  local orphans
  orphans="$(pgrep -f "${bridge_exec}" 2>/dev/null || true)"
  if [[ -n "${orphans}" ]]; then
    # shellcheck disable=SC2086
    kill ${orphans} >/dev/null 2>&1 || true
    sleep 0.3
    orphans="$(pgrep -f "${bridge_exec}" 2>/dev/null || true)"
    if [[ -n "${orphans}" ]]; then
      # shellcheck disable=SC2086
      kill -9 ${orphans} >/dev/null 2>&1 || true
    fi
  fi
  rm -f "${bridge_log}"
}
trap cleanup EXIT
sleep 2

for action in forward backward left right stop; do
  python3 scripts/cmd_vel_sender.py "${action}" --settle-ms 300
done
sleep 1

for expected in FORWARD BACKWARD TURN_LEFT TURN_RIGHT STOP; do
  if ! grep -q "CONTROL_ACTION=${expected}" "${bridge_log}"; then
    echo "missing CONTROL_ACTION=${expected}" >&2
    echo "--- bridge log ---" >&2
    cat "${bridge_log}" >&2
    exit 30
  fi
done
echo "dry-run DDS loop ok"

echo "VERIFY_CMD_VEL_BRIDGE_OK"
