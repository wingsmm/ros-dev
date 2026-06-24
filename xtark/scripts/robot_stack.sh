#!/usr/bin/env bash
set -euo pipefail
# Deprecated: use qt_stack.sh
ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "[deprecated] robot_stack.sh -> qt_stack.sh" >&2
exec "$ROOT/qt_stack.sh" "$@"
