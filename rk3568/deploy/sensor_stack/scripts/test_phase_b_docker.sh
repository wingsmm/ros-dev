#!/bin/bash
# 闃舵 B锛欴ocker + ROS2 璇濋甯х巼锛堥渶鍏堝畬鎴?colcon锛屼笖 .env 涓?VIDEO0/1 涓?video9/10锛?
set -euo pipefail
cd ~/sensor_stack

echo "=== Phase B: Docker ROS2 ==="
docker compose down 2>/dev/null || true
docker compose up -d astra-camera
echo "waiting 30s for launch..."
sleep 30
docker ps --filter name=astra-camera --format '{{.Status}}'
docker logs astra-camera 2>&1 | tail -25

docker exec astra-camera bash -lc '
  source /opt/ros/humble/setup.bash
  source /ros2_ws/install/setup.bash
  echo "=== topics ==="
  ros2 topic list | grep camera || true
  echo "=== depth hz (15s) ==="
  timeout 15 ros2 topic hz /camera/depth/image_raw 2>&1 | tail -8
  echo "=== ir hz (15s) ==="
  timeout 15 ros2 topic hz /camera/ir/image_raw 2>&1 | tail -8
  echo "=== color hz (25s) ==="
  timeout 25 ros2 topic hz /camera/color/image_raw 2>&1 | tail -8
  echo "=== depth bw (10s) ==="
  timeout 10 ros2 topic bw /camera/depth/image_raw 2>&1 | tail -5
'
