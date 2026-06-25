#!/bin/bash
set -eo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

VENV_PY="$ROOT/.venv/bin/python"
HUMBLE_SETUP="/opt/ros/humble/setup.bash"

# 默认清华源；可 export PIP_INDEX_URL=... 覆盖
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn}"

pip_install_venv() {
  "$VENV_PY" -m pip install \
    -i "$PIP_INDEX_URL" \
    --trusted-host "$PIP_TRUSTED_HOST" \
    "$@"
}

if [ ! -x "$VENV_PY" ]; then
  echo "ERROR: .venv missing or broken. Run:"
  echo "  cd $ROOT"
  echo "  python3 -m venv .venv"
  echo "  PIP_INDEX_URL=$PIP_INDEX_URL .venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi

install_venv_deps() {
  echo "[run.sh] installing requirements.txt into .venv (index=$PIP_INDEX_URL) ..."
  if ! pip_install_venv -r requirements.txt; then
    echo "ERROR: pip install into .venv failed."
    echo "       可换源重试，例如:"
    echo "         PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \\"
    echo "         PIP_TRUSTED_HOST=mirrors.aliyun.com ./run.sh --install-deps"
    exit 1
  fi
  if ! "$VENV_PY" -c "import numpy" 2>/dev/null; then
    echo "ERROR: numpy still missing in .venv after pip install."
    exit 1
  fi
}

fail_missing_numpy() {
  echo "ERROR: numpy not in .venv (required for ROS2 bridge)."
  echo "       Fix:"
  echo "         cd $ROOT"
  echo "         .venv/bin/python -m pip install -i $PIP_INDEX_URL -r requirements.txt"
  echo "       Or: ./run.sh --install-deps"
  exit 1
}

warn_missing_numpy() {
  echo "WARNING: numpy not in .venv; ROS2 bridge unavailable until installed."
  echo "         ./run.sh --install-deps"
}

NO_ROS=0
STRICT_ROS=0
INSTALL_DEPS=0
APP_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --no-ros) NO_ROS=1; APP_ARGS+=("$arg") ;;
    --strict-ros) STRICT_ROS=1 ;;
    --install-deps) INSTALL_DEPS=1 ;;
    *) APP_ARGS+=("$arg") ;;
  esac
done

if [ "$INSTALL_DEPS" -eq 1 ]; then
  install_venv_deps
fi

if [ -f "$HUMBLE_SETUP" ]; then
  # shellcheck disable=SC1091
  source "$HUMBLE_SETUP"
elif [ "$NO_ROS" -eq 0 ]; then
  if [ "$STRICT_ROS" -eq 1 ]; then
    echo "ERROR: $HUMBLE_SETUP not found."
    echo "       Install ROS2 Humble, or start with --no-ros for JSON/GUI only."
    exit 1
  fi
  echo "WARNING: $HUMBLE_SETUP not found; ROS2 bridge unavailable."
  echo "         Install Humble or use ./run.sh --no-ros for JSON/GUI only."
fi

if [ "$NO_ROS" -eq 0 ]; then
  if [ "$STRICT_ROS" -eq 1 ] && [ -z "${ROS_DISTRO:-}" ]; then
    echo "ERROR: ROS_DISTRO unset (source humble failed or missing)."
    exit 1
  fi
  if ! "$VENV_PY" -c "import numpy" 2>/dev/null; then
    if [ "$STRICT_ROS" -eq 1 ]; then
      fail_missing_numpy
    else
      warn_missing_numpy
    fi
  fi
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

exec "$VENV_PY" app.py "${APP_ARGS[@]}"
