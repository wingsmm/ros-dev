#!/usr/bin/env bash
set -euo pipefail

# robot_control_stack.sh
# Qt "机器人" module only: roscore + bringup + json_base_adapter.
# Does NOT start camera, navigation, SLAM, or rosbag.

ROOT="$(cd "$(dirname "$0")" && pwd)"
STACK_TAG="robot_control_stack"

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

LOG_DIR="${LOG_DIR:-$HOME/xtark_logs/robot_control_stack}"
PID_DIR="$LOG_DIR/pids"
ROSCORE_LOG="$LOG_DIR/roscore.log"
BRINGUP_LOG="$LOG_DIR/bringup.log"
JSON_LOG="$LOG_DIR/json_adapter.log"

usage() {
  cat <<EOF
Usage: ${STACK_TAG}.sh <command>

Commands:
  start    Start roscore (if needed) + bringup + json_base_adapter
  stop     Stop only processes started by this script
  restart  stop then start
  status   Show ROS env, ports, topics, and process health
  logs     Tail this stack logs
  help     Show this help

Does NOT start camera, web_video_server, gmapping, move_base, rf2o, or rosbag.
If robot_stack.sh or android_stack.sh already owns bringup/json, resolve conflicts first.

Qt JSON gateway: ${HOST_IP}:8765
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

check_stack_conflicts() {
  if pgrep -f "robot_stack.sh start" >/dev/null 2>&1; then
    echo "[WARN] robot_stack.sh may be active; avoid duplicate bringup/json"
  fi
  if pgrep -f "android_stack.sh start" >/dev/null 2>&1; then
    echo "[WARN] android_stack.sh may be active; it also uses bringup/roscore"
  fi
  if pgrep -f "roslaunch xtark_driver xtark_camera.launch" >/dev/null 2>&1; then
    echo "[INFO] camera stack detected (not started by this script)"
  fi
}

topic_hz_with_timeout() {
  local topic="$1"
  local timeout_sec="${2:-5}"
  timeout "$timeout_sec" rostopic hz "$topic" 2>/dev/null | head -n 3 || echo "[WARN] ${topic} hz probe timeout"
}

cmd_start() {
  mkdir -p "$LOG_DIR" "$PID_DIR"
  source_ros
  check_stack_conflicts

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
    echo "[ERR] bringup already running (other stack); stop it first"
    exit 1
  else
    echo "[INFO] starting bringup"
    nohup roslaunch "$BRINGUP_PKG" "$BRINGUP_LAUNCH" >"$BRINGUP_LOG" 2>&1 &
    write_pid bringup "$!"
    wait_for_topic /odom 30 || true
    wait_for_topic /scan 30 || true
  fi

  if pid_alive "$PID_DIR/json.pid"; then
    echo "[OK] json adapter already running (this stack)"
  elif pgrep -f "roslaunch $JSON_PKG $JSON_LAUNCH" >/dev/null 2>&1; then
    echo "[ERR] json adapter already running (other stack); stop it first"
    exit 1
  else
    echo "[INFO] starting json adapter"
    nohup roslaunch "$JSON_PKG" "$JSON_LAUNCH" >"$JSON_LOG" 2>&1 &
    write_pid json "$!"
    wait_for_port 8765 25 || true
  fi

  echo "[OK] ${STACK_TAG} start done"
  echo "Qt JSON gateway: ${HOST_IP}:8765"
}

cmd_stop() {
  stop_pid json
  stop_pid bringup
  stop_pid roscore
  echo "[OK] ${STACK_TAG} stop done (only PIDs started by this script)"
}

cmd_restart() {
  cmd_stop
  cmd_start
}

cmd_status() {
  source_ros
  echo "ROS_MASTER_URI=$ROS_MASTER_URI"
  echo "ROS_IP=$ROS_IP"
  echo "---ports---"
  if is_listening 11311; then echo "roscore:11311 listening"; else echo "roscore:11311 closed"; fi
  if is_listening 8765; then echo "json_gateway:8765 listening"; else echo "json_gateway:8765 closed"; fi
  echo "---processes (this stack PIDs)---"
  for name in roscore bringup json; do
    f="$PID_DIR/$name.pid"
    if pid_alive "$f"; then
      echo "$name pid=$(cat "$f")"
    else
      echo "$name not tracked"
    fi
  done
  echo "---processes (pgrep)---"
  pgrep -af "roscore|roslaunch $BRINGUP_PKG $BRINGUP_LAUNCH|roslaunch $JSON_PKG $JSON_LAUNCH|json_base_adapter" || true
  echo "---topics---"
  for topic in /cmd_vel /odom /scan /voltage; do
    echo "[$topic]"
    rostopic info "$topic" 2>/dev/null || echo "  (missing)"
  done
  echo "---rates (5s timeout)---"
  topic_hz_with_timeout /scan 5
  topic_hz_with_timeout /odom 5
  check_stack_conflicts
}

cmd_logs() {
  mkdir -p "$LOG_DIR"
  touch "$ROSCORE_LOG" "$BRINGUP_LOG" "$JSON_LOG"
  tail -n 40 -f "$ROSCORE_LOG" "$BRINGUP_LOG" "$JSON_LOG"
}

main() {
  case "${1:-help}" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    restart) cmd_restart ;;
    status) cmd_status ;;
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
