#!/bin/bash
set -eo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ ! -d .venv ]; then
  echo "ERROR: .venv missing. Run:"
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [ -f /opt/ros/humble/setup.bash ]; then
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash
fi

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"

# Qt on WSLg expects XDG_RUNTIME_DIR mode 0700; /mnt/* cannot chmod (drvfs).
RUNTIME_DIR="/tmp/xtark-qt-runtime-$(id -u)"
mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"
export XDG_RUNTIME_DIR="$RUNTIME_DIR"

export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

exec python app.py "$@"
