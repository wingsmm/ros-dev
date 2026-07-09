#!/usr/bin/env bash
# 兼容旧版：清理历史 fake static TF pid 文件（当前启动脚本已不再发布 TF）。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="${JETSON_COCKPIT_LOG_DIR:-$ROOT/logs}"
PID_FILE="$PID_DIR/unilidar_rviz_tf.pid"

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    sleep 0.2
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  echo "[OK] cleaned legacy static TF pid=$pid"
else
  echo "[INFO] nothing to stop (RViz is closed via cockpit or kill rviz2)"
fi
