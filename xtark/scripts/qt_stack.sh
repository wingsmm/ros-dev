#!/usr/bin/env bash
set -euo pipefail

# qt_stack.sh — sole daily entry for PC Qt client (camera, robot, odom compare pages).

ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=stack_common.sh
source "$ROOT/stack_common.sh"

STACK_NAME="qt_stack"

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
CAMERA_ENABLE="${CAMERA_ENABLE:-1}"
CAMERA_PKG="${CAMERA_PKG:-xtark_driver}"
CAMERA_LAUNCH="${CAMERA_LAUNCH:-xtark_camera.launch}"
LASER_ODOM_ENABLE="${LASER_ODOM_ENABLE:-1}"
LASER_ODOM_PKG="${LASER_ODOM_PKG:-xtark_laser_odometry}"
LASER_ODOM_LAUNCH="${LASER_ODOM_LAUNCH:-rf2o_odom_laser.launch}"

LOG_DIR="${LOG_DIR:-$(stack_log_dir "$STACK_NAME")}"
BAG_DIR="${BAG_DIR:-$LOG_DIR/bags}"
PID_DIR="$(stack_pid_dir "$STACK_NAME")"
ROSCORE_LOG="$LOG_DIR/roscore.log"
BRINGUP_LOG="$LOG_DIR/bringup.log"
JSON_LOG="$LOG_DIR/json_adapter.log"
CAMERA_LOG="$LOG_DIR/camera.log"
RF2O_LOG="$LOG_DIR/rf2o.log"
BAG_LOG="$LOG_DIR/rosbag.log"
RECORD_TOPICS="${RECORD_TOPICS:-/cmd_vel /odom_raw /odom /imu /odom_laser /scan /tf_static /xtark/aset /xtark/bset /xtark/cset /xtark/dset /xtark/avel /xtark/bvel /xtark/cvel /xtark/dvel}"

usage() {
  cat <<EOF
Usage: ${STACK_NAME}.sh <command>

Commands:
  start     Start Qt stack (roscore + bringup + JSON + camera + rf2o by default)
  stop      Stop only processes started by this stack (+ its rosbag)
  restart   stop then start
  status    Ports, PIDs, topics, stack ownership
  logs      Tail stack logs
  record    Start rosbag (${RECORD_TOPICS})

Mutually exclusive with android_stack.sh — start will fail if the other stack is active.

Env:
  CAMERA_ENABLE=${CAMERA_ENABLE}       0 = skip camera / :8080
  LASER_ODOM_ENABLE=${LASER_ODOM_ENABLE}  0 = skip rf2o /odom_laser
  LOG_DIR=${LOG_DIR}

Qt JSON: ${HOST_IP}:8765
Qt camera: http://${HOST_IP}:8080/stream?topic=/camera/image_raw
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

_qt_pid_file() {
  echo "$PID_DIR/$1.pid"
}

_qt_pid_alive() {
  stack_pid_alive "$(_qt_pid_file "$1")"
}

_qt_write_pid() {
  stack_write_pid "$STACK_NAME" "$1" "$2"
}

_qt_stop_pid() {
  stack_stop_pid "$STACK_NAME" "$1"
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
  local required="${3:-0}"
  local i=0
  while ! rostopic list 2>/dev/null | grep -qx "$topic"; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      if [ "$required" = "1" ]; then
        echo "[ERR] ${topic} not ready after ${max}s"
      else
        echo "[WARN] ${topic} not ready after ${max}s"
      fi
      return 1
    fi
    sleep 1
  done
  echo "[OK] ${topic}"
}

wait_for_port() {
  local port="$1"
  local max="${2:-20}"
  local required="${3:-0}"
  local i=0
  while ! stack_is_listening "$port"; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      if [ "$required" = "1" ]; then
        echo "[ERR] port ${port} not listening after ${max}s"
      fi
      return 1
    fi
    sleep 1
  done
  echo "[OK] :${port}"
}

assert_start_conflicts() {
  stack_assert_no_other_owner "$STACK_NAME"
  stack_assert_no_android_nav
  stack_assert_port_owned_or_free "$STACK_NAME" roscore 11311 roscore
  stack_assert_port_owned_or_free "$STACK_NAME" json 8765 json_gateway
  if [ "$CAMERA_ENABLE" = "1" ]; then
    stack_assert_port_owned_or_free "$STACK_NAME" camera 8080 web_video_server
  fi
  stack_assert_process_owned_or_absent \
    "$STACK_NAME" bringup "roslaunch $BRINGUP_PKG $BRINGUP_LAUNCH" bringup
  stack_assert_process_owned_or_absent \
    "$STACK_NAME" json "roslaunch $JSON_PKG $JSON_LAUNCH" json_adapter
  if [ "$CAMERA_ENABLE" = "1" ]; then
    stack_assert_process_owned_or_absent \
      "$STACK_NAME" camera "roslaunch $CAMERA_PKG $CAMERA_LAUNCH" camera
  fi
  if [ "$LASER_ODOM_ENABLE" = "1" ]; then
    stack_assert_process_owned_or_absent \
      "$STACK_NAME" rf2o "roslaunch $LASER_ODOM_PKG $LASER_ODOM_LAUNCH" rf2o
  fi
}

cmd_start() {
  mkdir -p "$LOG_DIR" "$BAG_DIR" "$PID_DIR"
  source_ros
  assert_start_conflicts

  if [ "$LASER_ODOM_ENABLE" = "1" ]; then
    if ! rospack find rf2o_laser_odometry >/dev/null 2>&1; then
      echo "[ERR] rf2o_laser_odometry not found"
      exit 1
    fi
    if ! rospack find "$LASER_ODOM_PKG" >/dev/null 2>&1; then
      echo "[ERR] package $LASER_ODOM_PKG not found"
      exit 1
    fi
  fi

  stack_claim_owner "$STACK_NAME"

  _qt_start_fail() {
    echo "[ERR] ${STACK_NAME} start failed; rolling back started processes"
    cmd_stop
    exit 1
  }

  if _qt_pid_alive roscore; then
    echo "[OK] roscore already running (this stack)"
    wait_for_rosmaster_api 10 || _qt_start_fail
  elif stack_is_listening 11311; then
    echo "[ERR] roscore port 11311 in use but not owned by ${STACK_NAME}"
    _qt_start_fail
  else
    echo "[INFO] starting roscore"
    nohup roscore >"$ROSCORE_LOG" 2>&1 &
    _qt_write_pid roscore "$!"
    wait_for_rosmaster_api 30 || _qt_start_fail
  fi

  if _qt_pid_alive bringup; then
    echo "[OK] bringup already running (this stack)"
  else
    echo "[INFO] starting bringup"
    nohup roslaunch "$BRINGUP_PKG" "$BRINGUP_LAUNCH" >"$BRINGUP_LOG" 2>&1 &
    _qt_write_pid bringup "$!"
  fi
  wait_for_topic /scan 30 1 || _qt_start_fail
  wait_for_topic /odom 30 1 || _qt_start_fail
  wait_for_topic /odom_raw 30 1 || _qt_start_fail

  if _qt_pid_alive json; then
    echo "[OK] json adapter already running (this stack)"
  else
    echo "[INFO] starting json adapter"
    nohup roslaunch "$JSON_PKG" "$JSON_LAUNCH" >"$JSON_LOG" 2>&1 &
    _qt_write_pid json "$!"
  fi
  wait_for_port 8765 25 1 || _qt_start_fail

  if [ "$CAMERA_ENABLE" = "1" ]; then
    if _qt_pid_alive camera; then
      echo "[OK] camera already running (this stack)"
    else
      echo "[INFO] starting camera preview"
      nohup roslaunch "$CAMERA_PKG" "$CAMERA_LAUNCH" >"$CAMERA_LOG" 2>&1 &
      _qt_write_pid camera "$!"
    fi
    wait_for_topic /camera/image_raw 25 0 || true
    wait_for_port 8080 25 0 || true
  else
    echo "[INFO] CAMERA_ENABLE=0, skip camera preview"
  fi

  if [ "$LASER_ODOM_ENABLE" = "1" ]; then
    if _qt_pid_alive rf2o; then
      echo "[OK] rf2o already running (this stack)"
    else
      echo "[INFO] starting rf2o"
      nohup roslaunch "$LASER_ODOM_PKG" "$LASER_ODOM_LAUNCH" >"$RF2O_LOG" 2>&1 &
      _qt_write_pid rf2o "$!"
      sleep 2
    fi
    wait_for_topic /odom_laser 30 1 || _qt_start_fail
  else
    echo "[INFO] LASER_ODOM_ENABLE=0, skip rf2o"
  fi

  echo "[OK] ${STACK_NAME} start done"
  echo "Qt JSON: ${HOST_IP}:8765"
  if [ "$CAMERA_ENABLE" = "1" ]; then
    echo "Qt camera: http://${HOST_IP}:8080/stream?topic=/camera/image_raw"
  fi
  echo "Record: $0 record"
}

cmd_stop() {
  _qt_stop_pid rosbag
  pkill -f "rosbag record -O ${BAG_DIR}/qt_stack_" 2>/dev/null || true
  rm -f "$PID_DIR/rosbag.path"

  if [ "$LASER_ODOM_ENABLE" != "0" ] || _qt_pid_alive rf2o; then
    _qt_stop_pid rf2o
  fi
  if [ "$CAMERA_ENABLE" != "0" ] || _qt_pid_alive camera; then
    _qt_stop_pid camera
  fi
  _qt_stop_pid json
  _qt_stop_pid bringup
  _qt_stop_pid roscore

  stack_release_owner "$STACK_NAME"
  echo "[OK] ${STACK_NAME} stop done (only PIDs started by this stack)"
}

cmd_restart() {
  cmd_stop
  cmd_start
}

cmd_record() {
  source_ros
  wait_for_rosmaster_api 15 || {
    echo "[ERR] rosmaster down"
    exit 1
  }

  for topic in /cmd_vel /odom /scan; do
    if ! rostopic list 2>/dev/null | grep -qx "$topic"; then
      echo "[ERR] missing $topic - run: $0 start"
      exit 1
    fi
  done
  if [ "$LASER_ODOM_ENABLE" = "1" ]; then
    if ! rostopic list 2>/dev/null | grep -qx /odom_laser; then
      echo "[ERR] missing /odom_laser - run: $0 start (LASER_ODOM_ENABLE=1)"
      exit 1
    fi
  fi

  if _qt_pid_alive rosbag; then
    echo "[OK] already recording pid=$(cat "$(_qt_pid_file rosbag)")"
    cat "$PID_DIR/rosbag.path" 2>/dev/null || true
    return 0
  fi

  mkdir -p "$BAG_DIR" "$PID_DIR"
  local bag_path
  bag_path="${BAG_DIR}/qt_stack_$(date +%Y%m%d_%H%M%S).bag"
  echo "[INFO] record ${RECORD_TOPICS} -> ${bag_path}"
  # shellcheck disable=SC2086
  nohup rosbag record -O "$bag_path" $RECORD_TOPICS >"$BAG_LOG" 2>&1 &
  _qt_write_pid rosbag "$!"
  echo "$bag_path" >"$PID_DIR/rosbag.path"
  echo "[OK] rosbag pid=$!"
}

topic_hz_brief() {
  local topic="$1"
  timeout 5 rostopic hz "$topic" 2>/dev/null | head -n 3 || echo "[WARN] ${topic} hz probe timeout"
}

cmd_status() {
  source_ros
  stack_refresh_all_owners
  echo "stack=${STACK_NAME}"
  echo "ROS_MASTER_URI=$ROS_MASTER_URI"
  echo "ROS_IP=$ROS_IP"
  if stack_owner_running "$STACK_NAME"; then
    echo "owner=active ($(stack_owner_file "$STACK_NAME"))"
  else
    echo "owner=inactive"
  fi
  if other="$(stack_other_owner "$STACK_NAME")"; then
    echo "[WARN] other stack owner active: $other"
  fi
  echo "CAMERA_ENABLE=$CAMERA_ENABLE LASER_ODOM_ENABLE=$LASER_ODOM_ENABLE"
  echo "---ports---"
  for spec in "11311:roscore" "8765:json_gateway" "8080:web_video_server"; do
    port="${spec%%:*}"
    name="${spec#*:}"
    if stack_is_listening "$port"; then
      echo "${name}:${port} listening"
    else
      echo "${name}:${port} closed"
    fi
  done
  echo "---PIDs (this stack)---"
  for name in roscore bringup json camera rf2o rosbag; do
    f="$(_qt_pid_file "$name")"
    if _qt_pid_alive "$name"; then
      echo "$name pid=$(cat "$f")"
    else
      echo "$name not tracked"
    fi
  done
  echo "---topics---"
  for topic in /cmd_vel /odom /odom_raw /odom_laser /scan /voltage /camera/image_raw; do
    echo "[$topic]"
    rostopic info "$topic" 2>/dev/null || echo "  (missing)"
  done
  echo "---rates (5s timeout)---"
  topic_hz_brief /scan
  topic_hz_brief /odom
  if rostopic list 2>/dev/null | grep -qx /odom_laser; then
    topic_hz_brief /odom_laser
  fi
}

cmd_logs() {
  mkdir -p "$LOG_DIR"
  touch "$ROSCORE_LOG" "$BRINGUP_LOG" "$JSON_LOG" "$RF2O_LOG" "$BAG_LOG" "$CAMERA_LOG"
  tail -n 40 -f \
    "$ROSCORE_LOG" "$BRINGUP_LOG" "$JSON_LOG" "$CAMERA_LOG" "$RF2O_LOG" "$BAG_LOG"
}

main() {
  case "${1:-}" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    restart) cmd_restart ;;
    status) cmd_status ;;
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
