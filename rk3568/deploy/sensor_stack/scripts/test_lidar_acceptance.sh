#!/bin/bash
# RK3568 RPLidar 楠屾敹锛歭aunch + /scan hz锛堝涓绘満闇€鑳借闂?/dev/lidar锛?
set -euo pipefail

PORT="${1:-/dev/lidar}"
LAUNCH="${2:-sllidar_a1_launch.py}"
TIMEOUT_HZ="${3:-18}"

echo "=== Lidar acceptance ==="
echo "port=$PORT launch=$LAUNCH"

if [ ! -e "$PORT" ]; then
  echo "ERROR: $PORT not found"
  ls -l /dev/ttyUSB* /dev/lidar 2>/dev/null || true
  exit 1
fi

source /opt/ros/humble/setup.bash 2>/dev/null || {
  echo "WARN: /opt/ros/humble not on host; use: docker compose run --rm --device $PORT cli bash $0 $PORT"
  exit 1
}
source "$HOME/ros2_ws/install/setup.bash"

pkill -f "sllidar.*launch" 2>/dev/null || true
sleep 1

ros2 launch sllidar_ros2 "$LAUNCH" serial_port:="$PORT" &
LPID=$!
sleep 8

echo "=== ros2 topic list (scan) ==="
ros2 topic list | grep scan || true

echo "=== /scan hz (${TIMEOUT_HZ}s) ==="
if timeout "$TIMEOUT_HZ" ros2 topic hz /scan 2>&1 | tail -8; then
  echo "=== PASS hint: average rate > 0 ==="
else
  echo "=== FAIL on $PORT 鈥?try: $0 /dev/ttyUSB1 ==="
  kill "$LPID" 2>/dev/null || true
  exit 1
fi

echo "=== one scan sample ==="
timeout 5 ros2 topic echo /scan --once 2>&1 | head -20

kill "$LPID" 2>/dev/null || true
echo "=== DONE ==="
