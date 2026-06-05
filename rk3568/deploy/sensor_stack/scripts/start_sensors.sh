#!/bin/bash
# RK3568 resident sensor launcher: Astra + RPLidar in one container.
set -eo pipefail

source /opt/ros/humble/setup.bash
source /ros2_ws/install/setup.bash

LOG_DIR="${SENSOR_LOG_DIR:-/var/log/sensor_stack}"
LIDAR_PORT="${LIDAR_SERIAL:-/host_dev/ttyUSB0}"
LIDAR_WAIT_SECONDS="${LIDAR_WAIT_SECONDS:-30}"
ENABLE_LIDAR="${ENABLE_LIDAR:-true}"
USE_UVC="${USE_UVC:-true}"
UVC_PID="${UVC_PRODUCT_ID:-1282}"

mkdir -p "$LOG_DIR"

cleanup() {
  jobs -p | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [ "$ENABLE_LIDAR" = "true" ]; then
  wait_left="$LIDAR_WAIT_SECONDS"
  while [ ! -e "$LIDAR_PORT" ] && [ "$wait_left" -gt 0 ]; do
    echo "[sensors] waiting for lidar port $LIDAR_PORT (${wait_left}s left)"
    sleep 1
    wait_left=$((wait_left - 1))
  done

  if [ -e "$LIDAR_PORT" ]; then
    echo "[sensors] lidar on $LIDAR_PORT"
    ros2 launch sllidar_ros2 sllidar_a1_launch.py \
      serial_port:="$LIDAR_PORT" frame_id:=laser \
      > "$LOG_DIR/lidar.log" 2>&1 &
  else
    echo "[sensors] WARN: lidar port $LIDAR_PORT missing, skip lidar"
  fi
fi

echo "[sensors] astra camera (uvc=$USE_UVC pid=$UVC_PID)"
if [ "$USE_UVC" = "false" ]; then
  ros2 launch astra_camera astra_pro.launch.xml use_uvc_camera:=false \
    > "$LOG_DIR/astra.log" 2>&1 &
else
  ros2 launch astra_camera astra_pro.launch.xml uvc_product_id:="$UVC_PID" \
    > "$LOG_DIR/astra.log" 2>&1 &
fi

# If any launch exits, stop the container and let Docker restart policy recover it.
wait -n
echo "[sensors] a child exited, stopping container"
exit 1
