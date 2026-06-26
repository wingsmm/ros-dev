#!/usr/bin/env bash
# Sourced by qt_stack.sh.

STACK_NAME="qt_stack"

HOST_IP="${HOST_IP:-192.168.1.169}"
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://${HOST_IP}:11311}"
export ROS_IP="${ROS_IP:-${HOST_IP}}"
unset ROS_HOSTNAME

ROS_SETUP="${ROS_SETUP:-/opt/ros/melodic/setup.bash}"
WS_SETUP="${WS_SETUP:-$HOME/ros_ws/devel/setup.bash}"

PROFILE="${PROFILE:-full}"

BRINGUP_ENABLE="${BRINGUP_ENABLE:-}"
JSON_ENABLE="${JSON_ENABLE:-}"
CAMERA_ENABLE="${CAMERA_ENABLE:-1}"
DEPTH_CAMERA_ENABLE="${DEPTH_CAMERA_ENABLE:-0}"
DEPTH_PREVIEW_ENABLE="${DEPTH_PREVIEW_ENABLE:-0}"
DEPTH_PREVIEW_MODE="${DEPTH_PREVIEW_MODE:-off}"
DEPTH_HTTP_ENABLE="${DEPTH_HTTP_ENABLE:-0}"
DEPTH_HTTP_PORT="${DEPTH_HTTP_PORT:-8082}"
LASER_ODOM_ENABLE="${LASER_ODOM_ENABLE:-1}"

BRINGUP_PKG="${BRINGUP_PKG:-xtark_driver}"
BRINGUP_LAUNCH="${BRINGUP_LAUNCH:-xtark_bringup.launch}"
JSON_PKG="${JSON_PKG:-xtark_json_bridge}"
JSON_LAUNCH="${JSON_LAUNCH:-json_base_adapter.launch}"

CAMERA_PKG="${CAMERA_PKG:-xtark_driver}"
CAMERA_LAUNCH="${CAMERA_LAUNCH:-xtark_camera.launch}"
CAMERA_MODE="${CAMERA_MODE:-}"

DEPTH_CAMERA_PKG="${DEPTH_CAMERA_PKG:-xtark_depth_preview}"
DEPTH_CAMERA_LAUNCH="${DEPTH_CAMERA_LAUNCH:-astra_depth_only.launch}"
DEPTH_PREVIEW_PKG="${DEPTH_PREVIEW_PKG:-xtark_depth_preview}"
DEPTH_PREVIEW_LAUNCH="${DEPTH_PREVIEW_LAUNCH:-depth_preview.launch}"
DEPTH_HTTP_PKG="${DEPTH_HTTP_PKG:-xtark_depth_preview}"
DEPTH_HTTP_LAUNCH="${DEPTH_HTTP_LAUNCH:-depth_http_server.launch}"
DEPTH_INPUT_TOPIC="${DEPTH_INPUT_TOPIC:-/camera/depth/image_raw}"
DEPTH_PREVIEW_TOPIC="${DEPTH_PREVIEW_TOPIC:-/camera/depth/preview}"

QT_RGB_TOPIC="${QT_RGB_TOPIC:-/camera/image_raw}"
ASTRA_RGB_TOPIC="${ASTRA_RGB_TOPIC:-/camera/rgb/image_raw}"
RGB_SOURCE="${RGB_SOURCE:-}"
ASTRA_UVC_RGB_PKG="${ASTRA_UVC_RGB_PKG:-xtark_depth_preview}"
ASTRA_UVC_RGB_LAUNCH="${ASTRA_UVC_RGB_LAUNCH:-astra_uvc_rgb_only.launch}"
ASTRA_UVC_DEVICE="${ASTRA_UVC_DEVICE:-}"

LASER_ODOM_PKG="${LASER_ODOM_PKG:-xtark_laser_odometry}"
LASER_ODOM_LAUNCH="${LASER_ODOM_LAUNCH:-rf2o_odom_laser.launch}"

LOG_DIR="${LOG_DIR:-$(stack_log_dir "$STACK_NAME")}"
BAG_DIR="${BAG_DIR:-$LOG_DIR/bags}"
PID_DIR="$(stack_pid_dir "$STACK_NAME")"

ROSCORE_LOG="$LOG_DIR/roscore.log"
BRINGUP_LOG="$LOG_DIR/bringup.log"
JSON_LOG="$LOG_DIR/json_adapter.log"
CAMERA_LOG="$LOG_DIR/camera.log"
DEPTH_CAMERA_LOG="$LOG_DIR/depth_camera.log"
DEPTH_PREVIEW_LOG="$LOG_DIR/depth_preview.log"
DEPTH_HTTP_LOG="$LOG_DIR/depth_http.log"
WEB_VIDEO_LOG="$LOG_DIR/web_video.log"
RF2O_LOG="$LOG_DIR/rf2o.log"
BAG_LOG="$LOG_DIR/rosbag.log"

RECORD_TOPICS="${RECORD_TOPICS:-/cmd_vel /odom_raw /odom /imu /odom_laser /scan /tf_static /xtark/aset /xtark/bset /xtark/cset /xtark/dset /xtark/avel /xtark/bvel /xtark/cvel /xtark/dvel}"

STARTED_STOPPERS=()

qt_usage() {
  cat <<EOF
Usage: qt_stack.sh <command>

Commands:
  start     Start modules in order; fail fast and rollback on error
  stop      Stop Qt stack modules
  restart   Stop then start
  status    Quick state view: PIDs, ports, topics
  check     Slow acceptance: frames, rates, MJPEG URL probes
  record    Start rosbag
  logs      Tail logs

Profiles:
  PROFILE=full            daily Qt stack
  PROFILE=camera_raw      RGB + depth raw, no depth preview
  PROFILE=camera_preview  Deprecated alias of camera_raw
  PROFILE=camera_depth    depth hardware diagnostic only
EOF
}

qt_pid_file() {
  echo "$PID_DIR/$1.pid"
}

qt_pid_alive() {
  stack_pid_alive "$(qt_pid_file "$1")"
}

qt_write_pid() {
  stack_write_pid "$STACK_NAME" "$1" "$2"
}

qt_stop_pid() {
  stack_stop_pid "$STACK_NAME" "$1"
}

qt_source_ros() {
  if [ ! -f "$ROS_SETUP" ]; then
    echo "[ERR] ROS setup not found: $ROS_SETUP"
    return 1
  fi
  if [ ! -f "$WS_SETUP" ]; then
    echo "[ERR] workspace setup not found: $WS_SETUP"
    return 1
  fi
  set +u
  # shellcheck disable=SC1090
  source "$ROS_SETUP"
  # shellcheck disable=SC1090
  source "$WS_SETUP"
  set -u
}

qt_resolve_profile() {
  case "$PROFILE" in
    camera_raw)
      BRINGUP_ENABLE=1
      JSON_ENABLE=1
      CAMERA_ENABLE=1
      DEPTH_CAMERA_ENABLE=1
      DEPTH_PREVIEW_ENABLE=0
      DEPTH_PREVIEW_MODE=off
      DEPTH_HTTP_ENABLE=1
      LASER_ODOM_ENABLE=0
      CAMERA_MODE=rgb_depth
      RGB_SOURCE="${RGB_SOURCE:-auto}"
      ;;
    camera_preview)
      BRINGUP_ENABLE=1
      JSON_ENABLE=1
      CAMERA_ENABLE=1
      DEPTH_CAMERA_ENABLE=1
      DEPTH_PREVIEW_ENABLE=0
      DEPTH_PREVIEW_MODE=off
      DEPTH_HTTP_ENABLE=1
      LASER_ODOM_ENABLE=0
      CAMERA_MODE=rgb_depth
      RGB_SOURCE="${RGB_SOURCE:-auto}"
      ;;
    camera_depth)
      BRINGUP_ENABLE=0
      JSON_ENABLE=0
      CAMERA_ENABLE=0
      DEPTH_CAMERA_ENABLE=1
      DEPTH_PREVIEW_ENABLE=0
      DEPTH_PREVIEW_MODE=off
      DEPTH_HTTP_ENABLE=0
      LASER_ODOM_ENABLE=0
      CAMERA_MODE=depth_only
      RGB_SOURCE="${RGB_SOURCE:-uvc_astra}"
      ;;
    full)
      BRINGUP_ENABLE="${BRINGUP_ENABLE:-1}"
      JSON_ENABLE="${JSON_ENABLE:-1}"
      CAMERA_MODE="${CAMERA_MODE:-rgb_only}"
      RGB_SOURCE="${RGB_SOURCE:-uvc}"
      ;;
    *)
      echo "[ERR] invalid PROFILE=$PROFILE"
      return 1
      ;;
  esac
}

qt_is_camera_profile() {
  [ "$PROFILE" = "camera_raw" ] || [ "$PROFILE" = "camera_preview" ]
}

qt_load_saved_runtime_config() {
  if [ -f "$PID_DIR/profile" ]; then
    PROFILE="$(cat "$PID_DIR/profile")"
  fi
  if [ -f "$PID_DIR/camera_mode" ]; then
    CAMERA_MODE="$(cat "$PID_DIR/camera_mode")"
  fi
  if [ -f "$PID_DIR/rgb_source" ]; then
    RGB_SOURCE="$(cat "$PID_DIR/rgb_source")"
  fi
}

qt_depth_preview_enabled() {
  [ "$DEPTH_PREVIEW_ENABLE" = "1" ] && [ "$DEPTH_PREVIEW_MODE" = "xtark" ]
}

qt_wait_rosmaster() {
  local max="${1:-30}"
  local i=0
  while ! rostopic list >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "[ERR] rosmaster not ready after ${max}s"
      return 1
    fi
    sleep 1
  done
}

qt_wait_port() {
  local port="$1"
  local max="${2:-20}"
  local i=0
  while ! stack_is_listening "$port"; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "[ERR] port $port not listening after ${max}s"
      return 1
    fi
    sleep 1
  done
}

qt_topic_has_publisher() {
  local topic="$1"
  rostopic info "$topic" 2>/dev/null \
    | awk '/^Publishers:/{f=1;next} /^Subscribers:/{f=0} f' \
    | grep -q '[^[:space:]]'
}

qt_wait_topic_publisher() {
  local topic="$1"
  local max="${2:-25}"
  local i=0
  while ! qt_topic_has_publisher "$topic"; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "[ERR] $topic has no publisher after ${max}s"
      return 1
    fi
    sleep 1
  done
}

qt_wait_topic_frame() {
  local topic="$1"
  local max="${2:-20}"
  local i=0
  while [ "$i" -lt "$max" ]; do
    if timeout 8 rostopic echo "$topic" -n 1 >/dev/null 2>&1; then
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  echo "[ERR] $topic has no frame after ${max}s"
  return 1
}

qt_resolve_astra_uvc_device() {
  if [ -n "$ASTRA_UVC_DEVICE" ]; then
    return 0
  fi
  ASTRA_UVC_DEVICE="$(ls /dev/v4l/by-id/*Astra_Pro*video-index0 2>/dev/null | head -1 || true)"
  if [ -z "$ASTRA_UVC_DEVICE" ]; then
    ASTRA_UVC_DEVICE="/dev/video0"
  fi
}

qt_start_step() {
  local name="$1"
  local start_fn="$2"
  local stop_fn="$3"

  echo "[START] $name"
  if "$start_fn"; then
    STARTED_STOPPERS+=("$stop_fn")
    echo "[OK] $name"
    return 0
  fi

  echo "[ERR] $name failed"
  qt_rollback
  exit 1
}

qt_rollback() {
  local i
  echo "[ROLLBACK] stopping started modules"
  for ((i=${#STARTED_STOPPERS[@]}-1; i>=0; i--)); do
    "${STARTED_STOPPERS[$i]}" || true
  done
  stack_release_owner "$STACK_NAME"
}

start_roscore() {
  if qt_pid_alive roscore; then
    qt_wait_rosmaster 10
    return 0
  fi
  if stack_is_listening 11311; then
    echo "[ERR] port 11311 in use but not owned by qt_stack"
    return 1
  fi
  nohup roscore >"$ROSCORE_LOG" 2>&1 &
  qt_write_pid roscore "$!"
  qt_wait_rosmaster 30
}

stop_roscore() {
  qt_stop_pid roscore
}

start_bringup() {
  if [ "$BRINGUP_ENABLE" != "1" ]; then
    echo "[SKIP] bringup disabled"
    return 0
  fi
  if ! qt_pid_alive bringup; then
    nohup roslaunch "$BRINGUP_PKG" "$BRINGUP_LAUNCH" >"$BRINGUP_LOG" 2>&1 &
    qt_write_pid bringup "$!"
  fi
  qt_wait_topic_publisher /scan 30
  qt_wait_topic_publisher /odom 30
  qt_wait_topic_publisher /odom_raw 30
}

stop_bringup() {
  qt_stop_pid bringup
}

start_json() {
  if [ "$JSON_ENABLE" != "1" ]; then
    echo "[SKIP] json disabled"
    return 0
  fi
  if stack_is_listening 8765 && ! qt_pid_alive json; then
    echo "[ERR] port 8765 in use but not owned by qt_stack"
    return 1
  fi
  if ! qt_pid_alive json; then
    nohup roslaunch "$JSON_PKG" "$JSON_LAUNCH" >"$JSON_LOG" 2>&1 &
    qt_write_pid json "$!"
  fi
  qt_wait_port 8765 25
}

stop_json() {
  qt_stop_pid json
}

start_rgb_camera() {
  if [ "$CAMERA_ENABLE" != "1" ] || [ "$CAMERA_MODE" = "depth_only" ]; then
    echo "[SKIP] rgb disabled"
    return 0
  fi

  case "$RGB_SOURCE" in
    uvc_astra)
      qt_resolve_astra_uvc_device
      if ! qt_pid_alive camera; then
        nohup roslaunch "$ASTRA_UVC_RGB_PKG" "$ASTRA_UVC_RGB_LAUNCH" \
          device:="$ASTRA_UVC_DEVICE" \
          output_topic:="$QT_RGB_TOPIC" \
          >"$CAMERA_LOG" 2>&1 &
        qt_write_pid camera "$!"
      fi
      ;;
    uvc)
      if ! qt_pid_alive camera; then
        nohup roslaunch "$CAMERA_PKG" "$CAMERA_LAUNCH" >"$CAMERA_LOG" 2>&1 &
        qt_write_pid camera "$!"
      fi
      ;;
    openni)
      if ! qt_topic_has_publisher "$ASTRA_RGB_TOPIC"; then
        echo "[ERR] OpenNI RGB missing: $ASTRA_RGB_TOPIC"
        return 1
      fi
      if ! qt_pid_alive rgb_relay; then
        nohup roslaunch xtark_depth_preview astra_rgb_relay.launch \
          input_topic:="$ASTRA_RGB_TOPIC" \
          output_topic:="$QT_RGB_TOPIC" \
          >"$CAMERA_LOG" 2>&1 &
        qt_write_pid rgb_relay "$!"
      fi
      ;;
    auto)
      if qt_topic_has_publisher "$ASTRA_RGB_TOPIC"; then
        RGB_SOURCE=openni
        start_rgb_camera
        return $?
      fi
      RGB_SOURCE=uvc_astra
      start_rgb_camera
      return $?
      ;;
    *)
      echo "[ERR] invalid RGB_SOURCE=$RGB_SOURCE"
      return 1
      ;;
  esac

  qt_wait_topic_publisher "$QT_RGB_TOPIC" 30
}

stop_rgb_camera() {
  qt_stop_pid rgb_relay
  qt_stop_pid camera
  pkill -f "roslaunch ${ASTRA_UVC_RGB_PKG} ${ASTRA_UVC_RGB_LAUNCH}" 2>/dev/null || true
  pkill -f "roslaunch ${CAMERA_PKG} ${CAMERA_LAUNCH}" 2>/dev/null || true
  pkill -f 'uvc_camera_node' 2>/dev/null || true
}

start_depth_camera() {
  if [ "$DEPTH_CAMERA_ENABLE" != "1" ]; then
    echo "[SKIP] depth camera disabled"
    return 0
  fi
  if ! qt_pid_alive depth_camera; then
    nohup roslaunch "$DEPTH_CAMERA_PKG" "$DEPTH_CAMERA_LAUNCH" >"$DEPTH_CAMERA_LOG" 2>&1 &
    qt_write_pid depth_camera "$!"
  fi
  qt_wait_topic_publisher "$DEPTH_INPUT_TOPIC" 40
  qt_wait_topic_publisher /camera/depth/camera_info 30
}

stop_depth_camera() {
  qt_stop_pid depth_camera
  pkill -f "roslaunch ${DEPTH_CAMERA_PKG} ${DEPTH_CAMERA_LAUNCH}" 2>/dev/null || true
}

start_depth_preview() {
  if ! qt_depth_preview_enabled; then
    echo "[SKIP] depth preview disabled"
    return 0
  fi
  if ! qt_pid_alive depth_preview; then
    nohup roslaunch "$DEPTH_PREVIEW_PKG" "$DEPTH_PREVIEW_LAUNCH" \
      input_topic:="$DEPTH_INPUT_TOPIC" \
      output_topic:="$DEPTH_PREVIEW_TOPIC" \
      >"$DEPTH_PREVIEW_LOG" 2>&1 &
    qt_write_pid depth_preview "$!"
  fi
  qt_wait_topic_publisher "$DEPTH_PREVIEW_TOPIC" 30
}

stop_depth_preview() {
  qt_stop_pid depth_preview
  pkill -f "roslaunch ${DEPTH_PREVIEW_PKG} ${DEPTH_PREVIEW_LAUNCH}" 2>/dev/null || true
}

start_depth_http() {
  if [ "$DEPTH_HTTP_ENABLE" != "1" ]; then
    echo "[SKIP] depth HTTP disabled"
    return 0
  fi
  if stack_is_listening "$DEPTH_HTTP_PORT" && ! qt_pid_alive depth_http; then
    echo "[ERR] port $DEPTH_HTTP_PORT in use but not owned by qt_stack"
    return 1
  fi
  if ! qt_pid_alive depth_http; then
    nohup roslaunch "$DEPTH_HTTP_PKG" "$DEPTH_HTTP_LAUNCH" \
      input_topic:="$DEPTH_INPUT_TOPIC" \
      camera_info_topic:=/camera/depth/camera_info \
      port:="$DEPTH_HTTP_PORT" \
      >"$DEPTH_HTTP_LOG" 2>&1 &
    qt_write_pid depth_http "$!"
  fi
  qt_wait_port "$DEPTH_HTTP_PORT" 30
  local i=0
  while ! curl -fsS --connect-timeout 2 --max-time 3 "http://127.0.0.1:${DEPTH_HTTP_PORT}/healthz" \
    | grep -q '"depth_ready":true'; do
    i=$((i + 1))
    if [ "$i" -ge 20 ]; then
      echo "[ERR] depth HTTP has no raw frame after 20s"
      return 1
    fi
    sleep 1
  done
}

stop_depth_http() {
  qt_stop_pid depth_http
  pkill -f "roslaunch ${DEPTH_HTTP_PKG} ${DEPTH_HTTP_LAUNCH}" 2>/dev/null || true
}

start_web_video() {
  if [ "$CAMERA_ENABLE" != "1" ]; then
    echo "[SKIP] web_video disabled"
    return 0
  fi
  if [ "$CAMERA_MODE" = "rgb_only" ] && [ "$RGB_SOURCE" = "uvc" ]; then
    qt_wait_port 8080 30
    return 0
  fi
  if stack_is_listening 8080 && ! qt_pid_alive web_video; then
    echo "[ERR] port 8080 in use but not owned by qt_stack"
    return 1
  fi
  if ! qt_pid_alive web_video; then
    nohup rosrun web_video_server web_video_server >"$WEB_VIDEO_LOG" 2>&1 &
    qt_write_pid web_video "$!"
  fi
  qt_wait_port 8080 30
}

stop_web_video() {
  qt_stop_pid web_video
  pkill -f 'rosrun web_video_server web_video_server' 2>/dev/null || true
}

start_rf2o() {
  if [ "$LASER_ODOM_ENABLE" != "1" ]; then
    echo "[SKIP] rf2o disabled"
    return 0
  fi
  if ! qt_pid_alive rf2o; then
    nohup roslaunch "$LASER_ODOM_PKG" "$LASER_ODOM_LAUNCH" >"$RF2O_LOG" 2>&1 &
    qt_write_pid rf2o "$!"
  fi
  qt_wait_topic_publisher /odom_laser 30
}

stop_rf2o() {
  qt_stop_pid rf2o
}

qt_prepare_start() {
  mkdir -p "$LOG_DIR" "$BAG_DIR" "$PID_DIR"
  qt_source_ros
  qt_resolve_profile
  stack_refresh_all_owners
  stack_assert_no_other_owner "$STACK_NAME"
  stack_claim_owner "$STACK_NAME"
  echo "$PROFILE" >"$PID_DIR/profile"
  echo "$CAMERA_MODE" >"$PID_DIR/camera_mode"
  echo "$RGB_SOURCE" >"$PID_DIR/rgb_source"
  echo "[INFO] PROFILE=$PROFILE CAMERA_MODE=$CAMERA_MODE RGB_SOURCE=$RGB_SOURCE"
}

qt_start() {
  qt_prepare_start
  qt_start_step roscore start_roscore stop_roscore
  qt_start_step bringup start_bringup stop_bringup
  qt_start_step json start_json stop_json
  qt_start_step rgb_camera start_rgb_camera stop_rgb_camera
  qt_start_step depth_camera start_depth_camera stop_depth_camera
  qt_start_step depth_http start_depth_http stop_depth_http
  qt_start_step depth_preview start_depth_preview stop_depth_preview
  qt_start_step web_video start_web_video stop_web_video
  qt_start_step rf2o start_rf2o stop_rf2o
  echo "[DONE] qt stack ready"
  echo "Qt JSON: ${HOST_IP}:8765"
  echo "Qt RGB: http://${HOST_IP}:8080/stream?topic=${QT_RGB_TOPIC}"
  if [ "$DEPTH_HTTP_ENABLE" = "1" ]; then
    echo "Qt Depth raw: http://${HOST_IP}:${DEPTH_HTTP_PORT}/v1/depth/latest"
  fi
  if qt_depth_preview_enabled; then
    echo "Qt Depth: http://${HOST_IP}:8080/stream?topic=${DEPTH_PREVIEW_TOPIC}"
  fi
}

qt_stop() {
  mkdir -p "$PID_DIR"
  qt_stop_pid rosbag
  pkill -f "rosbag record -O ${BAG_DIR}/qt_stack_" 2>/dev/null || true
  stop_rf2o || true
  stop_web_video || true
  stop_depth_preview || true
  stop_depth_http || true
  stop_depth_camera || true
  stop_rgb_camera || true
  stop_json || true
  stop_bringup || true
  stop_roscore || true
  rm -f "$PID_DIR/profile" "$PID_DIR/camera_mode" "$PID_DIR/rgb_source" "$PID_DIR/rosbag.path"
  stack_release_owner "$STACK_NAME"
  echo "[OK] qt_stack stop done"
}

qt_status() {
  qt_source_ros
  qt_load_saved_runtime_config
  qt_resolve_profile
  stack_refresh_all_owners
  echo "stack=$STACK_NAME"
  echo "PROFILE=$PROFILE CAMERA_MODE=$CAMERA_MODE RGB_SOURCE=$RGB_SOURCE"
  if stack_owner_running "$STACK_NAME"; then
    echo "owner=active"
  else
    echo "owner=inactive"
  fi
  for spec in "11311:roscore" "8765:json" "8080:web_video" "${DEPTH_HTTP_PORT}:depth_http"; do
    local port="${spec%%:*}"
    local name="${spec#*:}"
    if stack_is_listening "$port"; then
      echo "[OK] $name port $port"
    else
      echo "[WARN] $name port $port closed"
    fi
  done
  echo "---PIDs---"
  for name in roscore bringup json camera rgb_relay depth_camera depth_http depth_preview web_video rf2o rosbag; do
    if qt_pid_alive "$name"; then
      echo "$name pid=$(cat "$(qt_pid_file "$name")")"
    else
      echo "$name not tracked"
    fi
  done
  echo "---topics---"
  for topic in /scan /odom /odom_raw "$QT_RGB_TOPIC" "$DEPTH_INPUT_TOPIC" /camera/depth/camera_info "$DEPTH_PREVIEW_TOPIC"; do
    if rostopic list 2>/dev/null | grep -qx "$topic"; then
      echo "[OK] $topic"
    else
      echo "[MISS] $topic"
    fi
  done
  echo "[INFO] use '$0 check' for slow frame/rate/MJPEG checks"
}

qt_topic_hz() {
  local topic="$1"
  timeout 6 rostopic hz "$topic" 2>/dev/null | head -n 3 || echo "[WARN] $topic hz timeout"
}

qt_mjpeg_probe() {
  local topic="$1"
  local url="http://${HOST_IP}:8080/stream?topic=${topic}"
  if curl -s --connect-timeout 3 --max-time 5 "$url" | head -c 512 | strings | grep -q 'image/jpeg\|JFIF'; then
    echo "[OK] MJPEG $topic"
  else
    echo "[WARN] MJPEG $topic no JPEG header"
  fi
}

qt_check() {
  qt_source_ros
  qt_load_saved_runtime_config
  qt_resolve_profile
  qt_wait_rosmaster 10
  echo "---frames---"
  if [ "$CAMERA_ENABLE" = "1" ] && [ "$CAMERA_MODE" != "depth_only" ]; then
    qt_wait_topic_frame "$QT_RGB_TOPIC" 20
  fi
  if [ "$DEPTH_CAMERA_ENABLE" = "1" ] || rostopic list 2>/dev/null | grep -qx "$DEPTH_INPUT_TOPIC"; then
    qt_wait_topic_frame "$DEPTH_INPUT_TOPIC" 20
  fi
  if rostopic list 2>/dev/null | grep -qx "$DEPTH_PREVIEW_TOPIC"; then
    qt_wait_topic_frame "$DEPTH_PREVIEW_TOPIC" 20
  fi
  echo "---rates---"
  for topic in "$QT_RGB_TOPIC" "$DEPTH_INPUT_TOPIC" "$DEPTH_PREVIEW_TOPIC"; do
    if rostopic list 2>/dev/null | grep -qx "$topic"; then
      qt_topic_hz "$topic"
    fi
  done
  echo "---MJPEG---"
  if stack_is_listening 8080; then
    if [ "$CAMERA_ENABLE" = "1" ] && [ "$CAMERA_MODE" != "depth_only" ]; then
      qt_mjpeg_probe "$QT_RGB_TOPIC"
    fi
    if rostopic list 2>/dev/null | grep -qx "$DEPTH_PREVIEW_TOPIC"; then
      qt_mjpeg_probe "$DEPTH_PREVIEW_TOPIC"
    fi
  else
    echo "[WARN] web_video port 8080 closed"
  fi
}

qt_record() {
  qt_source_ros
  qt_wait_rosmaster 10
  mkdir -p "$BAG_DIR" "$PID_DIR"
  if qt_pid_alive rosbag; then
    echo "[OK] already recording pid=$(cat "$(qt_pid_file rosbag)")"
    cat "$PID_DIR/rosbag.path" 2>/dev/null || true
    return 0
  fi
  local bag_path="${BAG_DIR}/qt_stack_$(date +%Y%m%d_%H%M%S).bag"
  # shellcheck disable=SC2086
  nohup rosbag record -O "$bag_path" $RECORD_TOPICS >"$BAG_LOG" 2>&1 &
  qt_write_pid rosbag "$!"
  echo "$bag_path" >"$PID_DIR/rosbag.path"
  echo "[OK] rosbag pid=$!"
  echo "$bag_path"
}

qt_logs() {
  mkdir -p "$LOG_DIR"
  touch "$ROSCORE_LOG" "$BRINGUP_LOG" "$JSON_LOG" "$CAMERA_LOG" "$DEPTH_CAMERA_LOG" \
    "$DEPTH_PREVIEW_LOG" "$DEPTH_HTTP_LOG" "$WEB_VIDEO_LOG" "$RF2O_LOG" "$BAG_LOG"
  tail -n 40 -f "$ROSCORE_LOG" "$BRINGUP_LOG" "$JSON_LOG" "$CAMERA_LOG" \
    "$DEPTH_CAMERA_LOG" "$DEPTH_PREVIEW_LOG" "$DEPTH_HTTP_LOG" "$WEB_VIDEO_LOG" "$RF2O_LOG" "$BAG_LOG"
}
