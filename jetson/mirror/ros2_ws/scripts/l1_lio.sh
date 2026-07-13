#!/usr/bin/env bash
# Minimal Point-LIO launcher for Unitree L1 radar on Jetson.
#
# Usage:
#   l1_lio.sh start|stop|restart|status
#
# Semantics:
#   start   — launch Point-LIO (no RViz on Jetson).
#   stop    — kill pointlio_mapping process(es).
#   restart — stop then start.
#   status  — check if process is alive.
#
# Dependencies:
#   L1 driver (unitree_lidar_ros2) must already be running on the same
#   ROS_DOMAIN_ID before calling start.

set -euo pipefail

WS="${HOME}/qt/ros2_ws"
PID_FILE="${WS}/log/l1_lio.pid"
LOG_FILE="${WS}/log/l1_lio.log"

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

_lio_pids() {
  pgrep -f "pointlio_mapping" 2>/dev/null || true
}

_is_running() {
  local pids
  pids="$(_lio_pids)"
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

cmd_start() {
  if _is_running; then
    echo "l1-lio: already running"
    return 0
  fi
  mkdir -p "${WS}/log"
  source_ros
  nohup ros2 launch point_lio mapping_unilidar_l1.launch.py rviz:=false \
    >"${LOG_FILE}" 2>&1 &
  echo "$!" >"${PID_FILE}"
  sleep 2
  if _is_running; then
    echo "l1-lio: started"
    cmd_status
    return 0
  fi
  echo "l1-lio: start failed (see ${LOG_FILE})" >&2
  tail -n 20 "${LOG_FILE}" 2>/dev/null || true
  return 1
}

cmd_stop() {
  local pids
  pids="$(_lio_pids)"
  pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 0.5
    pids="$(_lio_pids)"
    pids="$(echo "${pids}" | xargs 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill -9 ${pids} 2>/dev/null || true
    fi
  fi
  rm -f "${PID_FILE}"
  echo "l1-lio: stopped"
}

cmd_restart() {
  cmd_stop
  sleep 0.5
  cmd_start
}

cmd_status() {
  if _is_running; then
    echo "l1-lio: running"
  else
    echo "l1-lio: stopped"
  fi
  return 0
}

usage() {
  cat <<'USAGE'
Usage: l1_lio.sh start|stop|restart|status
USAGE
}

cmd="${1:-status}"
case "${cmd}" in
  start)    cmd_start;  exit $? ;;
  stop)     cmd_stop;   exit $? ;;
  restart)  cmd_restart; exit $? ;;
  status)   cmd_status; exit $? ;;
  -h|--help|help) usage ;;
  *)
    echo "unknown command: ${cmd}" >&2
    usage >&2
    exit 2
    ;;
esac
