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
SLAM_ENABLE="${SLAM_ENABLE:-1}"
SLAM_SCAN_TOPIC="${SLAM_SCAN_TOPIC:-/scan}"
# xtark 使用 base_footprint，不�?ROS 默认�?base_link
SLAM_BASE_FRAME="${SLAM_BASE_FRAME:-base_footprint}"
SLAM_MAP_TOPIC="${SLAM_MAP_TOPIC:-/map}"
NAV_ENABLE="${NAV_ENABLE:-1}"
NAV_PKG="${NAV_PKG:-xtark_nav}"
NAV_LAUNCH="${NAV_LAUNCH:-online_slam_move_base.launch}"
NAV_SPEED_SYNC_MARKER="run_android_nav_speed_sync"
ROBOT_POSE_PKG="${ROBOT_POSE_PKG:-xtark_nav}"
ROBOT_POSE_LAUNCH="${ROBOT_POSE_LAUNCH:-robot_pose_in_map.launch}"
ROBOT_POSE_NODE="${ROBOT_POSE_NODE:-robot_pose_in_map_publisher}"
ROBOT_POSE_TOPIC="${ROBOT_POSE_TOPIC:-/robot_pose_in_map}"
ROBOT_POSE_RATE="${ROBOT_POSE_RATE:-10}"
ROBOT_POSE_TF_TIMEOUT="${ROBOT_POSE_TF_TIMEOUT:-0.3}"

# ===== gmapping 地图参数（直接改下面几行即可�?====
# 物理尺寸 �?(xmax-xmin) × (ymax-ymin)；栅格数 �?尺寸 / SLAM_DELTA
# 当前 4×4 m @ delta=0.1 �?�?40×40 格；Android 黄框�?/slam_gmapping/xmin 等自动读�?SLAM_XMIN=-2
SLAM_XMAX=2
SLAM_YMIN=-2
SLAM_YMAX=2
SLAM_DELTA=0.10
# 小空间建图：限制激光有效距离，避免地图被远距离回波撑大
SLAM_MAX_URANGE=2.0
SLAM_MAX_RANGE=2.5
SLAM_LINEAR_UPDATE=0.20
SLAM_ANGULAR_UPDATE=0.20
SLAM_TEMPORAL_UPDATE=2.0
SLAM_MAP_UPDATE_INTERVAL=1.0
# ===================================================

usage() {
  cat <<EOF
Usage: android_stack.sh <command>

Commands:
  start      Start roscore + bringup + camera + gmapping + move_base
  stop       Stop all Android-test processes
  status     Diagnostic output for /map, move_base, cmd_vel, TF
  watch-nav  Live echo of goal, status, cmd_vel (for A-B-A debugging)
  logs       Tail roscore/bringup/gmapping/move_base logs

Android app Master URI:
  ${ROS_MASTER_URI}

Environment exported before launch:
  ROS_MASTER_URI=${ROS_MASTER_URI}
  ROS_IP=${ROS_IP}
  XTARK_LOG_DIR=${XTARK_LOG_DIR}
  CAMERA_ENABLE=${CAMERA_ENABLE}
  SLAM_ENABLE=${SLAM_ENABLE}
  SLAM_SCAN_TOPIC=${SLAM_SCAN_TOPIC}
  SLAM_BASE_FRAME=${SLAM_BASE_FRAME}
  SLAM_MAP_TOPIC=${SLAM_MAP_TOPIC}
  gmapping map=[${SLAM_XMIN},${SLAM_XMAX}]x[${SLAM_YMIN},${SLAM_YMAX}] delta=${SLAM_DELTA}
  NAV_ENABLE=${NAV_ENABLE}
  NAV_PKG=${NAV_PKG}
  NAV_LAUNCH=${NAV_LAUNCH}
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

wait_for_rosmaster_api() {
  local max="${1:-30}"
  local i=0
  while ! rostopic list &>/dev/null; do
    sleep 1
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "[ERR] rosmaster API not ready after ${max}s"
      return 1
    fi
  done
  echo "rosmaster API ready (${i}s)"
}

wait_master() {
  local i=0
  while [ "$i" -lt 20 ]; do
    if is_listening_11311; then
      wait_for_rosmaster_api 30
      return $?
    fi
    sleep 1
    i=$((i + 1))
  done
  echo "[ERR] roscore did not open 11311"
  tail -80 "$XTARK_LOG_DIR/roscore.log" 2>/dev/null || true
  return 1
}

wait_for_topic() {
  local topic="$1"
  local max="${2:-40}"
  local i=0
  while ! rostopic list 2>/dev/null | grep -qx "$topic"; do
    sleep 1
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      echo "[ERR] topic $topic not available after ${max}s"
      return 1
    fi
  done
  echo "topic $topic available (${i}s)"
}

wait_topic_once() {
  local topic="$1"
  local timeout_sec="${2:-10}"
  echo "Waiting for first message on $topic (timeout ${timeout_sec}s) ..."
  if timeout "$timeout_sec" rostopic echo "$topic" -n 1 >/dev/null 2>&1; then
    echo "$topic ready"
    return 0
  fi
  echo "[WARN] $topic not ready within ${timeout_sec}s"
  return 1
}

wait_for_map_message() {
  local max="${1:-45}"
  local i=0
  while [ "$i" -lt "$max" ]; do
    if rostopic list 2>/dev/null | grep -qx "$SLAM_MAP_TOPIC"; then
      if timeout 10 rostopic echo "$SLAM_MAP_TOPIC" -n 1 >/dev/null 2>&1; then
        echo "$SLAM_MAP_TOPIC publishing (${i}s)"
        return 0
      fi
    fi
    sleep 1
    i=$((i + 1))
  done
  echo "[ERR] $SLAM_MAP_TOPIC not publishing after ${max}s"
  tail -40 "$XTARK_LOG_DIR/gmapping.log" 2>/dev/null || true
  return 1
}

is_gmapping_running() {
  pgrep -af 'rosrun gmapping slam_gmapping|slam_gmapping scan:=' >/dev/null 2>&1
}

is_move_base_node_up() {
  rosnode list 2>/dev/null | grep -qx '/move_base'
}

move_base_status_has_publisher() {
  rostopic info /move_base/status 2>/dev/null | grep -A5 '^Publishers:' | grep -q '/move_base'
}

wait_for_move_base_ready() {
  local max="${1:-45}"
  local i=0
  while [ "$i" -lt "$max" ]; do
    if is_move_base_node_up && move_base_status_has_publisher; then
      echo "move_base ready (/move_base/status publishing, ${i}s)"
      return 0
    fi
    if [ $((i % 5)) -eq 0 ] && [ "$i" -gt 0 ]; then
      echo "  ... still waiting for move_base (${i}s)"
    fi
    sleep 1
    i=$((i + 1))
  done
  echo "[ERR] move_base not ready after ${max}s"
  echo "[HINT] check move_base.log for base_link vs base_footprint TF errors"
  echo "--- move_base.log (tail) ---"
  tail -30 "$XTARK_LOG_DIR/move_base.log" 2>/dev/null || true
  return 1
}

start_gmapping() {
  if [ "$SLAM_ENABLE" != "1" ]; then
    echo "SLAM disabled (SLAM_ENABLE=$SLAM_ENABLE)"
    return 0
  fi

  if is_gmapping_running; then
    echo "gmapping already running"
    return 0
  fi

  echo "Cleaning stale /slam_gmapping registration if needed"
  rosnode cleanup >/tmp/run_android_rosnode_cleanup.log 2>&1 || true

  echo "Starting gmapping: scan:=${SLAM_SCAN_TOPIC} base_frame:=${SLAM_BASE_FRAME} map=[${SLAM_XMIN},${SLAM_XMAX}]x[${SLAM_YMIN},${SLAM_YMAX}] delta=${SLAM_DELTA} maxUrange=${SLAM_MAX_URANGE} maxRange=${SLAM_MAX_RANGE} linearUpdate=${SLAM_LINEAR_UPDATE} angularUpdate=${SLAM_ANGULAR_UPDATE}"
  nohup rosrun gmapping slam_gmapping \
    "scan:=${SLAM_SCAN_TOPIC}" \
    "_base_frame:=${SLAM_BASE_FRAME}" \
    "_xmin:=${SLAM_XMIN}" \
    "_xmax:=${SLAM_XMAX}" \
    "_ymin:=${SLAM_YMIN}" \
    "_ymax:=${SLAM_YMAX}" \
    "_delta:=${SLAM_DELTA}" \
    "_maxUrange:=${SLAM_MAX_URANGE}" \
    "_maxRange:=${SLAM_MAX_RANGE}" \
    "_linearUpdate:=${SLAM_LINEAR_UPDATE}" \
    "_angularUpdate:=${SLAM_ANGULAR_UPDATE}" \
    "_temporalUpdate:=${SLAM_TEMPORAL_UPDATE}" \
    "_map_update_interval:=${SLAM_MAP_UPDATE_INTERVAL}" \
    "__name:=slam_gmapping" \
    >"$XTARK_LOG_DIR/gmapping.log" 2>&1 &
  echo "gmapping started pid=$! log=$XTARK_LOG_DIR/gmapping.log"
}

start_navigation() {
  if [ "$NAV_ENABLE" != "1" ]; then
    echo "Navigation disabled (NAV_ENABLE=$NAV_ENABLE)"
    return 0
  fi

  if is_move_base_node_up && move_base_status_has_publisher; then
    echo "move_base already running"
    return 0
  fi

  if is_move_base_node_up && ! move_base_status_has_publisher; then
    echo "WARN: stale /move_base node without /move_base/status publisher; restarting navigation"
    pkill -f "$NAV_LAUNCH" || true
    pkill -f '[ /]move_base([ ]|$)' || true
    sleep 2
  fi

  echo "Starting move_base: roslaunch ${NAV_PKG} ${NAV_LAUNCH}"
  nohup roslaunch "$NAV_PKG" "$NAV_LAUNCH" \
    >"$XTARK_LOG_DIR/move_base.log" 2>&1 &
  echo "move_base started pid=$! log=$XTARK_LOG_DIR/move_base.log"
}

start_nav_speed_sync() {
  if [ "$NAV_ENABLE" != "1" ]; then
    return 0
  fi

  pkill -f "$NAV_SPEED_SYNC_MARKER" || true
  sleep 1

  nohup python - <<'PY' >"$XTARK_LOG_DIR/nav_speed_sync.log" 2>&1 &
# run_android_nav_speed_sync
import rospy
from dynamic_reconfigure.client import Client
from geometry_msgs.msg import Twist

MIN_LINEAR = 0.02
MAX_LINEAR = 0.30
MIN_ANGULAR = 0.05
MAX_ANGULAR = 0.80


class NavSpeedSync(object):
    def __init__(self):
        rospy.init_node("nav_speed_sync", anonymous=False)
        self._client = None
        self._last_linear = None
        self._last_angular = None
        rospy.Subscriber("/android/nav_speed", Twist, self._on_speed, queue_size=1)
        rospy.Timer(rospy.Duration(2.0), self._ensure_client)

    def _ensure_client(self, _event):
        if self._client is not None:
            return
        try:
            self._client = Client("/move_base/TrajectoryPlannerROS", timeout=2.0)
            rospy.loginfo("nav_speed_sync connected to TrajectoryPlannerROS")
        except Exception as exc:
            rospy.logwarn_throttle(10.0, "nav_speed_sync waiting for move_base: %s", exc)

    def _on_speed(self, msg):
        linear = max(MIN_LINEAR, min(MAX_LINEAR, abs(msg.linear.x)))
        angular = max(MIN_ANGULAR, min(MAX_ANGULAR, abs(msg.angular.z)))
        if linear == self._last_linear and angular == self._last_angular:
            return
        self._ensure_client(None)
        if self._client is None:
            return
        cfg = {
            "max_vel_x": linear,
            "min_vel_x": MIN_LINEAR,
            "max_vel_theta": angular,
            "min_in_place_vel_theta": MIN_ANGULAR,
            "acc_lim_x": min(0.90, max(0.30, linear * 3.0)),
            "acc_lim_theta": min(2.40, max(0.60, angular * 3.0)),
        }
        try:
            self._client.update_configuration(cfg)
            self._last_linear = linear
            self._last_angular = angular
            rospy.loginfo("nav_speed_sync applied max_vel_x=%.2f max_vel_theta=%.2f", linear, angular)
        except Exception as exc:
            rospy.logwarn("nav_speed_sync update failed: %s", exc)
            self._client = None


if __name__ == "__main__":
    try:
        NavSpeedSync()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
PY
  echo "nav_speed_sync started pid=$! log=$XTARK_LOG_DIR/nav_speed_sync.log"
}

start_robot_pose_in_map() {
  if [ "$SLAM_ENABLE" != "1" ]; then
    return 0
  fi

  if ! rospack find "$ROBOT_POSE_PKG" >/dev/null 2>&1; then
    echo "[WARN] robot pose package missing: $ROBOT_POSE_PKG"
    return 0
  fi

  pkill -f "$ROBOT_POSE_LAUNCH" || true
  pkill -f "$ROBOT_POSE_NODE" || true
  sleep 1
  echo "Starting robot_pose_in_map: roslaunch $ROBOT_POSE_PKG $ROBOT_POSE_LAUNCH"
  nohup roslaunch "$ROBOT_POSE_PKG" "$ROBOT_POSE_LAUNCH" \
    map_frame:=map \
    base_frame:=base_footprint \
    pose_topic:="$ROBOT_POSE_TOPIC" \
    rate:="$ROBOT_POSE_RATE" \
    transform_timeout:="$ROBOT_POSE_TF_TIMEOUT" \
    >"$XTARK_LOG_DIR/robot_pose_in_map.log" 2>&1 &
  echo "robot_pose_in_map started pid=$! log=$XTARK_LOG_DIR/robot_pose_in_map.log"
}

start_slam_and_nav() {
  if [ "$SLAM_ENABLE" = "1" ]; then
    echo "--- wait for $SLAM_SCAN_TOPIC before gmapping ---"
    wait_for_topic "$SLAM_SCAN_TOPIC" 45
    wait_for_topic "/odom" 25 || echo "[WARN] /odom slow; continuing"
    start_gmapping
    echo "--- wait for $SLAM_MAP_TOPIC before move_base ---"
    wait_topic_once "$SLAM_MAP_TOPIC" 15 || echo "[WARN] $SLAM_MAP_TOPIC not ready yet"
    wait_for_map_message 45
    start_robot_pose_in_map
  fi

  if [ "$NAV_ENABLE" = "1" ]; then
    start_navigation
    wait_for_move_base_ready 45
    start_nav_speed_sync
  fi
}

verify_startup() {
  local ok=1
  echo "--- startup verify ---"

  if ! is_listening_11311; then
    echo "[FAIL] roscore not listening on 11311"
    ok=0
  else
    echo "[OK] roscore on 11311"
  fi

  if ! pgrep -af "roslaunch $BRINGUP_PKG $BRINGUP_LAUNCH" >/dev/null; then
    echo "[FAIL] xtark bringup not running"
    ok=0
  else
    echo "[OK] xtark bringup running"
  fi

  if [ "$SLAM_ENABLE" = "1" ]; then
    if ! is_gmapping_running; then
      echo "[FAIL] gmapping not running"
      ok=0
    else
      echo "[OK] gmapping running"
    fi
    if ! timeout 8 rostopic echo "$SLAM_MAP_TOPIC" -n 1 >/dev/null 2>&1; then
      echo "[FAIL] $SLAM_MAP_TOPIC not publishing"
      ok=0
    else
      echo "[OK] $SLAM_MAP_TOPIC publishing"
    fi
    if ! timeout 5 rostopic echo "$ROBOT_POSE_TOPIC" -n 1 >/dev/null 2>&1; then
      echo "[FAIL] $ROBOT_POSE_TOPIC not publishing"
      ok=0
    else
      echo "[OK] $ROBOT_POSE_TOPIC publishing"
    fi
  fi

  if [ "$NAV_ENABLE" = "1" ]; then
    if ! is_move_base_node_up; then
      echo "[FAIL] /move_base node missing"
      ok=0
    elif ! move_base_status_has_publisher; then
      echo "[FAIL] /move_base/status has no publisher from move_base"
      ok=0
    else
      echo "[OK] move_base ready"
    fi
  fi

  if [ "$ok" -eq 1 ]; then
    echo "[OK] Android ROS stack ready for App"
    return 0
  fi
  echo "[FAIL] Android ROS stack incomplete; check logs in $XTARK_LOG_DIR"
  return 1
}

status() {
  source_ros
  echo "---env---"
  echo "ROS_MASTER_URI=$ROS_MASTER_URI"
  echo "ROS_IP=$ROS_IP"
  echo "---11311---"
  (ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null) | grep 11311 || true

  echo "---rosnode list---"
  rosnode list 2>&1 || true

  echo "---topics (nav subset)---"
  rostopic list 2>&1 | grep -E '^/(map|scan|odom|cmd_vel|move_base|move_base_simple|robot_pose|tf)' || true

  echo "---map---"
  rostopic info "$SLAM_MAP_TOPIC" 2>&1 || true
  timeout 5 rostopic hz "$SLAM_MAP_TOPIC" 2>&1 || true

  echo "---scan---"
  rostopic info /scan 2>&1 || true
  timeout 5 rostopic hz /scan 2>&1 || true

  echo "---odom---"
  rostopic info /odom 2>&1 || true
  timeout 5 rostopic hz /odom 2>&1 || true

  echo "---move_base goal---"
  rostopic info /move_base_simple/goal 2>&1 || true

  echo "---move_base status---"
  rostopic info /move_base/status 2>&1 || true
  timeout 3 rostopic echo /move_base/status -n 1 2>&1 || true

  echo "---cmd_vel---"
  rostopic info /cmd_vel 2>&1 || true
  timeout 3 rostopic echo /cmd_vel -n 1 2>&1 || true

  echo "---robot_pose_in_map---"
  rostopic info "$ROBOT_POSE_TOPIC" 2>&1 || true
  timeout 3 rostopic echo "$ROBOT_POSE_TOPIC" -n 1 2>&1 || true
  timeout 5 rostopic hz "$ROBOT_POSE_TOPIC" 2>&1 || true

  echo "---tf map base_footprint---"
  timeout 5 rosrun tf tf_echo map base_footprint 2>&1 | head -40 || true

  echo "---processes---"
  pgrep -af 'roscore|rosmaster|roslaunch xtark_driver xtark_bringup.launch|roslaunch xtark_driver xtark_camera.launch|uvc_camera_node|web_video_server|image_transport.*republish|rosrun gmapping slam_gmapping|slam_gmapping scan:=|online_slam_move_base.launch|[ /]move_base([ ]|$)|run_android_nav_speed_sync|robot_pose_in_map.launch|robot_pose_in_map_publisher' || true

  verify_startup || true
}

watch_nav() {
  source_ros
  echo "Watching Android navigation topics (Ctrl+C to stop)..."
  echo "  1. /move_base_simple/goal"
  echo "  2. /move_base/status"
  echo "  3. /cmd_vel"
  echo

  rostopic echo /move_base_simple/goal &
  local p1=$!
  rostopic echo /move_base/status &
  local p2=$!
  rostopic echo /cmd_vel &
  local p3=$!

  trap 'kill '"$p1"' '"$p2"' '"$p3"' 2>/dev/null; exit 0' INT TERM
  wait
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
    wait_for_rosmaster_api 15
  fi

  if pgrep -af "roslaunch $BRINGUP_PKG $BRINGUP_LAUNCH" >/dev/null; then
    echo "xtark bringup already running"
    start_slam_and_nav
    local rc=0
    verify_startup || rc=$?
    echo ""
    echo "--- quick status (run: $0 status | watch-nav for live goal/cmd_vel) ---"
    status
    return $rc
  fi

  echo "Android app Master URI: $ROS_MASTER_URI"
  echo "Starting xtark bringup with ROS_IP=$ROS_IP"
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

  start_slam_and_nav
  local rc=0
  verify_startup || rc=$?
  echo ""
  echo "--- quick status (run: $0 status | watch-nav for live goal/cmd_vel) ---"
  status
  return $rc
}

stop() {
  pkill -f "$ROBOT_POSE_LAUNCH" || true
  pkill -f "$ROBOT_POSE_NODE" || true
  pkill -f "$NAV_SPEED_SYNC_MARKER" || true
  pkill -f "$NAV_LAUNCH" || true
  pkill -f '[ /]move_base([ ]|$)' || true
  pkill -f 'rosrun gmapping slam_gmapping' || true
  pkill -f 'slam_gmapping scan:=' || true
  pkill -f "roslaunch $CAMERA_PKG $CAMERA_LAUNCH" || true
  pkill -f 'uvc_camera_node' || true
  pkill -f "roslaunch $BRINGUP_PKG $BRINGUP_LAUNCH" || true
  pkill -f "$BRINGUP_LAUNCH" || true
  pkill -f 'rosmaster --core -p 11311' || true
  pkill -f 'roscore' || true
  echo "Android-test roscore/bringup/gmapping/navigation stop requested"
}

cmd="${1:-help}"
case "$cmd" in
  start) start ;;
  status) status ;;
  stop) stop ;;
  watch-nav) watch_nav ;;
  logs) tail -120 "$XTARK_LOG_DIR/roscore.log" "$XTARK_LOG_DIR/bringup.log" "$XTARK_LOG_DIR/camera.log" "$XTARK_LOG_DIR/gmapping.log" "$XTARK_LOG_DIR/move_base.log" "$XTARK_LOG_DIR/nav_speed_sync.log" "$XTARK_LOG_DIR/robot_pose_in_map.log" 2>/dev/null || true ;;
  -h|--help|help|"") usage ;;
  *)
    echo "Unknown command: $cmd"
    usage
    exit 1
    ;;
esac
