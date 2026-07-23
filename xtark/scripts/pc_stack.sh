#!/usr/bin/env bash
set -euo pipefail

# Robot-side stack for VMware Qt client (roscore + bringup + camera ROS topics).

ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=stack_common.sh
source "$ROOT/stack_common.sh"
# shellcheck source=pc_stack_modules.sh
source "$ROOT/pc_stack_modules.sh"

main() {
  case "${1:-}" in
    camera-start) pc_camera_start ;;
    camera-stop) pc_camera_stop ;;
    camera-status) pc_status ;;
    camera-check) pc_camera_check ;;

    camera-nearfield-start) pc_camera_nearfield_start ;;
    camera-nearfield-stop) pc_camera_nearfield_stop ;;
    camera-nearfield-status) pc_status ;;
    camera-nearfield-check) pc_camera_nearfield_check ;;

    camera-deep-start) pc_camera_deep_start ;;
    camera-deep-stop) pc_camera_deep_stop ;;
    camera-deep-status) pc_status ;;
    camera-deep-check) pc_camera_deep_check ;;

    radar2d-start) pc_radar2d_start ;;
    radar2d-stop) pc_radar2d_stop ;;
    radar2d-status) pc_status ;;
    radar2d-check) pc_radar2d_check ;;

    full-start|start) pc_full_start ;;
    full-stop|stop) pc_full_stop ;;
    full-status|status) pc_status ;;
    full-check|check) pc_full_check ;;

    restart) pc_full_stop; pc_full_start ;;
    logs) pc_logs ;;
    -h|--help|help|"") pc_usage ;;
    *)
      echo "[ERR] unknown command: $1"
      pc_usage
      exit 1
      ;;
  esac
}

cd "$ROOT"
main "$@"
