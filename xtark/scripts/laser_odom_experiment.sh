#!/usr/bin/env bash
set -euo pipefail

# Sidecar only: start/stop rf2o -> /odom_laser. Does NOT touch robot_stack / android_stack bringup.

ROOT="$(cd "$(dirname "$0")" && pwd)"

ROS_SETUP="${ROS_SETUP:-/opt/ros/melodic/setup.bash}"
WS_SETUP="${WS_SETUP:-$HOME/ros_ws/devel/setup.bash}"
LOG_DIR="${XTARK_LOG_DIR:-$HOME/xtark_logs}/laser_odom_experiment"
LAUNCH_PKG="${LAUNCH_PKG:-xtark_laser_odometry}"
LAUNCH_FILE="${LAUNCH_FILE:-rf2o_odom_laser.launch}"
ODOM_LASER_TOPIC="${ODOM_LASER_TOPIC:-/odom_laser}"
SCAN_TOPIC="${SCAN_TOPIC:-/scan}"
MAIN_ODOM_TOPIC="${MAIN_ODOM_TOPIC:-/odom}"

usage() {
  cat <<EOF
Usage: laser_odom_experiment.sh <command>

Commands:
  start   Start rf2o_laser_odometry -> ${ODOM_LASER_TOPIC} (background)
  stop    Stop experiment node only
  status  Show process and topic probes
  logs    Tail experiment log

Does NOT start xtark_driver, gmapping, or move_base.
Requires main stack already publishing ${SCAN_TOPIC} and ${MAIN_ODOM_TOPIC}.

Environment:
  ROS_SETUP=${ROS_SETUP}
  WS_SETUP=${WS_SETUP}
  LOG_DIR=${LOG_DIR}
EOF
}

source_ros() {
  if [ ! -f "$ROS_SETUP" ]; then
    echo "[ERR] ROS setup not found: $ROS_SETUP"
    exit 1
  fi
  if [ ! -f "$WS_SETUP" ]; then
    echo "[ERR] workspace setup not found: $WS_SETUP"
    echo "      run: cd ~/ros_ws && catkin_make && source devel/setup.bash"
    exit 1
  fi
  set +u
  # shellcheck disable=SC1090
  source "$ROS_SETUP"
  # shellcheck disable=SC1090
  source "$WS_SETUP"
  set -u
}

is_running() {
  pgrep -f "roslaunch ${LAUNCH_PKG} ${LAUNCH_FILE}" >/dev/null 2>&1
}

wait_for_master() {
  local max="${1:-20}"
  local i=0
  while ! rostopic list &>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "[ERR] rosmaster not ready after ${max}s"
      return 1
    fi
    sleep 1
  done
}

wait_for_topic() {
  local topic="$1"
  local max="${2:-25}"
  local i=0
  while ! rostopic list 2>/dev/null | grep -qx "$topic"; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "[WARN] topic ${topic} not seen after ${max}s"
      return 1
    fi
    sleep 1
  done
  echo "[OK] ${topic} available"
}

cmd_start() {
  mkdir -p "$LOG_DIR"
  source_ros
  wait_for_master 20

  if ! rospack find rf2o_laser_odometry >/dev/null 2>&1; then
    echo "[ERR] rf2o_laser_odometry not found"
    echo "      try: sudo apt install ros-melodic-rf2o-laser-odometry"
    exit 1
  fi

  if ! rospack find "$LAUNCH_PKG" >/dev/null 2>&1; then
    echo "[ERR] package ${LAUNCH_PKG} not in workspace"
    echo "      copy xtark/${LAUNCH_PKG} to ~/ros_ws/src/ and catkin_make"
    exit 1
  fi

  wait_for_topic "$SCAN_TOPIC" 25 || true
  wait_for_topic "$MAIN_ODOM_TOPIC" 25 || true

  if is_running; then
    echo "[OK] experiment already running"
    return 0
  fi

  echo "[INFO] Starting roslaunch ${LAUNCH_PKG} ${LAUNCH_FILE}"
  nohup roslaunch "$LAUNCH_PKG" "$LAUNCH_FILE" >"$LOG_DIR/rf2o.log" 2>&1 &
  echo "[OK] started pid=$! log=$LOG_DIR/rf2o.log"

  sleep 2
  wait_for_topic "$ODOM_LASER_TOPIC" 30 || true
}

cmd_stop() {
  pkill -f "roslaunch ${LAUNCH_PKG} ${LAUNCH_FILE}" || true
  pkill -f 'rf2o_laser_odometry_node' || true
  sleep 1
  if is_running; then
    echo "[WARN] experiment may still be running"
    exit 1
  fi
  echo "[OK] stopped"
}

cmd_status() {
  source_ros 2>/dev/null || true
  echo "---process---"
  pgrep -af "roslaunch ${LAUNCH_PKG} ${LAUNCH_FILE}|rf2o_laser_odometry" || echo "not running"
  echo "---topics---"
  if rostopic list &>/dev/null; then
    for t in "$SCAN_TOPIC" "$MAIN_ODOM_TOPIC" "$ODOM_LASER_TOPIC"; do
      if rostopic list 2>/dev/null | grep -qx "$t"; then
        echo "[OK] $t"
        timeout 3 rostopic hz "$t" 2>&1 | head -3 || true
      else
        echo "[--] $t missing"
      fi
    done
  else
    echo "rosmaster not reachable"
  fi
}

cmd_logs() {
  mkdir -p "$LOG_DIR"
  touch "$LOG_DIR/rf2o.log"
  tail -n 80 -f "$LOG_DIR/rf2o.log"
}

main() {
  case "${1:-}" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    status) cmd_status ;;
    logs) cmd_logs ;;
    -h|--help|help|"") usage ;;
    *)
      echo "Unknown command: $1"
      usage
      exit 1
      ;;
  esac
}

cd "$ROOT"
main "$@"
