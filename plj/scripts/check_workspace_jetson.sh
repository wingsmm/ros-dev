#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source /opt/ros/humble/setup.bash
source "${ROOT_DIR}/install/setup.bash"

ros2 run slam_bringup workspace_doctor --profile full --project-root "${ROOT_DIR}"
ros2 pkg prefix point_lio
ros2 pkg prefix unitree_lidar_ros2
