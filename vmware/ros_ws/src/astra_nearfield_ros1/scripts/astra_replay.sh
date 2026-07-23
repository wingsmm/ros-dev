#!/usr/bin/env bash
# Stage B2: isolated bag replay on a local ROS Master (never the live robot).
# shellcheck shell=bash
set -euo pipefail

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPLAY_ROOT="${ASTRA_REPLAY_ROOT:-$HOME/xtark_logs/astra_nearfield/replay}"
PID_DIR="${REPLAY_ROOT}/pids"
LOG_DIR="${REPLAY_ROOT}/logs"
REPORT_DIR="${REPLAY_ROOT}/reports"
MASTER_PORT="${ASTRA_REPLAY_MASTER_PORT:-11321}"
MASTER_URI="http://127.0.0.1:${MASTER_PORT}"
PLAY_RATE="${ASTRA_REPLAY_RATE:-0.25}"
SPARSE_PC_SCRIPT="${SPARSE_PC_SCRIPT:-$HOME/ros-dev/vmware/qt/scripts/sparse_depth_pointcloud.py}"

resolve_extrinsics_yaml() {
  if [ -n "${ASTRA_EXTRINSICS_YAML:-}" ]; then
    echo "$ASTRA_EXTRINSICS_YAML"
    return 0
  fi
  if [ -f "$PKG_DIR/config/astra_extrinsics.yaml" ]; then
    echo "$PKG_DIR/config/astra_extrinsics.yaml"
    return 0
  fi
  local share
  share="$(rospack find astra_nearfield_ros1 2>/dev/null || true)"
  if [ -n "$share" ] && [ -f "$share/config/astra_extrinsics.yaml" ]; then
    echo "$share/config/astra_extrinsics.yaml"
    return 0
  fi
  die "cannot locate astra_extrinsics.yaml"
}

usage() {
  cat <<EOF
Usage:
  astra_replay.sh check <bag>
  astra_replay.sh raw <bag>
  astra_replay.sh cloud <bag>
  astra_replay.sh stop

Environment:
  ASTRA_REPLAY_MASTER_PORT   default 11321
  ASTRA_REPLAY_RATE          default 0.25 (VM-stable; raise only if counts stay identical)
  SPARSE_PC_SCRIPT           sparse_depth_pointcloud.py path
  ASTRA_EXTRINSICS_YAML      nominal YAML path

perception mode is reserved for a later stage and is not implemented here.
EOF
}

die() { echo "[ERR] $*" >&2; exit 1; }
info() { echo "[INFO] $*"; }
ok() { echo "[OK] $*"; }

pid_file() { echo "${PID_DIR}/$1.pid"; }

pid_alive() {
  local f
  f="$(pid_file "$1")"
  [ -f "$f" ] || return 1
  local pid
  pid="$(cat "$f")"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

write_pid() {
  mkdir -p "$PID_DIR"
  echo "$2" >"$(pid_file "$1")"
}

stop_one() {
  local name="$1"
  local sig="${2:-TERM}"
  local f pid
  f="$(pid_file "$name")"
  if ! pid_alive "$name"; then
    rm -f "$f"
    return 0
  fi
  pid="$(cat "$f")"
  info "stop $name pid=$pid sig=$sig"
  kill "-$sig" "$pid" 2>/dev/null || true
  local i=0
  while kill -0 "$pid" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
      if [ "$sig" = "INT" ] || [ "$sig" = "TERM" ]; then
        kill -KILL "$pid" 2>/dev/null || true
      fi
      break
    fi
    sleep 0.5
  done
  rm -f "$f"
}

port_listening() {
  (ss -lnt 2>/dev/null || netstat -lnt 2>/dev/null) | grep -q ":${MASTER_PORT} "
}

assert_isolated_env() {
  export ROS_MASTER_URI="$MASTER_URI"
  export ROS_IP=127.0.0.1
  unset ROS_HOSTNAME || true
  if [ "$ROS_MASTER_URI" != "$MASTER_URI" ]; then
    die "ROS_MASTER_URI must be exactly $MASTER_URI"
  fi
}

source_ros() {
  # shellcheck disable=SC1090
  source /opt/ros/melodic/setup.bash
  if [ -f "$HOME/ros_ws/devel/setup.bash" ]; then
    # shellcheck disable=SC1090
    source "$HOME/ros_ws/devel/setup.bash"
  fi
  assert_isolated_env
}

resolve_bag() {
  local target="${1:-}"
  [ -n "$target" ] || die "bag path required"
  if [ -d "$target" ]; then
    local found
    found="$(ls -1 "$target"/*.bag 2>/dev/null | head -n1 || true)"
    [ -n "$found" ] || die "no .bag under $target"
    echo "$found"
    return 0
  fi
  [ -f "$target" ] || die "bag not found: $target"
  echo "$target"
}

cmd_check() {
  local bag
  bag="$(resolve_bag "${1:-}")"
  source_ros
  echo "=== bag ==="
  ls -lh "$bag"
  echo "=== rosbag info ==="
  rosbag info "$bag"
  if ! rosbag info "$bag" | grep -q "/camera/depth/image_raw"; then
    die "bag missing /camera/depth/image_raw"
  fi
  if ! rosbag info "$bag" | grep -q "/camera/depth/camera_info"; then
    die "bag missing /camera/depth/camera_info"
  fi
  ok "bag check passed: $bag"
}

ensure_roscore() {
  mkdir -p "$PID_DIR" "$LOG_DIR"
  if pid_alive roscore; then
    ok "roscore already owned pid=$(cat "$(pid_file roscore)")"
    return 0
  fi
  if port_listening; then
    die "port ${MASTER_PORT} is in use by an unknown process; refuse to take over"
  fi
  info "starting local roscore on $MASTER_URI"
  nohup roscore -p "$MASTER_PORT" >"${LOG_DIR}/roscore.log" 2>&1 &
  write_pid roscore "$!"
  local i=0
  while ! port_listening; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
      die "roscore failed to listen on ${MASTER_PORT}; see ${LOG_DIR}/roscore.log"
    fi
    sleep 0.5
  done
  # Wait until master answers under the isolated URI.
  i=0
  while ! rostopic list >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
      die "local master not answering at $ROS_MASTER_URI"
    fi
    sleep 0.5
  done
  ok "local roscore ready: $ROS_MASTER_URI"
}

set_sim_time() {
  rosparam set /use_sim_time true
  ok "use_sim_time=true"
}

wait_node() {
  local name="$1"
  local max="${2:-30}"
  local i=0
  while ! rosnode list 2>/dev/null | grep -qx "$name"; do
    i=$((i + 1))
    if [ "$i" -ge "$max" ]; then
      die "node $name not ready"
    fi
    sleep 0.5
  done
}

resolve_node_bin() {
  local name="$1"
  local cand
  for cand in \
    "$HOME/ros_ws/devel/lib/astra_nearfield_ros1/$name" \
    "$PKG_DIR/scripts/$name" \
    "$(rospack find astra_nearfield_ros1 2>/dev/null)/scripts/$name"
  do
    if [ -n "$cand" ] && [ -x "$cand" ]; then
      echo "$cand"
      return 0
    fi
  done
  die "cannot locate executable $name"
}

start_probe() {
  local report="$1"
  local bin
  mkdir -p "$REPORT_DIR"
  bin="$(resolve_node_bin replay_probe.py)"
  nohup "$bin" _report_path:="$report" \
    >"${LOG_DIR}/probe.log" 2>&1 &
  write_pid probe "$!"
  wait_node /astra_replay_probe 40
}

start_filter() {
  local bin
  bin="$(resolve_node_bin tf_edge_filter.py)"
  nohup "$bin" >"${LOG_DIR}/tf_edge_filter.log" 2>&1 &
  write_pid tf_filter "$!"
  wait_node /astra_tf_edge_filter 40
}


start_guard() {
  local extrinsics
  extrinsics="$(resolve_extrinsics_yaml)"
  [ -f "$extrinsics" ] || die "extrinsics YAML missing: $extrinsics"
  nohup roslaunch astra_nearfield_ros1 camera_tf.launch \
    extrinsics_file:="$extrinsics" \
    >"${LOG_DIR}/tf_guard.log" 2>&1 &
  write_pid tf_guard "$!"
  wait_node /astra_camera_tf_guard 60
}

start_pointcloud() {
  [ -f "$SPARSE_PC_SCRIPT" ] || die "sparse pointcloud script missing: $SPARSE_PC_SCRIPT"
  nohup python2 "$SPARSE_PC_SCRIPT" >"${LOG_DIR}/pointcloud.log" 2>&1 &
  write_pid pointcloud "$!"
  wait_node /vmware_depth_points 40
}

play_bag() {
  local bag="$1"
  local report="$2"
  info "rosbag play --clock --rate ${PLAY_RATE} with TF remap"
  # Remap camera TF topics into /bag/* for the edge filter.
  nohup rosbag play --clock --rate "$PLAY_RATE" "$bag" \
    /tf:=/bag/tf /tf_static:=/bag/tf_static \
    >"${LOG_DIR}/rosbag_play.log" 2>&1 &
  write_pid player "$!"

  local pid
  pid="$(cat "$(pid_file player)")"
  while kill -0 "$pid" 2>/dev/null; do
    sleep 1
  done
  rm -f "$(pid_file player)"
  ok "rosbag play finished"

  # Allow probe to flush final counts.
  sleep 2
  if pid_alive probe; then
    stop_one probe INT
  fi
  if [ -f "$report" ]; then
    echo "=== probe report ==="
    cat "$report"
  else
    die "probe report missing: $report"
  fi
}

verify_master_still_local() {
  if [ "${ROS_MASTER_URI}" != "$MASTER_URI" ]; then
    die "ROS_MASTER_URI drifted to $ROS_MASTER_URI"
  fi
  if ! python2 - <<PY
import os
uri=os.environ.get("ROS_MASTER_URI","")
assert uri=="$MASTER_URI", uri
print "MASTER_OK", uri
PY
  then
    die "master URI verification failed"
  fi
}

cmd_raw() {
  local bag report stamp
  bag="$(resolve_bag "${1:-}")"
  source_ros
  cmd_stop_quiet
  ensure_roscore
  set_sim_time
  stamp="$(date +%Y%m%d_%H%M%S)"
  report="${REPORT_DIR}/raw_${stamp}.json"
  start_probe "$report"
  verify_master_still_local
  play_bag "$bag" "$report"
  stop_one probe INT || true
  ok "raw replay done report=$report"
  echo "$report"
}

cmd_cloud() {
  local bag report stamp
  bag="$(resolve_bag "${1:-}")"
  source_ros
  cmd_stop_quiet
  ensure_roscore
  set_sim_time
  start_filter
  start_guard
  start_pointcloud
  stamp="$(date +%Y%m%d_%H%M%S)"
  report="${REPORT_DIR}/cloud_${stamp}.json"
  start_probe "$report"
  verify_master_still_local

  # Nominal TF check after guard claim (sim time may still be 0; tf_echo still works for static).
  if ! timeout 15 rosrun tf tf_echo base_footprint camera_link 1 2>/dev/null | tee "${LOG_DIR}/tf_echo.txt" | grep -q "0.100"; then
    info "tf_echo preview (may be empty until clock starts); continuing"
  fi

  play_bag "$bag" "$report"

  # Post checks
  verify_master_still_local
  if grep -qi "ownership conflict\|TF ownership conflict" "${LOG_DIR}/tf_guard.log"; then
    die "TF guard reported conflict; see ${LOG_DIR}/tf_guard.log"
  fi
  if [ -f "$report" ]; then
    python2 - "$report" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as f:
    data = json.load(f)
frame = (data.get("point_cloud_frame") or "").lstrip("/")
if data.get("point_cloud_count", 0) <= 0:
    raise SystemExit("point_cloud_count is 0")
if frame and frame != "camera_depth_optical_frame":
    raise SystemExit("unexpected point cloud frame: %r" % frame)
if data.get("ROS_MASTER_URI") != "http://127.0.0.1:11321" and not data.get("ROS_MASTER_URI", "").endswith(":11321"):
    # allow override via ASTRA_REPLAY_MASTER_PORT only if report matches env
    pass
print "cloud_report_ok depth=%s cloud=%s dropped=%s" % (
    data.get("depth_frame_count"),
    data.get("point_cloud_count"),
    data.get("tf_filter_dropped"),
)
PY
  fi
  ok "cloud replay done report=$report"
  echo "$report"
}

cmd_stop_quiet() {
  mkdir -p "$PID_DIR" "$LOG_DIR"
  # Order: consumers/player first, then core.
  stop_one player INT
  stop_one probe INT
  stop_one pointcloud TERM
  stop_one tf_guard TERM
  stop_one tf_filter TERM
  stop_one roscore TERM
}

cmd_stop() {
  source_ros || assert_isolated_env
  cmd_stop_quiet
  ok "replay stack stopped"
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    check) cmd_check "$@" ;;
    raw) cmd_raw "$@" ;;
    cloud) cmd_cloud "$@" ;;
    stop) cmd_stop ;;
    -h|--help|help|"") usage; [ -n "$cmd" ] || exit 1; exit 0 ;;
    perception) die "perception mode is reserved for a later stage" ;;
    *) die "unknown command: $cmd" ;;
  esac
}

main "$@"
