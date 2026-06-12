#!/bin/bash
set -eo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

ROS_SETUP="${ROS_SETUP:-/opt/ros/melodic/setup.bash}"
WS_SETUP="${WS_SETUP:-$HOME/ros_ws/devel/setup.bash}"
LOG_DIR="${XTARK_LOG_DIR:-$HOME/xtark_logs}"

source_ros() {
  if [ ! -f "$ROS_SETUP" ]; then
    echo "ERROR: ROS setup not found: $ROS_SETUP"
    exit 1
  fi
  if [ ! -f "$WS_SETUP" ]; then
    echo "ERROR: workspace setup not found: $WS_SETUP"
    echo "Run: cd ~/ros_ws && catkin_make && source devel/setup.bash"
    exit 1
  fi
  # shellcheck disable=SC1090,SC1091
  source "$ROS_SETUP"
  # shellcheck disable=SC1090,SC1091
  source "$WS_SETUP"
}

wait_for_master() {
  local max="${1:-30}"
  local i=0
  while ! rostopic list &>/dev/null; do
    sleep 1
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "ERROR: rosmaster not ready after ${max}s"
      return 1
    fi
  done
}

wait_for_odom() {
  local max="${1:-20}"
  local i=0
  while ! rostopic list 2>/dev/null | grep -qx '/odom'; do
    sleep 1
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "WARN: /odom not seen after ${max}s; starting json adapter anyway"
      return 0
    fi
  done
}

usage() {
  cat <<'EOF'
Usage: json_stack.sh <command>

Commands:
  bringup   Foreground: xtark_driver bringup (terminal 1)
  json      Foreground: json_base_adapter (terminal 2, bringup must be up)
  start     Background: bringup then json adapter (logs under ~/xtark_logs)
  stop      Stop background bringup + json adapter
  status    Show matching roslaunch processes
  logs      Tail background logs (bringup + json)

Environment:
  ROS_SETUP      default /opt/ros/melodic/setup.bash
  WS_SETUP       default ~/ros_ws/devel/setup.bash
  XTARK_LOG_DIR  default ~/xtark_logs

Copy to xtark (example):
  scp -r xtark/scripts xtark@192.168.1.169:~/ros_ws/
  ssh xtark@192.168.1.169 '~/ros_ws/scripts/json_stack.sh start'
EOF
}

cmd_bringup() {
  source_ros
  exec roslaunch xtark_driver xtark_bringup.launch
}

cmd_json() {
  source_ros
  exec roslaunch xtark_json_bridge json_base_adapter.launch
}

is_running() {
  pgrep -f "$1" >/dev/null 2>&1
}

cmd_start() {
  mkdir -p "$LOG_DIR"
  source_ros

  if is_running "xtark_bringup.launch"; then
    echo "bringup already running"
  else
    nohup roslaunch xtark_driver xtark_bringup.launch \
      >"$LOG_DIR/bringup.log" 2>&1 &
    echo "bringup started pid=$! log=$LOG_DIR/bringup.log"
  fi

  wait_for_master 30
  wait_for_odom 20

  if is_running "json_base_adapter.launch"; then
    echo "json adapter already running"
  else
    nohup roslaunch xtark_json_bridge json_base_adapter.launch \
      >"$LOG_DIR/json_adapter.log" 2>&1 &
    echo "json adapter started pid=$! log=$LOG_DIR/json_adapter.log"
  fi

  echo "JSON TCP should listen on 0.0.0.0:8765 when adapter is ready"
  echo "Check: $0 status   or   $0 logs"
}

cmd_stop() {
  pkill -f "json_base_adapter.launch" 2>/dev/null || true
  pkill -f "json_base_adapter_node.py" 2>/dev/null || true
  pkill -f "xtark_bringup.launch" 2>/dev/null || true
  sleep 1
  if is_running "json_base_adapter" || is_running "xtark_bringup.launch"; then
    echo "WARN: some processes may still be running; run: $0 status"
    exit 1
  fi
  echo "stopped"
}

cmd_status() {
  if pgrep -af "xtark_bringup.launch|json_base_adapter" 2>/dev/null; then
    return 0
  fi
  echo "not running"
}

cmd_logs() {
  mkdir -p "$LOG_DIR"
  touch "$LOG_DIR/bringup.log" "$LOG_DIR/json_adapter.log"
  tail -n 40 -f "$LOG_DIR/bringup.log" "$LOG_DIR/json_adapter.log"
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    bringup) cmd_bringup ;;
    json) cmd_json ;;
    start) cmd_start ;;
    stop) cmd_stop ;;
    status) cmd_status ;;
    logs) cmd_logs ;;
    -h|--help|help|"") usage ;;
    *)
      echo "Unknown command: $cmd"
      usage
      exit 1
      ;;
  esac
}

cd "$ROOT"
main "$@"
