#!/usr/bin/env bash
# Jetson 本机启动：source Humble 后跑 Qt 壳
set -eo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

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

# 同机 ros2_ws（可选 overlay）
WS_SETUP="${ROS2_WS_SETUP:-$HOME/qt/ros2_ws/install/setup.bash}"
if [[ -f "$WS_SETUP" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "$WS_SETUP"
  set -u
fi

exec "$PY_BIN" app.py
