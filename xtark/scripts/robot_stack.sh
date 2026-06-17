#!/usr/bin/env bash
set -euo pipefail

# robot_stack.sh: one-command robot-side stack for Android observation + Qt preview/control.
#
# start  = roscore + base bringup + camera + JSON adapter
# stop   = stop JSON adapter + camera + base bringup
# status = show ports, topics, and processes needed by Android and Qt

HOST_IP="${HOST_IP:-192.168.1.169}"
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://${HOST_IP}:11311}"
export ROS_IP="${ROS_IP:-${HOST_IP}}"
unset ROS_HOSTNAME

ROS_SETUP="${ROS_SETUP:-/opt/ros/melodic/setup.bash}"
WS_SETUP="${WS_SETUP:-$HOME/ros_ws/devel/setup.bash}"

BRINGUP_PKG="${BRINGUP_PKG:-xtark_driver}"
BRINGUP_LAUNCH="${BRINGUP_LAUNCH:-xtark_bringup.launch}"
CAMERA_PKG="${CAMERA_PKG:-xtark_driver}"
CAMERA_LAUNCH="${CAMERA_LAUNCH:-xtark_camera.launch}"
JSON_PKG="${JSON_PKG:-xtark_json_bridge}"
JSON_LAUNCH="${JSON_LAUNCH:-json_base_adapter.launch}"

LOG_DIR="${LOG_DIR:-$HOME/xtark_logs/robot_stack}"
ROSCORE_LOG="$LOG_DIR/roscore.log"
BRINGUP_LOG="$LOG_DIR/bringup.log"
CAMERA_LOG="$LOG_DIR/camera.log"
JSON_LOG="$LOG_DIR/json_adapter.log"

usage() {
  cat <<EOF
Usage: robot_stack.sh <command>

Commands:
  start   Start roscore + base bringup + camera + JSON adapter
  stop    Stop JSON adapter + camera + base bringup + roscore
  status  Show Android/Qt control and camera diagnostics

Android:
  Master URI: ${ROS_MASTER_URI}
  Camera topic: /image_raw/compressed
  Control topic: /cmd_vel

Qt:
  MJPEG URL: http://${HOST_IP}:8080/stream?topic=/camera/image_raw
  JSON gateway: ${HOST_IP}:8765

Env:
  ROS_MASTER_URI=${ROS_MASTER_URI}
  ROS_IP=${ROS_IP}
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

is_listening() {
  local port="$1"
  (ss -lnt 2>/dev/null || netstat -lnt 2>/dev/null) | grep -q ":${port}"
}

is_running() {
  pgrep -f "$1" >/dev/null 2>&1
}

wait_for_rosmaster_api() {
  local max="${1:-30}"
  local i=0
  while ! rostopic list &>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "[ERR] rosmaster API not ready after ${max}s"
      return 1
    fi
    sleep 1
  done
}

wait_for_topic() {
  local topic="$1"
  local max="${2:-20}"
  local i=0
  while ! rostopic list 2>/dev/null | grep -qx "$topic"; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "[WARN] topic $topic not available after ${max}s"
      return 0
    fi
    sleep 1
  done
  echo "[OK] topic $topic available"
}

wait_for_port() {
  local port="$1"
  local name="${2:-port}"
  local max="${3:-20}"
  local i=0
  while ! is_listening "$port"; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "[WARN] ${name}:${port} not listening after ${max}s"
      return 0
    fi
    sleep 1
  done
  echo "[OK] ${name}:${port} listening"
}

start_roscore_if_needed() {
  mkdir -p "$LOG_DIR"
  if is_listening 11311; then
    echo "[OK] roscore already listening on 11311"
    wait_for_rosmaster_api 10 || true
    return 0
  fi

  echo "[INFO] Starting roscore (ROS_IP=$ROS_IP)"
  nohup roscore >"$ROSCORE_LOG" 2>&1 &
  echo "[OK] roscore started pid=$! log=$ROSCORE_LOG"
  wait_for_rosmaster_api 30
}

start_bringup() {
  if is_running "roslaunch $BRINGUP_PKG $BRINGUP_LAUNCH"; then
    echo "[OK] bringup already running"
    return 0
  fi
  echo "[INFO] Starting bringup: roslaunch $BRINGUP_PKG $BRINGUP_LAUNCH"
  nohup roslaunch "$BRINGUP_PKG" "$BRINGUP_LAUNCH" >"$BRINGUP_LOG" 2>&1 &
  echo "[OK] bringup started pid=$! log=$BRINGUP_LOG"
  wait_for_topic /odom 25
}

start_camera() {
  if is_running "roslaunch $CAMERA_PKG $CAMERA_LAUNCH"; then
    echo "[OK] camera already running"
    return 0
  fi
  echo "[INFO] Starting camera: roslaunch $CAMERA_PKG $CAMERA_LAUNCH"
  nohup roslaunch "$CAMERA_PKG" "$CAMERA_LAUNCH" >"$CAMERA_LOG" 2>&1 &
  echo "[OK] camera started pid=$! log=$CAMERA_LOG"
  wait_for_topic /image_raw/compressed 25
  wait_for_topic /camera/image_raw 25
  wait_for_port 8080 web_video_server 25
}

start_json_adapter() {
  if is_running "roslaunch $JSON_PKG $JSON_LAUNCH"; then
    echo "[OK] JSON adapter already running"
    return 0
  fi
  echo "[INFO] Starting JSON adapter: roslaunch $JSON_PKG $JSON_LAUNCH"
  nohup roslaunch "$JSON_PKG" "$JSON_LAUNCH" >"$JSON_LOG" 2>&1 &
  echo "[OK] JSON adapter started pid=$! log=$JSON_LOG"
  wait_for_port 8765 json_gateway 25
}

start() {
  source_ros
  start_roscore_if_needed
  start_bringup
  start_camera
  start_json_adapter
  echo ""
  echo "[OK] robot stack start requested"
  echo "Android Master URI: $ROS_MASTER_URI"
  echo "Android camera topic: /image_raw/compressed"
  echo "Qt MJPEG URL: http://$HOST_IP:8080/stream?topic=/camera/image_raw"
  echo "Qt JSON gateway: $HOST_IP:8765"
}

stop() {
  pkill -f "roslaunch $JSON_PKG $JSON_LAUNCH" || true
  pkill -f 'json_base_adapter_node.py' || true
  pkill -f "roslaunch $CAMERA_PKG $CAMERA_LAUNCH" || true
  pkill -f 'uvc_camera_node' || true
  pkill -f 'image_transport/republish' || true
  pkill -f 'web_video_server' || true
  pkill -f "roslaunch $BRINGUP_PKG $BRINGUP_LAUNCH" || true
  pkill -f 'roscore' || true
  pkill -f 'rosmaster' || true
  echo "[OK] stop requested"
}

print_port() {
  local port="$1"
  local name="$2"
  if is_listening "$port"; then
    echo "$name:$port listening"
  else
    echo "$name:$port closed"
  fi
}

status() {
  source_ros
  echo "ROS_MASTER_URI=$ROS_MASTER_URI"
  echo "ROS_IP=$ROS_IP"
  echo "ANDROID_ROS_TOPIC=/image_raw/compressed"
  echo "QT_MJPEG_URL=http://$HOST_IP:8080/stream?topic=/camera/image_raw"
  echo "QT_JSON_GATEWAY=$HOST_IP:8765"
  echo "---ports---"
  print_port 11311 roscore
  print_port 8080 web_video_server
  print_port 8765 json_gateway
  echo "---processes---"
  pgrep -af "roscore|roslaunch $BRINGUP_PKG $BRINGUP_LAUNCH|roslaunch $CAMERA_PKG $CAMERA_LAUNCH|roslaunch $JSON_PKG $JSON_LAUNCH|uvc_camera_node|image_transport/republish|web_video_server|json_base_adapter" || true
  echo "---topics---"
  for topic in /cmd_vel /odom /scan /image_raw/compressed /camera/image_raw; do
    echo "[$topic]"
    rostopic info "$topic" 2>/dev/null || true
  done
  if command -v curl >/dev/null 2>&1; then
    echo "---HTTP snapshot probe---"
    curl -fsS --max-time 2 -o /dev/null \
      -w 'http_code=%{http_code} content_type=%{content_type}\n' \
      "http://$HOST_IP:8080/snapshot?topic=/camera/image_raw" || true
  fi
}

cmd="${1:-help}"
case "$cmd" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  -h|--help|help|"") usage ;;
  *) echo "Unknown command: $cmd"; usage; exit 1 ;;
esac
