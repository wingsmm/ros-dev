#!/usr/bin/env bash
# Robot-side stack for VMware Qt client (ROS1 topics only).
# Runs on xtark-robot (169). Pair with vmware/qt on VM (154).
# No JSON :8765, no HTTP depth, no RViz, no teleop.

STACK_NAME="pc_stack"

HOST_IP="${HOST_IP:-192.168.1.168}"
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://${HOST_IP}:11311}"
export ROS_IP="${ROS_IP:-${HOST_IP}}"
unset ROS_HOSTNAME

ROS_SETUP="${ROS_SETUP:-/opt/ros/melodic/setup.bash}"
WS_SETUP="${WS_SETUP:-$HOME/ros_ws/devel/setup.bash}"

PROFILE="${PROFILE:-full}"

BRINGUP_ENABLE="${BRINGUP_ENABLE:-}"
BRINGUP_WAIT_SCAN="${BRINGUP_WAIT_SCAN:-1}"
BRINGUP_WAIT_ODOM_RAW="${BRINGUP_WAIT_ODOM_RAW:-1}"
CAMERA_ENABLE="${CAMERA_ENABLE:-}"
DEPTH_CAMERA_ENABLE="${DEPTH_CAMERA_ENABLE:-}"
RGB_SOURCE="${RGB_SOURCE:-auto}"
CAMERA_MODE="${CAMERA_MODE:-rgb_depth}"

BRINGUP_PKG="${BRINGUP_PKG:-xtark_driver}"
BRINGUP_LAUNCH="${BRINGUP_LAUNCH:-xtark_bringup.launch}"
CAMERA_PKG="${CAMERA_PKG:-xtark_driver}"
CAMERA_LAUNCH="${CAMERA_LAUNCH:-xtark_camera.launch}"
DEPTH_CAMERA_PKG="${DEPTH_CAMERA_PKG:-xtark_depth_preview}"
DEPTH_CAMERA_LAUNCH="${DEPTH_CAMERA_LAUNCH:-astra_depth_only.launch}"
DEPTH_CAMERA_PUBLISH_TF="${DEPTH_CAMERA_PUBLISH_TF:-1}"
DEPTH_INPUT_TOPIC="${DEPTH_INPUT_TOPIC:-/camera/depth/image_raw}"
QT_RGB_TOPIC="${QT_RGB_TOPIC:-/camera/image_raw}"
ASTRA_RGB_TOPIC="${ASTRA_RGB_TOPIC:-/camera/rgb/image_raw}"
ASTRA_UVC_RGB_PKG="${ASTRA_UVC_RGB_PKG:-xtark_depth_preview}"
ASTRA_UVC_RGB_LAUNCH="${ASTRA_UVC_RGB_LAUNCH:-astra_uvc_rgb_only.launch}"
ASTRA_UVC_DEVICE="${ASTRA_UVC_DEVICE:-}"

DEPTH_PREVIEW_ENABLE="${DEPTH_PREVIEW_ENABLE:-0}"
DEPTH_PREVIEW_PKG="${DEPTH_PREVIEW_PKG:-xtark_depth_preview}"
DEPTH_PREVIEW_LAUNCH="${DEPTH_PREVIEW_LAUNCH:-depth_preview.launch}"
DEPTH_PREVIEW_TOPIC="${DEPTH_PREVIEW_TOPIC:-/camera/depth/preview}"

LOG_DIR="${LOG_DIR:-$(stack_log_dir "$STACK_NAME")}"
PID_DIR="$(stack_pid_dir "$STACK_NAME")"

ROSCORE_LOG="$LOG_DIR/roscore.log"
BRINGUP_LOG="$LOG_DIR/bringup.log"
CAMERA_LOG="$LOG_DIR/camera.log"
DEPTH_CAMERA_LOG="$LOG_DIR/depth_camera.log"
DEPTH_PREVIEW_LOG="$LOG_DIR/depth_preview.log"

STARTED_STOPPERS=()

pc_usage() {
  cat <<EOF
Usage: pc_stack.sh <command>

Runs on xtark-robot. Starts roscore + bringup + camera ROS topics for VMware Qt.
Does NOT start JSON bridge, HTTP depth, RViz, or teleop.

Commands:
  camera-start / camera-stop / camera-status / camera-check
  camera-nearfield-start / camera-nearfield-stop / camera-nearfield-status / camera-nearfield-check
  camera-deep-start / camera-deep-stop / camera-deep-status / camera-deep-check
  radar2d-start / radar2d-stop / radar2d-status / radar2d-check
  full-start / full-stop / full-status / full-check
  logs        Tail pc_stack logs

Legacy aliases: start = full-start, stop = full-stop, status = full-status, check = full-check

Mutually exclusive with android_stack / qt_stack.

Environment:
  ROS_MASTER_URI=${ROS_MASTER_URI}
  ROS_IP=${ROS_IP}
EOF
}

pc_pid_file() {
  echo "$PID_DIR/$1.pid"
}

pc_pid_alive() {
  stack_pid_alive "$(pc_pid_file "$1")"
}

pc_write_pid() {
  stack_write_pid "$STACK_NAME" "$1" "$2"
}

pc_stop_pid() {
  stack_stop_pid "$STACK_NAME" "$1"
}

pc_source_ros() {
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

pc_resolve_profile() {
  case "$PROFILE" in
    camera)
      BRINGUP_ENABLE=1
      BRINGUP_WAIT_SCAN=0
      BRINGUP_WAIT_ODOM_RAW=0
      CAMERA_ENABLE=1
      DEPTH_CAMERA_ENABLE=1
      DEPTH_PREVIEW_ENABLE=0
      CAMERA_MODE=rgb_depth
      RGB_SOURCE="${RGB_SOURCE:-auto}"
      ;;
    camera_deep)
      BRINGUP_ENABLE=1
      BRINGUP_WAIT_SCAN=0
      BRINGUP_WAIT_ODOM_RAW=0
      CAMERA_ENABLE=1
      DEPTH_CAMERA_ENABLE=1
      DEPTH_PREVIEW_ENABLE=1
      CAMERA_MODE=rgb_depth
      RGB_SOURCE="${RGB_SOURCE:-auto}"
      ;;
    camera_nearfield)
      BRINGUP_ENABLE=1
      BRINGUP_WAIT_SCAN=0
      BRINGUP_WAIT_ODOM_RAW=0
      CAMERA_ENABLE=1
      DEPTH_CAMERA_ENABLE=1
      DEPTH_CAMERA_PUBLISH_TF=0
      DEPTH_PREVIEW_ENABLE=0
      CAMERA_MODE=rgb_depth
      RGB_SOURCE="${RGB_SOURCE:-auto}"
      ;;
    radar2d)
      BRINGUP_ENABLE=1
      BRINGUP_WAIT_SCAN=1
      BRINGUP_WAIT_ODOM_RAW=1
      CAMERA_ENABLE=0
      DEPTH_CAMERA_ENABLE=0
      DEPTH_PREVIEW_ENABLE=0
      ;;
    full)
      BRINGUP_ENABLE=1
      BRINGUP_WAIT_SCAN=1
      BRINGUP_WAIT_ODOM_RAW=1
      CAMERA_ENABLE=1
      DEPTH_CAMERA_ENABLE=1
      DEPTH_PREVIEW_ENABLE=0
      CAMERA_MODE=rgb_depth
      RGB_SOURCE="${RGB_SOURCE:-auto}"
      ;;
    *)
      echo "[ERR] invalid PROFILE=$PROFILE (use camera|camera_nearfield|camera_deep|radar2d|full)"
      return 1
      ;;
  esac
}

pc_save_mode() {
  mkdir -p "$PID_DIR"
  echo "$PROFILE" >"$PID_DIR/profile"
  echo "$PROFILE" >"$PID_DIR/mode"
}

pc_load_mode() {
  if [ -f "$PID_DIR/mode" ]; then
    PROFILE="$(cat "$PID_DIR/mode")"
    pc_resolve_profile || true
  elif [ -f "$PID_DIR/profile" ]; then
    PROFILE="$(cat "$PID_DIR/profile")"
    pc_resolve_profile || true
  fi
}

pc_mode_active() {
  [ -f "$PID_DIR/mode" ] || stack_owner_running "$STACK_NAME"
}

pc_wait_rosmaster() {
  local max="${1:-30}"
  local i=0
  while ! rostopic list >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "[ERR] roscore not ready after ${max}s"
      return 1
    fi
    sleep 1
  done
}

pc_wait_topic_publisher() {
  local topic="$1"
  local max="${2:-30}"
  local i=0
  while ! pc_topic_has_publisher "$topic"; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "[ERR] no publisher for $topic after ${max}s"
      return 1
    fi
    sleep 1
  done
}

pc_topic_has_publisher() {
  local topic="$1"
  rostopic info "$topic" 2>/dev/null \
    | awk '/^Publishers:/{f=1;next} /^Subscribers:/{f=0} f' \
    | grep -q '[^[:space:]]'
}

pc_resolve_astra_uvc_device() {
  if [ -n "$ASTRA_UVC_DEVICE" ] && [ -e "$ASTRA_UVC_DEVICE" ]; then
    return 0
  fi
  for dev in /dev/video0 /dev/video1; do
    if [ -e "$dev" ]; then
      ASTRA_UVC_DEVICE="$dev"
      return 0
    fi
  done
  echo "[ERR] no UVC device for Astra RGB"
  return 1
}

pc_start_roscore() {
  if pc_pid_alive roscore; then
    pc_wait_rosmaster 10
    return 0
  fi
  if stack_is_listening 11311; then
    echo "[ERR] port 11311 in use but not owned by pc_stack"
    return 1
  fi
  mkdir -p "$LOG_DIR"
  nohup roscore >"$ROSCORE_LOG" 2>&1 &
  pc_write_pid roscore "$!"
  pc_wait_rosmaster 30
}

pc_stop_roscore() {
  pc_stop_pid roscore
  pkill -f 'rosmaster --core -p 11311' 2>/dev/null || true
  pkill -f 'roscore' 2>/dev/null || true
}

pc_start_bringup() {
  if [ "$BRINGUP_ENABLE" != "1" ]; then
    echo "[SKIP] bringup disabled"
    return 0
  fi
  if ! pc_pid_alive bringup; then
    nohup roslaunch "$BRINGUP_PKG" "$BRINGUP_LAUNCH" >"$BRINGUP_LOG" 2>&1 &
    pc_write_pid bringup "$!"
  fi
  if [ "$BRINGUP_WAIT_SCAN" = "1" ]; then
    pc_wait_topic_publisher /scan 40
  fi
  pc_wait_topic_publisher /odom 40
  if [ "$BRINGUP_WAIT_ODOM_RAW" = "1" ]; then
    pc_wait_topic_publisher /odom_raw 30 || true
  fi
}

pc_stop_bringup() {
  pc_stop_pid bringup
  pkill -f "roslaunch ${BRINGUP_PKG} ${BRINGUP_LAUNCH}" 2>/dev/null || true
}

pc_start_rgb_camera() {
  if [ "$CAMERA_ENABLE" != "1" ] || [ "$CAMERA_MODE" = "depth_only" ]; then
    echo "[SKIP] rgb disabled"
    return 0
  fi
  case "$RGB_SOURCE" in
    uvc_astra)
      pc_resolve_astra_uvc_device || return 1
      if ! pc_pid_alive camera; then
        nohup roslaunch "$ASTRA_UVC_RGB_PKG" "$ASTRA_UVC_RGB_LAUNCH" \
          device:="$ASTRA_UVC_DEVICE" \
          output_topic:="$QT_RGB_TOPIC" \
          >"$CAMERA_LOG" 2>&1 &
        pc_write_pid camera "$!"
      fi
      ;;
    uvc)
      if ! pc_pid_alive camera; then
        nohup roslaunch "$CAMERA_PKG" "$CAMERA_LAUNCH" >"$CAMERA_LOG" 2>&1 &
        pc_write_pid camera "$!"
      fi
      ;;
    openni)
      if ! pc_topic_has_publisher "$ASTRA_RGB_TOPIC"; then
        echo "[ERR] OpenNI RGB missing: $ASTRA_RGB_TOPIC"
        return 1
      fi
      if ! pc_pid_alive rgb_relay; then
        nohup roslaunch xtark_depth_preview astra_rgb_relay.launch \
          input_topic:="$ASTRA_RGB_TOPIC" \
          output_topic:="$QT_RGB_TOPIC" \
          >>"$CAMERA_LOG" 2>&1 &
        pc_write_pid rgb_relay "$!"
      fi
      ;;
    auto)
      if pc_topic_has_publisher "$ASTRA_RGB_TOPIC"; then
        RGB_SOURCE=openni
        pc_start_rgb_camera
        return $?
      fi
      RGB_SOURCE=uvc_astra
      pc_start_rgb_camera
      return $?
      ;;
    *)
      echo "[ERR] invalid RGB_SOURCE=$RGB_SOURCE"
      return 1
      ;;
  esac
  pc_wait_topic_publisher "$QT_RGB_TOPIC" 40
}

pc_stop_rgb_camera() {
  pc_stop_pid rgb_relay
  pc_stop_pid camera
  pkill -f "roslaunch ${ASTRA_UVC_RGB_PKG} ${ASTRA_UVC_RGB_LAUNCH}" 2>/dev/null || true
  pkill -f "roslaunch ${CAMERA_PKG} ${CAMERA_LAUNCH}" 2>/dev/null || true
}

pc_depth_publish_tf_stamp() {
  echo "$PID_DIR/depth_camera_publish_tf"
}

pc_depth_launch_has_publish_tf() {
  local desired="$1"
  # Match the live roslaunch argv recorded by the OS (authoritative for reuse).
  pgrep -af "roslaunch .*${DEPTH_CAMERA_LAUNCH}" 2>/dev/null \
    | grep -q "publish_tf:=${desired}"
}

pc_start_depth_camera() {
  if [ "$DEPTH_CAMERA_ENABLE" != "1" ]; then
    echo "[SKIP] depth camera disabled"
    return 0
  fi
  local desired="$DEPTH_CAMERA_PUBLISH_TF"
  local stamp
  stamp="$(pc_depth_publish_tf_stamp)"
  local recorded=""
  if [ -f "$stamp" ]; then
    recorded="$(cat "$stamp")"
  fi

  if pc_pid_alive depth_camera; then
    local must_restart=0
    if [ "$recorded" != "$desired" ]; then
      echo "[INFO] depth_camera publish_tf stamp '$recorded' != desired '$desired'; restarting"
      must_restart=1
    elif ! pc_depth_launch_has_publish_tf "$desired"; then
      echo "[INFO] live depth launch argv missing publish_tf:=$desired; restarting"
      must_restart=1
    fi
    if [ "$must_restart" = "1" ]; then
      pc_stop_depth_camera
    fi
  fi

  if ! pc_pid_alive depth_camera; then
    nohup roslaunch "$DEPTH_CAMERA_PKG" "$DEPTH_CAMERA_LAUNCH" \
      publish_tf:="$desired" \
      >"$DEPTH_CAMERA_LOG" 2>&1 &
    pc_write_pid depth_camera "$!"
    mkdir -p "$PID_DIR"
    echo "$desired" >"$stamp"
  fi
  pc_wait_topic_publisher "$DEPTH_INPUT_TOPIC" 50
  pc_wait_topic_publisher /camera/depth/camera_info 30
}

pc_stop_depth_camera() {
  pc_stop_pid depth_camera
  pkill -f "roslaunch ${DEPTH_CAMERA_PKG} ${DEPTH_CAMERA_LAUNCH}" 2>/dev/null || true
  rm -f "$(pc_depth_publish_tf_stamp)"
}

pc_depth_preview_enabled() {
  [ "$DEPTH_PREVIEW_ENABLE" = "1" ]
}

pc_start_depth_preview() {
  if ! pc_depth_preview_enabled; then
    echo "[SKIP] depth preview disabled"
    return 0
  fi
  if ! pc_pid_alive depth_preview; then
    nohup roslaunch "$DEPTH_PREVIEW_PKG" "$DEPTH_PREVIEW_LAUNCH" \
      input_topic:="$DEPTH_INPUT_TOPIC" \
      output_topic:="$DEPTH_PREVIEW_TOPIC" \
      >"$DEPTH_PREVIEW_LOG" 2>&1 &
    pc_write_pid depth_preview "$!"
  fi
  pc_wait_topic_publisher "$DEPTH_PREVIEW_TOPIC" 30
}

pc_stop_depth_preview() {
  pc_stop_pid depth_preview
  pkill -f "roslaunch ${DEPTH_PREVIEW_PKG} ${DEPTH_PREVIEW_LAUNCH}" 2>/dev/null || true
}

pc_start_step() {
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
  pc_rollback
  exit 1
}

pc_rollback() {
  local i
  echo "[ROLLBACK] stopping started modules"
  for ((i = ${#STARTED_STOPPERS[@]} - 1; i >= 0; i--)); do
    "${STARTED_STOPPERS[$i]}" || true
  done
  STARTED_STOPPERS=()
  stack_release_owner "$STACK_NAME"
}

pc_start_with_profile() {
  local mode="$1"
  PROFILE="$mode"
  pc_resolve_profile || exit 1
  pc_save_mode
  pc_source_ros || exit 1
  stack_assert_no_other_owner "$STACK_NAME"

  echo "ROS_MASTER_URI=$ROS_MASTER_URI"
  echo "ROS_IP=$ROS_IP"
  echo "MODE=$PROFILE"
  echo "DEPTH_CAMERA_PUBLISH_TF=$DEPTH_CAMERA_PUBLISH_TF"

  stack_claim_owner "$STACK_NAME"
  STARTED_STOPPERS=()

  pc_start_step roscore pc_start_roscore pc_stop_roscore
  if [ "$BRINGUP_ENABLE" = "1" ]; then
    pc_start_step bringup pc_start_bringup pc_stop_bringup
  fi
  if [ "$CAMERA_ENABLE" = "1" ]; then
    pc_start_step rgb_camera pc_start_rgb_camera pc_stop_rgb_camera
  fi
  if [ "$DEPTH_CAMERA_ENABLE" = "1" ]; then
    pc_start_step depth_camera pc_start_depth_camera pc_stop_depth_camera
  fi
  if pc_depth_preview_enabled; then
    pc_start_step depth_preview pc_start_depth_preview pc_stop_depth_preview
  fi

  echo "[OK] pc_stack $PROFILE started on robot"
}

pc_camera_start() { pc_start_with_profile camera; }
pc_camera_nearfield_start() { pc_start_with_profile camera_nearfield; }
pc_camera_deep_start() { pc_start_with_profile camera_deep; }
pc_radar2d_start() { pc_start_with_profile radar2d; }
pc_full_start() { pc_start_with_profile full; }

pc_camera_stop() {
  pc_load_mode
  pc_stop_depth_preview
  pc_stop_rgb_camera
  pc_stop_depth_camera
  if [ "$PROFILE" = "camera" ] || [ "$PROFILE" = "camera_nearfield" ] || [ "$PROFILE" = "camera_deep" ] || [ ! -f "$PID_DIR/mode" ]; then
    pc_stop_bringup
    pc_stop_roscore
    stack_release_owner "$STACK_NAME"
    rm -f "$PID_DIR/mode" "$PID_DIR/profile"
  fi
  echo "[OK] pc_stack camera stopped"
}

pc_camera_deep_stop() {
  pc_camera_stop
}

pc_camera_nearfield_stop() {
  pc_camera_stop
}

pc_radar2d_stop() {
  pc_load_mode
  pc_stop_bringup
  if [ "$PROFILE" = "radar2d" ] || { [ "$PROFILE" != "full" ] && ! pc_pid_alive camera && ! pc_pid_alive depth_camera; }; then
    pc_stop_roscore
    stack_release_owner "$STACK_NAME"
    rm -f "$PID_DIR/mode" "$PID_DIR/profile"
  fi
  echo "[OK] pc_stack radar2d stopped"
}

pc_full_stop() {
  pc_load_mode
  pc_stop_depth_preview
  pc_stop_depth_camera
  pc_stop_rgb_camera
  pc_stop_bringup
  pc_stop_roscore
  stack_release_owner "$STACK_NAME"
  rm -f "$PID_DIR/mode" "$PID_DIR/profile"
  echo "[OK] pc_stack full stopped"
}

pc_start() {
  pc_full_start
}

pc_stop() {
  pc_full_stop
}

pc_status() {
  pc_load_mode
  pc_source_ros 2>/dev/null || true

  echo "=== pc_stack status (robot) ==="
  echo "MODE=${PROFILE:-unknown}"
  echo "DEPTH_CAMERA_PUBLISH_TF=${DEPTH_CAMERA_PUBLISH_TF:-unknown}"
  echo "ROS_MASTER_URI=${ROS_MASTER_URI:-unset}"
  echo "ROS_IP=${ROS_IP:-unset}"
  echo "LOG_DIR=$LOG_DIR"

  if rostopic list >/dev/null 2>&1; then
    echo "master: OK"
  else
    echo "master: UNREACHABLE"
  fi

  if stack_owner_running "$STACK_NAME"; then
    echo "owner: active"
  else
    echo "owner: inactive"
  fi

  for name in roscore bringup camera rgb_relay depth_camera depth_preview; do
    if pc_pid_alive "$name"; then
      echo "$name: running pid=$(cat "$(pc_pid_file "$name")")"
    else
      echo "$name: stopped"
    fi
  done

  if rostopic list >/dev/null 2>&1; then
    echo "--- topics ---"
    for t in /scan /odom /camera/image_raw /camera/depth/image_raw /camera/depth/camera_info "$DEPTH_PREVIEW_TOPIC"; do
      if pc_topic_has_publisher "$t"; then
        echo "$t: publisher OK"
      else
        echo "$t: no publisher"
      fi
    done
  fi
}

pc_check_topics() {
  local require_scan="$1"
  local require_depth="$2"
  local require_depth_frame="${3:-0}"
  pc_source_ros || exit 1
  pc_wait_rosmaster 25 || exit 1

  if [ "$require_scan" = "1" ]; then
    local i=0
    while ! pc_topic_has_publisher /scan; do
      i=$((i + 1))
      if [ "$i" -ge 25 ]; then
        echo "[ERR] /scan has no publisher"
        exit 1
      fi
      sleep 1
    done
    echo "[OK] /scan publisher present"
    i=0
    while ! pc_topic_has_publisher /odom; do
      i=$((i + 1))
      if [ "$i" -ge 25 ]; then
        echo "[ERR] /odom has no publisher"
        exit 1
      fi
      sleep 1
    done
    echo "[OK] /odom publisher present"
  fi

  if [ "$require_depth" = "1" ]; then
    local i=0
    while ! pc_topic_has_publisher "$QT_RGB_TOPIC"; do
      i=$((i + 1))
      if [ "$i" -ge 40 ]; then
        echo "[ERR] $QT_RGB_TOPIC has no publisher"
        exit 1
      fi
      sleep 1
    done
    echo "[OK] $QT_RGB_TOPIC publisher present"

    i=0
    while ! pc_topic_has_publisher "$DEPTH_INPUT_TOPIC"; do
      i=$((i + 1))
      if [ "$i" -ge 40 ]; then
        echo "[ERR] $DEPTH_INPUT_TOPIC has no publisher"
        exit 1
      fi
      sleep 1
    done
    echo "[OK] $DEPTH_INPUT_TOPIC publisher present"

    i=0
    while ! pc_topic_has_publisher /camera/depth/camera_info; do
      i=$((i + 1))
      if [ "$i" -ge 30 ]; then
        echo "[ERR] /camera/depth/camera_info has no publisher"
        exit 1
      fi
      sleep 1
    done
    echo "[OK] /camera/depth/camera_info publisher present"

    if timeout 10 rostopic echo "$DEPTH_INPUT_TOPIC" -n 1 >/dev/null 2>&1; then
      echo "[OK] depth frame received"
    elif [ "$require_depth_frame" = "1" ]; then
      echo "[ERR] depth publisher exists but no frame within 10s"
      exit 1
    else
      echo "[WARN] depth publisher exists but no frame within 10s"
    fi
    if timeout 10 rostopic echo /camera/depth/camera_info -n 1 >/dev/null 2>&1; then
      echo "[OK] CameraInfo frame received"
    else
      echo "[ERR] CameraInfo publisher exists but no message within 10s"
      exit 1
    fi
  fi
}

pc_camera_check() {
  pc_check_topics 0 1
  if pc_topic_has_publisher "$DEPTH_PREVIEW_TOPIC"; then
    echo "[ERR] $DEPTH_PREVIEW_TOPIC should not run in camera (lightweight) mode"
    exit 1
  fi
  echo "[OK] $DEPTH_PREVIEW_TOPIC not published (lightweight)"
}
pc_assert_nearfield_publish_tf_live() {
  if [ "$DEPTH_CAMERA_PUBLISH_TF" != "0" ]; then
    echo "[ERR] PROFILE=$PROFILE resolved DEPTH_CAMERA_PUBLISH_TF=$DEPTH_CAMERA_PUBLISH_TF (want 0)"
    return 1
  fi
  if ! pc_pid_alive depth_camera; then
    echo "[ERR] depth_camera not running; cannot verify publish_tf"
    return 1
  fi
  local stamp recorded=""
  stamp="$(pc_depth_publish_tf_stamp)"
  if [ -f "$stamp" ]; then
    recorded="$(cat "$stamp")"
    if [ "$recorded" != "0" ]; then
      echo "[ERR] depth_camera stamp publish_tf=$recorded (want 0); restart with camera-nearfield-start"
      return 1
    fi
  else
    echo "[WARN] missing $stamp (legacy start); relying on live argv"
  fi
  if ! pc_depth_launch_has_publish_tf 0; then
    echo "[ERR] live depth launch does not show publish_tf:=0"
    pgrep -af "roslaunch .*${DEPTH_CAMERA_LAUNCH}" || true
    return 1
  fi
  echo "[OK] live Astra depth launch publish_tf:=0 (profile+stamp+argv)"
}

pc_camera_nearfield_check() {
  PROFILE=camera_nearfield
  pc_resolve_profile || exit 1
  pc_camera_check
  pc_assert_nearfield_publish_tf_live || exit 1
}
pc_camera_deep_check() {
  PROFILE=camera_deep
  pc_resolve_profile || exit 1
  pc_check_topics 0 1 1
  pc_check_depth_preview
}
pc_radar2d_check() { pc_check_topics 1 0; }
pc_full_check() { pc_check_topics 1 1; }

pc_check_depth_preview() {
  if ! pc_depth_preview_enabled; then
    return 0
  fi
  local i=0
  while ! pc_topic_has_publisher "$DEPTH_PREVIEW_TOPIC"; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
      echo "[ERR] $DEPTH_PREVIEW_TOPIC has no publisher"
      exit 1
    fi
    sleep 1
  done
  echo "[OK] $DEPTH_PREVIEW_TOPIC publisher present"
  if timeout 10 rostopic echo "$DEPTH_PREVIEW_TOPIC" -n 1 >/dev/null 2>&1; then
    echo "[OK] depth preview frame received"
  else
    echo "[ERR] depth preview publisher exists but no frame within 10s"
    exit 1
  fi
}

pc_check() {
  pc_full_check
}

pc_logs() {
  mkdir -p "$LOG_DIR"
  tail -n 40 -F "$ROSCORE_LOG" "$BRINGUP_LOG" "$CAMERA_LOG" "$DEPTH_CAMERA_LOG" "$DEPTH_PREVIEW_LOG" 2>/dev/null \
    || tail -n 80 "$ROSCORE_LOG" "$BRINGUP_LOG" "$CAMERA_LOG" "$DEPTH_CAMERA_LOG" "$DEPTH_PREVIEW_LOG" 2>/dev/null \
    || echo "[INFO] no logs yet under $LOG_DIR"
}
