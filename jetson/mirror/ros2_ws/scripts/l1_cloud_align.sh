#!/usr/bin/env bash
# Manage l1_cloud_align node on Jetson (does NOT touch unitree_lidar_ros2 or static TF).
#
# Usage:
#   l1_cloud_align.sh start|stop|restart|status
#
# YAML source of truth (edit on Jetson, then restart):
#   ~/qt/ros2_ws/src/l1_cloud_align/config/l1_cloud_align.yaml
#
# stop kills l1_cloud_align.launch.py + l1_cloud_align_node only.

set -euo pipefail

WS="${HOME}/qt/ros2_ws"
ALIGN_YAML="${WS}/src/l1_cloud_align/config/l1_cloud_align.yaml"
PID_FILE="${WS}/log/l1_cloud_align.pid"
LOG_FILE="${WS}/log/l1_cloud_align.log"
LAUNCH_MATCH="l1_cloud_align.launch.py"
NODE_MATCH="l1_cloud_align_node"

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

_pids() {
  {
    pgrep -f "${LAUNCH_MATCH}" 2>/dev/null || true
    pgrep -f "${NODE_MATCH}" 2>/dev/null || true
  } | sort -u | tr '\n' ' '
}

_is_running() {
  local pids
  pids="$(_pids)"
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

_stop() {
  local pids
  pids="$(_pids)"
  pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 0.4
    pids="$(_pids)"
    pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill -9 ${pids} 2>/dev/null || true
    fi
  fi
  rm -f "${PID_FILE}"
}

cmd_start() {
  if _is_running; then
    echo "l1-cloud-align: already running"
    exit 0
  fi
  if [[ ! -f "${ALIGN_YAML}" ]]; then
    echo "l1-cloud-align: missing align yaml: ${ALIGN_YAML}" >&2
    exit 1
  fi
  mkdir -p "${WS}/log"
  source_ros
  nohup ros2 launch l1_cloud_align l1_cloud_align.launch.py \
    "align_yaml:=${ALIGN_YAML}" \
    >"${LOG_FILE}" 2>&1 &
  echo "$!" >"${PID_FILE}"
  sleep 0.8
  if _is_running; then
    echo "l1-cloud-align: started pid=$(cat "${PID_FILE}") yaml=${ALIGN_YAML}"
  else
    echo "l1-cloud-align: start failed (see ${LOG_FILE})" >&2
    tail -n 20 "${LOG_FILE}" 2>/dev/null || true
    exit 1
  fi
}

cmd_stop() {
  if ! _is_running; then
    _stop
    echo "l1-cloud-align: already stopped"
    exit 0
  fi
  _stop
  echo "l1-cloud-align: stopped"
}

cmd_restart() {
  _stop
  sleep 0.4
  cmd_start
}

cmd_status() {
  if _is_running; then
    local pid
    pid="$(cat "${PID_FILE}" 2>/dev/null || _pids | awk '{print $1}' || true)"
    echo "l1-cloud-align: running pid=${pid:-?} yaml=${ALIGN_YAML}"
  else
    echo "l1-cloud-align: stopped yaml=${ALIGN_YAML}"
  fi
}

usage() {
  cat <<'USAGE'
Usage: l1_cloud_align.sh start|stop|restart|status
USAGE
}

cmd="${1:-status}"
case "${cmd}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  status) cmd_status ;;
  -h|--help|help) usage ;;
  *)
    echo "unknown command: ${cmd}" >&2
    usage >&2
    exit 2
    ;;
esac
