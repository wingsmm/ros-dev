#!/usr/bin/env bash
set -euo pipefail

# laser_odom_experiment.sh
# Owns only rf2o -> /odom_laser and optional rosbag.
# It does not start bringup, JSON, or roscore.

ROOT="$(cd "$(dirname "$0")" && pwd)"
STACK_TAG="laser_odom_experiment"

ROS_SETUP="${ROS_SETUP:-/opt/ros/melodic/setup.bash}"
WS_SETUP="${WS_SETUP:-$HOME/ros_ws/devel/setup.bash}"
LOG_DIR="${LOG_DIR:-$HOME/xtark_logs/laser_odom_experiment}"
BAG_DIR="${BAG_DIR:-$LOG_DIR/bags}"
PID_DIR="$LOG_DIR/pids"
LAUNCH_PKG="${LAUNCH_PKG:-xtark_laser_odometry}"
LAUNCH_FILE="${LAUNCH_FILE:-rf2o_odom_laser.launch}"
RECORD_TOPICS="${RECORD_TOPICS:-/odom /odom_laser /scan}"

usage() {
  cat <<EOF
Usage: ${STACK_TAG}.sh <command>

Commands:
  start   Start rf2o -> /odom_laser (requires /scan from another stack)
  stop    Stop rf2o + this stack's rosbag only
  record  Start rosbag (${RECORD_TOPICS})
  logs    Tail rf2o log

LOG_DIR=${LOG_DIR}
BAG_DIR=${BAG_DIR}
EOF
}

source_ros() {
  if [ ! -f "$ROS_SETUP" ] || [ ! -f "$WS_SETUP" ]; then
    echo "[ERR] ROS or workspace setup missing"
    exit 1
  fi
  set +u
  # shellcheck disable=SC1090
  source "$ROS_SETUP"
  # shellcheck disable=SC1090
  source "$WS_SETUP"
  set -u
}

pid_alive() {
  local f="$1"
  [ -f "$f" ] || return 1
  local pid
  pid="$(cat "$f")"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

write_pid() {
  mkdir -p "$PID_DIR"
  echo "$2" >"$PID_DIR/$1.pid"
}

stop_pid() {
  local name="$1"
  local f="$PID_DIR/$name.pid"
  if pid_alive "$f"; then
    kill "$(cat "$f")" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$f"
}

is_rf2o_running() {
  pgrep -f "roslaunch ${LAUNCH_PKG} ${LAUNCH_FILE}" >/dev/null 2>&1
}

wait_for_master() {
  local i=0
  while ! rostopic list &>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge 20 ]; then
      echo "[ERR] rosmaster not ready"
      exit 1
    fi
    sleep 1
  done
}

cmd_start() {
  mkdir -p "$LOG_DIR" "$PID_DIR"
  source_ros
  wait_for_master

  if ! rospack find rf2o_laser_odometry >/dev/null 2>&1; then
    echo "[ERR] rf2o_laser_odometry not found"
    exit 1
  fi
  if ! rospack find "$LAUNCH_PKG" >/dev/null 2>&1; then
    echo "[ERR] package ${LAUNCH_PKG} not found"
    exit 1
  fi

  if pid_alive "$PID_DIR/rf2o.pid" || is_rf2o_running; then
    echo "[OK] rf2o already running"
    return 0
  fi

  echo "[INFO] roslaunch ${LAUNCH_PKG} ${LAUNCH_FILE}"
  nohup roslaunch "$LAUNCH_PKG" "$LAUNCH_FILE" >"$LOG_DIR/rf2o.log" 2>&1 &
  write_pid rf2o "$!"
  sleep 2
  if rostopic list 2>/dev/null | grep -qx /odom_laser; then
    echo "[OK] /odom_laser up"
  else
    echo "[WARN] /odom_laser not seen yet"
  fi
}

cmd_stop() {
  stop_pid rosbag
  pkill -f "rosbag record -O ${BAG_DIR}/laser_odom_experiment_" 2>/dev/null || true
  rm -f "$PID_DIR/rosbag.path"

  stop_pid rf2o
  echo "[OK] ${STACK_TAG} stop done"
}

cmd_record() {
  source_ros
  wait_for_master
  for t in /odom /odom_laser /scan; do
    if ! rostopic list 2>/dev/null | grep -qx "$t"; then
      echo "[ERR] missing $t"
      exit 1
    fi
  done
  if pid_alive "$PID_DIR/rosbag.pid"; then
    echo "[OK] already recording"
    cat "$PID_DIR/rosbag.path" 2>/dev/null || true
    return 0
  fi
  mkdir -p "$BAG_DIR" "$PID_DIR"
  local bag="${BAG_DIR}/laser_odom_experiment_$(date +%Y%m%d_%H%M%S).bag"
  # shellcheck disable=SC2086
  nohup rosbag record -O "$bag" $RECORD_TOPICS >"$LOG_DIR/rosbag.log" 2>&1 &
  write_pid rosbag "$!"
  echo "$bag" >"$PID_DIR/rosbag.path"
  echo "[OK] recording -> $bag"
}

cmd_logs() {
  mkdir -p "$LOG_DIR"
  touch "$LOG_DIR/rf2o.log" "$LOG_DIR/rosbag.log"
  tail -n 80 -f "$LOG_DIR/rf2o.log" "$LOG_DIR/rosbag.log"
}

main() {
  case "${1:-}" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    record) cmd_record ;;
    logs) cmd_logs ;;
    -h|--help|help|"") usage ;;
    *) echo "Unknown: $1"; usage; exit 1 ;;
  esac
}

cd "$ROOT"
main "$@"
