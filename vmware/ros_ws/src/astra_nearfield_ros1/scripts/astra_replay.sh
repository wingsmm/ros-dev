#!/usr/bin/env bash
# Stage B2: isolated bag replay on a local ROS Master (never the live robot).
# shellcheck shell=bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || realpath "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
PKG_DIR="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
REPLAY_ROOT="${ASTRA_REPLAY_ROOT:-$HOME/xtark_logs/astra_nearfield/replay}"
PID_DIR="${REPLAY_ROOT}/pids"
LOG_DIR="${REPLAY_ROOT}/logs"
REPORT_DIR="${REPLAY_ROOT}/reports"
MASTER_PORT="${ASTRA_REPLAY_MASTER_PORT:-11321}"
MASTER_URI="http://127.0.0.1:${MASTER_PORT}"
PLAY_RATE="${ASTRA_REPLAY_RATE:-0.25}"
SPARSE_PC_SCRIPT="${SPARSE_PC_SCRIPT:-$HOME/ros-dev/vmware/qt/scripts/sparse_depth_pointcloud.py}"

KEEP_ALIVE=0
CLEANED_UP=0
TRAP_INSTALLED=0

# Expected cmdline substrings for PID identity checks.
declare -A PID_EXPECT=()
PID_EXPECT[roscore]="roscore"
PID_EXPECT[player]="rosbag play"
PID_EXPECT[probe]="replay_probe"
PID_EXPECT[tf_filter]="tf_edge_filter"
PID_EXPECT[tf_guard]="roslaunch|camera_tf_guard|astra_nearfield_ros1"
PID_EXPECT[pointcloud]="sparse_depth_pointcloud"

usage() {
  cat <<EOF
Usage:
  astra_replay.sh check <bag>
  astra_replay.sh raw <bag> [--keep-alive]
  astra_replay.sh cloud <bag> [--keep-alive]
  astra_replay.sh stop

Options:
  --keep-alive   leave local stack running after success (for RViz). Default: cleanup.

Environment:
  ASTRA_REPLAY_MASTER_PORT     default 11321
  ASTRA_REPLAY_RATE            default 0.25 (VM-stable)
  ASTRA_REPLAY_ALLOW_FOREIGN   default 0; set 1 to allow other nearfield procs
  SPARSE_PC_SCRIPT             sparse_depth_pointcloud.py path
  ASTRA_EXTRINSICS_YAML        nominal YAML path

perception mode is reserved for a later stage and is not implemented here.
EOF
}

die() { echo "[ERR] $*" >&2; exit 1; }
info() { echo "[INFO] $*"; }
ok() { echo "[OK] $*"; }

pid_file() { echo "${PID_DIR}/$1.pid"; }
cmd_file() { echo "${PID_DIR}/$1.cmd"; }
rc_file() { echo "${PID_DIR}/$1.rc"; }

pid_cmdline() {
  local pid="$1"
  if [ -r "/proc/${pid}/cmdline" ]; then
    tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null | sed 's/[[:space:]]*$//'
    return 0
  fi
  return 1
}

pid_matches_expected() {
  local name="$1"
  local pid="$2"
  local expect pattern cmdline
  expect="${PID_EXPECT[$name]:-}"
  [ -n "$expect" ] || return 1
  cmdline="$(pid_cmdline "$pid" || true)"
  [ -n "$cmdline" ] || return 1
  if [ -f "$(cmd_file "$name")" ]; then
    local saved
    saved="$(cat "$(cmd_file "$name")")"
    if [ -n "$saved" ] && echo "$cmdline" | grep -Fq -- "$saved"; then
      return 0
    fi
  fi
  IFS='|' read -r -a patterns <<<"$expect"
  for pattern in "${patterns[@]}"; do
    if echo "$cmdline" | grep -Eq -- "$pattern"; then
      return 0
    fi
  done
  return 1
}

pid_alive() {
  local name="$1"
  local f pid
  f="$(pid_file "$name")"
  [ -f "$f" ] || return 1
  pid="$(cat "$f")"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  if ! pid_matches_expected "$name" "$pid"; then
    info "stale PID file for $name pid=$pid (cmdline mismatch); clearing"
    rm -f "$f" "$(cmd_file "$name")" "$(rc_file "$name")"
    return 1
  fi
  return 0
}

write_pid() {
  local name="$1"
  local pid="$2"
  local marker="${3:-}"
  mkdir -p "$PID_DIR"
  echo "$pid" >"$(pid_file "$name")"
  if [ -z "$marker" ]; then
    marker="$(pid_cmdline "$pid" || echo "${PID_EXPECT[$name]}")"
  fi
  echo "$marker" >"$(cmd_file "$name")"
}

stop_one() {
  local name="$1"
  local sig="${2:-TERM}"
  local f pid cmdline
  f="$(pid_file "$name")"
  if ! pid_alive "$name"; then
    rm -f "$f" "$(cmd_file "$name")" "$(rc_file "$name")"
    return 0
  fi
  pid="$(cat "$f")"
  cmdline="$(pid_cmdline "$pid" || echo "?")"
  if ! pid_matches_expected "$name" "$pid"; then
    info "refuse to signal $name pid=$pid; cmdline mismatch: $cmdline"
    rm -f "$f" "$(cmd_file "$name")" "$(rc_file "$name")"
    return 1
  fi
  info "stop $name pid=$pid sig=$sig"
  kill "-$sig" "$pid" 2>/dev/null || true
  local i=0
  while kill -0 "$pid" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
      if [ "$sig" = "INT" ] || [ "$sig" = "TERM" ]; then
        if pid_matches_expected "$name" "$pid"; then
          kill -KILL "$pid" 2>/dev/null || true
        fi
      fi
      break
    fi
    sleep 0.5
  done
  rm -f "$f" "$(cmd_file "$name")" "$(rc_file "$name")"
}

port_listening() {
  (ss -lnt 2>/dev/null || netstat -lnt 2>/dev/null) | grep -E ":${MASTER_PORT}([[:space:]]|$)" >/dev/null
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
  set +u
  # shellcheck disable=SC1090
  source /opt/ros/melodic/setup.bash
  if [ -f "$HOME/ros_ws/devel/setup.bash" ]; then
    # shellcheck disable=SC1090
    source "$HOME/ros_ws/devel/setup.bash"
  fi
  set -u
  assert_isolated_env
}

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

parse_keep_alive_args() {
  # Sets KEEP_ALIVE and BAG_ARG from remaining args.
  KEEP_ALIVE=0
  BAG_ARG=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --keep-alive) KEEP_ALIVE=1; shift ;;
      *)
        if [ -n "$BAG_ARG" ]; then
          die "unexpected argument: $1"
        fi
        BAG_ARG="$1"
        shift
        ;;
    esac
  done
}

assert_no_foreign_nearfield() {
  local pid env_uri owned ignore
  owned=""
  for name in roscore player probe tf_filter tf_guard pointcloud; do
    if [ -f "$(pid_file "$name")" ]; then
      owned="$owned $(cat "$(pid_file "$name")")"
    fi
  done
  for pid in $(pgrep -f 'sparse_depth_pointcloud|astra_camera_tf_guard|camera_tf_guard\.py|tf_edge_filter\.py' 2>/dev/null || true); do
    ignore=0
    for o in $owned; do
      if [ "$pid" = "$o" ]; then ignore=1; break; fi
    done
    [ "$ignore" = "1" ] && continue
    env_uri="$(tr '\0' '\n' <"/proc/${pid}/environ" 2>/dev/null | awk -F= '/^ROS_MASTER_URI=/{print $2; exit}' || true)"
    if echo "${env_uri}" | grep -Eq '192\.168\.1\.168|:11311'; then
      if [ "${ASTRA_REPLAY_ALLOW_FOREIGN:-0}" != "1" ]; then
        die "foreign nearfield pid=$pid on live Master (${env_uri:-unknown}); stop it or set ASTRA_REPLAY_ALLOW_FOREIGN=1"
      fi
      info "ALLOW_FOREIGN: nearfield pid=$pid master=${env_uri}"
    elif [ -n "$env_uri" ] && [ "$env_uri" != "$MASTER_URI" ]; then
      if [ "${ASTRA_REPLAY_ALLOW_FOREIGN:-0}" != "1" ]; then
        die "foreign nearfield pid=$pid master=$env_uri; set ASTRA_REPLAY_ALLOW_FOREIGN=1 to override"
      fi
      info "ALLOW_FOREIGN: nearfield pid=$pid master=$env_uri"
    fi
  done
}

install_traps() {
  [ "$TRAP_INSTALLED" = "1" ] && return 0
  TRAP_INSTALLED=1
  trap 'cleanup_on_exit' EXIT
  trap 'KEEP_ALIVE=0; cleanup_on_exit; exit 130' INT
  trap 'KEEP_ALIVE=0; cleanup_on_exit; exit 143' TERM
}

cleanup_on_exit() {
  [ "$CLEANED_UP" = "1" ] && return 0
  CLEANED_UP=1
  if [ "$KEEP_ALIVE" = "1" ]; then
    info "keep-alive set; leaving local replay stack running (use astra_replay.sh stop)"
    return 0
  fi
  cmd_stop_quiet || true
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
  write_pid roscore "$!" "roscore -p ${MASTER_PORT}"
  local i=0
  while ! port_listening; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
      die "roscore failed to listen on ${MASTER_PORT}; see ${LOG_DIR}/roscore.log"
    fi
    sleep 0.5
  done
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
  write_pid probe "$!" "replay_probe"
  wait_node /astra_replay_probe 40
}

start_filter() {
  local bin
  bin="$(resolve_node_bin tf_edge_filter.py)"
  nohup "$bin" >"${LOG_DIR}/tf_edge_filter.log" 2>&1 &
  write_pid tf_filter "$!" "tf_edge_filter"
  wait_node /astra_tf_edge_filter 40
}

start_guard() {
  local extrinsics
  extrinsics="$(resolve_extrinsics_yaml)"
  [ -f "$extrinsics" ] || die "extrinsics YAML missing: $extrinsics"
  nohup roslaunch astra_nearfield_ros1 camera_tf.launch \
    extrinsics_file:="$extrinsics" \
    >"${LOG_DIR}/tf_guard.log" 2>&1 &
  write_pid tf_guard "$!" "roslaunch astra_nearfield_ros1 camera_tf.launch"
  wait_node /astra_camera_tf_guard 60
}

start_pointcloud() {
  [ -f "$SPARSE_PC_SCRIPT" ] || die "sparse pointcloud script missing: $SPARSE_PC_SCRIPT"
  nohup python2 "$SPARSE_PC_SCRIPT" >"${LOG_DIR}/pointcloud.log" 2>&1 &
  write_pid pointcloud "$!" "sparse_depth_pointcloud"
  wait_node /vmware_depth_points 40
}

play_bag() {
  local bag="$1"
  local report="$2"
  local mode="$3"
  local play_rc=0
  info "rosbag play --clock --rate ${PLAY_RATE} with TF remap"
  nohup rosbag play --clock --rate "$PLAY_RATE" "$bag" \
    /tf:=/bag/tf /tf_static:=/bag/tf_static \
    >"${LOG_DIR}/rosbag_play.log" 2>&1 &
  write_pid player "$!" "rosbag play"
  local pid
  pid="$(cat "$(pid_file player)")"
  set +e
  wait "$pid"
  play_rc=$?
  set -e
  echo "$play_rc" >"$(rc_file player)"
  rm -f "$(pid_file player)" "$(cmd_file player)"
  info "rosbag play exit_code=$play_rc"
  if [ "$play_rc" -ne 0 ]; then
    die "rosbag play failed with exit_code=$play_rc; see ${LOG_DIR}/rosbag_play.log"
  fi
  ok "rosbag play finished"

  sleep 2
  if pid_alive probe; then
    stop_one probe INT
  fi
  [ -f "$report" ] || die "probe report missing: $report"
  echo "=== probe report ==="
  cat "$report"
  validate_report "$report" "$mode"
}

validate_report() {
  local report="$1"
  local mode="$2"
  MODE="$mode" MASTER_URI="$MASTER_URI" python2 - "$report" <<'PY'
import json, os, sys
path = sys.argv[1]
mode = os.environ["MODE"]
master = os.environ["MASTER_URI"]
with open(path) as f:
    data = json.load(f)
depth = int(data.get("depth_frame_count") or 0)
info = int(data.get("camera_info_count") or 0)
cloud = int(data.get("point_cloud_count") or 0)
dur = float(data.get("simulated_duration_s") or 0.0)
uri = data.get("ROS_MASTER_URI") or ""
if depth <= 0:
    raise SystemExit("depth_frame_count must be > 0 (got %s)" % depth)
if info <= 0:
    raise SystemExit("camera_info_count must be > 0 (got %s)" % info)
if dur <= 0.0:
    raise SystemExit("simulated_duration_s must be > 0")
if uri != master:
    raise SystemExit("ROS_MASTER_URI=%r expected %r" % (uri, master))
if mode == "cloud":
    frame = (data.get("point_cloud_frame") or "").lstrip("/")
    if cloud <= 0:
        raise SystemExit("point_cloud_count must be > 0")
    if frame and frame != "camera_depth_optical_frame":
        raise SystemExit("unexpected point cloud frame: %r" % frame)
    if not data.get("tf_guard_status_received"):
        raise SystemExit("tf_guard status topic was never received")
    if data.get("tf_guard_conflict") is True:
        raise SystemExit("tf_guard_conflict=true")
    if data.get("tf_guard_conflict") is None:
        raise SystemExit("tf_guard_conflict is null (status missing)")
print "report_ok mode=%s depth=%s info=%s cloud=%s dur=%.3f conflict=%s" % (
    mode, depth, info, cloud, dur, data.get("tf_guard_conflict"))
PY
}

verify_master_still_local() {
  if [ "${ROS_MASTER_URI}" != "$MASTER_URI" ]; then
    die "ROS_MASTER_URI drifted to $ROS_MASTER_URI"
  fi
  python2 - <<PY
import os
uri=os.environ.get("ROS_MASTER_URI","")
assert uri=="$MASTER_URI", uri
print "MASTER_OK", uri
PY
}

assert_stack_stopped() {
  local name
  for name in player probe pointcloud tf_guard tf_filter roscore; do
    if pid_alive "$name"; then
      die "after stop, $name still alive pid=$(cat "$(pid_file "$name")")"
    fi
  done
  if port_listening; then
    die "after stop, port ${MASTER_PORT} still listening"
  fi
  ok "stack fully stopped (no owned PIDs; :${MASTER_PORT} closed)"
}

cmd_raw() {
  local bag report stamp
  parse_keep_alive_args "$@"
  bag="$(resolve_bag "$BAG_ARG")"
  install_traps
  source_ros
  assert_no_foreign_nearfield
  cmd_stop_quiet
  CLEANED_UP=0
  ensure_roscore
  set_sim_time
  stamp="$(date +%Y%m%d_%H%M%S)"
  report="${REPORT_DIR}/raw_${stamp}.json"
  start_probe "$report"
  verify_master_still_local
  play_bag "$bag" "$report" raw
  ok "raw replay done report=$report"
  echo "$report"
}

cmd_cloud() {
  local bag report stamp
  parse_keep_alive_args "$@"
  bag="$(resolve_bag "$BAG_ARG")"
  install_traps
  source_ros
  assert_no_foreign_nearfield
  cmd_stop_quiet
  CLEANED_UP=0
  ensure_roscore
  set_sim_time
  start_filter
  start_guard
  start_pointcloud
  stamp="$(date +%Y%m%d_%H%M%S)"
  report="${REPORT_DIR}/cloud_${stamp}.json"
  start_probe "$report"
  verify_master_still_local

  if ! timeout 15 rosrun tf tf_echo base_footprint camera_link 1 2>/dev/null | tee "${LOG_DIR}/tf_echo.txt" | grep -q "0.100"; then
    info "tf_echo preview (may be empty until clock starts); continuing"
  fi

  play_bag "$bag" "$report" cloud
  verify_master_still_local
  if grep -qi "ownership conflict\|TF ownership conflict" "${LOG_DIR}/tf_guard.log"; then
    die "TF guard reported conflict; see ${LOG_DIR}/tf_guard.log"
  fi
  ok "cloud replay done report=$report"
  echo "$report"
}

cmd_stop_quiet() {
  mkdir -p "$PID_DIR" "$LOG_DIR"
  stop_one player INT || true
  stop_one probe INT || true
  stop_one pointcloud TERM || true
  stop_one tf_guard TERM || true
  stop_one tf_filter TERM || true
  stop_one roscore TERM || true
  cleanup_orphan_roscore_on_port || true
}

cleanup_orphan_roscore_on_port() {
  port_listening || return 0
  local pids="" pid cmdline
  if command -v fuser >/dev/null 2>&1; then
    pids="$(fuser "${MASTER_PORT}/tcp" 2>/dev/null || true)"
  elif command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -t -iTCP:"${MASTER_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  fi
  for pid in $pids; do
    cmdline="$(pid_cmdline "$pid" || true)"
    if echo "$cmdline" | grep -Eq "roscore|rosmaster"; then
      if echo "$cmdline" | grep -Eq -- "-p[[:space:]]*${MASTER_PORT}|-p=${MASTER_PORT}|[[:space:]]${MASTER_PORT}([[:space:]]|$)"; then
        info "stop orphan ROS master on :${MASTER_PORT} pid=$pid"
        kill -TERM "$pid" 2>/dev/null || true
        local i=0
        while kill -0 "$pid" 2>/dev/null; do
          i=$((i + 1))
          if [ "$i" -ge 20 ]; then
            kill -KILL "$pid" 2>/dev/null || true
            break
          fi
          sleep 0.5
        done
      else
        info "port ${MASTER_PORT} held by unrelated ROS master pid=$pid ($cmdline); not killing"
      fi
    else
      info "port ${MASTER_PORT} held by non-roscore pid=$pid ($cmdline); not killing"
    fi
  done
}

cmd_stop() {
  KEEP_ALIVE=0
  source_ros || assert_isolated_env
  cmd_stop_quiet
  CLEANED_UP=1
  assert_stack_stopped
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
