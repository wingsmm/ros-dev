#!/usr/bin/env bash
set -euo pipefail
# Deprecated: use CAMERA_ENABLE=0 LASER_ODOM_ENABLE=0 qt_stack.sh
ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "[deprecated] robot_control_stack.sh -> CAMERA_ENABLE=0 LASER_ODOM_ENABLE=0 qt_stack.sh" >&2
export CAMERA_ENABLE=0
export LASER_ODOM_ENABLE=0
exec "$ROOT/qt_stack.sh" "$@"
