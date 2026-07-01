#!/usr/bin/env bash
set -euo pipefail

# Qt stack entrypoint.
# Rule: start modules in order; if one module fails, stop already-started modules
# in reverse order and do not continue.

ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=stack_common.sh
source "$ROOT/stack_common.sh"
# shellcheck source=qt_camera_modules.sh
source "$ROOT/qt_camera_modules.sh"

main() {
  case "${1:-}" in
    start) qt_start ;;
    stop) qt_stop ;;
    restart) qt_stop; qt_start ;;
    status) qt_status ;;
    check) qt_check ;;
    record) qt_record ;;
    logs) qt_logs ;;
    radar2d-start|2d-start) qt_radar2d_start ;;
    radar2d-stop|2d-stop) qt_radar2d_stop ;;
    radar2d-restart|2d-restart) qt_radar2d_stop; qt_radar2d_start ;;
    radar2d-status|2d-status) qt_radar2d_status ;;
    radar2d-check|2d-check) qt_radar2d_check ;;
    camera-start|cam-start) qt_camera_start ;;
    camera-stop|cam-stop) qt_camera_stop ;;
    camera-restart|cam-restart) qt_camera_stop; qt_camera_start ;;
    camera-status|cam-status) qt_camera_status ;;
    camera-check|cam-check) qt_camera_check ;;
    -h|--help|help|"") qt_usage ;;
    *)
      echo "[ERR] unknown command: $1"
      qt_usage
      exit 1
      ;;
  esac
}

cd "$ROOT"
main "$@"
