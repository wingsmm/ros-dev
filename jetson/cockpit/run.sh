#!/usr/bin/env bash
set -eo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Avoid conda's Python; Humble rclpy is compiled against system Python 3.10.
if [[ -n "${CONDA_PREFIX:-}" ]]; then
  echo "[run.sh] detected conda env: $CONDA_PREFIX — falling back to system python3"
fi
PY_BIN="${COCKPIT_PYTHON:-/usr/bin/python3}"
if [[ ! -x "$PY_BIN" ]]; then
  echo "[run.sh] $PY_BIN 不存在，退回 PATH 中的 python3" >&2
  PY_BIN="python3"
fi

ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
set +u
# shellcheck disable=SC1090
source "$ROS_SETUP"
set -u

exec "$PY_BIN" app.py
