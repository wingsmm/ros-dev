#!/usr/bin/env bash
# Idempotent L1 stack on Jetson: unitree_lidar_ros2 + l1_static_tf + l1_cloud_align.
#
# Usage:
#   l1_stack.sh start|stop|restart|status
#
# Semantics:
#   start   — start any piece that is not running; repair old localhost-only
#             processes. Order: L1 driver -> static TF -> cloud_align.
#             Waits for /unilidar/cloud and /unilidar/cloud_aligned publishers.
#   stop    — stop unitree_lidar_ros2 + l1_static_tf + l1_cloud_align.
#   restart — stop then start.
#   status  — L1 / TF / align / cloud / aligned publisher summary.
#
# Extrinsics apply is NOT done here. Cockpit「应用对齐参数」writes
# ~/qt/ros2_ws/src/l1_cloud_align/config/l1_cloud_align.yaml and
# restarts ONLY l1_cloud_align (via l1_cloud_align.sh restart) —
# the static TF and the L1 driver are untouched.

set -euo pipefail

WS="${HOME}/qt/ros2_ws"
TF_SCRIPT="${WS}/scripts/l1_static_tf.sh"
ALIGN_SCRIPT="${WS}/scripts/l1_cloud_align.sh"
PID_FILE="${WS}/log/l1_driver.pid"
LOG_FILE="${WS}/log/l1_driver.log"
CLOUD_TOPIC="/unilidar/cloud"
ALIGNED_TOPIC="/unilidar/cloud_aligned"
CLOUD_WAIT_SEC="${L1_CLOUD_WAIT_SEC:-15}"

# Narrow matches — do not kill unrelated ROS2 nodes.
L1_NODE_MATCH="unitree_lidar_ros2_node"
L1_LAUNCH_MATCH="ros2 launch unitree_lidar_ros2"

source_ros() {
  set +u
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash
  if [[ -f "${WS}/install/setup.bash" ]]; then
    # shellcheck disable=SC1091
    source "${WS}/install/setup.bash"
  fi
  set -u
  export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
  export ROS_LOCALHOST_ONLY=0
}

_l1_pids() {
  {
    pgrep -f "${L1_NODE_MATCH}" 2>/dev/null || true
    pgrep -f "${L1_LAUNCH_MATCH}" 2>/dev/null || true
  } | sort -u | tr '\n' ' '
}

_any_pid_localhost_only() {
  local pid
  for pid in "$@"; do
    if [[ -r "/proc/${pid}/environ" ]] &&
      tr '\0' '\n' <"/proc/${pid}/environ" | grep -qx "ROS_LOCALHOST_ONLY=1"; then
      return 0
    fi
  done
  return 1
}

_l1_has_localhost_only() {
  local pids
  pids="$(_l1_pids)"
  # shellcheck disable=SC2086
  _any_pid_localhost_only ${pids}
}

_l1_is_running() {
  local pids
  pids="$(_l1_pids)"
  pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    return 0
  fi
  if [[ -f "${PID_FILE}" ]]; then
    local pid
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

_tf_is_running() {
  if [[ -x "${TF_SCRIPT}" ]] || [[ -f "${TF_SCRIPT}" ]]; then
    bash "${TF_SCRIPT}" status 2>/dev/null | grep -qi "running"
  else
    pgrep -f "l1_static_tf.launch.py" >/dev/null 2>&1
  fi
}

_align_is_running() {
  if [[ -x "${ALIGN_SCRIPT}" ]] || [[ -f "${ALIGN_SCRIPT}" ]]; then
    bash "${ALIGN_SCRIPT}" status 2>/dev/null | grep -qi "running"
  else
    pgrep -f "l1_cloud_align_node" >/dev/null 2>&1
  fi
}

_cloud_has_publisher() {
  source_ros
  local info
  info="$(ros2 topic info "${CLOUD_TOPIC}" 2>/dev/null || true)"
  echo "${info}" | grep -qiE "Publisher count:\s*[1-9]"
}

_aligned_has_publisher() {
  source_ros
  local info
  info="$(ros2 topic info "${ALIGNED_TOPIC}" 2>/dev/null || true)"
  echo "${info}" | grep -qiE "Publisher count:\s*[1-9]"
}

_wait_cloud() {
  local i
  for i in $(seq 1 "${CLOUD_WAIT_SEC}"); do
    if _cloud_has_publisher; then
      return 0
    fi
    sleep 1
  done
  return 1
}

_wait_aligned() {
  local i
  for i in $(seq 1 "${CLOUD_WAIT_SEC}"); do
    if _aligned_has_publisher; then
      return 0
    fi
    sleep 1
  done
  return 1
}

_stop_l1() {
  local pids
  pids="$(_l1_pids)"
  pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 0.5
    pids="$(_l1_pids)"
    pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill -9 ${pids} 2>/dev/null || true
    fi
  fi
  rm -f "${PID_FILE}"
}

_start_l1() {
  if _l1_is_running; then
    if _l1_has_localhost_only; then
      echo "l1-driver: restarting old ROS_LOCALHOST_ONLY=1 process"
      _stop_l1
    else
      echo "l1-driver: already running"
      return 0
    fi
  fi
  if _l1_is_running; then
    echo "l1-driver: already running"
    return 0
  fi
  mkdir -p "${WS}/log"
  source_ros
  nohup ros2 launch unitree_lidar_ros2 launch.py \
    >"${LOG_FILE}" 2>&1 &
  echo "$!" >"${PID_FILE}"
  sleep 0.8
  if _l1_is_running; then
    echo "l1-driver: started pid=$(cat "${PID_FILE}") log=${LOG_FILE}"
    return 0
  fi
  echo "l1-driver: start failed (see ${LOG_FILE})" >&2
  tail -n 30 "${LOG_FILE}" 2>/dev/null || true
  return 1
}

_start_tf_if_needed() {
  if [[ ! -f "${TF_SCRIPT}" ]]; then
    echo "l1-static-tf: missing script ${TF_SCRIPT}" >&2
    return 1
  fi
  # l1_static_tf.sh start is idempotent and repairs old ROS_LOCALHOST_ONLY=1
  # processes without changing the YAML extrinsics.
  bash "${TF_SCRIPT}" start
}

_start_align_if_needed() {
  if [[ ! -f "${ALIGN_SCRIPT}" ]]; then
    echo "l1-cloud-align: missing script ${ALIGN_SCRIPT}" >&2
    return 1
  fi
  bash "${ALIGN_SCRIPT}" start
}

_status_line() {
  local l1_state tf_state align_state cloud_state aligned_state
  if _l1_is_running; then
    l1_state="running"
  else
    l1_state="stopped"
  fi
  if _tf_is_running; then
    tf_state="running"
  else
    tf_state="stopped"
  fi
  if _align_is_running; then
    align_state="running"
  else
    align_state="stopped"
  fi
  if _cloud_has_publisher; then
    cloud_state="yes"
  else
    cloud_state="no"
  fi
  if _aligned_has_publisher; then
    aligned_state="yes"
  else
    aligned_state="no"
  fi
  echo "l1-stack: L1=${l1_state} TF=${tf_state} align=${align_state} cloud=${cloud_state} aligned=${aligned_state}"
}

cmd_start() {
  local ok=0
  _start_l1 || ok=1
  _start_tf_if_needed || ok=1
  _start_align_if_needed || ok=1
  if _wait_cloud; then
    echo "l1-stack: cloud publisher ready"
  else
    echo "l1-stack: cloud publisher not seen within ${CLOUD_WAIT_SEC}s" >&2
    ok=1
  fi
  if _wait_aligned; then
    echo "l1-stack: aligned publisher ready"
  else
    echo "l1-stack: aligned publisher not seen within ${CLOUD_WAIT_SEC}s" >&2
    ok=1
  fi
  _status_line
  return "${ok}"
}

cmd_stop() {
  _stop_l1
  if [[ -f "${TF_SCRIPT}" ]]; then
    bash "${TF_SCRIPT}" stop || true
  fi
  if [[ -f "${ALIGN_SCRIPT}" ]]; then
    bash "${ALIGN_SCRIPT}" stop || true
  fi
  echo "l1-stack: stopped"
  _status_line
  return 0
}

cmd_restart() {
  cmd_stop
  sleep 0.5
  cmd_start
}

cmd_status() {
  _status_line
  return 0
}

usage() {
  cat <<'USAGE'
Usage: l1_stack.sh start|stop|restart|status
USAGE
}

cmd="${1:-status}"
case "${cmd}" in
  start)
    cmd_start
    exit $?
    ;;
  stop)
    cmd_stop
    exit $?
    ;;
  restart)
    cmd_restart
    exit $?
    ;;
  status)
    cmd_status
    exit $?
    ;;
  -h|--help|help) usage ;;
  *)
    echo "unknown command: ${cmd}" >&2
    usage >&2
    exit 2
    ;;
esac
