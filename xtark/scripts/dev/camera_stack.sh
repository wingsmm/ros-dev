#!/usr/bin/env bash
set -euo pipefail

# dev/camera_stack.sh — camera-only debugging (not a daily entrypoint; use qt_stack.sh).

HOST_IP="${HOST_IP:-192.168.1.168}"
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://${HOST_IP}:11311}"
export ROS_IP="${ROS_IP:-${HOST_IP}}"
unset ROS_HOSTNAME

ROS_SETUP="${ROS_SETUP:-/opt/ros/melodic/setup.bash}"
WS_SETUP="${WS_SETUP:-$HOME/ros_ws/devel/setup.bash}"

CAMERA_PKG="${CAMERA_PKG:-xtark_driver}"
CAMERA_LAUNCH="${CAMERA_LAUNCH:-xtark_camera.launch}"

LOG_DIR="${LOG_DIR:-$HOME/xtark_logs/camera_only}"
LOG_FILE="$LOG_DIR/camera.log"

usage() {
  cat <<EOF
Usage: camera_stack.sh <command>

Commands:
  start   Start roscore (if needed) + xtark camera only
  stop    Stop camera roslaunch + nodes
  status  Show Android/Qt camera topic and HTTP diagnostics
  urls    Print Android ROS topic and Qt/Browser camera URLs
  logs    Tail recent camera log

Daily use: ~/ros_ws/scripts/qt_stack.sh start
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

is_listening_11311() {
  (ss -lnt 2>/dev/null || netstat -lnt 2>/dev/null) | grep -q ':11311'
}

wait_for_rosmaster_api() {
  local max="${1:-15}"
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

start_roscore_if_needed() {
  if is_listening_11311; then
    echo "[OK] roscore already listening on 11311"
    wait_for_rosmaster_api 10 || true
    return 0
  fi
  mkdir -p "$LOG_DIR"
  echo "[INFO] Starting roscore (ROS_IP=$ROS_IP)"
  nohup roscore >"$LOG_DIR/roscore.log" 2>&1 &
  echo "[OK] roscore started pid=$!"
  wait_for_rosmaster_api 15
}

start() {
  source_ros
  mkdir -p "$LOG_DIR"
  start_roscore_if_needed

  if pgrep -af "roslaunch $CAMERA_PKG $CAMERA_LAUNCH" >/dev/null; then
    echo "[OK] camera already running"
    return 0
  fi

  echo "[INFO] Starting camera: roslaunch $CAMERA_PKG $CAMERA_LAUNCH"
  nohup roslaunch "$CAMERA_PKG" "$CAMERA_LAUNCH" >"$LOG_FILE" 2>&1 &
  echo "[OK] camera started pid=$! log=$LOG_FILE"
}

stop() {
  pkill -f "roslaunch $CAMERA_PKG $CAMERA_LAUNCH" || true
  pkill -f 'uvc_camera_node' || true
  pkill -f 'image_transport/republish' || true
  pkill -f 'web_video_server' || true
  echo "[OK] stop requested"
}

status() {
  source_ros
  echo "ROS_MASTER_URI=$ROS_MASTER_URI"
  echo "QT_MJPEG_URL=http://$HOST_IP:8080/stream?topic=/camera/image_raw"
  rostopic info /camera/image_raw 2>/dev/null || true
}

urls() {
  cat <<EOF
Qt / Browser MJPEG preview:
  http://$HOST_IP:8080/stream?topic=/camera/image_raw
EOF
}

logs() {
  mkdir -p "$LOG_DIR"
  tail -120 "$LOG_FILE" 2>/dev/null || echo "[WARN] no log yet: $LOG_FILE"
}

cmd="${1:-help}"
case "$cmd" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  urls) urls ;;
  logs) logs ;;
  -h|--help|help|"") usage ;;
  *) echo "Unknown command: $cmd"; usage; exit 1 ;;
esac
