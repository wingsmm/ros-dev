#!/bin/bash
# 闃舵 A锛歊K3568 瀹夸富鏈虹洿杩烇紙鏃?Docker锛夛紝鍕夸笌 astra-camera 瀹瑰櫒鍚屾椂鍗?UVC
set -euo pipefail
DEV="${1:-/dev/video9}"
COUNT="${2:-90}"

echo "=== Phase A: host direct (no Docker) ==="
echo "device: $DEV"
lsusb | grep 2bc5 || true
v4l2-ctl --list-devices 2>/dev/null | sed -n '/Astra/,/^$/p' || true

v4l2-ctl -d "$DEV" --set-fmt-video=width=640,height=480,pixelformat=MJPG
rm -f /tmp/astra_host.mjpg
TIMEFORMAT='v4l2_stream_elapsed_sec %R'
time v4l2-ctl -d "$DEV" --stream-mmap --stream-count="$COUNT" --stream-to=/tmp/astra_host.mjpg
ls -lh /tmp/astra_host.mjpg
