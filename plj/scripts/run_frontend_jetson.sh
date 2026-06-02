#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source /opt/ros/humble/setup.bash
source "${ROOT_DIR}/install/setup.bash"

ros2 launch slam_bringup system.launch.py \
  mode:=frontend \
  launch_sensors:=true \
  sensor_source:=unitree_l1 \
  lidar_port:=/dev/unilidar_serial4
