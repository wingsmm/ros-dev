#!/usr/bin/env bash
# 一键启动 Unitree L1 原始点云 RViz2（WSL/PC，不部署到 Jetson）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="${UNILIDAR_RVIZ_CONFIG:-$ROOT/config/unilidar.rviz}"

set +u
# shellcheck disable=SC1090
source "${ROS_SETUP:-/opt/ros/humble/setup.bash}"
set -u

if [[ ! -f "$CONFIG" ]]; then
  echo "[ERR] rviz config missing: $CONFIG" >&2
  exit 2
fi

echo "[OK] rviz2 -d $CONFIG"
exec rviz2 -d "$CONFIG"
