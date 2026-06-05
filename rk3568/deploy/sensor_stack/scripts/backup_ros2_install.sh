#!/bin/bash
# 澶囦唤瀹夸富鏈?~/ros2_ws/install锛坈olcon 浜х墿鍦ㄦ寕杞界洰褰曪紝涓嶅湪闀滃儚閲岋級
set -euo pipefail
WS="${1:-$HOME/ros2_ws}"
OUT="${WS}/../ros2_ws_install_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
if [ ! -d "$WS/install" ]; then
  echo "no $WS/install"
  exit 1
fi
tar -czf "$OUT" -C "$WS" install
ls -lh "$OUT"
echo "OK: $OUT"
