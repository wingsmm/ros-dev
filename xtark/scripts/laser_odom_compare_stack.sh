#!/usr/bin/env bash
set -euo pipefail
# Deprecated: use qt_stack.sh
ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "[deprecated] laser_odom_compare_stack.sh -> qt_stack.sh" >&2
exec "$ROOT/qt_stack.sh" "$@"
