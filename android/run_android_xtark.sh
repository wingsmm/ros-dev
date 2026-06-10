#!/usr/bin/env bash
set -euo pipefail

HOST_IP="${HOST_IP:-192.168.1.169}"
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://${HOST_IP}:11311}"
export ROS_IP="${ROS_IP:-${HOST_IP}}"
unset ROS_HOSTNAME
export XTARK_LOG_DIR="${XTARK_LOG_DIR:-$HOME/xtark_logs/android}"
BRINGUP_PKG="${BRINGUP_PKG:-xtark_driver}"
BRINGUP_LAUNCH="${BRINGUP_LAUNCH:-xtark_bringup.launch}"
CAMERA_ENABLE="${CAMERA_ENABLE:-1}"
CAMERA_PKG="${CAMERA_PKG:-xtark_driver}"
CAMERA_LAUNCH="${CAMERA_LAUNCH:-xtark_camera.launch}"

usage() {
  cat <<EOF
Usage: run_android.sh <command>

Commands:
  start    Start roscore + xtark bringup for Android/rosjava testing
  status   Show ROS master, topics, and related processes
  stop     Stop Android-test bringup processes
  logs     Tail Android-test logs

Android app Master URI:
  ${ROS_MASTER_URI}

Environment exported before launch:
  ROS_MASTER_URI=${ROS_MASTER_URI}
  ROS_IP=${ROS_IP}
  XTARK_LOG_DIR=${XTARK_LOG_DIR}
  CAMERA_ENABLE=${CAMERA_ENABLE}
EOF
}

source_ros() {
  set +u
  source /opt/ros/melodic/setup.bash
  source "$HOME/ros_ws/devel/setup.bash"
  set -u
}

is_listening_11311() {
  (ss -lnt 2>/dev/null || netstat -lnt 2>/dev/null) | grep -q ':11311'
}

wait_master() {
  i=0
  while [ "$i" -lt 20 ]; do
    if is_listening_11311; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  echo "[ERR] roscore did not open 11311"
  tail -80 "$XTARK_LOG_DIR/roscore.log" 2>/dev/null || true
  return 1
}

status() {
  source_ros
  echo "---env---"
  echo "ROS_MASTER_URI=$ROS_MASTER_URI"
  echo "ROS_IP=$ROS_IP"
  echo "---11311---"
  (ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null) | grep 11311 || true
  echo "---topics---"
  rostopic list 2>&1 | head -80 || true
  echo "---cmd_vel_info---"
  rostopic info /cmd_vel 2>&1 || true
  echo "---camera_info---"
  rostopic info /image_raw/compressed 2>&1 || true
  echo "---processes---"
  pgrep -af 'roscore|rosmaster|roslaunch xtark_driver xtark_bringup.launch|roslaunch xtark_driver xtark_camera.launch|uvc_camera_node|web_video_server|image_transport.*republish' || true
}

start() {
  source_ros
  mkdir -p "$XTARK_LOG_DIR"

  if ! is_listening_11311; then
    echo "Starting roscore with ROS_IP=$ROS_IP"
    nohup roscore >"$XTARK_LOG_DIR/roscore.log" 2>&1 &
    echo "roscore started pid=$! log=$XTARK_LOG_DIR/roscore.log"
    wait_master
  else
    echo "roscore already listening on 11311"
  fi

  if pgrep -af "roslaunch $BRINGUP_PKG $BRINGUP_LAUNCH" >/dev/null; then
    echo "xtark bringup already running"
    status
    return 0
  fi

  echo "Android app Master URI: $ROS_MASTER_URI"
  echo "Starting xtark bringup only with ROS_IP=$ROS_IP"
  nohup roslaunch "$BRINGUP_PKG" "$BRINGUP_LAUNCH" \
    >"$XTARK_LOG_DIR/bringup.log" 2>&1 &
  echo "bringup started pid=$! log=$XTARK_LOG_DIR/bringup.log"

  if [ "$CAMERA_ENABLE" = "1" ]; then
    if [ ! -e /dev/video0 ]; then
      echo "WARN: /dev/video0 not found; camera not started"
    elif pgrep -af "roslaunch $CAMERA_PKG $CAMERA_LAUNCH" >/dev/null; then
      echo "camera already running"
    else
      echo "Starting camera: roslaunch $CAMERA_PKG $CAMERA_LAUNCH"
      nohup roslaunch "$CAMERA_PKG" "$CAMERA_LAUNCH" \
        >"$XTARK_LOG_DIR/camera.log" 2>&1 &
      echo "camera started pid=$! log=$XTARK_LOG_DIR/camera.log"
    fi
  fi

  sleep 5
  status
}

stop() {
  pkill -f "roslaunch $CAMERA_PKG $CAMERA_LAUNCH" || true
  pkill -f 'uvc_camera_node' || true
  pkill -f "roslaunch $BRINGUP_PKG $BRINGUP_LAUNCH" || true
  pkill -f "$BRINGUP_LAUNCH" || true
  pkill -f 'rosmaster --core -p 11311' || true
  pkill -f 'roscore' || true
  echo "Android-test roscore/bringup stop requested"
}

cmd="${1:-help}"
case "$cmd" in
  start) start ;;
  status) status ;;
  stop) stop ;;
  logs) tail -120 "$XTARK_LOG_DIR/roscore.log" "$XTARK_LOG_DIR/bringup.log" "$XTARK_LOG_DIR/camera.log" 2>/dev/null || true ;;
  -h|--help|help|"") usage ;;
  *)
    echo "Unknown command: $cmd"
    usage
    exit 1
    ;;
esac
