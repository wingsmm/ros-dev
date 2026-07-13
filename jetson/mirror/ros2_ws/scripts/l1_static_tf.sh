#!/usr/bin/env bash
# Manage l1_tf_bringup static TF on Jetson (does NOT touch unitree_lidar_ros2).
#
# Usage:
#   l1_static_tf.sh start|stop|restart|status
#
# Extrinsics source of truth (edit on Jetson, then restart TF):
#   ~/qt/ros2_ws/src/l1_tf_bringup/config/l1_extrinsics.yaml
#
# stop kills l1_static_tf.launch.py and static_transform_publisher for
# unilidar_lidar — do not run a second manual static TF to the same child.

set -euo pipefail

WS="${HOME}/qt/ros2_ws"
EXTRINSICS_YAML="${WS}/src/l1_tf_bringup/config/l1_extrinsics.yaml"
PID_FILE="${WS}/log/l1_static_tf.pid"
LOG_FILE="${WS}/log/l1_static_tf.log"
LAUNCH_MATCH="l1_static_tf.launch.py"

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

_launch_pids() {
  pgrep -f "${LAUNCH_MATCH}" 2>/dev/null || true
}

_tf_publisher_pids() {
  pgrep -f "static_transform_publisher.*unilidar_lidar" 2>/dev/null || true
}

_is_running() {
  local pids
  pids="$(_launch_pids)"
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
  pids="$(_launch_pids)"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 0.4
    pids="$(_launch_pids)"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill -9 ${pids} 2>/dev/null || true
    fi
  fi
  pids="$(_tf_publisher_pids)"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
  fi
  rm -f "${PID_FILE}"
}

cmd_start() {
  if _is_running; then
    echo "l1-static-tf: already running"
    exit 0
  fi
  if [[ ! -f "${EXTRINSICS_YAML}" ]]; then
    echo "l1-static-tf: missing extrinsics yaml: ${EXTRINSICS_YAML}" >&2
    exit 1
  fi
  mkdir -p "${WS}/log"
  source_ros
  nohup ros2 launch l1_tf_bringup l1_static_tf.launch.py \
    "extrinsics_yaml:=${EXTRINSICS_YAML}" \
    >"${LOG_FILE}" 2>&1 &
  echo "$!" >"${PID_FILE}"
  sleep 0.6
  if _is_running; then
    echo "l1-static-tf: started pid=$(cat "${PID_FILE}") yaml=${EXTRINSICS_YAML}"
  else
    echo "l1-static-tf: start failed (see ${LOG_FILE})" >&2
    tail -n 20 "${LOG_FILE}" 2>/dev/null || true
    exit 1
  fi
}

cmd_stop() {
  if ! _is_running; then
    _stop
    echo "l1-static-tf: already stopped"
    exit 0
  fi
  _stop
  echo "l1-static-tf: stopped"
}

cmd_restart() {
  _stop
  sleep 0.4
  cmd_start
}

cmd_status() {
  if _is_running; then
    local pid
    pid="$(cat "${PID_FILE}" 2>/dev/null || _launch_pids | head -1 || true)"
    echo "l1-static-tf: running pid=${pid:-?} yaml=${EXTRINSICS_YAML}"
  else
    echo "l1-static-tf: stopped yaml=${EXTRINSICS_YAML}"
  fi
}

usage() {
  cat <<'USAGE'
Usage: l1_static_tf.sh start|stop|restart|status
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
