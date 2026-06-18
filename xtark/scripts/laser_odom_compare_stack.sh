#!/usr/bin/env bash
set -euo pipefail

# laser_odom_compare_stack.sh
# Owns only this compare stack: roscore + bringup + JSON + rf2o + rosbag.
# It does not call or stop robot_stack/android_stack. Stop conflicting stacks manually.

ROOT="$(cd "$(dirname "$0")" && pwd)"
STACK_TAG="laser_odom_compare_stack"

HOST_IP="${HOST_IP:-192.168.1.169}"
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://${HOST_IP}:11311}"
export ROS_IP="${ROS_IP:-${HOST_IP}}"
unset ROS_HOSTNAME

ROS_SETUP="${ROS_SETUP:-/opt/ros/melodic/setup.bash}"
WS_SETUP="${WS_SETUP:-$HOME/ros_ws/devel/setup.bash}"

BRINGUP_PKG="${BRINGUP_PKG:-xtark_driver}"
BRINGUP_LAUNCH="${BRINGUP_LAUNCH:-xtark_bringup.launch}"
JSON_PKG="${JSON_PKG:-xtark_json_bridge}"
JSON_LAUNCH="${JSON_LAUNCH:-json_base_adapter.launch}"
LASER_ODOM_PKG="${LASER_ODOM_PKG:-xtark_laser_odometry}"
LASER_ODOM_LAUNCH="${LASER_ODOM_LAUNCH:-rf2o_odom_laser.launch}"

LOG_DIR="${LOG_DIR:-$HOME/xtark_logs/laser_odom_compare}"
BAG_DIR="${BAG_DIR:-$LOG_DIR/bags}"
PID_DIR="$LOG_DIR/pids"
ROSCORE_LOG="$LOG_DIR/roscore.log"
BRINGUP_LOG="$LOG_DIR/bringup.log"
JSON_LOG="$LOG_DIR/json_adapter.log"
RF2O_LOG="$LOG_DIR/rf2o.log"
BAG_LOG="$LOG_DIR/rosbag.log"
RECORD_TOPICS="${RECORD_TOPICS:-/cmd_vel /odom /odom_laser /scan}"

usage() {
  cat <<EOF
Usage: ${STACK_TAG}.sh <command>

Commands:
  start   Start this stack only (roscore + bringup + JSON + rf2o)
  stop    Stop only processes started by this script + its rosbag
  record  Start rosbag for this stack (${RECORD_TOPICS})
  logs    Tail this stack logs

Does NOT start/stop robot_stack or android_stack.
If ports/topics conflict, stop the other stack first yourself.

Qt: JSON ${HOST_IP}:8765 -> /cmd_vel

LOG_DIR=${LOG_DIR}
BAG_DIR=${BAG_DIR}
EOF
}

source_ros() {
  if [ ! -f "$ROS_SETUP" ]; then
    echo "[ERR] ROS setup not found: $ROS_SETUP"
    exit 1
  fi
  if [ ! -f "$WS_SETUP" ]; then
    echo "[ERR] workspace setup not found: $WS_SETUP"
    exit 1
  fi
  set +u
  # shellcheck disable=SC1090
  source "$ROS_SETUP"
  # shellcheck disable=SC1090
  source "$WS_SETUP"
  set -u
}

is_listening() {
  local port="$1"
  (ss -lnt 2>/dev/null || netstat -lnt 2>/dev/null) | grep -q ":${port}"
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
    local pid
    pid="$(cat "$f")"
    echo "[INFO] stop $name pid=$pid"
    kill "$pid" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$f"
}

wait_for_rosmaster_api() {
  local max="${1:-30}"
  local i=0
  while ! rostopic list &>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
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
      echo "[WARN] ${topic} not ready after ${max}s"
      return 1
    fi
    sleep 1
  done
  echo "[OK] ${topic}"
}

wait_for_port() {
  local port="$1"
  local max="${2:-20}"
  local i=0
  while ! is_listening "$port"; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      return 1
    fi
    sleep 1
  done
  echo "[OK] :${port}"
}

cmd_start() {
  mkdir -p "$LOG_DIR" "$BAG_DIR" "$PID_DIR"
  source_ros

  if is_listening 11311 && ! pid_alive "$PID_DIR/roscore.pid"; then
    echo "[WARN] roscore already up (not started by this stack); reusing"
    wait_for_rosmaster_api 15 || exit 1
  elif ! is_listening 11311; then
    echo "[INFO] starting roscore"
    nohup roscore >"$ROSCORE_LOG" 2>&1 &
    write_pid roscore "$!"
    wait_for_rosmaster_api 30 || exit 1
  fi

  if pid_alive "$PID_DIR/bringup.pid"; then
    echo "[OK] bringup already running (this stack)"
  elif pgrep -f "roslaunch $BRINGUP_PKG $BRINGUP_LAUNCH" >/dev/null 2>&1; then
    echo "[WARN] bringup already running (other stack?); skip start"
  else
    echo "[INFO] starting bringup"
    nohup roslaunch "$BRINGUP_PKG" "$BRINGUP_LAUNCH" >"$BRINGUP_LOG" 2>&1 &
    write_pid bringup "$!"
    wait_for_topic /scan 30 || true
    wait_for_topic /odom 30 || true
  fi

  if pid_alive "$PID_DIR/json.pid"; then
    echo "[OK] json adapter already running (this stack)"
  elif pgrep -f "roslaunch $JSON_PKG $JSON_LAUNCH" >/dev/null 2>&1; then
    echo "[WARN] json adapter already running (other stack?); skip start"
  else
    echo "[INFO] starting json adapter"
    nohup roslaunch "$JSON_PKG" "$JSON_LAUNCH" >"$JSON_LOG" 2>&1 &
    write_pid json "$!"
    wait_for_port 8765 25 || true
  fi

  if ! rospack find rf2o_laser_odometry >/dev/null 2>&1; then
    echo "[ERR] rf2o_laser_odometry not found"
    exit 1
  fi
  if ! rospack find "$LASER_ODOM_PKG" >/dev/null 2>&1; then
    echo "[ERR] package $LASER_ODOM_PKG not found"
    exit 1
  fi

  if pid_alive "$PID_DIR/rf2o.pid"; then
    echo "[OK] rf2o already running (this stack)"
  elif pgrep -f "roslaunch $LASER_ODOM_PKG $LASER_ODOM_LAUNCH" >/dev/null 2>&1; then
    echo "[WARN] rf2o already running (laser_odom_experiment?); skip start"
  else
    echo "[INFO] starting rf2o"
    nohup roslaunch "$LASER_ODOM_PKG" "$LASER_ODOM_LAUNCH" >"$RF2O_LOG" 2>&1 &
    write_pid rf2o "$!"
    sleep 2
    wait_for_topic /odom_laser 30 || true
  fi

  echo "[OK] ${STACK_TAG} start done"
  echo "Qt JSON: ${HOST_IP}:8765  |  record: $0 record"
}

cmd_stop() {
  stop_pid rosbag
  pkill -f "rosbag record -O ${BAG_DIR}/laser_odom_compare_" 2>/dev/null || true
  rm -f "$PID_DIR/rosbag.path"

  stop_pid rf2o
  stop_pid json
  stop_pid bringup
  stop_pid roscore

  echo "[OK] ${STACK_TAG} stop done (only PIDs started by this script)"
}

cmd_record() {
  source_ros
  wait_for_rosmaster_api 15 || { echo "[ERR] rosmaster down"; exit 1; }

  for topic in /cmd_vel /odom /odom_laser /scan; do
    if ! rostopic list 2>/dev/null | grep -qx "$topic"; then
      echo "[ERR] missing $topic - run: $0 start"
      exit 1
    fi
  done

  if pid_alive "$PID_DIR/rosbag.pid"; then
    echo "[OK] already recording pid=$(cat "$PID_DIR/rosbag.pid")"
    cat "$PID_DIR/rosbag.path" 2>/dev/null || true
    return 0
  fi

  mkdir -p "$BAG_DIR" "$PID_DIR"
  local bag_path
  bag_path="${BAG_DIR}/laser_odom_compare_$(date +%Y%m%d_%H%M%S).bag"
  echo "[INFO] record ${RECORD_TOPICS} -> ${bag_path}"
  # shellcheck disable=SC2086
  nohup rosbag record -O "$bag_path" $RECORD_TOPICS >"$BAG_LOG" 2>&1 &
  write_pid rosbag "$!"
  echo "$bag_path" >"$PID_DIR/rosbag.path"
  echo "[OK] rosbag pid=$!"
}

cmd_logs() {
  mkdir -p "$LOG_DIR"
  touch "$ROSCORE_LOG" "$BRINGUP_LOG" "$JSON_LOG" "$RF2O_LOG" "$BAG_LOG"
  tail -n 40 -f "$ROSCORE_LOG" "$BRINGUP_LOG" "$JSON_LOG" "$RF2O_LOG" "$BAG_LOG"
}

main() {
  case "${1:-}" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    record) cmd_record ;;
    logs) cmd_logs ;;
    -h|--help|help|"") usage ;;
    *)
      echo "Unknown: $1"
      usage
      exit 1
      ;;
  esac
}

cd "$ROOT"
main "$@"
