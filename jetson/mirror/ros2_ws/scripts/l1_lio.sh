#!/usr/bin/env bash
# Full L1 localization stack on Jetson:
#   l1_stack (driver + TF + cloud_align) + Point-LIO + lio_odom_adapter
#
# Usage:
#   l1_lio.sh start|stop|restart|status|logs
#
# start is idempotent; total budget ~45s. Does not pkill ros2 broadly.
# Does NOT use correct_odom_unilidar_l1.launch.py (frame rename only).
# Does NOT feed /unilidar/cloud_aligned into Point-LIO.
# Does NOT synthesize odom from /cmd_vel.

set -euo pipefail

WS="${HOME}/qt/ros2_ws"
L1_STACK="${WS}/scripts/l1_stack.sh"
PID_LIO="${WS}/log/l1_lio.pid"
LOG_LIO="${WS}/log/l1_lio.log"
PID_ADAPTER="${WS}/log/lio_odom_adapter.pid"
LOG_ADAPTER="${WS}/log/lio_odom_adapter.log"

CLOUD_TOPIC="/unilidar/cloud"
IMU_TOPIC="/unilidar/imu"
AFT_TOPIC="/aft_mapped_to_init"
ODOM_TOPIC="/odom"
PATH_TOPIC="/odom_path"
REGISTERED_TOPIC="/cloud_registered"

START_DEADLINE_SEC="${L1_LIO_START_TIMEOUT_SEC:-45}"
LIO_MATCH="pointlio_mapping"
LIO_LAUNCH_MATCH="mapping_unilidar_l1.launch.py"
ADAPTER_MATCH="lio_odom_adapter_node"
ADAPTER_LAUNCH_MATCH="lio_odom_adapter.launch.py"

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

_now_sec() {
  date +%s
}

_topic_has_publisher() {
  local topic="$1"
  source_ros
  local info
  info="$(ros2 topic info "${topic}" 2>/dev/null || true)"
  echo "${info}" | grep -qiE "Publisher count:\s*[1-9]"
}

_wait_topic() {
  local topic="$1"
  local deadline="$2"
  local label="$3"
  while (( $(_now_sec) < deadline )); do
    if _topic_has_publisher "${topic}"; then
      echo "l1-lio: ${label} ready (${topic})"
      return 0
    fi
    sleep 1
  done
  echo "l1-lio: FAIL stage=${label} timeout waiting for ${topic}" >&2
  return 1
}

_pids_match() {
  {
    pgrep -f "$1" 2>/dev/null || true
  } | sort -u | tr '\n' ' ' | xargs 2>/dev/null || true
}

_kill_pids() {
  local pids="$1"
  pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
  if [[ -z "${pids}" ]]; then
    return 0
  fi
  # shellcheck disable=SC2086
  kill ${pids} 2>/dev/null || true
  sleep 0.5
  pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
  # re-query callers should pass fresh list; best-effort SIGKILL leftovers:
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi
}

_lio_pids() {
  {
    pgrep -f "${LIO_MATCH}" 2>/dev/null || true
    pgrep -f "${LIO_LAUNCH_MATCH}" 2>/dev/null || true
  } | sort -u | tr '\n' ' '
}

_adapter_pids() {
  {
    pgrep -f "${ADAPTER_MATCH}" 2>/dev/null || true
    pgrep -f "${ADAPTER_LAUNCH_MATCH}" 2>/dev/null || true
  } | sort -u | tr '\n' ' '
}

_lio_is_running() {
  local pids
  pids="$(_lio_pids)"
  pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
  [[ -n "${pids}" ]] && return 0
  if [[ -f "${PID_LIO}" ]]; then
    local pid
    pid="$(cat "${PID_LIO}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

_adapter_is_running() {
  local pids
  pids="$(_adapter_pids)"
  pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
  [[ -n "${pids}" ]] && return 0
  if [[ -f "${PID_ADAPTER}" ]]; then
    local pid
    pid="$(cat "${PID_ADAPTER}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

_start_lio() {
  if _lio_is_running; then
    echo "l1-lio: Point-LIO already running"
    return 0
  fi
  mkdir -p "${WS}/log"
  source_ros
  nohup ros2 launch point_lio mapping_unilidar_l1.launch.py rviz:=false \
    >"${LOG_LIO}" 2>&1 &
  echo "$!" >"${PID_LIO}"
  sleep 1
  if _lio_is_running; then
    echo "l1-lio: Point-LIO started pid=$(cat "${PID_LIO}")"
    return 0
  fi
  echo "l1-lio: FAIL stage=LIO start (see ${LOG_LIO})" >&2
  tail -n 30 "${LOG_LIO}" 2>/dev/null || true
  return 1
}

_start_adapter() {
  if _adapter_is_running; then
    echo "l1-lio: adapter already running"
    return 0
  fi
  mkdir -p "${WS}/log"
  source_ros
  nohup ros2 launch lio_odom_adapter lio_odom_adapter.launch.py \
    >"${LOG_ADAPTER}" 2>&1 &
  echo "$!" >"${PID_ADAPTER}"
  sleep 1
  if _adapter_is_running; then
    echo "l1-lio: adapter started pid=$(cat "${PID_ADAPTER}")"
    return 0
  fi
  echo "l1-lio: FAIL stage=adapter start (see ${LOG_ADAPTER})" >&2
  tail -n 30 "${LOG_ADAPTER}" 2>/dev/null || true
  return 1
}

_stop_adapter() {
  local pids
  pids="$(_adapter_pids)"
  _kill_pids "${pids}"
  # second pass in case PIDs changed
  pids="$(_adapter_pids)"
  pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi
  rm -f "${PID_ADAPTER}"
  echo "l1-lio: adapter stopped"
}

_stop_lio() {
  local pids
  pids="$(_lio_pids)"
  _kill_pids "${pids}"
  pids="$(_lio_pids)"
  pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi
  rm -f "${PID_LIO}"
  echo "l1-lio: Point-LIO stopped"
}

_status_kv() {
  local l1="stopped" tf="stopped" align="stopped" lio="stopped" adapter="stopped"
  local cloud="no" registered="no" odom="no" path="no"

  if [[ -f "${L1_STACK}" ]]; then
    local line
    line="$(bash "${L1_STACK}" status 2>/dev/null || true)"
    echo "${line}" | grep -q "L1=running" && l1="running"
    echo "${line}" | grep -q "TF=running" && tf="running"
    echo "${line}" | grep -q "align=running" && align="running"
    echo "${line}" | grep -q "cloud=yes" && cloud="yes"
  fi

  _lio_is_running && lio="running"
  _adapter_is_running && adapter="running"

  if _topic_has_publisher "${REGISTERED_TOPIC}"; then
    registered="yes"
  fi
  if _topic_has_publisher "${ODOM_TOPIC}"; then
    odom="yes"
  fi
  if _topic_has_publisher "${PATH_TOPIC}"; then
    path="yes"
  fi
  # refresh cloud independently if stack status lacked it
  if [[ "${cloud}" != "yes" ]] && _topic_has_publisher "${CLOUD_TOPIC}"; then
    cloud="yes"
  fi

  cat <<EOF
L1=${l1}
TF=${tf}
align=${align}
LIO=${lio}
adapter=${adapter}
cloud=${cloud}
registered=${registered}
odom=${odom}
path=${path}
EOF
}

cmd_start() {
  local deadline
  deadline=$(( $(_now_sec) + START_DEADLINE_SEC ))

  if [[ ! -f "${L1_STACK}" ]]; then
    echo "l1-lio: FAIL stage=l1_stack missing ${L1_STACK}" >&2
    return 1
  fi

  echo "l1-lio: starting L1 stack…"
  if ! bash "${L1_STACK}" start; then
    echo "l1-lio: FAIL stage=l1_stack" >&2
    _status_kv
    return 1
  fi

  if ! _wait_topic "${CLOUD_TOPIC}" "${deadline}" "cloud"; then
    _status_kv
    return 1
  fi
  if ! _wait_topic "${IMU_TOPIC}" "${deadline}" "imu"; then
    _status_kv
    return 1
  fi

  if ! _start_lio; then
    _status_kv
    return 1
  fi
  if ! _wait_topic "${AFT_TOPIC}" "${deadline}" "aft_mapped"; then
    _status_kv
    return 1
  fi

  if ! _start_adapter; then
    _status_kv
    return 1
  fi
  if ! _wait_topic "${ODOM_TOPIC}" "${deadline}" "odom"; then
    _status_kv
    return 1
  fi
  if ! _wait_topic "${PATH_TOPIC}" "${deadline}" "odom_path"; then
    _status_kv
    return 1
  fi

  echo "l1-lio: start OK"
  _status_kv
  return 0
}

cmd_stop() {
  _stop_adapter
  _stop_lio
  if [[ -f "${L1_STACK}" ]]; then
    bash "${L1_STACK}" stop || true
  fi
  rm -f "${PID_LIO}" "${PID_ADAPTER}"
  echo "l1-lio: stopped"
  _status_kv
  return 0
}

cmd_restart() {
  cmd_stop
  sleep 0.5
  cmd_start
}

cmd_status() {
  _status_kv
  return 0
}

cmd_logs() {
  echo "=== ${LOG_LIO} ==="
  tail -n 80 "${LOG_LIO}" 2>/dev/null || echo "(no lio log)"
  echo "=== ${LOG_ADAPTER} ==="
  tail -n 80 "${LOG_ADAPTER}" 2>/dev/null || echo "(no adapter log)"
}

usage() {
  cat <<'USAGE'
Usage: l1_lio.sh start|stop|restart|status|logs
USAGE
}

cmd="${1:-status}"
case "${cmd}" in
  start)    cmd_start;  exit $? ;;
  stop)     cmd_stop;   exit $? ;;
  restart)  cmd_restart; exit $? ;;
  status)   cmd_status; exit $? ;;
  logs)     cmd_logs;   exit $? ;;
  -h|--help|help) usage ;;
  *)
    echo "unknown command: ${cmd}" >&2
    usage >&2
    exit 2
    ;;
esac
