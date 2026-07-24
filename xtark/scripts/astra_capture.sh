#!/usr/bin/env bash
# Stage B1: record Astra near-field depth bags on the robot (local disk only).
# shellcheck shell=bash
set -euo pipefail

STACK_NAME="astra_nearfield"
XTARK_LOGS_ROOT="${XTARK_LOGS_ROOT:-$HOME/xtark_logs}"
LOG_DIR="${XTARK_LOGS_ROOT}/${STACK_NAME}"
BAG_ROOT="${LOG_DIR}/bags"
PID_DIR="${LOG_DIR}/pids"
MIN_FREE_GB="${ASTRA_CAPTURE_MIN_FREE_GB:-5}"
DISK_MARGIN_PCT="${ASTRA_CAPTURE_DISK_MARGIN_PCT:-30}"
EXPECTED_HOSTNAME="${ASTRA_CAPTURE_HOSTNAME:-xtark-robot}"
PC_STACK="${PC_STACK_SH:-$HOME/ros_ws/scripts/pc_stack.sh}"
# Rough MB/s budgets measured/estimated on this chassis.
DEPTH_MB_PER_S="${ASTRA_CAPTURE_DEPTH_MBPS:-12}"
RGB_MB_PER_S="${ASTRA_CAPTURE_RGB_MBPS:-25}"
SCAN_MB_PER_S="${ASTRA_CAPTURE_SCAN_MBPS:-1}"
BASE_MB_PER_S="${ASTRA_CAPTURE_BASE_MBPS:-2}"

usage() {
  cat <<EOF
Usage:
  astra_capture.sh start --scene <name> --lighting <label> [options]
  astra_capture.sh status
  astra_capture.sh stop
  astra_capture.sh inspect <bag_or_session_dir>

Options:
  --scene <name>                 required
  --lighting <label>             required
  --distance-m <float>           optional
  --camera-state stationary|handheld   default: stationary
  --duration <sec>               default 60, range 10..300
  --rgb                          also record /camera/image_raw
  --scan                         also record /scan
  --notes <text>                 optional
EOF
}

die() {
  echo "[ERR] $*" >&2
  exit 1
}

info() {
  echo "[INFO] $*"
}

ok() {
  echo "[OK] $*"
}

pid_file() {
  echo "${PID_DIR}/$1.pid"
}

cmd_file() {
  echo "${PID_DIR}/$1.cmd"
}

pid_cmdline() {
  local pid="$1"
  if [ -r "/proc/${pid}/cmdline" ]; then
    tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null | sed 's/[[:space:]]*$//'
    return 0
  fi
  return 1
}

pid_is_our_rosbag() {
  local pid="$1"
  local cmdline bag_marker
  cmdline="$(pid_cmdline "$pid" || true)"
  [ -n "$cmdline" ] || return 1
  echo "$cmdline" | grep -Eq 'rosbag[[:space:]]+record' || return 1
  if [ -f "$(cmd_file rosbag)" ]; then
    bag_marker="$(cat "$(cmd_file rosbag)")"
    if [ -n "$bag_marker" ] && echo "$cmdline" | grep -Fq -- "$bag_marker"; then
      return 0
    fi
  fi
  # Fallback: session bag path marker.
  if [ -f "${PID_DIR}/bag.path" ]; then
    bag_marker="$(cat "${PID_DIR}/bag.path")"
    [ -n "$bag_marker" ] && echo "$cmdline" | grep -Fq -- "$bag_marker" && return 0
  fi
  return 1
}

pid_alive() {
  local f pid
  f="$(pid_file "$1")"
  [ -f "$f" ] || return 1
  pid="$(cat "$f")"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  if [ "$1" = "rosbag" ] && ! pid_is_our_rosbag "$pid"; then
    info "stale rosbag PID file pid=$pid (cmdline mismatch); clearing"
    rm -f "$f" "$(cmd_file rosbag)"
    return 1
  fi
  return 0
}

write_pid() {
  mkdir -p "$PID_DIR"
  echo "$2" >"$(pid_file "$1")"
  if [ -n "${3:-}" ]; then
    echo "$3" >"$(cmd_file "$1")"
  fi
}

source_ros() {
  # shellcheck disable=SC1090
  source /opt/ros/melodic/setup.bash
  if [ -f "$HOME/ros_ws/devel/setup.bash" ]; then
    # shellcheck disable=SC1090
    source "$HOME/ros_ws/devel/setup.bash"
  fi
  export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
  if [ -z "${ROS_IP:-}" ] && [ -z "${ROS_HOSTNAME:-}" ]; then
    export ROS_IP
    ROS_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
}

assert_robot_host() {
  local host
  host="$(hostname 2>/dev/null || true)"
  if [ "${ASTRA_CAPTURE_ALLOW_HOST:-0}" = "1" ]; then
    info "ASTRA_CAPTURE_ALLOW_HOST=1; skipping hostname check (got ${host})"
    return 0
  fi
  if [ "$host" != "$EXPECTED_HOSTNAME" ]; then
    die "hostname is '${host}', expected '${EXPECTED_HOSTNAME}' (set ASTRA_CAPTURE_ALLOW_HOST=1 to override)"
  fi
}

assert_disk_space() {
  local duration="$1"
  local want_rgb="$2"
  local want_scan="$3"
  local avail need_mb rate_mb need_gb
  mkdir -p "$BAG_ROOT"
  avail="$(df -BG --output=avail "$BAG_ROOT" 2>/dev/null | tail -n1 | tr -dc '0-9')"
  if [ -z "$avail" ]; then
    avail="$(df -BG "$BAG_ROOT" | awk 'NR==2 {print $4}' | tr -dc '0-9')"
  fi
  if [ -z "$avail" ]; then
    die "cannot determine free disk space under $BAG_ROOT"
  fi
  rate_mb="$BASE_MB_PER_S"
  rate_mb=$((rate_mb + DEPTH_MB_PER_S))
  if [ "$want_rgb" = "1" ]; then
    rate_mb=$((rate_mb + RGB_MB_PER_S))
  fi
  if [ "$want_scan" = "1" ]; then
    rate_mb=$((rate_mb + SCAN_MB_PER_S))
  fi
  need_mb=$((duration * rate_mb))
  need_mb=$((need_mb + need_mb * DISK_MARGIN_PCT / 100))
  need_gb=$(( (need_mb + 1023) / 1024 ))
  if [ "$need_gb" -lt "$MIN_FREE_GB" ]; then
    need_gb="$MIN_FREE_GB"
  fi
  if [ "$avail" -lt "$need_gb" ]; then
    die "free disk ${avail}GB < required ${need_gb}GB (duration=${duration}s rgb=${want_rgb} scan=${want_scan} est=${rate_mb}MB/s +${DISK_MARGIN_PCT}%)"
  fi
  ok "disk free ${avail}GB (need ${need_gb}GB for ${duration}s @~${rate_mb}MB/s +${DISK_MARGIN_PCT}%)"
}

assert_master() {
  if ! rostopic list >/dev/null 2>&1; then
    die "ROS Master unreachable (ROS_MASTER_URI=${ROS_MASTER_URI:-unset})"
  fi
  ok "ROS Master reachable: ${ROS_MASTER_URI}"
}

assert_nearfield() {
  if [ ! -x "$PC_STACK" ]; then
    die "pc_stack not found/executable: $PC_STACK"
  fi
  if ! "$PC_STACK" camera-nearfield-check; then
    die "camera-nearfield-check failed; start camera-nearfield first"
  fi
}

assert_depth_topics() {
  if ! timeout 10 rostopic echo /camera/depth/image_raw -n 1 >/dev/null 2>&1; then
    die "/camera/depth/image_raw: no frame within 10s"
  fi
  if ! timeout 10 rostopic echo /camera/depth/camera_info -n 1 >/dev/null 2>&1; then
    die "/camera/depth/camera_info: no message within 10s"
  fi
  ok "depth image + CameraInfo have data"
}

assert_no_active_capture() {
  if pid_alive rosbag; then
    die "capture already running pid=$(cat "$(pid_file rosbag)")"
  fi
  if [ -f "${PID_DIR}/session.dir" ]; then
    local old
    old="$(cat "${PID_DIR}/session.dir")"
    if [ -n "$old" ] && ls "${old}"/*.bag.active >/dev/null 2>&1; then
      die "found active bag under $old; stop or clean first"
    fi
  fi
}

write_manifest_start() {
  local path="$1"
  python2 - "$path" <<'PY'
import json, os, sys
path = sys.argv[1]
data = json.loads(os.environ["ASTRA_MANIFEST_JSON"])
with open(path, "w") as f:
    json.dump(data, f, indent=2, sort_keys=True)
    f.write("\n")
PY
}

finalize_manifest() {
  # Commit only while exit_status is still "recording" (single writer).
  # Prints "committed:<status>" or "skipped:<existing>".
  local path="$1"
  local exit_status="$2"
  local bag_path="$3"
  local rosbag_rc="${4:-}"
  python2 - "$path" "$exit_status" "$bag_path" "$rosbag_rc" <<'PY'
import json, os, sys, time
path, exit_status, bag_path = sys.argv[1], sys.argv[2], sys.argv[3]
rosbag_rc = sys.argv[4] if len(sys.argv) > 4 else ""
with open(path) as f:
    data = json.load(f)
cur = data.get("exit_status", "")
if cur != "recording":
    print "skipped:%s" % cur
    sys.exit(0)
data["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
data["exit_status"] = exit_status
if rosbag_rc != "":
    try:
        data["rosbag_exit_code"] = int(rosbag_rc)
    except ValueError:
        data["rosbag_exit_code"] = rosbag_rc
if os.path.isfile(bag_path):
    data["bag_size_bytes"] = os.path.getsize(bag_path)
else:
    data["bag_size_bytes"] = 0
with open(path, "w") as f:
    json.dump(data, f, indent=2, sort_keys=True)
    f.write("\n")
print "committed:%s" % exit_status
PY
}

mark_stop_requested() {
  local session_dir="${1:-}"
  local reason="${2:-manual}"
  mkdir -p "$PID_DIR"
  # Atomic create: O_CREAT|O_EXCL via noclobber.
  local marker="${PID_DIR}/stop.requested"
  if (set -o noclobber; echo "$reason $(date +%Y-%m-%dT%H:%M:%S%z)" >"$marker") 2>/dev/null; then
    ok "stop.requested written ($reason)"
  else
    info "stop.requested already present"
  fi
  if [ -n "$session_dir" ] && [ -d "$session_dir" ]; then
    (set -o noclobber; echo "$reason $(date +%Y-%m-%dT%H:%M:%S%z)" >"${session_dir}/stop.requested") 2>/dev/null || true
  fi
}

stop_was_requested() {
  local session_dir="${1:-}"
  [ -f "${PID_DIR}/stop.requested" ] && return 0
  [ -n "$session_dir" ] && [ -f "${session_dir}/stop.requested" ] && return 0
  return 1
}

clear_stop_requested() {
  rm -f "${PID_DIR}/stop.requested"
}

validate_bag_min_frames() {
  local info_path="$1"
  python2 - "$info_path" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
def count_for(topic):
    m = re.search(r"%s\s+(\d+)\s+msgs" % re.escape(topic), text)
    return int(m.group(1)) if m else 0
depth = count_for("/camera/depth/image_raw")
info = count_for("/camera/depth/camera_info")
if depth <= 0:
    raise SystemExit("bag has no /camera/depth/image_raw messages")
if info <= 0:
    raise SystemExit("bag has no /camera/depth/camera_info messages")
print "bag_min_ok depth=%s info=%s" % (depth, info)
PY
}

validate_bag_contents() {
  local bag_path="$1"
  local duration="$2"
  local info_path="$3"
  DURATION="$duration" python2 - "$bag_path" "$info_path" <<'PY'
import re, sys, os
bag, info_path = sys.argv[1], sys.argv[2]
duration = float(os.environ["DURATION"])
text = open(info_path).read()
def count_for(topic):
    m = re.search(r"%s\s+(\d+)\s+msgs" % re.escape(topic), text)
    return int(m.group(1)) if m else 0
depth = count_for("/camera/depth/image_raw")
info = count_for("/camera/depth/camera_info")
m = re.search(r"duration:\s+([0-9.]+)s", text)
bag_dur = float(m.group(1)) if m else 0.0
if depth <= 0:
    raise SystemExit("bag has no /camera/depth/image_raw messages")
if info <= 0:
    raise SystemExit("bag has no /camera/depth/camera_info messages")
# Allow recorder startup skew: at least 70% of requested duration.
if bag_dur < max(5.0, duration * 0.7):
    raise SystemExit("bag duration %.1fs too short for requested %.1fs" % (bag_dur, duration))
print "bag_ok depth=%s info=%s duration=%.1fs" % (depth, info, bag_dur)
PY
}

cmd_start() {
  local scene="" lighting="" distance_m="" notes=""
  local camera_state="stationary"
  local duration=60
  local want_rgb=0 want_scan=0

  while [ $# -gt 0 ]; do
    case "$1" in
      --scene) scene="${2:-}"; shift 2 ;;
      --lighting) lighting="${2:-}"; shift 2 ;;
      --distance-m) distance_m="${2:-}"; shift 2 ;;
      --camera-state) camera_state="${2:-}"; shift 2 ;;
      --duration) duration="${2:-}"; shift 2 ;;
      --rgb) want_rgb=1; shift ;;
      --scan) want_scan=1; shift ;;
      --notes) notes="${2:-}"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) die "unknown argument: $1" ;;
    esac
  done

  [ -n "$scene" ] || die "--scene is required"
  [ -n "$lighting" ] || die "--lighting is required"
  case "$camera_state" in
    stationary|handheld) ;;
    *) die "--camera-state must be stationary|handheld" ;;
  esac
  if ! [[ "$duration" =~ ^[0-9]+$ ]] || [ "$duration" -lt 10 ] || [ "$duration" -gt 300 ]; then
    die "--duration must be integer 10..300 (got $duration)"
  fi

  assert_robot_host
  source_ros
  assert_master
  assert_nearfield
  assert_depth_topics
  assert_no_active_capture
  assert_disk_space "$duration" "$want_rgb" "$want_scan"

  if ! rosbag record --help 2>&1 | grep -Eq -- '--duration'; then
    die "rosbag record lacks --duration; refuse to guess"
  fi

  local stamp capture_id session_dir bag_path log_path manifest_path info_path
  stamp="$(date +%Y%m%d_%H%M%S)"
  capture_id="${stamp}_${scene}"
  session_dir="${BAG_ROOT}/${capture_id}"
  mkdir -p "$session_dir" "$PID_DIR"
  bag_path="${session_dir}/capture.bag"
  log_path="${session_dir}/capture.log"
  manifest_path="${session_dir}/manifest.json"
  info_path="${session_dir}/rosbag_info.txt"

  local topics=(
    /camera/depth/image_raw
    /camera/depth/camera_info
    /tf
    /tf_static
    /odom
  )
  local optional=()
  if [ "$want_rgb" = "1" ]; then
    topics+=(/camera/image_raw)
    optional+=(/camera/image_raw)
  fi
  if [ "$want_scan" = "1" ]; then
    topics+=(/scan)
    optional+=(/scan)
  fi

  local started_at topics_json opt_json
  started_at="$(date +%Y-%m-%dT%H:%M:%S%z)"
  topics_json="$(python2 -c 'import json,sys; print json.dumps(sys.argv[1:])' "${topics[@]}")"
  if [ ${#optional[@]} -eq 0 ]; then
    opt_json='[]'
  else
    opt_json="$(python2 -c 'import json,sys; print json.dumps(sys.argv[1:])' "${optional[@]}")"
  fi
  export ASTRA_MANIFEST_JSON
  ASTRA_MANIFEST_JSON="$(
    DISTANCE_M="$distance_m" SCENE="$scene" LIGHTING="$lighting" \
    CAMERA_STATE="$camera_state" NOTES="$notes" CAPTURE_ID="$capture_id" \
    STARTED_AT="$started_at" DURATION="$duration" MASTER="$ROS_MASTER_URI" \
    HOST="$(hostname)" TOPICS_JSON="$topics_json" OPT_JSON="$opt_json" \
    python2 - <<'PY'
import json, os
distance = os.environ.get("DISTANCE_M", "").strip()
payload = {
  "schema_version": 1,
  "capture_id": os.environ["CAPTURE_ID"],
  "scene": os.environ["SCENE"],
  "distance_m": float(distance) if distance else None,
  "lighting": os.environ["LIGHTING"],
  "camera_state": os.environ["CAMERA_STATE"],
  "notes": os.environ.get("NOTES", ""),
  "hostname": os.environ["HOST"],
  "started_at": os.environ["STARTED_AT"],
  "finished_at": "",
  "requested_duration_s": int(os.environ["DURATION"]),
  "actual_topics": json.loads(os.environ["TOPICS_JSON"]),
  "optional_topics": json.loads(os.environ.get("OPT_JSON") or "[]"),
  "ROS_MASTER_URI": os.environ["MASTER"],
  "camera_profile": "camera_nearfield",
  "extrinsics_status": "nominal",
  "bag_size_bytes": 0,
  "exit_status": "recording",
}
print json.dumps(payload)
PY
  )"
  write_manifest_start "$manifest_path"

  echo "$session_dir" >"${PID_DIR}/session.dir"
  echo "$bag_path" >"${PID_DIR}/bag.path"
  echo "$manifest_path" >"${PID_DIR}/manifest.path"
  clear_stop_requested
  rm -f "${session_dir}/stop.requested"

  info "recording ${duration}s -> $bag_path"
  info "topics: ${topics[*]}"
  nohup rosbag record -O "$bag_path" --duration="${duration}" "${topics[@]}" >"$log_path" 2>&1 &
  write_pid rosbag "$!" "$bag_path"
  ok "rosbag pid=$! session=$session_dir"
  info "waiting for rosbag to finish (--duration=${duration}) ..."

  local rb_pid rb_rc=0
  rb_pid="$(cat "$(pid_file rosbag)")"
  local waited=0
  local max_wait=$((duration + 90))
  while kill -0 "$rb_pid" 2>/dev/null; do
    if ! pid_is_our_rosbag "$rb_pid"; then
      finalize_manifest "$manifest_path" "pid_identity_lost" "$bag_path" ""
      die "rosbag pid=$rb_pid lost identity during capture"
    fi
    sleep 1
    waited=$((waited + 1))
    if [ "$waited" -ge "$max_wait" ]; then
      info "duration watchdog: sending SIGINT to rosbag pid=$rb_pid"
      mark_stop_requested "$session_dir" "watchdog"
      if pid_is_our_rosbag "$rb_pid"; then
        kill -INT "$rb_pid" 2>/dev/null || true
      fi
      break
    fi
  done
  set +e
  wait "$rb_pid" 2>/dev/null
  rb_rc=$?
  set -e
  rm -f "$(pid_file rosbag)" "$(cmd_file rosbag)"
  info "rosbag exit_code=$rb_rc"

  local i=0
  while ls "${session_dir}"/*.bag.active >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 60 ]; then
      finalize_manifest "$manifest_path" "bag_active_timeout" "$bag_path" "$rb_rc"
      die ".bag.active still present under $session_dir"
    fi
    sleep 1
  done

  # rosbag may finish renaming .bag.active -> .bag a moment after exit.
  i=0
  while [ ! -f "$bag_path" ]; do
    local found
    found="$(ls -1 "$session_dir"/*.bag 2>/dev/null | head -n1 || true)"
    if [ -n "$found" ]; then
      bag_path="$found"
      break
    fi
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
      finalize_manifest "$manifest_path" "missing_bag" "$bag_path" "$rb_rc"
      die "bag file missing under $session_dir"
    fi
    sleep 1
  done

  # Non-zero exit is "stopped" only with an explicit stop.requested marker.
  if [ "$rb_rc" -ne 0 ]; then
    if ! stop_was_requested "$session_dir"; then
      finalize_manifest "$manifest_path" "rosbag_failed" "$bag_path" "$rb_rc"
      die "rosbag record failed exit_code=$rb_rc (no stop.requested); see $log_path"
    fi
    if [ ! -f "$bag_path" ]; then
      finalize_manifest "$manifest_path" "missing_bag" "$bag_path" "$rb_rc"
      die "stop requested but bag missing under $session_dir"
    fi
    if ! rosbag info "$bag_path" >"$info_path" 2>&1; then
      finalize_manifest "$manifest_path" "rosbag_info_failed" "$bag_path" "$rb_rc"
      die "rosbag info failed after stop; see $info_path"
    fi
    if ! validate_bag_min_frames "$info_path"; then
      finalize_manifest "$manifest_path" "bag_validation_failed" "$bag_path" "$rb_rc"
      die "stopped bag failed min frame check; see $info_path"
    fi
    finalize_manifest "$manifest_path" "stopped" "$bag_path" "$rb_rc"
    clear_stop_requested
    ok "capture stopped early: $bag_path"
    ok "manifest: $manifest_path"
    echo "$session_dir"
    return 0
  fi

  if ! rosbag info "$bag_path" >"$info_path" 2>&1; then
    finalize_manifest "$manifest_path" "rosbag_info_failed" "$bag_path" "$rb_rc"
    die "rosbag info failed; see $info_path"
  fi
  if ! validate_bag_contents "$bag_path" "$duration" "$info_path"; then
    finalize_manifest "$manifest_path" "bag_validation_failed" "$bag_path" "$rb_rc"
    die "bag validation failed; see $info_path"
  fi
  finalize_manifest "$manifest_path" "ok" "$bag_path" "$rb_rc"
  clear_stop_requested
  ok "capture complete: $bag_path"
  ok "manifest: $manifest_path"
  echo "$session_dir"
}

cmd_status() {
  mkdir -p "$PID_DIR"
  if pid_alive rosbag; then
    ok "recording pid=$(cat "$(pid_file rosbag)")"
    [ -f "${PID_DIR}/session.dir" ] && echo "session=$(cat "${PID_DIR}/session.dir")"
    [ -f "${PID_DIR}/bag.path" ] && echo "bag=$(cat "${PID_DIR}/bag.path")"
  else
    echo "recording: stopped"
    [ -f "${PID_DIR}/session.dir" ] && echo "last_session=$(cat "${PID_DIR}/session.dir")"
  fi
}

cmd_stop() {
  mkdir -p "$PID_DIR"
  if ! pid_alive rosbag; then
    ok "no active capture"
    return 0
  fi
  local pid session_dir bag_path manifest_path info_path
  pid="$(cat "$(pid_file rosbag)")"
  if ! pid_is_our_rosbag "$pid"; then
    die "refuse to signal pid=$pid; not our rosbag record process"
  fi
  session_dir=""
  bag_path=""
  manifest_path=""
  [ -f "${PID_DIR}/session.dir" ] && session_dir="$(cat "${PID_DIR}/session.dir")"
  [ -f "${PID_DIR}/bag.path" ] && bag_path="$(cat "${PID_DIR}/bag.path")"
  [ -f "${PID_DIR}/manifest.path" ] && manifest_path="$(cat "${PID_DIR}/manifest.path")"

  # Ownership marker BEFORE signal — start shell may finalize from wait().
  mark_stop_requested "$session_dir" "manual"

  info "SIGINT rosbag pid=$pid"
  kill -INT "$pid" 2>/dev/null || true
  local i=0 rb_rc="signal"
  while kill -0 "$pid" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge 45 ]; then
      die "rosbag pid=$pid did not exit after SIGINT"
    fi
    sleep 1
  done
  # stop may run in another shell than the one that spawned rosbag; never wait.
  rm -f "$(pid_file rosbag)" "$(cmd_file rosbag)"
  info "rosbag process exited (rc unknown from this shell; recorded as signal)"

  if [ -z "$session_dir" ]; then
    ok "capture stopped"
    return 0
  fi

  i=0
  while ls "${session_dir}"/*.bag.active >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 60 ]; then
      die ".bag.active still present under $session_dir"
    fi
    sleep 1
  done
  i=0
  while [ -z "$bag_path" ] || [ ! -f "$bag_path" ]; do
    bag_path="$(ls -1 "$session_dir"/*.bag 2>/dev/null | head -n1 || true)"
    if [ -n "$bag_path" ] && [ -f "$bag_path" ]; then
      break
    fi
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
      if [ -n "$manifest_path" ] && [ -f "$manifest_path" ]; then
        finalize_manifest "$manifest_path" "missing_bag" "${bag_path:-}" "$rb_rc"
      fi
      die "bag file missing under $session_dir after stop"
    fi
    sleep 1
  done

  source_ros
  info_path="${session_dir}/rosbag_info.txt"
  if ! rosbag info "$bag_path" >"$info_path" 2>&1; then
    if [ -n "$manifest_path" ] && [ -f "$manifest_path" ]; then
      finalize_manifest "$manifest_path" "rosbag_info_failed" "$bag_path" "$rb_rc"
    fi
    die "rosbag info failed after stop; see $info_path"
  fi
  if ! validate_bag_min_frames "$info_path"; then
    if [ -n "$manifest_path" ] && [ -f "$manifest_path" ]; then
      finalize_manifest "$manifest_path" "bag_validation_failed" "$bag_path" "$rb_rc"
    fi
    die "stopped bag failed min frame check; see $info_path"
  fi
  # Only commit if start shell has not already finalized (still recording).
  if [ -n "$manifest_path" ] && [ -f "$manifest_path" ]; then
    finalize_manifest "$manifest_path" "stopped" "$bag_path" "$rb_rc"
  fi
  # Leave stop.requested for the start shell to observe; next start clears it.
  ok "capture stopped bag=$bag_path"
}

cmd_inspect() {
  local target="${1:-}"
  [ -n "$target" ] || die "inspect requires bag path or session directory"
  source_ros
  local bag="" manifest="" info=""
  if [ -d "$target" ]; then
    bag="$(ls -1 "$target"/*.bag 2>/dev/null | head -n1 || true)"
    manifest="$target/manifest.json"
    info="$target/rosbag_info.txt"
  elif [ -f "$target" ]; then
    bag="$target"
    manifest="$(dirname "$target")/manifest.json"
    info="$(dirname "$target")/rosbag_info.txt"
  else
    die "not found: $target"
  fi
  [ -n "$bag" ] && [ -f "$bag" ] || die "bag not found for $target"
  echo "=== bag ==="
  ls -lh "$bag"
  if [ -f "$manifest" ]; then
    echo "=== manifest ==="
    cat "$manifest"
  fi
  echo "=== rosbag info ==="
  if [ -f "$info" ]; then
    cat "$info"
  else
    rosbag info "$bag"
  fi
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    start) cmd_start "$@" ;;
    status) cmd_status ;;
    stop) cmd_stop ;;
    inspect) cmd_inspect "$@" ;;
    -h|--help|help|"") usage; [ -n "$cmd" ] || exit 1; exit 0 ;;
    *) die "unknown command: $cmd" ;;
  esac
}

main "$@"
