#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THIRD_INSTALL="${ROOT_DIR}/third/_install"

source /opt/ros/humble/setup.bash

if [[ -d "${ROOT_DIR}/src/.venv" ]]; then
  source "${ROOT_DIR}/src/.venv/bin/activate"
fi

export CMAKE_PREFIX_PATH="${THIRD_INSTALL}:${CMAKE_PREFIX_PATH:-}"
export LD_LIBRARY_PATH="${THIRD_INSTALL}/lib:${THIRD_INSTALL}/lib64:${LD_LIBRARY_PATH:-}"
export LIVOX_SDK_INSTALL_PREFIX="${THIRD_INSTALL}"

cd "${ROOT_DIR}"
colcon build --symlink-install --base-paths src third \
  --cmake-args \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_PREFIX_PATH="${CMAKE_PREFIX_PATH}"

echo "Workspace build complete."
echo "Source with: source ${ROOT_DIR}/install/setup.bash"
